"""梅花易数 Provider —— 体用生克断事之机。"""
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
from mingli.engines import meihua as mh_engine
from mingli.engines.loader import engine_version
from mingli.systems.base import InputError

ENGINE = "xuan-shu/scripts/qigua.py"


class MeihuaProvider:
    id = "meihua"
    name = "梅花易数"
    region = "east"
    category = ["moment", "randomized"]
    status = "active"
    strengths = "快速象数判断：报数即起卦，体用生克定吉凶倾向，适合求速断"
    limitations = ("起卦装卦确定，断卦为体用生克+旺衰（规则+裁量）；外应仅卦象不明时参考；"
                   "数决定论前提未证")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "mode", "label": "起卦方式", "type": "select",
                 "options": ["numbers", "lunar", "solar"], "required": True},
                {"name": "numbers", "label": "报数（2 或 3 个）", "type": "int-list", "required": False},
                {"name": "lunar", "label": "农历（年支数 月 日 时辰数）", "type": "int-list", "required": False},
                {"name": "solar", "label": "公历（年 月 日 时）", "type": "int-list", "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        errs = []
        mode = input_data.get("mode")
        if mode not in ("numbers", "lunar", "solar"):
            errs.append("mode 须为 numbers/lunar/solar")
            return errs
        vals = input_data.get(mode == "numbers" and "numbers" or (mode == "lunar" and "lunar" or "solar")) or []
        if mode == "numbers" and len(vals) not in (2, 3):
            errs.append("报数起卦需要 2 或 3 个数")
        if mode in ("lunar", "solar") and len(vals) != 4:
            errs.append(("农历" if mode == "lunar" else "公历") + "起卦需要 4 个数：年 月 日 时")
        return errs

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        if self.validate_input(input_data):
            raise InputError("；".join(self.validate_input(input_data)))
        try:
            data = mh_engine.meihua_calculate(
                numbers=input_data.get("numbers"),
                lunar=input_data.get("lunar"),
                solar=input_data.get("solar"),
            )
        except (ValueError, RuntimeError) as e:
            raise InputError(str(e)) from e
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("qigua"),
            inputSnapshot={k: v for k, v in input_data.items() if k in ("mode", "numbers", "lunar", "solar")},
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
        tiyong = data["tiYong"]
        shengke_txt = tiyong["shengKe"]
        # 体用生克主极性（吉凶主干，依体用总诀）
        if shengke_txt.startswith("用生体"):
            ty_pol = "positive"
        elif shengke_txt.startswith("用克体"):
            ty_pol = "negative"
        else:
            ty_pol = "neutral"
        conclusions: list[Conclusion] = [
            build_conclusion(
                claim=f"体卦{tiyong['body']['trigram']}（{tiyong['body']['wuxing']}）、"
                      f"用卦{tiyong['use']['trigram']}（{tiyong['use']['wuxing']}）：{shengke_txt}",
                reasoning=[
                    f"动爻在第 {data['movingLine']} 爻——动爻所在卦为用卦，另一卦为体卦",
                    "体用生克是梅花断卦主轴：用生体吉、用克体凶、体生用泄、体克用费力、比和平",
                    "本卦看当下，互卦看过程，变卦看结果；变卦五行定最终趋势",
                ],
                rules=[RuleRef(
                    ruleId="meihua/tiyong-shengke",
                    source="《梅花易数》体用总诀 / references/duangua-guide.md §2",
                    sourceLevel="B")],
                calc_refs=["tiYong.shengKe", "movingLine"],
                polarity=ty_pol,
            ),
            build_conclusion(
                claim=f"变卦{data['bianGua']['name']}示最终趋势，互卦{data['huGua']['name']}示中间过程",
                reasoning=[
                    "互卦五行：" + "、".join(filter(None, [data['huGua'].get('upperWuxing'), data['huGua'].get('lowerWuxing')])),
                    "变卦五行与体卦关系修正吉凶程度：变生体终吉，变克体终凶",
                ],
                rules=[RuleRef(
                    ruleId="meihua/hubian-gua",
                    source="《梅花易数》互变卦 / references/duangua-guide.md §2",
                    sourceLevel="B")],
                calc_refs=["bianGua", "huGua"],
                polarity=ty_pol,   # 终势与体用主干同向修正（生克延展，见上）
            ),
        ]
        uncertainty: list[str] = []
        if data["movingLine"] <= 0:
            uncertainty.append("体用不分（无动爻）：卦象不明，不强行解读")
        return InterpretationResult(
            systemId="meihua",
            summary=f"本卦{data['benGua']['name']}，{shengke_txt.split('→')[0].strip()}。体系内规则语言，非事实断言。",
            conclusions=conclusions,
            uncertainty=uncertainty,
            limitations=[
                "断卦为体用生克+旺衰裁量；外应仅在卦象不明时参考并注明",
                "数决定论前提未证（piping-guide §1）",
            ],
            interpreter="rule-engine",
        )

    def recommend_for(self, question: Question) -> float:
        from mingli.core.router import classify_question
        cls = classify_question(question.text)
        score = 0.0
        if any(w in question.text for w in ("快速", "速断", "马上知道", "简单看看")):
            score += 0.4
        if cls.horizon == "near-term":
            score += 0.3
        if cls.category in ("decision", "career", "relationship", "finance"):
            score += 0.2
        return max(0.0, min(1.0, score))
