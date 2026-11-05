"""Router / Registry / Provider 接口测试。"""
from __future__ import annotations

import pytest

from mingli.core.models import Question
from mingli.core.router import classify_question
from mingli.systems.bootstrap import get_registry


@pytest.fixture(scope="module")
def registry():
    return get_registry()


class TestRegistry:
    def test_seven_active_systems(self, registry):
        ids = {p.id for p in registry.active_providers()}
        assert {"bazi", "liuyao", "daliuren", "xiaoliuren", "meihua", "tarot", "yijing"} <= ids

    def test_planned_registered(self, registry):
        statuses = {r["id"]: r["status"] for r in registry.describe_all()}
        assert statuses.get("qimen") == "planned"
        assert statuses.get("ziwei") == "knowledge-only"   # 已从 planned 升级为有知识的诚实登记
        assert statuses.get("western-astrology") == "planned"

    def test_describe_all_honest(self, registry):
        rows = registry.describe_all()
        planned = [r for r in rows if not r["runnable"]]
        assert all(r["status"] in ("planned", "knowledge-only") for r in planned)

    def test_get_unknown_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_provider_protocol(self, registry):
        for p in registry.active_providers():
            # 协议七项齐全
            assert p.id and p.name and p.region and isinstance(p.category, list)
            schema = p.input_schema()
            assert "fields" in schema
            errs = p.validate_input({})
            assert isinstance(errs, list)


class TestClassify:
    def test_career_decision(self):
        cls = classify_question("我该不该换工作？")
        assert cls.category in ("career", "decision")

    def test_timing_is_modifier(self):
        """'什么时候升职'：主题 career 保留，timing 作为时态修饰。"""
        cls = classify_question("我什么时候能升职？")
        assert cls.category == "career"
        assert cls.hasTiming is True

    def test_pure_timing(self):
        cls = classify_question("这事什么时候有个结果")
        assert cls.category == "timing"

    def test_horizon(self):
        near = classify_question("这次面试能过吗？")
        long = classify_question("我的大运流年怎么样？")
        assert near.horizon == "near-term"
        assert long.horizon == "long-term"

    def test_sensitive(self):
        cls = classify_question("我想问要不要投资这只股票")
        assert "investment" in cls.sensitive

    def test_crisis(self):
        cls = classify_question("我不想活了，帮我算算")
        assert cls.crisis is True

    def test_other_fallback(self):
        cls = classify_question("今天天气如何")
        assert cls.category == "other"


class TestRouter:
    def test_recommend_returns_sorted(self, registry):
        from mingli.core.router import QuestionRouter
        router = QuestionRouter(registry.active_providers())
        _, recs = router.recommend("我最近要不要换工作？")
        scores = [r.score for r in recs]
        assert scores == sorted(scores, reverse=True)
        assert len(recs) >= 1

    def test_near_term_event_prefers_moment_systems(self, registry):
        from mingli.core.router import QuestionRouter
        router = QuestionRouter(registry.active_providers())
        cls, recs = router.recommend("这件事下周能不能成？")
        if recs and cls.horizon == "near-term":
            top = recs[0].systemId
            # 起课/抽牌类应排在纯 natal 类之前（或至少八字不因长期框架加分登顶）
            assert not (top == "bazi" and any(
                registry.get(r.systemId).recommend_for(Question(text="这件事下周能不能成？")) > 0.5 + 1e-9
                for r in recs))

    def test_reason_present(self, registry):
        from mingli.core.router import QuestionRouter
        router = QuestionRouter(registry.active_providers())
        _, recs = router.recommend("帮我看看今年的财运")
        for r in recs:
            assert r.reason.strip()


class TestProviders:
    def test_all_calculate_and_interpret(self, registry):
        """每个 active Provider 的完整链路：validate → calculate → interpret 可跑通。"""
        kb = _kb()
        cases = {
            "bazi": {"year": 1990, "month": 6, "day": 15, "hour": 8},
            "liuyao": {"mode": "random", "seed": 7},
            "meihua": {"mode": "numbers", "numbers": [3, 7]},
            "xiaoliuren": {"mode": "numbers", "numbers": [3, 5, 6]},
            "daliuren": {"mode": "datetime", "datetimeInput": [2026, 8, 11, 15]},
            "tarot": {"spread": "three", "seed": 42},
            "yijing": {"guaName": "地山谦"},
        }
        q = Question(text="测试问题：今年事业如何？", category="career")
        for sid, input_data in cases.items():
            p = registry.get(sid)
            assert p.validate_input(input_data) == [], f"{sid} 输入应合法"
            calc = p.calculate(input_data)
            assert calc.systemId == sid
            assert calc.engineVersion
            interp = p.interpret(calc, q, kb)
            assert interp.summary
            for conc in interp.conclusions:
                assert conc.reasoning, f"{sid} 断语缺推理链"
                assert conc.rules, f"{sid} 断语缺规则引用"
                for ref in conc.calcRefs:
                    from mingli.core.interpret.rules import resolve_path
                    ok, _ = resolve_path(calc.data, ref.path)
                    assert ok, f"{sid} 悬空计算引用: {ref.path}"

    def test_validate_rejects_bad_input(self, registry):
        bad_cases = {
            "bazi": {"year": 1800, "month": 1, "day": 1},
            "liuyao": {"mode": "coins", "coins": [9]},
            "tarot": {"spread": "nope"},
            "xiaoliuren": {"mode": "lunar", "lunar": [99, 5, 6]},
        }
        for sid, bad in bad_cases.items():
            p = registry.get(sid)
            assert p.validate_input(bad), f"{sid} 应拒绝非法输入"

    def test_bazi_rejects_nonexistent_dates(self, registry):
        """真实日历校验：jdn() 会把越界日静默滚动到下月，必须在 validate 拦下。"""
        p = registry.get("bazi")
        for m, d in ((2, 30), (2, 31), (4, 31), (6, 31), (11, 31)):
            errs = p.validate_input({"year": 1990, "month": m, "day": d})
            assert errs, f"1990-{m}-{d} 应被判为不存在日期"
        assert p.validate_input({"year": 1990, "month": 11, "day": 30}) == []

    def test_bazi_midnight_hour_not_swapped(self, registry):
        """0 点（子时）是合法时辰——falsy 兜底曾把它换成 12 点午时。"""
        from mingli.engines import bazi as bazi_engine
        p = registry.get("bazi")
        calc = p.calculate({"year": 1990, "month": 5, "day": 12, "hour": 0})
        engine_direct = bazi_engine.bazi_calculate(1990, 5, 12, hour=0)
        assert calc.data["siZhu"] == engine_direct["siZhu"]
        assert calc.data["columns"][3]["zhi"] == "子"
        assert calc.inputSnapshot["h"] == 0

    def test_yijing_rejects_unknown_gua_name(self, registry):
        """坏卦名须在 validate_input 被拦（此前穿透到 calculate 抛错 → Web 500）。"""
        p = registry.get("yijing")
        assert p.validate_input({"guaName": "不存在的卦"}) != []
        assert p.validate_input({"guaName": "地山谦"}) == []
        assert p.validate_input({}) == []   # 无卦名走纯义理，合法


def _kb():
    import os
    kb_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mingli", "knowledge")
    from mingli.core.knowledge import load_knowledge
    return load_knowledge(kb_dir)
