"""规则版解释引擎 —— 默认实现（离线可用、确定性、可测试）。

工作方式：各 Provider 的 interpret() 负责"体系特定读法"（如六爻取用神、
梅花体用），本模块提供共享的结论组装与校验工具：
- build_conclusion(): 强制断语携带推理链+规则引用+计算引用
- verify_conclusion(): 校验 calcRefs 路径真实存在于 CalculationResult.data
  （悬空引用 = 程序错误，报告层拒绝渲染）

LLM 插槽（llm.py）产出同样结构，经同一校验——LLM 不能绕过可追溯约束。
"""
from __future__ import annotations

import re
from typing import Any

from mingli.core.models import CalcRef, CalculationResult, Conclusion, RuleRef


def build_conclusion(
    claim: str,
    reasoning: list[str],
    rules: list[RuleRef],
    calc_refs: list[str],
    polarity: str | None = None,   # positive/negative/neutral/symbolic
) -> Conclusion:
    """组装一条可追溯断语。calc_refs 为 data 字段路径列表。"""
    return Conclusion(
        claim=claim,
        reasoning=reasoning,
        rules=rules,
        calcRefs=[CalcRef(path=p) for p in calc_refs],
        polarity=polarity,  # type: ignore[arg-type]
    )


def resolve_path(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    """按点分路径取值；支持 [n] 数组下标。返回 (存在?, 值)。"""
    cur: Any = data
    for part in path.split("."):
        if "[" in part:
            match = re.fullmatch(r"([^\[\]]+)\[(\d+)\]", part)
            if not match:
                return False, None
            head, index = match.groups()
            idx = int(index)
            if not isinstance(cur, dict) or head not in cur:
                return False, None
            cur = cur[head]
            if not isinstance(cur, list) or idx >= len(cur):
                return False, None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return False, None
            cur = cur[part]
    return True, cur


def verify_conclusion(conc: Conclusion, calc: CalculationResult) -> list[str]:
    """校验断语：推理链非空、规则非空、计算引用全部可达。返回错误列表。"""
    errors: list[str] = []
    if not conc.reasoning:
        errors.append(f"断语缺推理链: {conc.claim[:30]}…")
    if not conc.rules:
        errors.append(f"断语缺规则引用: {conc.claim[:30]}…")
    if not conc.calcRefs:
        errors.append("断语缺计算引用")
    for ref in conc.calcRefs:
        ok, _ = resolve_path(calc.data, ref.path)
        if not ok:
            errors.append(f"计算引用不可达: {ref.path}")
        else:
            _, val = resolve_path(calc.data, ref.path)
            ref.value = val  # 回填，供报告展示
    return errors


def format_calc_value(val: Any, limit: int = 120) -> str:
    """原始数据展示用：dict/list 转紧凑文本。"""
    s = str(val)
    return s if len(s) <= limit else s[:limit] + "…"
