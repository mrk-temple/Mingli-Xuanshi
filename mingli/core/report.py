"""报告渲染器 —— 可追溯报告（第十原则）+ 强制质量门（第一原则程序化）。

渲染流程（无开关、不可跳过）：
1. 校验每条 conclusion：推理链非空 / 规则引用存在 / calcRefs 全部可达。
   任一失败 → 拒绝渲染（宁可不出报告，不可出不可追溯的报告）。
2. 事实节（脚本原样输出）与解读节严格分列；每条断语可展开
   结论→推理链→规则→原始数据→来源。
3. "体系局限"节强制注入（五大未证假设 + 本体系局限条目）。
4. 敏感域提示 + 免责声明硬编码在尾部。
"""
from __future__ import annotations

from typing import Any

from mingli.core.interpret.rules import format_calc_value, verify_conclusion
from mingli.core.knowledge import load_knowledge
from mingli.core.models import (
    CalculationResult,
    DivinationSession,
)
from mingli.core.reading import display_guide, validate_guide
from mingli.core.safety import DISCLAIMER, assess, downgrade_claims

# 五大未证假设（piping-guide §1）——所有体系共用
FIVE_ASSUMPTIONS = [
    "八字决定论：出生时刻→命运的因果链从未被论证",
    "数决定论：随机起数→所问之事的关联未被论证",
    "天人同构：自然现象类比人事吉凶，类比被当作推理",
    "变通条款免疫：任何失败都可归因于'未通变'，理论免疫于证伪",
    "同命不同运：同八字者贵贱祸福迥异（三命通会亲证反例）",
]


class ReportError(Exception):
    """报告校验失败（悬空引用/缺推理链等）时抛出。"""


def render_markdown(
    session: DivinationSession,
    question_text: str | None = None,
) -> str:
    """把一次 session 渲染为 Markdown 报告。校验失败抛 ReportError。"""
    interp = session.interpretation
    if interp is None:
        raise ReportError("session 无解读结果，拒绝出报告")
    errors: list[str] = []
    knowledge = load_knowledge()
    for conc in interp.conclusions:
        errors.extend(verify_conclusion(conc, session.calculation))
        if knowledge.for_system(session.systemId):
            for rr in conc.rules:
                rule = knowledge.get_rule(rr.ruleId)
                if rule is None or rule.systemId != session.systemId:
                    errors.append(f"规则引用无法核验: {rr.ruleId}")
    if interp.readerGuide:
        errors.extend(validate_guide(interp.readerGuide, interp))
    if errors:
        raise ReportError("报告校验失败：" + "；".join(errors))

    safety = assess(question_text or session.question.text)
    claims = downgrade_claims([c.claim for c in interp.conclusions], safety)

    lines: list[str] = []
    lines.append(f"# {session.calculation.systemId} 分析报告")
    lines.append("")
    lines.append(f"> 会话：{session.id}　时间:{session.createdAt}　解释器：{interp.interpreter}")
    lines.append(f"> 所问：{question_text or session.question.text}")
    if interp.readerGuide and interp.readerGuide.mode == "llm":
        lines.append("> 规则结论由离线规则引擎产生；模型仅编辑白话阅读指引，未改写计算事实与规则结论。")
    lines.append("")

    guide = display_guide(session.calculation, session.question, interp)
    if guide:
        lines.append("## 先用白话回答（解释层，非科学预测）")
        lines.append(guide.answer.text)
        lines.append("关联规则结论：" + "、".join(str(i) for i in guide.answer.conclusionRefs))
        for point in guide.points:
            lines.append(f"- {point.text}（见规则结论 {point.conclusionRefs}）")
        lines.append("### 可以做的下一步（现实建议，不是盘面预测）")
        for action in guide.actions:
            lines.append(f"- **{action.title}**：{action.detail}")
        lines.append("")

    # ── 事实层 ──
    lines.append("## 一、计算结果（确定性引擎输出，事实）")
    lines.append("```")
    lines.append(session.calculation.rawText.rstrip() or _summarize_calc(session.calculation))
    lines.append("```")
    if session.calculation.warnings:
        for w in session.calculation.warnings:
            lines.append(f"- ⚠️ {w}")
    lines.append("")

    # ── 解读层 ──
    lines.append("## 二、解读（体系内规则语言，非事实断言）")
    lines.append(interp.summary)
    lines.append("")
    for i, (conc, claim) in enumerate(zip(interp.conclusions, claims, strict=True), 1):
        lines.append(f"### 断语 {i}：{claim}")
        lines.append("**推理链**：")
        for j, r in enumerate(conc.reasoning, 1):
            lines.append(f"  {j}. {r}")
        lines.append("**依据规则**：")
        for rr in conc.rules:
            rule = knowledge.get_rule(rr.ruleId)
            level, source = (rule.sourceLevel, rule.source) if rule else (rr.sourceLevel, rr.source)
            lines.append(f"  - `{rr.ruleId}`（来源等级 {level}）：{source}")
        lines.append("**原始数据引用**：")
        for ref in conc.calcRefs:
            v = format_calc_value(ref.value)
            lines.append(f"  - `calc.{ref.path}` = {v}")
        lines.append("")

    if interp.uncertainty:
        lines.append("## 三、两可与不确定点")
        for u in interp.uncertainty:
            lines.append(f"- {u}")
        lines.append("")

    disputes = [r for r in knowledge.for_system(session.systemId) if r.disputes or "@" in r.id]
    if disputes:
        lines.append("## 流派分歧（并列，不合并；本次采用规则以结论编号为准）")
        for rule in disputes:
            lines.append(f"- `{rule.id}` [{rule.tradition}]：{rule.statement}")
            for dispute in rule.disputes:
                lines.append(f"  - 分歧：{dispute}")
            lines.append(f"  - [{rule.sourceLevel}] {rule.source}")
        lines.append("")

    # ── 强制：体系局限 ──
    lines.append("## 体系局限（必写）")
    lines.append("- 五大未证假设：" + "；".join(FIVE_ASSUMPTIONS))
    for lim in interp.limitations or ["本体系断语均为体系内规则语言，有效性未被科学验证。"]:
        lines.append(f"- {lim}")
    lines.append("")

    # ── 强制：安全与免责 ──
    for n in safety.notices:
        lines.append(f"> **{n}**")
    if safety.sensitive:
        lines.append(f"（敏感域标记：{', '.join(safety.sensitive)}——相关断语已降级为参考性表述）")
    lines.append(f"**免责声明**：{DISCLAIMER}")
    return "\n".join(lines)


