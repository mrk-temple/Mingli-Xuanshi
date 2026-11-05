"""命理玄师 Web 应用 —— FastAPI + Jinja2 SSR ·「观星・玄师」界面。

三空间信息架构（2026-08 重构 · design.md 精神不变）：
    /                       首页 —— 三个核心入口（生成 / 对话 / 记录研究）
    /generate               ① 术数生成：按输入方式分组的体系选择 → 起局表单
    /generate/{sid}         具体体系生成页（原 /run/{sid}）
    /session/{sid}          术数结果页：Layer1 原始结果 + Layer2 结构解释 + [与玄师讨论]
    /chat                   ② 玄师对话：讨论串列表
    /chat/{tid}             对话页（左侧研究对象 / 中间聊天 / 右侧证据）
    /research               ③ 记录与研究：我的记录 / 预测实验室 / 学习空间
    /settings               ⚙ 设置中心（AI 接入 / 外观 / 模型行为 / 数据）

兼容路由（旧链接 302 → 新空间）：
    /ask /recommend → /generate        /history /lab /learn → /research
    /run/{sid} → /generate/{sid}       /systems → /generate

约束（铁律程序化，未变）：
    - calculate() 是唯一计算入口（确定性引擎），interpret() 只消费计算结果+规则库
    - 报告渲染强制"体系局限 + 免责"，证据链悬空引用即拒绝
    - 对照引擎（comparison.py）物理上不产出综合概率/分数
"""
from __future__ import annotations

import datetime
import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from mingli.core import llm_config
from mingli.core.comparison import ComparisonRun, build_comparison
from mingli.core.experiment import evaluate, mark_no_outcome
from mingli.core.interpret.llm import (
    chat_with_llm,
    llm_available,
    recommend_with_llm,
    synthesize_with_llm,
)
from mingli.core.knowledge import load_knowledge
from mingli.core.models import (
    ChartProfile,
    ChatThread,
    ChatTurn,
    DivinationSession,
    Experiment,
    Question,
)
from mingli.core.reading import (
    GLOSSARY,
    SYSTEM_INTROS,
    display_guide,
    enrich_with_llm,
    offline_guide,
    tradition_notes,
)
from mingli.core.report import evidence_trace_json, export_ai_json, render_markdown
from mingli.core.router import QuestionRouter, classify_question
from mingli.core.safety import DISCLAIMER, assess
from mingli.core.session import ChatStore, ExperimentStore, ProfileStore, SessionStore
from mingli.systems.base import InputError
from mingli.systems.bootstrap import get_registry

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_DIR = os.path.join(_APP_DIR, "templates")
_STATIC_DIR = os.path.join(_APP_DIR, "static")

app = FastAPI(title="命理玄师 Mingli XuanShi", version="0.4.0")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
templates.env.globals["reading_intros"] = SYSTEM_INTROS


def _pretty_json(obj) -> str:
    """JSON 展示用：保留中文（Jinja 内置 tojson 默认把中文转成 unicode 转义，可读性差）；
    返回 Markup 以跳过 autoescape，保证 JSON 里的引号/符号原样可读。"""
    import json

    from markupsafe import Markup
    return Markup(json.dumps(obj, ensure_ascii=False, indent=2))


templates.env.filters["pretty_json"] = _pretty_json

_registry = get_registry()
_knowledge = load_knowledge()
_sessions = SessionStore()
_experiments = ExperimentStore()
_profiles = ProfileStore()
_chats = ChatStore()

# 术数生成空间的分组（design.md §2 输入模型；yijing=义理问答单列）
_GENERATE_GROUPS: list[dict] = [
    {"key": "natal", "name": "命盘类", "en": "NATAL",
     "desc": "按出生时刻排出传统符号结构；阶段划分不证明现实吉凶",
     "cats": ["natal"]},
    {"key": "moment", "name": "问事 · 起课类", "en": "HORARY",
     "desc": "带着具体问题查看传统规则的观察角度，再核对现实信息",
     "cats": ["moment", "knowledge", "decision-framework"]},
    {"key": "randomized", "name": "随机抽取类", "en": "RANDOMIZED",
     "desc": "随机产生符号，用作反思问题与选择的线索",
     "cats": []},   # 由 randomized 标签单独归组
]


def _group_of(provider) -> str:
    # 优先级：命盘 > 问事起课 > 纯随机抽取（六爻/梅花虽可随机起卦，但定位是一事一占）
    for g in _GENERATE_GROUPS[:2]:
        if any(c in provider.category for c in g["cats"]):
            return g["key"]
    if "randomized" in provider.category:
        return "randomized"
    return "moment"


def _router() -> QuestionRouter:
    return QuestionRouter(_registry.active_providers())


def _settings() -> dict:
    """解释器当前模式：/settings 页保存的优先，否则 MINGLI_INTERPRETER，否则 rule-engine。"""
    return {"interpreter": llm_config.interpreter()}


def _run_interpretation(provider, calc, question) -> tuple:
    """规则结论始终独立生成，LLM 仅生成白话展示层。"""
    mode = _settings()["interpreter"]
    interp = provider.interpret(calc, question, _knowledge)
    interp.readerGuide = offline_guide(calc, question, interp)
    verdict = assess(question.text)
    if mode == "llm" and llm_available() and not (verdict.crisis or verdict.sensitive):
        try:
            interp.readerGuide = enrich_with_llm(calc, question, interp, _knowledge)
            interp.interpreter = "llm"
            interp.model = llm_config.model()
        except Exception:  # noqa: BLE001 - 不向页面泄露供应商异常或凭据
            interp.presentationNote = "AI 白话解读暂不可用或未通过校验，已使用离线阅读指引。计算结果与规则依据仍可查看。"
    elif mode == "llm" and not llm_available():
        interp.presentationNote = "未配置可用模型，当前显示离线阅读指引。"
    return interp, interp.presentationNote


