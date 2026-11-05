"""LLM 解释插槽 —— 可选，配置 API Key（/settings 页或 ANTHROPIC_API_KEY）后启用。

约束（不可绕过）：
- LLM 只接收 CalculationResult.data + 检索到的规则条目 + 输出格式要求；
  不接收"自由发挥权"。输出必须符合 Conclusion 结构（claim/reasoning/rules/calcRefs），
  经 verify_conclusion() 校验——引用悬空即整体拒绝。
- 系统提示词注入 xuan-shu 铁律：不用必/定/绝、事实解读分离、标注体系局限。
- 未配置 key 或调用失败时自动回落 rule-engine，报告注明解释器类型。

本平台只走远程 API（Anthropic Messages API），不运行任何本地部署模型。
"""
from __future__ import annotations

import json

from mingli.core import llm_config
from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalcRef,
    CalculationResult,
    Conclusion,
    InterpretationResult,
    Question,
    RuleRef,
)

SYSTEM_PROMPT = """你是命理玄师（Mingli XuanShi）的解释引擎。你收到的输入是：
1. 一个术数体系的确定性计算结果（JSON）——这是唯一的事实依据；
2. 该体系的规则库条目（含来源等级 S/A/B/C/D）。

铁律：
- 只基于计算结果与规则条目解读，不得重新计算任何术数事实，不得引入规则库之外的断律。
- 每条结论必须给出：推理链（逐步）、所用规则 id、所依据的计算字段路径（calcRefs）。
- 不用"必/定/绝"式断言；吉凶倾向用"多有/恐/倾向"等体系内规则语言。
- 规则冲突时不调和：并列展示各流派说法并说明本次采用哪个及原因。
- 输出严格 JSON：{"summary": str, "conclusions": [{"claim","reasoning":[str],"rules":[ruleId],"calcRefs":[path]}], "uncertainty": [str], "limitations": [str]}
"""


def _call_llm(system_prompt: str, user_content: str, max_tokens: int = 3000,
              model: str | None = None, json_mode: bool = False) -> str:
    """Provider 感知的统一 LLM 调用：anthropic 原生 / OpenAI 兼容（DeepSeek 等）。

    返回首条文本；失败抛 RuntimeError 由上层处理。
    """
    if not llm_available():
        raise RuntimeError("未配置 API Key：请到 /settings 页填写，或设置 ANTHROPIC_API_KEY 环境变量")
    use_model = model or llm_config.model()
    p = llm_config.provider()

    if p == "anthropic":
        try:
            import anthropic  # 延迟导入：未安装且不需要时不报错
        except ImportError as e:
            raise RuntimeError("缺少 anthropic SDK：pip install anthropic") from e
        client = anthropic.Anthropic(api_key=llm_config.api_key())
        resp = client.messages.create(
            model=use_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        block = next((b for b in resp.content if getattr(b, "type", "") == "text"), None)
        text_out = block.text if block else None  # type: ignore[union-attr]
        if not text_out:
            raise RuntimeError("Anthropic 端点返回空文本")
        return text_out

    # openai-compatible（deepseek / 自定义 base_url 等）
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("缺少 openai SDK：pip install openai") from e
    base = llm_config.base_url() or None
    oai_client = OpenAI(api_key=llm_config.api_key(), base_url=base, timeout=45.0, max_retries=0)
    oai_resp = oai_client.chat.completions.create(
        model=use_model,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}} if p == "mimo" else None,
        response_format={"type": "json_object"} if json_mode else {"type": "text"},
        temperature=0.2 if p == "mimo" else None,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    choice = oai_resp.choices[0] if oai_resp.choices else None
    text = choice.message.content if choice and choice.message else None
    if not text:
        raise RuntimeError("OpenAI 兼容端点返回空文本")
    return text


def llm_available() -> bool:
    """是否已配置有效的远程 API Key（页面保存或环境变量）。本项目无本地部署模型。"""
    return llm_config.has_key()


