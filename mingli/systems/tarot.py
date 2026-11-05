"""塔罗 Provider —— 西占线（randomized 类，自省式解读）。"""
from __future__ import annotations

from typing import Any

from mingli.core.interpret.rules import build_conclusion
from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalculationResult,
    Conclusion,
    InterpretationResult,
    Question,
    RuleRef,
)
from mingli.engines import tarot as tarot_engine
from mingli.engines.loader import engine_version
from mingli.systems.base import InputError

ENGINE = "xuan-shu/scripts/tarot.py"


class TarotProvider:
    id = "tarot"
    name = "塔罗（RWS）"
    region = "west"
    category = ["randomized"]
    status = "active"
    strengths = "心理/象征视角：牌阵+牌义做自我反思与多角度审度，不给宿命结论"
    limitations = ("塔罗与易学体系无本源关系；元素对应为后天 syncretic 映射"
                   "（版本声明：宝剑=金）；抽牌与所问之事的关联未被论证")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "spread", "label": "牌阵", "type": "select",
                 "options": ["single", "three", "celtic"], "required": True},
                {"name": "seed", "label": "随机种子（可选，可复现）", "type": "int", "required": False},
                {"name": "noReversals", "label": "无逆位模式", "type": "bool", "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        if input_data.get("spread") not in ("single", "three", "celtic"):
            return ["spread 须为 single/three/celtic"]
        return []

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        if self.validate_input(input_data):
            raise InputError("；".join(self.validate_input(input_data)))
        data = tarot_engine.tarot_calculate(
            spread=input_data["spread"],
            seed=input_data.get("seed"),
            no_reversals=bool(input_data.get("noReversals")),
        )
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("tarot"),
            inputSnapshot={"spread": input_data["spread"],
                           "seed": input_data.get("seed"),
                           "noReversals": bool(input_data.get("noReversals"))},
            data=data,
            rawText="",
            warnings=[],
        )

    def interpret(
        self,
        calculation: CalculationResult,
        question: Question | None,
        knowledge: KnowledgeBase,
    ) -> InterpretationResult:
        data = calculation.data
        cards = data["cards"]
        conclusions: list[Conclusion] = []

        # 五步解读之 1：定基调（大阿卡纳占比）
        major_count = sum(1 for c in cards if c["group"] == "大阿卡纳")
        tone = ("大阿卡纳主导：人生主题级事件，解读从具体事务升到人生阶段"
                if major_count >= max(2, len(cards) // 2)
                else "小阿卡纳为主：日常事务与具体情境层面")
        conclusions.append(build_conclusion(
            claim=f"基调：{tone}（大阿卡纳 {major_count}/{len(cards)} 张）",
            reasoning=[
                "抽牌事实：" + "；".join(
                    f"{c['position']}={c['nameZh']}{c['nameEn']}（{c['orientation']}）"
                    for c in cards),
                "五步解读第一步：按大阿卡纳占比定基调（tarot-guide §2）",
            ],
            rules=[RuleRef(
                ruleId="tarot/wubu-jiedu",
                source="RWS 通行解读法 / references/tarot-guide.md §2",
                sourceLevel="B")],
            calc_refs=["cards"],
            polarity="symbolic",   # 基调是大/小阿卡纳构成，非吉凶——象征层
        ))

        # 逐张读（位置 × 牌义 × 正逆）
        for i, c in enumerate(cards):
            orient_txt = ""
            if c["reversed"]:
                orient_txt = "逆位读作'能量受阻/内在化/提醒'，不读作凶"
            conclusions.append(build_conclusion(
                claim=f"「{c['position']}」位：{c['nameZh']} {c['nameEn']}（{c['orientation']}）——{c['keywords'].split('、')[0]}",
                reasoning=[
                    f"位置含义：{c['positionMeaning']}",
                    f"牌义关键词：{c['keywords']}",
                    orient_txt or "正位按本义读",
                    "解读 = 牌义 × 牌阵位置 × 所问事项 × 牌间关系（结论须能回溯此四元）",
                ],
                rules=[RuleRef(
                    ruleId="tarot/paiyi-sucha",
                    source="RWS 韦特体系牌义 / references/tarot-meanings.md",
                    sourceLevel="C")],
                calc_refs=[f"cards[{i}]"],
                polarity="symbolic",   # 塔罗定位自我反思，不参与吉凶并论
            ))

        uncertainty: list[str] = []
        rev_ratio = sum(1 for c in cards if c["reversed"]) / len(cards)
        if rev_ratio >= 0.5:
            uncertainty.append("逆位占比过半：整体能量偏内在化/受阻——建议类解读加重'先清理内在'方向")

        return InterpretationResult(
            systemId="tarot",
            summary=(f"{data['spreadName']}。塔罗定位是自我反思工具，不是预言。"
                     f"随机源：{data['randomSource']}。"),
            conclusions=conclusions,
            uncertainty=uncertainty,
            limitations=[
                "塔罗与易学体系无本源关系；元素对应为 syncretic 映射（版本：宝剑=金）",
                "随机起数→所问之事的关联未被论证（数决定论）",
                "不承诺吉凶与确定性：抽牌与解读不预测未来",
            ],
            interpreter="rule-engine",
        )

    def recommend_for(self, question: Question) -> float:
        from mingli.core.router import classify_question
        cls = classify_question(question.text)
        score = 0.0
        if any(w in question.text for w in ("心态", "心理", "感受", "纠结", "迷茫")):
            score += 0.5
        if cls.category == "relationship":
            score += 0.3
        if cls.category in ("decision", "career"):
            score += 0.2
        return max(0.0, min(1.0, score))