# ---------------------------------------------------------------------------
# 日盘信息（今日干支/月令/节气——确定性引擎，非玄学声明）
# ---------------------------------------------------------------------------

_ZODIAC = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]


def _today_info() -> dict:
    from mingli.engines.loader import load_engine
    common = load_engine("common")
    today = datetime.date.today()
    y, m, d = today.year, today.month, today.day
    dgan, dzhi = common.day_ganzhi(y, m, d)
    jd = float(common.jdn(y, m, d)) + 0.5
    ygan, yzhi, mgan, mzhi = common.year_month_ganzhi(jd)
    info = {
        "solar": f"{y}-{m:02d}-{d:02d}",
        "ganzhi": f"{common.TIAN_GAN[ygan]}{common.DI_ZHI[yzhi]}年 {common.TIAN_GAN[mgan]}{common.DI_ZHI[mzhi]}月 {common.TIAN_GAN[dgan]}{common.DI_ZHI[dzhi]}日",
        "yueling": f"{common.DI_ZHI[mzhi]}月",
        "shengri": _ZODIAC[yzhi],
        "jieqi": "",
        "lunar": "",
    }
    try:
        from lunar_python import Solar
        ln = Solar.fromYmd(y, m, d).getLunar()
        info["jieqi"] = ln.getJieQi() or ""
        info["lunar"] = f"农历{ln.getMonthInChinese()}月{ln.getDayInChinese()}"
    except Exception:
        pass
    return info


def _workbench_stats() -> dict:
    exps = _experiments.list_all()
    return {
        "session_count": len(_sessions.list_all()),
        "pending_count": sum(1 for e in exps if e.status == "pending"),
        "stats": _experiments.stats(),
        "active_count": len(_registry.active_providers()),
        "recent_sessions": _sessions.list_all()[:5],
        "chat_count": len(_chats.list_all()),
    }


# ---------------------------------------------------------------------------
# 首页 —— 克制三入口：生成 / 对话 / 研究记录
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {
        **_workbench_stats(),
        "today": _today_info(),
    })


# ---------------------------------------------------------------------------
# ① 术数生成
# ---------------------------------------------------------------------------

@app.get("/generate", response_class=HTMLResponse)
async def generate_home(request: Request):
    rows = _registry.describe_all()
    runnable = [r for r in rows if r["runnable"]]
    providers_by_id = {p.id: p for p in _registry.active_providers()}
    groups: dict[str, list[dict]] = {g["key"]: [] for g in _GENERATE_GROUPS}
    for r in runnable:
        p = providers_by_id.get(r["id"])
        if p is not None:
            groups.setdefault(_group_of(p), []).append(r)
    planned = [r for r in rows if not r["runnable"]]
    return templates.TemplateResponse(request, "generate.html", {
        "groups": [
            {**g, "rows": groups.get(g["key"], [])} for g in _GENERATE_GROUPS],
        "planned": planned,
        "active_count": len(_registry.active_providers()),
    })


@app.get("/systems", response_class=HTMLResponse)
async def systems_page_redirect():
    return RedirectResponse("/generate", status_code=302)


@app.get("/run/{system_id}", response_class=HTMLResponse)
async def run_form_redirect(system_id: str, request: Request):
    # 兼容旧链接：转发查询串（profile/q 预填不丢）
    qs = request.url.query
    target = f"/generate/{system_id}" + (f"?{qs}" if qs else "")
    return RedirectResponse(target, status_code=302)


def _mode_options(schema: dict) -> list[dict]:
    for f in schema.get("fields", []):
        if f.get("name") == "mode":
            return [{"value": o, "label": o} for o in f.get("options", [])]
    return []


def _profile_prefill(profile_id: str) -> dict | None:
    try:
        p = _profiles.load(profile_id)
    except FileNotFoundError:
        return None
    return {"year": p.year, "month": p.month, "day": p.day,
            "hour": p.hour, "gender": p.gender, "longitude": p.longitude}


@app.get("/generate/{system_id}", response_class=HTMLResponse)
async def run_form(request: Request, system_id: str, q: str = "", profile: str = ""):
    try:
        provider = _registry.get(system_id)
    except KeyError:
        return RedirectResponse("/generate", status_code=302)
    schema = provider.input_schema()
    prefill = _profile_prefill(profile) if profile else None
    return templates.TemplateResponse(request, "run.html", {
        "provider": provider, "schema": schema["fields"], "q": q,
        "mode_options": _mode_options(schema),
        "profiles": _profiles.list_all(),
        "is_natal": "natal" in provider.category,
        "prefill": prefill or {},
    })


@app.post("/generate/{system_id}")
async def run_submit(request: Request, system_id: str, q: str = Form(default="")):
    form = await request.form()
    try:
        provider = _registry.get(system_id)
    except KeyError:
        return RedirectResponse("/generate", status_code=302)

    input_data = _collect_input(provider.id, form)
    errs = provider.validate_input(input_data)
    if errs:
        schema = provider.input_schema()
        return templates.TemplateResponse(request, "run.html", {
            "provider": provider, "schema": schema["fields"], "q": q,
            "mode_options": _mode_options(schema), "errors": errs,
            "profiles": _profiles.list_all(),
            "is_natal": "natal" in provider.category,
            "prefill": _form_prefill(provider.id, form),
        }, status_code=400)

    try:
        calc = provider.calculate(input_data)
    except InputError as e:
        # validate_input 漏拦的非法输入：如实回表单报错，绝不裸 500
        schema = provider.input_schema()
        return templates.TemplateResponse(request, "run.html", {
            "provider": provider, "schema": schema["fields"], "q": q,
            "mode_options": _mode_options(schema), "errors": [str(e)],
            "profiles": _profiles.list_all(),
            "is_natal": "natal" in provider.category,
            "prefill": _form_prefill(provider.id, form),
        }, status_code=400)

    question = Question(text=q or "(未提供问题)",
                        category=classify_question(q).category if q else "other")
    interp, fallback_note = await run_in_threadpool(_run_interpretation, provider, calc, question)

    session = DivinationSession(question=question, systemId=system_id,
                                calculation=calc, interpretation=interp)
    disclaimer = DISCLAIMER
    safety = assess(q)
    if safety.notices:
        disclaimer += " " + " ".join(safety.notices)
    session.disclaimer = disclaimer
    _sessions.save(session)
    return RedirectResponse(f"/session/{session.id}", status_code=303)