def evidence_trace_json(session: DivinationSession) -> dict[str, Any]:
    """结论 → 推理链 → 规则 → 原始数据 的机器可读 trace（UI 展开用）。"""
    interp = session.interpretation
    assert interp is not None  # noqa: S101 - render 前置已保证
    trace: dict[str, Any] = {
        "sessionId": session.id,
        "systemId": session.systemId,
        "engine": session.calculation.engine,
        "engineVersion": session.calculation.engineVersion,
        "inputSnapshot": session.calculation.inputSnapshot,
        "conclusions": [],
    }
    knowledge = load_knowledge()
    for conc in interp.conclusions:
        rules = []
        for rr in conc.rules:
            rule = knowledge.get_rule(rr.ruleId)
            rules.append({**rr.model_dump(), **({"source": rule.source,
                          "sourceLevel": rule.sourceLevel, "tradition": rule.tradition,
                          "disputes": rule.disputes, "statement": rule.statement} if rule else {})})
        resolved = []
        for ref in conc.calcRefs:
            ok, val = _resolve(session.calculation.data, ref.path)
            resolved.append({"path": ref.path, "exists": ok, "value": val})
        trace["conclusions"].append({
            "claim": conc.claim,
            "reasoning": conc.reasoning,
            "rules": rules,
            "calcRefs": resolved,
        })
    return trace


def _resolve(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    from mingli.core.interpret.rules import resolve_path
    return resolve_path(data, path)


def export_ai_json(session: DivinationSession) -> dict[str, Any]:
    """盘局导出（供第三方 AI 分析）——中性盘面数据，不含吉凶综合结论。

    设计（区别于 report.md）：
    - 以 machine-readable 为主：只含盘面事实与结构化结论，供别的 AI 自己分析；
    - 不含「感情/财运/事业/学业」等通俗转译（本项目已从解读层移除，天然不出现）；
    - 结论严格带 calcRefs（可回推盘面字段）与规则来源，可追溯。
    """
    interp = session.interpretation
    trace = evidence_trace_json(session) if interp else {}

    return {
        "kind": "mingli-xuanshi/divination-export",
        "version": 1,
        "meta": {
            "sessionId": session.id,
            "systemId": session.systemId,
            "engine": session.calculation.engine,
            "engineVersion": session.calculation.engineVersion,
            "createdAt": session.createdAt,
            "question": session.question.text,
            "interpreter": interp.interpreter if interp else None,
        },
        "inputSnapshot": session.calculation.inputSnapshot,
        "calculation": session.calculation.data,          # 盘面原始数据（确定性引擎输出）
        "conclusions": trace.get("conclusions", []),       # 结构化结论 + calcRefs 追溯
        "uncertainty": interp.uncertainty if interp else [],
        "limitations": interp.limitations if interp else [],
        "disclaimer": DISCLAIMER,
        "_note": "本文件为确定性排盘的中性数据导出，供第三方 AI 自主分析。"
                 "不含吉凶综合结论与通俗转译；体系局限见 limitations。",
    }


def _summarize_calc(calc: CalculationResult) -> str:
    import json as _json
    return _json.dumps(calc.data, ensure_ascii=False)[:2000]
