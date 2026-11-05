"""多体系对照引擎测试 —— 极性聚合、收敛/分歧/不可比较、红线约束。"""
from __future__ import annotations

from mingli.core.comparison import ComparisonRun, build_comparison
from mingli.core.models import Conclusion, InterpretationResult, RuleRef


def _interp(polarities: list[str]) -> InterpretationResult:
    cons = []
    for i, p in enumerate(polarities):
        cons.append(Conclusion(
            claim=f"测试断语{i}",
            reasoning=["判据"],
            rules=[RuleRef(ruleId=f"t/r{i}", source="测试出处", sourceLevel="B")],
            calcRefs=[],
            polarity=p,  # type: ignore[arg-type]
        ))
    return InterpretationResult(systemId="t", summary="摘要", conclusions=cons)


def _run(sid: str, pols: list[str]) -> ComparisonRun:
    return ComparisonRun.from_interpretation(sid, sid, "测试体系", _interp(pols))


def _cls(cat="career"):
    return {"category": cat, "horizon": "near-term"}


class TestAggregatePolarity:
    def test_majority(self):
        r = _run("a", ["positive", "positive", "neutral"])
        assert r.polarity == "positive"

    def test_symbolic_ignored_for_polarity(self):
        r = _run("a", ["symbolic", "symbolic"])
        assert r.polarity == "symbolic"   # 无吉凶极性 → 归象征

    def test_mixed_symbolic_and_real(self):
        r = _run("a", ["positive", "symbolic"])
        assert r.polarity == "positive"   # 有实质极性时不归象征

    def test_unknown_when_empty(self):
        r = _run("a", [])
        assert r.polarity == "unknown"


class TestBuildComparison:
    def test_convergence(self):
        runs = [_run("六爻", ["positive", "neutral"]), _run("小六壬", ["positive"]),
                _run("塔罗", ["symbolic"])]
        cmp = build_comparison("问", _cls(), runs)
        assert cmp["convergence"], "两条正极性应判收敛"
        assert any("吉象" in c and "非事实概率" in c for c in cmp["convergence"])

    def test_divergence(self):
        runs = [_run("六爻", ["positive"]), _run("大六壬", ["negative"])]
        cmp = build_comparison("问", _cls(), runs)
        assert cmp["divergence"]
        assert any("两向相左" in d for d in cmp["divergence"])

    def test_symbolic_not_comparable(self):
        runs = [_run("塔罗", ["symbolic"]), _run("易经", ["symbolic"])]
        cmp = build_comparison("问", _cls(), runs)
        assert cmp["nonComparable"]
        assert any("象征/自省视角" in n for n in cmp["nonComparable"])
        assert not cmp["convergence"]   # 象征不触发"收敛"

    def test_neutrals_only(self):
        runs = [_run("六爻", ["neutral"]), _run("小六壬", ["neutral"])]
        cmp = build_comparison("问", _cls(), runs)
        assert any("平" in n for n in cmp["nonComparable"])

    def test_skipped_run_never_polarizes(self):
        skip = ComparisonRun(systemId="八字", systemName="八字", strengths="s", skipped=True,
                             skip_reason="未提供出生资料")
        runs = [skip, _run("六爻", ["positive"])]
        cmp = build_comparison("问", _cls(), runs)
        # 只有一体系有效 → 不判收敛（至少需 2）
        assert not cmp["convergence"]

    def test_red_line_no_percentage(self):
        """红线：输出结构不含任何占比字段/合成评分字段。"""
        runs = [_run("六爻", ["positive"]), _run("小六壬", ["positive"]),
                _run("塔罗", ["symbolic"])]
        cmp = build_comparison("问", _cls(), runs)
        import json
        blob = json.dumps(cmp, ensure_ascii=False)
        assert "%" not in blob
        assert "score" not in blob and "probability" not in blob
        # 收敛措辞必须是"独立趋同观察"，不得出现"故必成"式断言
        for c in cmp["convergence"]:
            assert "必" not in c and "一定" not in c

    def test_notes_explain_independence(self):
        runs = [_run("六爻", ["positive"])]
        cmp = build_comparison("问", _cls(), runs)
        assert any("独立" in n for n in cmp["notes"])