# 兼容旧 POST /run/{sid}
@app.post("/run/{system_id}")
async def run_submit_compat(request: Request, system_id: str, q: str = Form(default="")):
    return await run_submit(request, system_id, q)


def _collect_input(system_id: str, form) -> dict:
    """表单 → Provider 输入 dict。各体系的字段名约定见各自 input_schema。"""
    data: dict = {}
    g = form.get

    if system_id == "bazi":
        data.update(year=_int(g("year")), month=_int(g("month")), day=_int(g("day")),
                    hour=_int(g("hour")) if g("hour") else None,
                    gender=g("gender") or None)
        if g("longitude"):
            data["longitude"] = float(g("longitude"))
    elif system_id == "liuyao":
        mode = g("mode") or "random"
        data["mode"] = mode
        if mode == "coins":
            data["coins"] = _int_list(g("coins"))
        elif mode == "numbers":
            data["numbers"] = _int_list(g("numbers"))
        elif mode == "time":
            data["timeInput"] = _int_list(g("timeInput"))
        elif mode == "random":
            data["seed"] = _int_or_none(g("seed"))
    elif system_id in ("meihua", "xiaoliuren"):
        mode = g("mode") or ("numbers" if system_id == "xiaoliuren" else "solar")
        data["mode"] = mode
        key = {"numbers": "numbers", "lunar": "lunar", "solar": "solar"}[mode]
        vals = _int_list(g(key))
        data[key] = vals if vals else None
    elif system_id == "daliuren":
        mode = g("mode") or "datetime"
        data["mode"] = mode
        if mode == "datetime":
            data["datetimeInput"] = _int_list(g("datetimeInput"))
        else:
            data["dayGanZhi"] = g("dayGanZhi")
            data["hourZhi"] = g("hourZhi")
            data["yueJiangZhi"] = g("yueJiangZhi")
    elif system_id == "tarot":
        data["spread"] = g("spread") or "three"
        seed = _int_or_none(g("seed"))
        if seed is not None:
            data["seed"] = seed
        data["noReversals"] = bool(g("noReversals"))
    elif system_id == "yijing":
        if g("guaName"):
            data["guaName"] = g("guaName")
    return {k: v for k, v in data.items() if v is not None}


def _form_prefill(system_id: str, form) -> dict:
    """错误回显时从已提交表单取值，避免用户重输（与 _collect_input 同构）。"""
    return _collect_input(system_id, form)


def _int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _int_or_none(v):
    return _int(v)


def _int_list(v) -> list[int]:
    if not v:
        return []
    parts = str(v).replace(",", " ").replace("，", " ").split()
    return [_n for p in parts if (_n := _int(p)) is not None]


# ---------------------------------------------------------------------------
# 术数结果页（Layer 1 原始结果 / Layer 2 结构解释 / [与玄师讨论] 入口）
# ---------------------------------------------------------------------------

@app.get("/session/{session_id}", response_class=HTMLResponse)
async def session_page(request: Request, session_id: str):
    try:
        session = _sessions.load(session_id)
    except FileNotFoundError:
        return RedirectResponse("/research", status_code=302)
    md = ""
    error = None
    try:
        md = render_markdown(session)
    except Exception as e:  # noqa: BLE001 - 校验失败如实展示
        error = str(e)
    trace = evidence_trace_json(session) if session.interpretation and not error else {}
    linked = [e for e in _experiments.list_all() if e.sessionId == session_id]
    threads = _chats.for_session(session_id)
    return templates.TemplateResponse(request, "session.html", {
        "s": session, "md": md, "trace": trace, "report_error": error,
        "disclaimer": session.disclaimer or DISCLAIMER,
        "linked_experiments": linked, "threads": threads,
        "llm_ready": llm_available(),
        "guide": display_guide(session.calculation, session.question, session.interpretation)
                 if session.interpretation and not error else None,
        "glossary": GLOSSARY.get(session.systemId, []),
        "traditions": tradition_notes(session.systemId, _knowledge),
    })


@app.get("/session/{session_id}/report.md")
async def session_report_md(session_id: str):
    from fastapi.responses import PlainTextResponse
    session = _sessions.load(session_id)
    try:
        return PlainTextResponse(render_markdown(session), media_type="text/markdown; charset=utf-8")
    except Exception as e:  # noqa: BLE001
        return PlainTextResponse(f"报告生成失败：{e}", media_type="text/plain; charset=utf-8")


@app.get("/session/{session_id}/export.ai.json")
async def session_export_ai(session_id: str):
    """盘局导出（机器可读）——供第三方 AI 自主分析的中性数据。"""
    try:
        session = _sessions.load(session_id)
    except FileNotFoundError:
        return RedirectResponse("/research", status_code=302)
    try:
        payload = export_ai_json(session)
    except Exception as e:  # noqa: BLE001 - 导出失败如实提示
        return JSONResponse({"error": f"导出失败：{e}"}, status_code=500)
    return JSONResponse(payload,
                        headers={"Content-Disposition": f'attachment; filename="{session_id}.export.ai.json"'})


@app.get("/session/{session_id}/report", response_class=HTMLResponse)
async def session_report_print(request: Request, session_id: str):
    """盘局导出（人读）——可打印报告页。"""
    try:
        session = _sessions.load(session_id)
    except FileNotFoundError:
        return RedirectResponse("/research", status_code=302)
    md = ""
    error = None
    try:
        md = render_markdown(session)
    except Exception as e:  # noqa: BLE001
        error = str(e)
    return templates.TemplateResponse(request, "report_print.html", {
        "s": session, "md": md, "report_error": error,
        "disclaimer": session.disclaimer or DISCLAIMER,
    })


