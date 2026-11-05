"""SystemProvider 统一接口 —— 术数体系插件化（第三原则）。

每个体系实现本协议并注册到 SystemRegistry。接口七项对齐任务书：
    id / name / region / category / inputSchema / validateInput() /
    calculate() / interpret() / recommendQuestion()

status 三态（诚实原则）：
    active         计算器+规则库可用
    knowledge-only 有知识/规则但无可靠计算器，UI 明示"仅知识参考"
    planned        已登记未实现，UI 如实标注，绝不假装支持

Calculator ≠ LLM 的程序保证：calculate() 由确定性引擎实现；
interpret() 只消费 CalculationResult 与规则库，不重新计算任何术数事实。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from mingli.core.models import (
    CalculationResult,
    InterpretationResult,
    Question,
)

if TYPE_CHECKING:
    from mingli.core.knowledge import KnowledgeBase


@runtime_checkable
class SystemProvider(Protocol):
    """术数体系 Provider 协议。"""

    id: str
    name: str
    region: str
    # 体系类别标签，如 ["natal"]（出生时刻型）/ ["moment","randomized"] 等，
    # 对齐 design.md §2 的 A-F 输入模型分类。
    category: list[str]
    status: str
    # 一句话定位：这个体系擅长回答什么结构的问题（Router 依据）
    strengths: str
    limitations: str

    def input_schema(self) -> dict[str, Any]:
        """返回输入字段的 JSON-schema 风格描述（Web 表单据此渲染）。"""
        ...

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        """校验输入；返回错误列表（空列表 = 通过）。不抛异常。"""
        ...

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        """调用确定性引擎计算。输入非法时抛 InputError。"""
        ...

    def interpret(
        self,
        calculation: CalculationResult,
        question: Question | None,
        knowledge: KnowledgeBase,
    ) -> InterpretationResult:
        """基于计算结果 + 规则库产出可追溯解读。不做任何术数重算。"""
        ...

    def recommend_for(self, question: Question) -> float:
        """问题→本体系的匹配分（0-1）。只表达信息模型匹配度，不是'准确度'。"""
        ...


class InputError(Exception):
    """Provider.calculate 收到非法输入时抛出（validate_input 已先行拦截）。"""
