"""八字解读 —— 体系特定读法（规则版）。

范围声明：本阶段只做"结构层"解读——旺衰三问原料、五行偏重、十神分布、
大运定位。旺衰裁决与用神取舍属"规则+裁量"（geju-yongshen.md §4 三因子
需要裁量），规则引擎给出**结构化提示 + 两可标注**，不硬断；完整断命
（格局/用神/岁运断语）在知识库深化后逐条程序化。
"""
from __future__ import annotations

from mingli.core.interpret.rules import build_conclusion
from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalculationResult,
    Conclusion,
    InterpretationResult,
    Question,
    RuleRef,
)

_LIMITS = [
    "旺衰/格局/用神为'规则+裁量'，本报告仅给结构化倾向，两可处已标注区分条件",
    "同八字异命反证成立（三命通会：鲁公与走卒等成组案例），本盘断语不构成事实预言",
    "女命断语与出身贵贱断法属父权伦理投射与现代职业错位，本系统不予采用",
]


def interpret_bazi(
    calculation: CalculationResult,
    question: Question | None,
    knowledge: KnowledgeBase,
) -> InterpretationResult:
    data = calculation.data
    cols = data["columns"]
    day_col = next(c for c in cols if c["pillar"] == "day")
    wx_hidden = data["wuxingHidden"]
    yueling = data["yueLing"]

    conclusions: list[Conclusion] = []
    uncertainty: list[str] = []

    # ── 结论 1：日主与月令关系（得令与否的确定性部分）──
    day_wx = day_col["ganWuxing"]
    de_ling = (day_wx == yueling["dangLingWuxing"]) or _sheng(day_wx, yueling["dangLingWuxing"])
    conclusions.append(build_conclusion(
        claim=(f"日主{day_col['gan']}（{day_wx}）生于{yueling['zhi']}月"
               f"（当令{yueling['dangLingWuxing']}），{'得令或得生' if de_ling else '不得月令生扶'}"),
        reasoning=[
            f"脚本输出月令：{yueling['zhi']}月（节序 {yueling['jieIndex']}/12），当令五行 {yueling['dangLingWuxing']}",
            f"日干五行 {day_wx} 与当令五行关系：{'同气/受生 → 得令倾向' if de_ling else '无直接生扶'}",
            "得令只是旺衰三问之一（得令/得地/得势），完整裁决须再评透干虚实、根气质量、印星有无",
        ],
        rules=[RuleRef(
            ruleId="bazi/wangshuai-sanwen",
            source="《滴天髓》衰旺章 / references/geju-yongshen.md §4a",
            sourceLevel="B")],
        calc_refs=["columns[2].ganWuxing", "yueLing.dangLingWuxing"],
        polarity="neutral",   # 得令与否是旺衰原料，非吉凶断言
    ))
    uncertainty.append("身强身弱未落定：需按 geju-yongshen §4b 三因子（透干虚实/根气质量/月令权重）裁量，两可时给出区分条件")

    # ── 结论 2：五行分布偏重（纯统计事实的体系内读法）──
    strongest = max(wx_hidden, key=lambda k: wx_hidden[k])
    weakest = min(wx_hidden, key=lambda k: wx_hidden[k])
    conclusions.append(build_conclusion(
        claim=f"全盘（含藏干）以{strongest}为最多（{wx_hidden[strongest]}）、{weakest}最少（{wx_hidden[weakest]}），五行有偏",
        reasoning=[
            f"脚本五行统计（含藏干）：{'、'.join(f'{k}{v}' for k, v in wx_hidden.items())}",
            "'中和为贵'（《碧渊篇》）：太过与不及同病，偏重之五行为盘面主要张力所在",
        ],
        rules=[RuleRef(
            ruleId="bazi/zhonghe",
            source="渊海子平《碧渊赋》/ references/geju-yongshen.md §4c",
            sourceLevel="B")],
        calc_refs=["wuxingHidden"],
        polarity="neutral",   # 偏重是结构事实，需用神定吉凶
    ))

    # ── 结论 3：十神分布 ──
    shishen_count: dict[str, int] = {}
    for c in cols:
        if c["shiShen"] != "日主":
            shishen_count[c["shiShen"]] = shishen_count.get(c["shiShen"], 0) + 1
    top_ss = max(shishen_count.items(), key=lambda kv: kv[1]) if shishen_count else ("无比劫官财", 0)
    conclusions.append(build_conclusion(
        claim=f"四柱十神中「{top_ss[0]}」出现最多（{top_ss[1]}处），为盘面显性主题之一",
        reasoning=[
            "十神按日干对其余三干判定（脚本计算）：" +
            "、".join(f"{c['pillarCn']}{c['gan']}={c['shiShen']}" for c in cols),
            "断律应用前须过质量门：逢吉神先看破害、逢凶神先查制化（《喜忌篇》）",
        ],
        rules=[RuleRef(
            ruleId="bazi/shishen-duanlv",
            source="渊海子平各论篇 / references/mingli-program.md §3",
            sourceLevel="B")],
        calc_refs=["columns"],
        polarity="neutral",
    ))

    # ── 大运定位（如有）──
    dayun = data.get("daYun")
    if dayun:
        current = next((s for s in dayun["steps"] if s["current"]), None)
        if current:
            conclusions.append(build_conclusion(
                claim=f"当前行至第{current['index']}步大运 {current['ganZhi']}（{current['startYm']}–{current['endYm']}）",
                reasoning=[
                    f"起运约 {dayun['qiyunYears']} 岁 {dayun['qiyunMonths']} 个月，{'顺' if dayun['forward'] else '逆'}推十年一步（渊海子平《论起大运》）",
                    "岁运吉凶须以用神喜忌为标尺判断——用神未定前不对该运下吉凶断语",
                ],
                rules=[RuleRef(
                    ruleId="bazi/dayun-siyun",
                    source="渊海子平《论起大运》《论大运》/ references/shensha-suiyun.md §2",
                    sourceLevel="B")],
                calc_refs=[f"daYun.steps[{current['index'] - 1}]"],
                polarity="neutral",   # 岁运吉凶须以用神为标尺，未定句不标吉凶
            ))

    return InterpretationResult(
        systemId="bazi",
        summary=(f"{data['siZhu']}。以上结论限结构层：日主月令关系、五行偏重、十神主题"
                 + ("、当前大运定位" if dayun else "")
                 + "。完整断命（调候→格局→用神→岁运断语）待知识库深化后启用。"),
        conclusions=conclusions,
        uncertainty=uncertainty,
        limitations=_LIMITS,
        interpreter="rule-engine",
    )


def _sheng(a: str, b: str) -> bool:
    """a 生 b？"""
    common = load_common()
    return common.SHENG.get(a) == b


def load_common():
    from mingli.engines.loader import load_engine
    return load_engine("common")