@app.post("/session/{session_id}/tags")
async def session_tags(request: Request, session_id: str,
                       tags: str = Form(""), favorite: str = Form("")):
    """记录元数据：标签（逗号分隔）与收藏。"""
    try:
        s = _sessions.load(session_id)
    except FileNotFoundError:
        return RedirectResponse("/research", status_code=302)
    s.tags = [t.strip() for t in tags.split(",") if t.strip()]
    s.favorite = bool(favorite)
    _sessions.save(s)
    return RedirectResponse(f"/session/{session_id}", status_code=303)


# ---------------------------------------------------------------------------
# ② 玄师对话
# ---------------------------------------------------------------------------

def _chat_context(session) -> dict:
    """组装玄师对话 Context：问题 + 体系 + 计算结果 + 结构化解释 + 规则引用。

    只搬运已有事实与规则，不做任何计算——这是「AI 不脑算」铁律的数据边界。
    """
    interp = session.interpretation
    conclusions_payload = []
    if interp:
        conclusions_payload = [{
            "claim": c.claim,
            "reasoning": c.reasoning,
            "rules": [{"ruleId": rr.ruleId, "sourceLevel": rr.sourceLevel} for rr in c.rules],
            "calcRefs": [ref.path for ref in c.calcRefs],
            "polarity": c.polarity,
        } for c in interp.conclusions]
    return {
        "sessionId": session.id,
        "systemId": session.systemId,
        "question": session.question.text,
        "questionCategory": session.question.category,
        "inputSnapshot": session.calculation.inputSnapshot,
        "calculation": session.calculation.data,
        "interpretation": {
            "summary": interp.summary if interp else None,
            "conclusions": conclusions_payload,
            "uncertainty": interp.uncertainty if interp else [],
            "limitations": interp.limitations if interp else [],
            "interpreter": interp.interpreter if interp else None,
        } if interp else None,
        "disclaimerBasis": "以上 calculation 为确定性引擎输出的事实层；interpretation 为规则库解读。",
    }


@app.get("/chat", response_class=HTMLResponse)
async def chat_index(request: Request):
    threads = _chats.list_all()
    enriched = []
    for t in threads[:50]:
        try:
            s = _sessions.load(t.sessionId)
            sys_name, q_text = s.systemId, s.question.text
        except (FileNotFoundError, ValueError):
            sys_name, q_text = "?", "(盘局已删除)"
        enriched.append({"thread": t, "systemName": sys_name, "questionText": q_text})
    return templates.TemplateResponse(request, "chat.html", {
        "threads": enriched, "llm_ready": llm_available(),
    })


@app.get("/chat/new/{session_id}")
async def chat_new(request: Request, session_id: str):
    """从结果页进入：为该 session 建讨论串并跳到对话页。"""
    try:
        s = _sessions.load(session_id)
    except FileNotFoundError:
        return RedirectResponse("/research", status_code=302)
    t = ChatThread(sessionId=session_id, title=s.question.text[:24])
    _chats.save(t)
    return RedirectResponse(f"/chat/{t.id}", status_code=303)


@app.get("/chat/{thread_id}", response_class=HTMLResponse)
async def chat_page(request: Request, thread_id: str):
    try:
        t = _chats.load(thread_id)
    except FileNotFoundError:
        return RedirectResponse("/chat", status_code=302)
    try:
        s = _sessions.load(t.sessionId)
        context = _chat_context(s)
        ctx_error = None
    except (FileNotFoundError, ValueError) as e:
        context, ctx_error = None, str(e)
    trace = evidence_trace_json(s) if s.interpretation else {}
    return templates.TemplateResponse(request, "chat_detail.html", {
        "t": t, "s": s, "context": context, "ctx_error": ctx_error,
        "trace": trace, "llm_ready": llm_available(),
        "disclaimer": s.disclaimer or DISCLAIMER,
    })


@app.post("/chat/{thread_id}/send")
async def chat_send(request: Request, thread_id: str, message: str = Form(...)):
    message = message.strip()
    if not message:
        return RedirectResponse(f"/chat/{thread_id}", status_code=303)
    try:
        t = _chats.load(thread_id)
    except FileNotFoundError:
        return RedirectResponse("/chat", status_code=302)

    t.messages.append(ChatTurn(role="user", text=message))
    reply = None
    error = None
    if not llm_available():
        error = ("未配置 API Key——玄师对话需要远程大模型。请到 /settings 页配置；"
                 "确定性计算与规则解读不受影响。")
    else:
        try:
            s = _sessions.load(t.sessionId)
            rules = _knowledge.for_system(s.systemId)
            payload = _chat_context(s)
            payload["rules"] = [{
                "id": r.id, "statement": r.statement,
                "sourceLevel": r.sourceLevel, "tradition": r.tradition,
            } for r in rules]
            history = [{"role": m.role, "text": m.text} for m in t.messages]
            reply = chat_with_llm(payload, history[:-1], message)
        except Exception as e:  # noqa: BLE001 - 对话失败如实提示，不污染线程
            error = f"玄师暂时无法回应（{e}）"

    if reply is not None:
        t.messages.append(ChatTurn(role="assistant", text=reply))
    elif error and t.messages and t.messages[-1].role == "user":
        # 失败轮次以 assistant 身份记录错误说明，保持 user/assistant 交替可渲染
        t.messages.append(ChatTurn(role="assistant", text=f"[系统提示] {error}"))
    _chats.save(t)
    return RedirectResponse(f"/chat/{thread_id}", status_code=303)


@app.post("/chat/{thread_id}/delete")
async def chat_delete(request: Request, thread_id: str):
    _chats.delete(thread_id)
    return RedirectResponse("/chat", status_code=303)


# ---------------------------------------------------------------------------
# ③ 记录与研究（三 Tab：我的记录 / 预测实验室 / 学习空间）
# ---------------------------------------------------------------------------

