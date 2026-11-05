"""小六壬 Provider —— 掌诀线（moment+randomized 类，速断）。"""
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
from mingli.engines import xiaoliuren as xlr_engine
from mingli.engines.loader import engine_version
from mingli.systems.base import InputError

ENGINE = "xuan-shu/scripts/xiaoliuren.py"


class XiaoliurenProvider:
    id = "xiaoliuren"
    name = "小六壬（马前课）"
    region = "east"
    category = ["moment", "randomized"]
    status = "active"
    strengths = "六宫轮转速断：报三数即得吉凶主调与行动指向（宜缓/宜动/防口舌）"
    limitations = ("六宫算法完全确定，但断辞展开为通行本；古法与总数累加法相差 2 位"
                   "（默认古法）；与大六壬仅共享'六壬'之名，术理无传承关系")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "mode", "label": "起课方式", "type": "select",
                 "options": ["numbers", "lunar", "solar"], "required": True},
                {"name": "numbers", "label": "报三数（依次代月/日/时数）", "type": "int-list", "required": False},
                {"name": "lunar", "label": "农历（月 日 时辰序）", "type": "int-list", "required": False},
                {"name": "solar", "label": "公历（年 月 日 时）", "type": "int-list", "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        errs = []
        mode = input_data.get("mode")
        if mode not in ("numbers", "lunar", "solar"):
            errs.append("mode 须为 numbers/lunar/solar")
            return errs
        if mode == "solar":
            vals = input_data.get("solar") or []
            if len(vals) != 4:
                errs.append("公历起课需要 年 月 日 时")
            return errs
        vals = input_data.get("numbers" if mode == "numbers" else "lunar") or []
        if len(vals) != 3:
            errs.append("需要三个数")
            return errs
        m, d, h = vals
        if not (isinstance(m, int) and isinstance(d, int) and isinstance(h, int)):
            errs.append("三个数均须为整数")
        elif mode == "lunar" and not (1 <= m <= 12 and 1 <= d <= 30 and 1 <= h <= 12):
            errs.append("输入越界：月 1-12，日 1-30，时辰 1-12（子=1…亥=12）")
        return errs

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        if self.validate_input(input_data):
            raise InputError("；".join(self.validate_input(input_data)))
        try:
            data = xlr_engine.xiaoliuren_calculate(
                numbers=input_data.get("numbers"),
                lunar=input_data.get("lunar"),
                solar=input_data.get("solar"),
            )
        except (ValueError, RuntimeError) as e:
            raise InputError(str(e)) from e
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("xiaoliuren"),
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
        dg = data["duanGong"]
        # 断宫主吉凶 → 主极性（通行宫性表）
        dg_pol = "positive" if dg["name"] in ("大安", "速喜", "小吉") else "negative"
        conclusions: list[Conclusion] = [
            build_conclusion(
                claim=f"断宫落「{dg['name']}」（{dg['jixiong']}·{dg['wuxing']}·六神{dg['liushen']}），主调：{_zhu_tiao(dg['name'])}",
                reasoning=[
                    f"古法三步重锚：月上起日、日上起时——月宫{data['yueGong']['name']}、日宫{data['riGong']['name']}、断宫{dg['name']}",
                    f"断辞（通行本）：{dg['duanci'][:40]}…",
                    f"月宫看起因（{data['yueGong']['name']}）、日宫看过程（{data['riGong']['name']}）、断宫定结果主调",
                ],
                rules=[RuleRef(
                    ruleId="xiaoliuren/duangong",
                    source="小六壬通行本断辞 / references/xiaoliuren-guide.md §2-§4",
                    sourceLevel="C")],
                calc_refs=["duanGong", "yueGong.name", "riGong.name"],
                polarity=dg_pol,
            ),
        ]
        return InterpretationResult(
            systemId="xiaoliuren",
            summary=f"{data['qiKeSource']}。断宫{dg['name']}（{dg['jixiong']}）。速断定位：结论简短、给行动指向。",
            conclusions=conclusions,
            uncertainty=["23 点子时归属、闰月归属有流派分歧：以用户自报农历口径为准"]
            if data["mode"] != "numbers" else [],
            limitations=[
                "断辞为通行本（各版本个别字词有出入），来源等级 C（当代实践资料）",
                "小六壬与大六壬仅共享'六壬'之名，术理无传承关系——不混用两套断法",
            ],
            interpreter="rule-engine",
        )

    def recommend_for(self, question: Question) -> float:
        from mingli.core.router import classify_question
        cls = classify_question(question.text)
        score = 0.0
        if any(w in question.text for w in ("快速", "速断", "掐指")):
            score += 0.5
        if cls.horizon == "near-term":
            score += 0.3
        return max(0.0, min(0.8, score))


_ZHU_TIAO_MAP = {
    "大安": "安稳守成，宜按部就班",
    "留连": "迟滞难成，宜缓不宜急",
    "速喜": "迅速有喜，宜趁势而动",
    "赤口": "口舌是非，慎言慎行",
    "小吉": "和合有成，宜合作协商",
    "空亡": "落空无利，宜收手守静",
}


def _zhu_tiao(gong: str) -> str:
    return _ZHU_TIAO_MAP.get(gong, "")