def interpret_with_llm(
    system_id: str,
    calculation: CalculationResult,
    question: Question | None,
    knowledge: KnowledgeBase,
    model: str | None = None,
) -> InterpretationResult:
    """调用 Anthropic API 生成解释；失败抛 RuntimeError 由上层回落规则引擎。"""
    if not llm_available():
        raise RuntimeError("未配置 API Key：请到 /settings 页填写，或设置 ANTHROPIC_API_KEY 环境变量")
    rules = knowledge.for_system(system_id)
    rules_payload = [
        {"id": r.id, "tradition": r.tradition, "statement": r.statement,
         "sourceLevel": r.sourceLevel, "disputes": r.disputes}
        for r in rules
    ]
    user_content = json.dumps({
        "systemId": system_id,
        "question": question.text if question else None,
        "questionCategory": question.category if question else None,
        "calculation": calculation.data,
        "rules": rules_payload,
    }, ensure_ascii=False)

    text = _call_llm(SYSTEM_PROMPT, user_content, max_tokens=4000, model=model)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(f"LLM 输出不是合法 JSON: {e}") from e

    conclusions: list[Conclusion] = []
    all_rule_ids = {r.id: r for r in rules}
    for c in payload.get("conclusions", []):
        rr: list[RuleRef] = []
        for rid in c.get("rules", []):
            match = all_rule_ids.get(rid)
            if match is None:
                raise RuntimeError(f"LLM 引用了未知规则: {rid}")
            rr.append(RuleRef(ruleId=match.id, source=match.source, sourceLevel=match.sourceLevel))
        conclusions.append(Conclusion(
            claim=c["claim"],
            reasoning=list(c.get("reasoning", [])),
            rules=rr,
            calcRefs=[CalcRef(path=p) for p in c.get("calcRefs", [])],
        ))

    result = InterpretationResult(
        systemId=system_id,
        summary=payload.get("summary", ""),
        conclusions=conclusions,
        uncertainty=payload.get("uncertainty", []),
        limitations=payload.get("limitations", []),
        interpreter="llm",
        model=model or llm_config.model(),
    )
    from mingli.core.interpret.rules import verify_conclusion
    if not conclusions or any(verify_conclusion(c, calculation) for c in conclusions):
        raise RuntimeError("LLM 结论未通过证据校验")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 综合分析层（第二层 · Dify 式「知识检索 + LLM 综合」）
#
# 输入：同一问题的多体系结论（已各自独立解读）+ 用户问题 + 检索到的规则。
# 输出：三层 —— ① 各体系对本问题的针对性回答 ② 分歧如何理解 ③ 一条可验证建议。
#
# 铁律（沿用项目红线，锁死在 prompt 与返回校验）：
# - LLM 只消费「结论文本 + 规则」，绝不重新计算任何术数事实、绝不引入盘外断律；
# - 绝不产出综合概率 / 百分比 / 命中率（对标 comparison 红线，测试也会锁）；
# - symbolic（象征/自省体系）只作视角提醒，不与吉凶并论；
# - 无 key / 调用失败 → 抛 RuntimeError，由上层优雅回落。
# ═══════════════════════════════════════════════════════════════════════════

SYNTHESIS_PROMPT = """你是命理玄师（Mingli XuanShi）的「综合分析层」。输入包含：
1. 用户问题；
2. 多个术数体系各自独立的确定性结论（JSON，每体系的 claim + polarity + 结论编号）；
3. 按用户问题检索出的相关规则条目（含来源等级 S/A/B/C/D）。

你的任务是对同一问题做「跨体系综合解读」，输出严格三层 JSON：
{
  "responses": [
    {"systemId": "...", "systemName": "...", "answer": "该体系对你这个问题的针对性回答（1-3句，只基于该体系已给出的结论，不得扩展）"}
  ],
  "divergence": ["分歧1：...（说明哪些体系方向相反，以及为何可能出现这种分歧——理论前提/输入结构不同；不得强行中和为'吉凶参半'）"],
  "action": "一条可验证的行动建议（具体到可设实验记录、可对答案的颗粒度，例如'三个月内观察某事件是否发生/某结果如何'），并说明依据哪个/些体系的结论",
  "notes": ["综合建议与红线提醒，1-2句"]
}

铁律：
- responses 里的 answer 只能转述对应体系已给出的结论，不得补充、夸大、新增吉凶断语；不重新计算任何术数。
- 不创建任何综合评分、百分比、概率、命中率。只用文字描述方向趋同或相左。
- symbolic 体系（塔罗/易经）只提供视角与提醒，明确标注其不参与吉凶并论。
- divergence 只描述分歧与成因，不强行调和。
- action 必须可验证（有明确观察窗口与判据），这是这个平台的实验价值所在。
- 输出必须严格是合法 JSON，不附加任何解释文字。
"""