@app.get("/research", response_class=HTMLResponse)
async def research_page(request: Request, tab: str = "", q: str = "",
                        system: str = "", fav: str = ""):
    sessions = _sessions.list_all()
    if q.strip():
        kw = q.strip().lower()
        sessions = [s for s in sessions
                    if kw in s.question.text.lower()
                    or kw in s.systemId.lower()
                    or any(kw in t.lower() for t in s.tags)]
    if system:
        sessions = [s for s in sessions if s.systemId == system]
    if fav:
        sessions = [s for s in sessions if s.favorite]
    experiments = _experiments.list_all()

    learn_blocks = []
    for row in _registry.describe_all():
        rules = _knowledge.for_system(row["id"])
        if not rules:
            continue
        level_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
        learn_blocks.append({
            "systemId": row["id"], "name": row["name"],
            "strengths": row["strengths"],
            "limitations": row.get("limitations", ""), "status": row["status"],
            "rules": sorted(rules, key=lambda r: (level_order.get(r.sourceLevel, 9), r.id)),
        })

    active_tab = tab if tab in ("records", "lab", "learn") else (
        "lab" if (experiments and not sessions) else ("learn" if not sessions else "records"))
    return templates.TemplateResponse(request, "research.html", {
        "tab": active_tab,
        "sessions": sessions,
        "experiments": experiments,
        "stats": _experiments.stats(),
        "learn_blocks": learn_blocks,
        "active_count": len(_registry.active_providers()),
        "filter_q": q, "filter_system": system, "filter_fav": fav,
        "all_system_ids": sorted({s.systemId for s in _sessions.list_all()}),
        "chat_counts": {t.sessionId: 1 for t in _chats.list_all()},
    })


@app.get("/history", response_class=HTMLResponse)
async def history_redirect():
    return RedirectResponse("/research?tab=records", status_code=302)


@app.get("/lab", response_class=HTMLResponse)
async def lab_redirect():
    return RedirectResponse("/research?tab=lab", status_code=302)


@app.get("/learn", response_class=HTMLResponse)
async def learn_redirect():
    return RedirectResponse("/research?tab=learn", status_code=302)


@app.post("/lab/new/{session_id}")
async def lab_create(request: Request, session_id: str,
                     prediction: str = Form(...),
                     window_start: str = Form(...), window_end: str = Form(...),
                     blind: bool = Form(False)):
    s = _sessions.load(session_id)
    exp = Experiment(sessionId=session_id, systemId=s.systemId,
                     questionText=s.question.text, prediction=prediction,
                     windowStart=window_start, windowEnd=window_end,
                     blind=blind)
    _experiments.save(exp)
    return RedirectResponse(f"/research/lab-detail/{exp.id}", status_code=303)


@app.get("/research/lab-detail/{exp_id}", response_class=HTMLResponse)
async def lab_detail(request: Request, exp_id: str):
    from mingli.core.experiment import VERDICT_RULES
    try:
        exp = _experiments.load(exp_id)
    except FileNotFoundError:
        return RedirectResponse("/research?tab=lab", status_code=302)
    return templates.TemplateResponse(request, "lab_detail.html", {
        "e": exp, "verdict_rules": VERDICT_RULES,
    })


@app.get("/lab/{exp_id}", response_class=HTMLResponse)
async def lab_detail_compat(request: Request, exp_id: str):
    return await lab_detail(request, exp_id)


@app.post("/research/lab-detail/{exp_id}/evaluate")
async def lab_evaluate(request: Request, exp_id: str,
                       outcome: str = Form(...),
                       hit_exact: bool = Form(False),
                       hit_direction: bool = Form(False),
                       hit_timing: bool = Form(False),
                       ambiguous: bool = Form(False)):
    exp = _experiments.load(exp_id)
    exp = evaluate(exp, outcome, hit_exact=hit_exact, hit_direction=hit_direction,
                   hit_timing=hit_timing, ambiguous=ambiguous)
    _experiments.save(exp)
    return RedirectResponse(f"/research/lab-detail/{exp_id}", status_code=303)


@app.post("/lab/{exp_id}/evaluate", response_class=HTMLResponse)
async def lab_evaluate_compat(request: Request, exp_id: str,
                              outcome: str = Form(...),
                              hit_exact: bool = Form(False),
                              hit_direction: bool = Form(False),
                              hit_timing: bool = Form(False),
                              ambiguous: bool = Form(False)):
    return await lab_evaluate(request, exp_id, outcome, hit_exact=hit_exact,
                              hit_direction=hit_direction, hit_timing=hit_timing,
                              ambiguous=ambiguous)


@app.post("/research/lab-detail/{exp_id}/no-outcome")
async def lab_no_outcome(request: Request, exp_id: str, note: str = Form(default="")):
    exp = _experiments.load(exp_id)
    exp = mark_no_outcome(exp, note)
    _experiments.save(exp)
    return RedirectResponse(f"/research/lab-detail/{exp_id}", status_code=303)


@app.post("/lab/{exp_id}/no-outcome", response_class=HTMLResponse)
async def lab_no_outcome_compat(request: Request, exp_id: str, note: str = Form(default="")):
    return await lab_no_outcome(request, exp_id, note)


# ---------------------------------------------------------------------------
# 个人命盘库（/charts）· 历法（/cal）—— 生成空间的配套工具，路由保留
# ---------------------------------------------------------------------------

def _charts_resp(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "charts.html", {
        "profiles": _profiles.list_all(),
        "error": error,
    })


@app.get("/charts", response_class=HTMLResponse)
async def charts_page(request: Request, error: str = ""):
    return _charts_resp(request, error=error)


