"""多体系对照 —— Same Question Lab（design.md §8/§11，第七原则）。

严格独立：同一问题先各体系独立计算+解读，再依据结构化极性（positive/negative/
neutral/symbolic）建立 Cross-System View——只呈收敛点 / 分歧点 / 不可比较项。

红线（本模块的物理约束，不是口头承诺）：
- 本模块只读极性标签与结论文本，**不产生任何"综合概率/分数"**；
- convergence 措辞必须是"独立趋同观察"，禁止"N 术一致故必成"；
- symbolic（象征/自省视角体系）明确不参与吉凶并论，单独列出。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mingli.core.models import InterpretationResult

_POL_LABEL = {"positive": "吉象", "negative": "忌象", "neutral": "平", "symbolic": "象意"}


@dataclass
class ComparisonRun:
    systemId: str
    systemName: str
    strengths: str
    region: str = "east"
    skipped: bool = False
    skip_reason: str = ""
    polarity: str = "unknown"                       # absolute / neutral / symbolic / unknown
    summary: str = ""
    conclusions: list[Any] = field(default_factory=list)   # pydantic Conclusion 对象

    @classmethod
    def from_interpretation(
        cls,
        system_id: str,
        system_name: str,
        strengths: str,
        interp: InterpretationResult | None,
        region: str = "east",
    ) -> ComparisonRun:
        if interp is None:
            return cls(systemId=system_id, systemName=system_name, strengths=strengths,
                       region=region, skipped=True, skip_reason="无解读结果")
        return cls(
            systemId=system_id, systemName=system_name, strengths=strengths, region=region,
            polarity=_aggregate_polarity(interp),
            summary=interp.summary,
            conclusions=[c.model_dump() for c in interp.conclusions],   # 可序列化；模板点访问兼容 dict
        )


def _aggregate_polarity(interp: InterpretationResult) -> str:
    """体系主极性：取结论中非 symbolic 极性的众数；无则 symbolic；
    类别全空标 unknown。"""
    counts: dict[str, int] = {}
    has_symbolic = False
    for c in interp.conclusions:
        p = c.polarity
        if p == "symbolic":
            has_symbolic = True
            continue
        if p:
            counts[p] = counts.get(p, 0) + 1
    if not counts:
        return "symbolic" if has_symbolic else "unknown"
    return max(counts.items(), key=lambda kv: kv[1])[0]


def build_comparison(
    question_text: str,
    classification: dict[str, Any],
    runs: list[ComparisonRun],
) -> dict[str, Any]:
    """输入独立解读结果，输出收敛/分歧/不可比较。只做并排观察，不做融合。"""
    usable = [r for r in runs if not r.skipped and r.polarity in ("positive", "negative", "neutral")]
    symbolic_runs = [r for r in runs if not r.skipped and r.polarity == "symbolic"]
    unknown_runs = [r for r in runs if not r.skipped and r.polarity == "unknown"]

    convergence: list[str] = []
    divergence: list[str] = []
    non_comparable: list[str] = []

    def names(rs: list[ComparisonRun]) -> str:
        return "「" + "、".join(r.systemName for r in rs) + "」"

    # ── 收敛：同向 ≥ 2 体系（且均为非象征的吉/忌倾向）──
    pos = [r for r in usable if r.polarity == "positive"]
    neg = [r for r in usable if r.polarity == "negative"]
    if len(pos) >= 2:
        convergence.append(f"{names(pos)} 各自独立起局，主倾向均呈吉象——方向趋同（象征层面观察，非事实概率）。")
    if len(neg) >= 2:
        convergence.append(f"{names(neg)} 各自独立起局，主倾向均呈忌象——方向趋同（象征层面观察，非事实概率）。")

    # ── 分歧：正负反向并存 ──
    if pos and neg:
        divergence.append(f"{names(pos)} 呈吉象，而 {names(neg)} 呈忌象——两向相左。注意两者理论前提、输入结构均不同，此分歧不必然说明某方有误，只说明各自判据不同。")
        divergence.append("分歧处置：不强行中和为'吉凶参半'；若需行动，取其与你现状最匹配之判据，并保持可验证（设实验记录）。")

    # ── 不可比较 ──
    if symbolic_runs:
        non_comparable.append(
            f"{names(symbolic_runs)} 属象征/自省视角体系（塔罗自省、易经义理启发），"
            "其结论不与吉凶并论——它们提供的是视角与提醒，而非事之成败倾向。")
    if unknown_runs:
        non_comparable.append(
            f"{names(unknown_runs)} 主倾向未定型（结构层或课体未定），本轮不参与吉凶对照。")
    if not convergence and not divergence and not non_comparable:
        non_comparable.append("本轮各体系主倾向均为平（neutrals）：未呈现明确方向，需结合细节展开细读。")

    notes = [
        f"对照问题：{question_text}（类型 {classification.get('category')} / 尺度 {classification.get('horizon')}）",
        "各体系输入结构与理论前提互相独立：一排八字依出生时刻，一卦依起卦，一组牌依抽取——它们共享的只是'此次对照'这一问题语境。",
        "所谓'收敛'仅指象征层面的方向趋同，系统刻意不将同向条数折算为任何概率。",
    ]

    return {
        "question": question_text,
        "classification": classification,
        "runs": [r.__dict__ for r in runs],
        "convergence": convergence,
        "divergence": divergence,
        "nonComparable": non_comparable,
        "notes": notes,
    }