def synthesize_with_llm(
    question_text: str,
    classification: dict | None,
    runs_payload: list[dict],
    rules_payload: list[dict],
    model: str | None = None,
) -> dict:
    """多体系综合（第二层）。输入均为可序列化 dict；返回三层结构 dict。

    失败抛 RuntimeError，由上层回落为「确定性对照 + 提示未启用综合分析」。
    """
    if not llm_available():
        raise RuntimeError("未配置 API Key：请到 /settings 页填写，或设置 ANTHROPIC_API_KEY 环境变量")
    user_content = json.dumps({
        "question": question_text,
        "classification": classification or {},
        "runs": runs_payload,
        "rules": rules_payload,
    }, ensure_ascii=False)

    text = _call_llm(SYNTHESIS_PROMPT, user_content, max_tokens=3000, model=model)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(f"综合层 LLM 输出不是合法 JSON: {e}") from e

    _sanitize_synthesis(payload)
    return payload


def _sanitize_synthesis(payload: dict) -> None:
    """校验并清洗综合输出：锁死红线——不得产出百分比/综合分/命中率。"""
    import re

    text = json.dumps(payload, ensure_ascii=False)
    m = re.search(r"\d+(\.\d+)?\s*%", text)
    if m:
        raise RuntimeError(f"综合层输出含百分比，违反红线: {m.group(0)}")
    # 结构兜底
    if not isinstance(payload.get("responses"), list):
        raise RuntimeError("综合层输出缺 responses 列表")
    if not isinstance(payload.get("action"), str) or not payload["action"].strip():
        raise RuntimeError("综合层输出缺 action")
    payload.setdefault("divergence", [])
    payload.setdefault("notes", [])


# ═══════════════════════════════════════════════════════════════════════════
# 问事推荐建议（/ask 页 · 可选插槽）
#
# 目的：结合用户问题与分类结果，给出「先开哪个体系、问题怎么表达才可验证」
# 的行动建议——不制造吉凶断语，只帮助用户把问题问得更清晰、更适合起局。
# 无 key / 失败抛 RuntimeError，由上层优雅降级（不显示建议段）。
# ═══════════════════════════════════════════════════════════════════════════

RECOMMEND_PROMPT = """你是命理玄师（Mingli XuanShi）的「问事导航」。输入：
1. 用户的问题；
2. 问题分类（category / horizon / 敏感域）；
3. 推荐起局的体系列表（名称 + 匹配理由）。

你的任务：给用户一段「如何开启这局」的建议，输出严格 JSON：
{
  "advice": "针对这个问题的总体建议（1-3句：先开哪个体系、为什么；怎样把问题表达得更适合起局——要具体到可验证、可对比，比如把'我该不该换工作'改成'三个月内是否收到新 offer，我该不该接受'）",
  "tips": ["1-3 条补充分句"]
}

铁律：
- 这不是算命，是"如何提问才可验证"的导航：建议围绕把问题变清晰、可设实验记录。
- 不给出任何吉凶、成败、好坏判断；不声称哪个体系"更准"（它们只是匹配维度不同）。
- 若问题涉及生死危机或敏感域，明确建议优先寻求现实帮助，不建议起局。
- 输出必须严格合法 JSON，不含解释文字。
"""


def recommend_with_llm(
    question_text: str,
    classification: dict | None,
    recommendations: list[dict],
    model: str | None = None,
) -> dict:
    """对推荐页生成"开局方式建议"。返回 {"advice": str, "tips": [str]}。

    失败抛 RuntimeError，上层降级（不显示建议段）。
    """
    if not llm_available():
        raise RuntimeError("未配置 API Key：请到 /settings 页填写，或设置 ANTHROPIC_API_KEY 环境变量")
    user_content = json.dumps({
        "question": question_text,
        "classification": classification or {},
        "recommendations": recommendations,
    }, ensure_ascii=False)

    text = _call_llm(RECOMMEND_PROMPT, user_content, max_tokens=1200, model=model)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(f"推荐建议 LLM 输出不是合法 JSON: {e}") from e

    if not isinstance(payload.get("advice"), str) or not payload["advice"].strip():
        raise RuntimeError("推荐建议缺 advice")
    payload.setdefault("tips", [])
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# 玄师对话（第二空间 · 基于术数 Session 的上下文增强讨论）
#
# 与单次解读的区别：多轮、可追问、携带完整 Session Context（计算结果 + 结构化
# 解释 + 规则引用）。铁律不变且锁死在 prompt：
# - 只消费已产生的确定性计算结果与规则库，绝不重新计算任何术数事实；
# - 上下文中没有的计算/规则 → 明确回答"当前信息不足以支持这个判断"；
# - 不产出百分比/概率/综合分；吉凶用体系内限定语言；
# - 敏感域（医疗/投资/法律等）不给行动性断言，提示现实帮助。
# 对话历史只追加消息，永不修改 CalculationResult——计算层不可被对话污染。
# ═══════════════════════════════════════════════════════════════════════════

