"""易经义理解读 —— 决策启发规则表（每条带出处，yijing-yili.md §3）。"""
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

# 可执行规则表（脱离占筮前提独立成立；yijing-yili.md §3 全表精选）
YILI_RULES = [
    ("盈满时守戒", "事业鼎盛期决策", "盛极必衰，思患预防、知进知退", "丰卦彖传、乾文言"),
    ("困境守志", "逆境", "困而不失其所亨；受压制则'用晦而明'", "困卦、明夷"),
    ("居功处谦", "有功劳被称颂", "'卑以自牧'，有功不伐", "谦卦"),
    ("藏器待时", "等待行动窗口", "'君子藏器于身，待时而动'", "系辞下 5 章"),
    ("作事谋始", "签约/合伙/分歧前", "争端在起点防范", "讼卦象传"),
    ("慎言慎密", "高风险沟通", "'几事不密则害成'", "系辞上 8 章"),
    ("成功后以未济心态", "项目收尾后", "'初吉终乱'，不恋完成态", "既济卦"),
    ("安不忘危", "稳定期治理", "'其亡其亡，系于苞桑'", "否卦九五"),
    ("改革取信后行", "推动变革", "'己日乃孚''革言三就'——再三审慎才革", "革卦"),
]


def interpret_yijing(
    calculation: CalculationResult,
    question: Question | None,
    knowledge: KnowledgeBase,
) -> InterpretationResult:
    data = calculation.data
    conclusions: list[Conclusion] = []
    uncertainty: list[str] = []

    gua_name = data.get("guaName")
    if gua_name:
        up, low = data["upper"], data["lower"]
        conclusions.append(build_conclusion(
            claim=f"卦象：{gua_name}（上{up['name']}下{low['name']}）——上{up['xiang']}下{low['xiang']}",
            reasoning=[
                f"上下卦结构由六爻阴阳排布确定（脚本计算）：{data['lines']}",
                "解卦框架（先判位→再察时→后看谦）：位看爻位中正当否，时看盛衰节律，谦看德性收敛",
                "'知者观其彖辞，思过半矣'（系辞下 9 章）",
            ],
            rules=[RuleRef(
                ruleId="yijing/jiegua-kuangjia",
                source="《易经》系辞 / references/yijing-yili.md §4",
                sourceLevel="S")],
            calc_refs=["guaName", "lines"],
            polarity="symbolic",   # 卦象结构是象意层，非吉凶断言
        ))

    # 场景匹配的义理规则
    qcat = question.category if question else "other"
    picked = _pick_rules(qcat)
    for name, scene, content, source in picked:
        conclusions.append(build_conclusion(
            claim=f"{name}：{content}",
            reasoning=[
                f"触发场景：{scene}" + (f"（你的问题归类为 {qcat}，命中此场景）" if question else ""),
                "本规则属义理层——脱离占筮前提独立成立（可独立成知），非预言",
            ],
            rules=[RuleRef(
                ruleId=f"yilinx/{name}",
                source=f"《易经》{source} / references/yijing-yili.md §3",
                sourceLevel="S")],
            calc_refs=["mode"] if not gua_name else ["guaName"],
            polarity="symbolic",   # 决策启发不构成吉凶预言
        ))

    return InterpretationResult(
        systemId="yijing",
        summary=("易经义理定位：哲学启发与决策框架，不是预言。"
                 + (f"当前卦：{gua_name}。" if gua_name else "纯义理模式（未指定卦名）。")),
        conclusions=conclusions,
        uncertainty=uncertainty + [
            "384 爻辞几乎覆盖所有情境（巴纳姆效应），任何结果都能找到支持辞——引用时自查是否事后附会",
        ],
        limitations=[
            "占筮有效性主张（'极数知来''易与天地准'）前提未证、不可证伪",
            "内部矛盾实例：乾'用九见群龙无首吉' vs 比卦上六'比之无首凶'——同一象两种断辞",
        ],
        interpreter="rule-engine",
    )


_SCENE_MAP = {
    "career": ["盈满时守戒", "困境守志", "改革取信后行", "藏器待时"],
    "decision": ["作事谋始", "藏器待时", "成功后以未济心态"],
    "relationship": ["慎言慎密", "居功处谦"],
    "finance": ["安不忘危", "盈满时守戒"],
    "study": ["居功处谦", "藏器待时"],
    "timing": ["藏器待时", "改革取信后行"],
}


def _pick_rules(category: str) -> list[tuple[str, str, str, str]]:
    wanted = set(_SCENE_MAP.get(category, []))
    if not wanted:
        return YILI_RULES[:3]
    return [r for r in YILI_RULES if r[0] in wanted]
