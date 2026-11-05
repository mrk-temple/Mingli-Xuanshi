"""Session / Report / Experiment / Knowledge / Safety 测试。"""
from __future__ import annotations

import os

import pytest

from mingli.core.experiment import VERDICT_RULES, evaluate, mark_no_outcome
from mingli.core.knowledge import load_knowledge
from mingli.core.models import (
    CalculationResult,
    Conclusion,
    DivinationSession,
    Experiment,
    InterpretationResult,
    Question,
    RuleRef,
)
from mingli.core.report import ReportError, evidence_trace_json, render_markdown
from mingli.core.safety import DISCLAIMER, assess, downgrade_claims
from mingli.core.session import ExperimentStore, SessionStore

KB = load_knowledge(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mingli", "knowledge"))


def _fake_calc() -> CalculationResult:
    return CalculationResult(
        systemId="test",
        engine="test/engine.py",
        engineVersion="1",
        inputSnapshot={},
        data={"a": {"b": 1}, "list": [10, 20]},
        rawText="测试输出文本",
    )


def _good_interp() -> InterpretationResult:
    from mingli.core.interpret.rules import build_conclusion
    return InterpretationResult(
        systemId="test",
        summary="摘要",
        conclusions=[
            build_conclusion(
                claim="多有倾向 X",
                reasoning=["因 a.b=1（判据）", "故倾向 X"],
                rules=[RuleRef(ruleId="t/rule", source="某书某篇", sourceLevel="B")],
                calc_refs=["a.b", "list[1]"],
            )
        ],
        limitations=["局限一"],
    )


def _session(calc=None, interp=None) -> DivinationSession:
    return DivinationSession(
        question=Question(text="测试问题"),
        systemId="test",
        calculation=calc or _fake_calc(),
        interpretation=interp if interp is not None else _good_interp(),
    )


class TestKnowledge:
    def test_loads_all_systems(self):
        for sid in ["bazi", "liuyao", "meihua", "daliuren", "xiaoliuren", "tarot", "yijing"]:
            assert KB.for_system(sid), f"{sid} 无知识条目"

    def test_source_levels_valid(self):
        for r in KB._rules:
            assert r.sourceLevel in ("S", "A", "B", "C", "D")
            assert r.source.strip()

    def test_tradition_conflicts_preserved(self):
        """流派冲突并列存在，不合并；冲突说明在至少一方标注。"""
        gufa = [r for r in KB._rules if r.id == "xiaoliuren/gufa@gufa"]
        summ = [r for r in KB._rules if r.id == "xiaoliuren/gufa@sum"]
        assert gufa and summ   # 两种流派规则同时存在
        assert any(r.disputes for r in gufa + summ)  # 冲突至少被一方标注
        assert "古法" in summ[0].disputes[0]  # sum 版本声明与古法的分歧

    def test_search(self):
        hits = KB.search("liuyao", ["用神", "求财"])
        assert any("用神" in h.statement for h in hits)


class TestReport:
    def test_render_contains_mandatory_sections(self):
        md = render_markdown(_session())
        assert "体系局限" in md
        assert "免责声明" in md
        assert DISCLAIMER[:12] in md
        assert "五大未证假设" in md
        # 事实与解读分节
        assert "事实" in md and "解读" in md

    def test_evidence_trace(self):
        s = _session()
        render_markdown(s)  # 触发 calcRefs 回填
        trace = evidence_trace_json(s)
        conc = trace["conclusions"][0]
        assert conc["claim"]
        assert conc["reasoning"]
        values = {r["path"]: r["value"] for r in conc["calcRefs"]}
        assert values["a.b"] == 1
        assert values["list[1]"] == 20

    def test_dangling_ref_rejected(self):
        """悬空引用 → 拒绝渲染。"""
        bad = _good_interp()
        bad.conclusions[0].calcRefs = [type(bad.conclusions[0].calcRefs[0])(path="不存在的.路径")]
        with pytest.raises(ReportError):
            render_markdown(_session(interp=bad))

    def test_missing_reasoning_rejected(self):
        bad = _good_interp()
        bad.conclusions[0] = Conclusion.model_copy(bad.conclusions[0], update={"reasoning": []})
        with pytest.raises(ReportError):
            render_markdown(_session(interp=bad))

    def test_sensitive_downgrade(self):
        v = assess("要不要投资股票加仓？")
        assert "investment" in v.sensitive
        fixed = downgrade_claims(["股价一定会涨"], v)
        assert "一定" not in fixed[0]


class TestSessionStore:
    def test_roundtrip(self, tmp_path):
        store = SessionStore(root=str(tmp_path))
        s = _session()
        store.save(s)
        loaded = store.load(s.id)
        assert loaded.calculation.data == s.calculation.data
        assert loaded.interpretation.conclusions[0].claim == s.interpretation.conclusions[0].claim


class TestExperiment:
    def _exp(self) -> Experiment:
        return Experiment(sessionId="s_test", systemId="liuyao",
                          questionText="面试能过吗", prediction="有机会但过程反复",
                          windowStart="2026-09-01", windowEnd="2026-09-10")

    def test_verdict_priority_exact(self):
        e = evaluate(self._exp(), "完全应验", hit_exact=True, hit_direction=True, hit_timing=True)
        assert e.verdict == "exact-hit"

    def test_direction_only(self):
        e = evaluate(self._exp(), "方向对但时间不对", hit_direction=True, hit_timing=False)
        assert e.verdict == "direction-hit"

    def test_timing_only(self):
        e = evaluate(self._exp(), "窗口内发生但方向不符", hit_direction=False, hit_timing=True)
        assert e.verdict == "timing-hit"

    def test_partial(self):
        e = evaluate(self._exp(), "方向时间都对但不完全", hit_direction=True, hit_timing=True)
        assert e.verdict == "partial-hit"

    def test_miss(self):
        e = evaluate(self._exp(), "都不符", hit_direction=False, hit_timing=False)
        assert e.verdict == "miss"

    def test_ambiguous_beats_all(self):
        e = evaluate(self._exp(), "说不清", hit_exact=True, ambiguous=True)
        assert e.verdict == "ambiguous"

    def test_no_outcome(self):
        e = mark_no_outcome(self._exp())
        assert e.verdict == "no-outcome"

    def test_rules_are_public(self):
        """七种判定规则全部公开可查——诚实约束的落点。"""
        assert set(VERDICT_RULES) == {"exact-hit", "partial-hit", "direction-hit",
                                      "timing-hit", "miss", "ambiguous", "no-outcome"}

    def test_store_stats(self, tmp_path):
        store = ExperimentStore(root=str(tmp_path))
        e1 = self._exp()
        evaluate(e1, "应验", hit_exact=True)
        e2 = self._exp()
        evaluate(e2, "未中", hit_direction=False, hit_timing=False)
        for e in (e1, e2):
            store.save(e)
        stats = store.stats()
        assert stats["n"] == 2
        assert stats["verdictCounts"]["exact-hit"] == 1
        assert stats["verdictCounts"]["miss"] == 1