@app.post("/charts")
async def charts_create(request: Request,
                        name: str = Form(""),
                        year: int = Form(...),
                        month: int = Form(...),
                        day: int = Form(...),
                        hour: int | None = Form(None),
                        gender: str = Form(""),
                        longitude: float | None = Form(None),
                        note: str = Form("")):
    if not 1900 <= year <= 2100 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return _charts_resp(request, error="出生日期不合法（年 1900-2100，月 1-12，日 1-31）")
    try:
        datetime.date(year, month, day)
    except ValueError:
        return _charts_resp(request, error=f"出生日期不存在：{year}-{month:02d}-{day:02d}")
    if hour is not None and not 0 <= hour <= 23:
        return _charts_resp(request, error="出生小时须为 0-23")
    if gender not in ("男", "女", ""):
        return _charts_resp(request, error="性别须为 男/女")
    p = ChartProfile(
        name=name if name.strip() else f"命盘 {year}-{month}-{day}",
        year=year, month=month, day=day,
        hour=hour, gender=gender or None, longitude=longitude,
        note=note,
    )
    _profiles.save(p)
    return RedirectResponse("/charts", status_code=303)


@app.post("/charts/{profile_id}/delete")
async def charts_delete(request: Request, profile_id: str):
    _profiles.delete(profile_id)
    return RedirectResponse("/charts", status_code=303)


@app.get("/cal", response_class=HTMLResponse)
async def cal_page(request: Request, date: str = ""):
    target = _parse_date(date) or datetime.date.today()
    days = _days_in_month(target.year, target.month)
    month_rows = [_calendar_info(target.year, target.month, d) for d in range(1, days + 1)]
    first = target.replace(day=1)
    prev_first = (first - datetime.timedelta(days=1)).replace(day=1)
    next_first = first + datetime.timedelta(days=days)
    return templates.TemplateResponse(request, "cal.html", {
        "detail": _calendar_info(target.year, target.month, target.day),
        "month_rows": month_rows,
        "date": target.isoformat(),
        "year": target.year, "month": target.month,
        "prev": prev_first.isoformat(),
        "next": next_first.isoformat(),
        "today": datetime.date.today().isoformat(),
    })


def _parse_date(s: str) -> datetime.date | None:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _calendar_info(y: int, m: int, d: int) -> dict:
    """指定公历日的确定性历法信息（干支/月令/生肖/农历/节气）。"""
    from mingli.engines.loader import load_engine
    common = load_engine("common")
    dgan, dzhi = common.day_ganzhi(y, m, d)
    jd = float(common.jdn(y, m, d)) + 0.5
    ygan, yzhi, mgan, mzhi = common.year_month_ganzhi(jd)
    gan = lambda i: common.TIAN_GAN[i]  # noqa: E731
    zhi = lambda i: common.DI_ZHI[i]  # noqa: E731
    info = {
        "year": y, "month": m, "day": d,
        "solar": f"{y}-{m:02d}-{d:02d}",
        "year_ganzhi": gan(ygan) + zhi(yzhi),
        "month_ganzhi": gan(mgan) + zhi(mzhi),
        "day_ganzhi": gan(dgan) + zhi(dzhi),
        "yueling": f"{zhi(mzhi)}月",
        "shengri": _ZODIAC[yzhi],
        "jieqi": "",
        "lunar": "",
    }
    try:
        from lunar_python import Solar
        ln = Solar.fromYmd(y, m, d).getLunar()
        info["jieqi"] = ln.getJieQi() or ""
        info["lunar"] = f"农历{ln.getMonthInChinese()}月{ln.getDayInChinese()}"
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# 问事推荐（/ask → 生成空间引导；POST 逻辑保留）
# ---------------------------------------------------------------------------

@app.get("/ask", response_class=HTMLResponse)
async def ask_form(request: Request):
    return templates.TemplateResponse(request, "ask.html", {})


@app.post("/ask")
async def ask_submit(request: Request, text: str = Form(...)):
    text = text.strip()
    if not text:
        return templates.TemplateResponse(request, "ask.html", {"error": "请输入问题"}, status_code=400)

    safety = assess(text)
    if safety.crisis:
        return templates.TemplateResponse(request, "ask.html", {
            "error": safety.notices[0], "text": text}, status_code=200)

    cls, recs = _router().recommend(text)
    anti = QuestionRouter.anti_recommendation(cls)

    rec_payload = [{"systemId": r.systemId, "systemName": r.systemName,
                    "score": r.score, "reason": r.reason} for r in recs if getattr(r, "systemId", None) != "compare"]
    recommend = None
    recommend_note = None
    if rec_payload and llm_available():
        try:
            recommend = recommend_with_llm(
                text, {"category": cls.category, "horizon": cls.horizon}, rec_payload)
        except Exception as e:  # noqa: BLE001 - 建议失败不阻断推荐页
            recommend_note = f"建议暂不可用（{e}）"

    return templates.TemplateResponse(request, "recommend.html", {
        "question_text": text,
        "classification": cls,
        "recommendations": recs,
        "anti": anti,
        "recommend": recommend,
        "recommend_note": recommend_note,
        "safety_notices": safety.notices,
        "no_compare_hint": True,
    })


# ---------------------------------------------------------------------------
# 多体系对照 & 综合分析（研究模式 · 归属生成空间的研究型起局）
# ---------------------------------------------------------------------------

