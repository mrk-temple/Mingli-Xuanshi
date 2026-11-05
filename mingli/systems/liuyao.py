"""六爻 Provider —— 纳甲线（moment+randomized 类）。"""
from __future__ import annotations

from typing import Any

from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalculationResult,
    InterpretationResult,
    Question,
)
from mingli.engines import liuyao as ly_engine
from mingli.engines.loader import engine_version
from mingli.systems.base import InputError

ENGINE = "xuan-shu/scripts/liuyao.py"


class LiuyaoProvider:
    id = "liuyao"
    name = "六爻纳甲"
    region = "east"
    category = ["moment", "randomized"]
    status = "active"
    strengths = "断一件具体事情的成败走向：取用神、看世应动变、定吉凶倾向（起课断一事）"
    limitations = ("装卦确定，取用神与吉凶推断是规则+裁量；铜钱阴阳约定已按主流显式选择"
                   "（字=阴、背=阳）；占筮有效性前提（数决定论）未证")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "mode", "label": "起卦方式", "type": "select",
                 "options": ["coins", "numbers", "time", "random"], "required": True},
                {"name": "coins", "label": "摇卦背数（6 个，自下而上）", "type": "int-list",
                 "required": False},
                {"name": "numbers", "label": "报数（2 或 3 个）", "type": "int-list", "required": False},
                {"name": "timeInput", "label": "农历时间（年支序 月 日 时辰序）", "type": "int-list",
                 "required": False},
                {"name": "seed", "label": "随机种子（模拟摇卦可复现）", "type": "int", "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        errs = []
        mode = input_data.get("mode")
        if mode not in ("coins", "numbers", "time", "random"):
            errs.append("mode 须为 coins/numbers/time/random")
            return errs
        if mode == "coins":
            coins = input_data.get("coins") or []
            if len(coins) != 6 or any(not isinstance(c, int) or not 0 <= c <= 3 for c in coins):
                errs.append("铜钱摇卦需要 6 个整数（每爻背数 0-3，自下而上）")
        elif mode == "numbers":
            nums = input_data.get("numbers") or []
            if len(nums) not in (2, 3):
                errs.append("报数起卦需要 2 或 3 个数")
        elif mode == "time":
            t = input_data.get("timeInput") or []
            if len(t) != 4:
                errs.append("农历时间起卦需要 4 个数：年支序 月 日 时辰序")
        return errs

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        if self.validate_input(input_data):
            raise InputError("；".join(self.validate_input(input_data)))
        date = input_data.get("date")
        try:
            data = ly_engine.liuyao_calculate(
                mode=input_data["mode"],
                coins=input_data.get("coins"),
                numbers=input_data.get("numbers"),
                time_input=input_data.get("timeInput"),
                seed=input_data.get("seed"),
                zi_as_yang=bool(input_data.get("ziAsYang")),
                date=tuple(date) if date else None,
            )
        except ValueError as e:
            raise InputError(str(e)) from e
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("liuyao"),
            inputSnapshot={"mode": input_data["mode"], **{
                k: v for k, v in input_data.items() if k in ("coins", "numbers", "timeInput", "seed", "ziAsYang")}},
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
        from mingli.systems.liuyao_interpret import interpret_liuyao
        return interpret_liuyao(calculation, question, knowledge)

    def recommend_for(self, question: Question) -> float:
        from mingli.core.router import classify_question
        cls = classify_question(question.text)
        score = 0.0
        if cls.category == "decision" or "该不该" in question.text or "要不要" in question.text:
            score += 0.5
        if cls.horizon == "near-term":
            score += 0.3
        if cls.category in ("career", "relationship", "finance", "study"):
            score += 0.2
        return max(0.0, min(1.0, score))
