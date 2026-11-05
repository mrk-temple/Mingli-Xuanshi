"""易经义理 Provider —— 义理线（knowledge 类，无占筮计算）。

定位（yijing-yili.md）：义理可独立成知——概念问答、决策启发、解卦框架。
calculate() 输出卦象结构事实（给定卦名）；interpret() 按"先判位→再察时→
后看谦"框架引用可执行规则表，每条带出处章节。
"""
from __future__ import annotations

from typing import Any

from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalculationResult,
    InterpretationResult,
    Question,
)
from mingli.engines import yijing as yj_engine
from mingli.engines.loader import engine_version, load_engine
from mingli.systems.base import InputError

ENGINE = "mingli/engines/yijing.py"


class YijingProvider:
    id = "yijing"
    name = "易经义理"
    region = "east"
    category = ["knowledge", "decision-framework"]
    status = "active"
    strengths = ("决策启发与自省框架：'判位-察时-谦'三轴脱离占筮前提独立成立，"
                 "每条规则带易经原文出处")
    limitations = ("占筮有效性主张前提未证不可证伪；384 爻辞几乎覆盖所有情境"
                   "（巴纳姆效应），'应验'不可复现")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "guaName", "label": "卦名（六十四卦之一，如 谦）", "type": "text",
                 "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        # 卦名可选：无卦名走纯义理问答；有则须为六十四卦之一（与引擎同表校验）
        gua_name = (input_data.get("guaName") or "").strip()
        if not gua_name:
            return []
        from mingli.engines.yijing import _name_to_trigrams
        if gua_name not in _name_to_trigrams():
            return [f"未知卦名「{gua_name}」——须为六十四卦名之一，如 乾为天、地山谦、水火既济"]
        return []

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        gua_name = (input_data.get("guaName") or "").strip()
        data: dict[str, Any]
        if gua_name:
            try:
                data = yj_engine.yijing_calculate(gua_name=gua_name)
            except ValueError as e:
                raise InputError(str(e)) from e
        else:
            qg = load_engine("qigua")
            data = {"mode": "pure-yili", "note": "未指定卦名：纯义理模式，仅输出决策启发规则"}
            _ = qg  # 引擎可用性确认
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("qigua"),
            inputSnapshot={"guaName": gua_name},
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
        from mingli.systems.yijing_interpret import interpret_yijing
        return interpret_yijing(calculation, question, knowledge)

    def recommend_for(self, question: Question) -> float:
        text = question.text
        score = 0.0
        if any(w in text for w in ("启示", "哲理", "怎么看待", "心态", "智慧")):
            score += 0.5
        if any(w in text for w in ("谦", "变革", "困境", "等待时机")):
            score += 0.2
        return max(0.0, min(1.0, score))
