"""Experiment Lab —— 预测记录与命中判定（design.md §9，第六原则）。

七种判定枚举：exact-hit / partial-hit / direction-hit / timing-hit / miss / ambiguous / no-outcome

诚实约束（不可妥协）：
- 判定由用户录入真实结果后，按**用户可见的判定规则表**程序化得出；
- 系统绝不为了"看起来准"自动放宽口径——把 miss 判成 direction-hit 之类的
  自动优化被这里禁止（本模块没有任何"提高命中率"的路径）；
- 判定规则本身随 stats() 一并展示给用户。
"""
from __future__ import annotations

import datetime as _dt

from mingli.core.models import Experiment, ExperimentStatus, Verdict


def evaluate(
    exp: Experiment,
    outcome_text: str,
    *,
    hit_exact: bool = False,
    hit_direction: bool = False,
    hit_timing: bool | None = False,
    ambiguous: bool = False,
) -> Experiment:
    """录入真实结果并按显式布尔输入判定。

    UI 层把"结果与预测的关系"拆成几个明确的是/非问题让用户勾选，
    本函数按固定优先级合成 verdict——顺序公开可查：

        1. 勾选"无法确认结果"      → no-outcome
        2. 勾选"结果模糊难判"      → ambiguous
        3. 完全一致                → exact-hit
        4. 方向一致 + 时间一致      → partial-hit（方向对且时间对但不完全）
        5. 仅方向一致              → direction-hit
        6. 仅时间一致              → timing-hit
        7. 都不一致                → miss
    """
    now = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")
    if ambiguous:
        verdict: Verdict = "ambiguous"
    elif hit_exact:
        verdict = "exact-hit"
    elif hit_direction and (hit_timing or hit_timing is None):
        verdict = "partial-hit"
    elif hit_direction:
        verdict = "direction-hit"
    elif hit_timing:
        verdict = "timing-hit"
    else:
        verdict = "miss"

    exp.outcome = outcome_text
    exp.verdict = verdict
    exp.verdictReasoning = VERDICT_RULES[verdict]
    exp.status = ExperimentStatus.EVALUATED
    exp.evaluatedAt = now
    return exp


def mark_no_outcome(exp: Experiment, note: str = "") -> Experiment:
    """窗口已过但事件未发生/无法验证。"""
    exp.outcome = note or None
    exp.verdict = "no-outcome"
    exp.verdictReasoning = VERDICT_RULES["no-outcome"]
    exp.status = ExperimentStatus.NO_OUTCOME
    return exp


VERDICT_RULES: dict[str, str] = {
    "exact-hit": "用户确认结果与预测完全一致。",
    "partial-hit": "方向一致且时间窗口内发生，但细节不完全吻合。",
    "direction-hit": "方向/趋势判断一致，但时间或细节不符。",
    "timing-hit": "事件在预测窗口内发生，但方向与预测不符。",
    "miss": "方向与时间均与预测不符。",
    "ambiguous": "结果存在多解或难以归类，用户标记为模糊。",
    "no-outcome": "窗口期内事件未发生或无法验证。",
}


def is_window_open(exp: Experiment, on_date: _dt.date | None = None) -> bool:
    d = on_date or _dt.date.today()
    start = _dt.date.fromisoformat(exp.windowStart)
    end = _dt.date.fromisoformat(exp.windowEnd)
    return start <= d <= end