def _run_analysis_pipeline(
    q: str,
    systems: list[str],
    seed: int,
    birth_year, birth_month, birth_day, birth_hour, birth_gender,
) -> dict:
    """同一问题的多体系分析管线：逐体系独立起局 → 确定性对照 → 知识检索 + LLM 综合。

    compare 与 analyze 两条路由共用。综合层是可选插槽：无 key / 失败 → 不阻断对照。
    """
    cls = classify_question(q)
    anti = QuestionRouter.anti_recommendation(cls)
    question = Question(text=q, category=cls.category)
    runs: list[ComparisonRun] = []
    today = datetime.date.today()

    for sid in systems:
        try:
            provider = _registry.get(sid)
        except KeyError:
            continue
        input_data = _comparison_input(sid, seed, today, birth_year, birth_month,
                                       birth_day, birth_hour, birth_gender)
        if sid in ("bazi", "ziwei") and not input_data:
            runs.append(ComparisonRun(systemId=sid, systemName=provider.name,
                                      strengths=provider.strengths, region=provider.region,
                                      skipped=True, skip_reason="未提供出生资料——命局型体系须以出生时刻定框架"))
            continue
        errs = provider.validate_input(input_data)
        if errs:
            runs.append(ComparisonRun(systemId=sid, systemName=provider.name,
                                      strengths=provider.strengths, region=provider.region,
                                      skipped=True, skip_reason="；".join(errs)))
            continue
        try:
            calc = provider.calculate(input_data)
        except Exception as e:  # noqa: BLE001 - 对照隔离失败，如实跳过
            runs.append(ComparisonRun(systemId=sid, systemName=provider.name,
                                      strengths=provider.strengths, region=provider.region,
                                      skipped=True, skip_reason=f"引擎错误：{e}"))
            continue
        interp = provider.interpret(calc, question, _knowledge)
        runs.append(ComparisonRun.from_interpretation(sid, provider.name, provider.strengths,
                                                      interp, region=provider.region))

    cmp = build_comparison(q, {"category": cls.category, "horizon": cls.horizon}, runs)

    synthesis = None
    synthesis_note = None
    usable_runs = [r for r in runs if not r.skipped]
    if usable_runs:
        rules = _knowledge.search_by_question(q, limit=12)
        runs_payload = [{
            "systemId": r.systemId,
            "systemName": r.systemName,
            "polarity": r.polarity,
            "summary": r.summary,
            "conclusions": [c.get("claim") for c in r.conclusions if c.get("claim")],
        } for r in usable_runs]
        rules_payload = [{
            "id": r.id, "statement": r.statement, "sourceLevel": r.sourceLevel,
            "keywords": r.keywords,
        } for r in rules]
        if llm_available():
            try:
                synthesis = synthesize_with_llm(
                    q, {"category": cls.category, "horizon": cls.horizon},
                    runs_payload, rules_payload)
            except Exception as e:  # noqa: BLE001 - 综合层失败不阻断对照主表
                synthesis_note = f"综合解析暂不可用（{e}）。对照主表与逐体系展开不受影响。"
        else:
            synthesis_note = ("配置 ANTHROPIC_API_KEY 可启用「玄师综合分析」——结合你的问题，把多体系结论讲成可行动的话。"
                              "现在即可到 /settings（API 设置）页填写 Key。")

    return {
        "cmp": cmp, "anti": anti, "runs": runs,
        "synthesis": synthesis, "synthesis_note": synthesis_note,
    }


@app.get("/compare", response_class=HTMLResponse)
async def compare_form(request: Request, q: str = "", profile: str = ""):
    pf = _profile_prefill(profile) if profile else None
    return templates.TemplateResponse(request, "compare.html", {
        "active_systems": _registry.active_providers(),
        "has_runs": False, "q": q,
        "seed": "7", "profiles": _profiles.list_all(),
        "birth_year": pf.get("year") if pf else None,
        "birth_month": pf.get("month") if pf else None,
        "birth_day": pf.get("day") if pf else None,
        "birth_hour": pf.get("hour") if pf else None,
        "birth_gender": pf.get("gender") if pf else "",
    })


@app.post("/compare")
async def compare_submit(request: Request,
                         q: str = Form(...),
                         systems: list[str] = Form(default=[]),
                         seed: int = Form(7),
                         birth_year: int | None = Form(None),
                         birth_month: int | None = Form(None),
                         birth_day: int | None = Form(None),
                         birth_hour: int | None = Form(None),
                         birth_gender: str = Form("")):
    q = q.strip()
    if not q:
        return RedirectResponse("/compare", status_code=303)
    if not systems:
        return templates.TemplateResponse(request, "compare.html", {
            "active_systems": _registry.active_providers(), "has_runs": False, "q": q,
            "seed": seed, "error": "请至少选择一个体系。"})

    out = _run_analysis_pipeline(q, systems, seed,
                                 birth_year, birth_month, birth_day, birth_hour, birth_gender)
    return templates.TemplateResponse(request, "compare.html", {
        "active_systems": _registry.active_providers(),
        "has_runs": True, "q": q, "seed": seed,
        "cmp": out["cmp"], "anti": out["anti"],
        "synthesis": out["synthesis"], "synthesis_note": out["synthesis_note"],
        "selected": systems,
        "birth_year": birth_year, "birth_month": birth_month, "birth_day": birth_day,
        "birth_hour": birth_hour, "birth_gender": birth_gender,
    })


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_form(request: Request, q: str = "", profile: str = ""):
    pf = _profile_prefill(profile) if profile else None
    return templates.TemplateResponse(request, "analyze.html", {
        "active_systems": _registry.active_providers(),
        "has_runs": False, "q": q,
        "seed": "7", "profiles": _profiles.list_all(),
        "birth_year": pf.get("year") if pf else None,
        "birth_month": pf.get("month") if pf else None,
        "birth_day": pf.get("day") if pf else None,
        "birth_hour": pf.get("hour") if pf else None,
        "birth_gender": pf.get("gender") if pf else "",
    })


@app.post("/analyze")
async def analyze_submit(request: Request,
                         q: str = Form(...),
                         systems: list[str] = Form(default=[]),
                         seed: int = Form(7),
                         birth_year: int | None = Form(None),
                         birth_month: int | None = Form(None),
                         birth_day: int | None = Form(None),
                         birth_hour: int | None = Form(None),
                         birth_gender: str = Form("")):
    q = q.strip()
    if not q:
        return RedirectResponse("/analyze", status_code=303)
    if not systems:
        return templates.TemplateResponse(request, "analyze.html", {
            "active_systems": _registry.active_providers(), "has_runs": False, "q": q,
            "seed": seed, "error": "请至少选择一个体系。"})

    out = _run_analysis_pipeline(q, systems, seed,
                                 birth_year, birth_month, birth_day, birth_hour, birth_gender)
    return templates.TemplateResponse(request, "analyze.html", {
        "active_systems": _registry.active_providers(),
        "has_runs": True, "q": q, "seed": seed,
        "cmp": out["cmp"], "anti": out["anti"],
        "synthesis": out["synthesis"], "synthesis_note": out["synthesis_note"],
        "selected": systems,
        "birth_year": birth_year, "birth_month": birth_month, "birth_day": birth_day,
        "birth_hour": birth_hour, "birth_gender": birth_gender,
    })