_STYLE_DIRECTIVE = {
    "concise": "行文简洁：每答不超过 5 句，先给要点再给一句依据。",
    "standard": "行文标准：观点 + 依据 + 一处不确定性提醒。",
    "research": "行文深入：展开推理链，主动列出流派分歧与反例视角，结尾给出可验证的观察建议。",
}

CHAT_SYSTEM_PROMPT = """你是命理玄师（Mingli XuanShi）的「玄师对话」引擎。用户正在围绕
一个已经生成的术数结果与你讨论。你的 Context 包含：
1. 用户原始问题与本次使用的术数体系；
2. 该体系的确定性计算结果（JSON）——这是唯一的事实依据，由引擎算出，你绝不能改写或重算；
3. 规则库对该结果的既有结构化解释（含推理链、规则引用、来源等级）。

铁律：
- 只基于上述 Context 解释、讨论、分析。Context 中没有的计算事实或规则，明确说
  「当前信息不足以支持这个判断」，绝不编造盘面细节或引入规则库之外的断律。
- 用户问的若需要新的起局/排盘（如换一个问题问新卦），告知需回「术数生成」重新起局，
  而不是用旧盘硬答。
- 不用「必/定/绝」式断言；吉凶倾向用「多有/恐/倾向」等体系内规则语言。
- 不产出任何概率、百分比、命中率或综合评分。
- 涉及医疗、投资、法律等重大现实决策时：说明术数不构成专业建议，建议咨询现实专业人士。
- 回答用中文；直接回应问题，不重复贴大段原始数据（用户可见左侧研究对象面板）。
- 面向普通读者先用白话回答，术语出现时在同句解释；明确区分反思建议和规则判断。
- 塔罗/易经不得断言用户现况或他人心态，不把“未来”牌位当作现实趋势。用自问方式展开象征。
{style_directive}
"""


def chat_with_llm(
    context_payload: dict,
    history: list[dict],
    user_message: str,
    model: str | None = None,
) -> str:
    """玄师对话：携带 Session Context + 历史 + 新消息，返回助手回复文本。

    context_payload 由 Web 层组装（question/system/calculation/interpretation/rules），
    本函数不做任何术数计算——它只是把已有事实与规则交给 LLM 讨论。
    失败抛 RuntimeError，上层降级为提示。
    """
    if not llm_available():
        raise RuntimeError("未配置 API Key：请到 /settings 页填写，或设置 ANTHROPIC_API_KEY 环境变量")

    system_prompt = CHAT_SYSTEM_PROMPT.replace(
        "{style_directive}", _STYLE_DIRECTIVE.get(llm_config.style(), _STYLE_DIRECTIVE["standard"]))

    # 首条 user 消息 = 完整 Context（结构化 JSON）；后续轮次是纯文本对话
    context_json = json.dumps(context_payload, ensure_ascii=False)
    messages: list[dict[str, str]] = [{"role": "user", "content": context_json}]
    for h in history:
        role = h.get("role")
        text = h.get("text", "")
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_message})

    use_model = model or llm_config.model()
    p = llm_config.provider()

    if p == "anthropic":
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError("缺少 anthropic SDK：pip install anthropic") from e
        client = anthropic.Anthropic(api_key=llm_config.api_key())
        resp = client.messages.create(
            model=use_model, max_tokens=3000,
            system=system_prompt,
            messages=messages,  # type: ignore[arg-type]
        )
        block = next((b for b in resp.content if getattr(b, "type", "") == "text"), None)
        text_out = block.text if block else None  # type: ignore[union-attr]
        if not text_out:
            raise RuntimeError("Anthropic 端点返回空文本")
        return text_out

    # openai-compatible
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("缺少 openai SDK：pip install openai") from e
    oai_client = OpenAI(api_key=llm_config.api_key(), base_url=llm_config.base_url() or None,
                        timeout=45.0, max_retries=0)
    oai_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}, *messages]
    oai_resp = oai_client.chat.completions.create(
        model=use_model, max_tokens=3000,
        extra_body={"thinking": {"type": "disabled"}} if p == "mimo" else None,
        messages=oai_messages)  # type: ignore[arg-type]
    choice = oai_resp.choices[0] if oai_resp.choices else None
    text_out = choice.message.content if choice and choice.message else None
    if not text_out:
        raise RuntimeError("OpenAI 兼容端点返回空文本")
    return text_out