def _comparison_input(sid: str, seed: int, today: datetime.date,
                      birth_year, birth_month, birth_day, birth_hour, birth_gender) -> dict:
    """对照模式下各体系的自动/给定输入（可复现，来源在页面上如实标注）。"""
    if sid == "bazi":
        if all(v is not None for v in (birth_year, birth_month, birth_day)):
            return {"year": birth_year, "month": birth_month, "day": birth_day,
                    # 0 点（子时）是合法输入，falsy 兜底会把它换成午时
                    "hour": birth_hour if birth_hour is not None else 12,
                    "gender": birth_gender or None}
        return {}
    if sid == "liuyao":
        return {"mode": "random", "seed": seed}
    if sid == "meihua":
        return {"mode": "numbers", "numbers": [3, 7]}
    if sid == "xiaoliuren":
        return {"mode": "numbers", "numbers": [3, 5, 6]}
    if sid == "daliuren":
        return {"mode": "datetime", "datetimeInput": [today.year, today.month, today.day, 12]}
    if sid == "tarot":
        return {"spread": "three", "seed": seed}
    if sid == "yijing":
        return {}
    return {}


# ---------------------------------------------------------------------------
# ⚙ 设置中心（AI 接入 / 外观 / 模型行为 / 数据）
# ---------------------------------------------------------------------------

def _mask_key(key: str) -> str:
    return "••••••••"


def _settings_view() -> dict:
    key = llm_config.api_key()
    file_cfg = llm_config.load() or {}
    file_has_key = bool(file_cfg.get("api_key") or file_cfg.get("api_key_file"))
    return {
        "has_key": bool(key),
        "key_masked": _mask_key(key) if key else None,
        "key_from_env": bool(key) and not file_has_key,
        "key_from_file": bool(file_cfg.get("api_key_file")),
        "model": llm_config.model(),
        "interpreter": llm_config.interpreter(),
        "provider": llm_config.provider(),
        "providers": llm_config.PROVIDERS,
        "base_url": file_cfg.get("base_url") or "",
        "style": llm_config.style(),
        "styles": llm_config.STYLES,
        "data_stats": {
            "sessions": len(_sessions.list_all()),
            "experiments": len(_experiments.list_all()),
            "chats": len(_chats.list_all()),
            "profiles": len(_profiles.list_all()),
        },
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", _settings_view())


@app.post("/settings")
async def settings_save(request: Request,
                        action: str = Form("save"),
                        api_key: str = Form(""),
                        model: str = Form(""),
                        interpreter: str = Form(""),
                        provider: str = Form(""),
                        base_url: str = Form(""),
                        style: str = Form("")):
    if action == "clear":
        llm_config.clear()
    elif action == "test":
        pass  # 测试连接走独立端点 /settings/test
    else:
        cur = llm_config.load()
        if api_key.strip():
            cur["api_key"] = api_key.strip()
        if model.strip():
            cur["model"] = model.strip()
        if interpreter in ("rule-engine", "llm"):
            cur["interpreter"] = interpreter
        if provider in llm_config.PROVIDERS:
            cur["provider"] = provider
        if base_url.strip():
            cur["base_url"] = base_url.strip()
        if style in llm_config.STYLES:
            cur["style"] = style
        llm_config.save(cur)
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/test")
async def settings_test():
    """测试连接：发一个最小请求验证 Key/端点可用。"""
    if not llm_available():
        return JSONResponse({"ok": False, "error": "未配置 API Key"}, status_code=400)
    try:
        from mingli.core.interpret.llm import _call_llm
        text = _call_llm("你是连接测试助手。", '回复两个字："连通"', max_tokens=16)
        return JSONResponse({"ok": True, "reply": text.strip()[:40]})
    except Exception as e:  # noqa: BLE001 - 测试端点要如实报错
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@app.post("/settings/data/export")
async def settings_export():
    """全量导出：sessions + experiments + chats 打包为一个 JSON。"""
    import json as _json

    payload = {
        "kind": "mingli-xuanshi/full-export",
        "exportedAt": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "sessions": [s.model_dump() for s in _sessions.list_all()],
        "experiments": [e.model_dump() for e in _experiments.list_all()],
        "chats": [t.model_dump() for t in _chats.list_all()],
        "note": "个人研究数据全量导出；不含 API Key 等机密配置。",
    }
    body = _json.dumps(payload, ensure_ascii=False, indent=1)
    return JSONResponse(body, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="mingli-export.json"'})


def _remove_quietly(path: str) -> None:
    import contextlib
    with contextlib.suppress(OSError):
        os.remove(path)


@app.post("/settings/data/clear-sessions")
async def settings_clear_sessions():
    """删除全部盘局记录（实验记录保留——判定链完整性优先）。"""
    for s in _sessions.list_all():
        _remove_quietly(os.path.join(_sessions.root, f"{s.id}.json"))
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/data/clear-chats")
async def settings_clear_chats():
    for t in _chats.list_all():
        _remove_quietly(os.path.join(_chats.root, f"{t.id}.json"))
    return RedirectResponse("/settings", status_code=303)


# ---------------------------------------------------------------------------
# 日历辅助
# ---------------------------------------------------------------------------

def _days_in_month(y: int, m: int) -> int:
    import calendar as _cal
    return _cal.monthrange(y, m)[1]


def _days_ago(n: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()
