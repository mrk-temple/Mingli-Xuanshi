"""统一数据模型 —— Question / CalculationResult / InterpretationResult / EvidenceTrace / Session。

设计要点（design.md §5 + 第十原则"可追溯"）：
- CalculationResult 是唯一事实层，由确定性引擎产出，带 engine 版本与输入快照。
- InterpretationResult 的每条结论必须携带 evidence：规则引用 + 计算数据引用。
  report 渲染时校验 calc_refs 指向的字段真实存在——悬空引用视为程序错误。
- Session 把一次完整分析（问题→计算→解释→报告）落盘为可复查的 JSON。
"""
from __future__ import annotations

import datetime as _dt
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictInt

# ---------------------------------------------------------------------------
# 枚举与小类型
# ---------------------------------------------------------------------------

Region = Literal["east", "west", "cross-cultural"]

QuestionCategory = Literal[
    "career",        # 职业/工作
    "relationship",  # 感情/人际
    "finance",       # 财务
    "study",         # 学业/考试
    "decision",      # 二选一/抉择
    "timing",        # 时机/应期
    "self",          # 自身状态/性格
    "other",
]

SystemStatus = Literal["active", "knowledge-only", "planned"]

# 来源等级（design.md §13）：S 原典 / A 学术 / B 主流教材 / C 当代实践 / D 网络
SourceLevel = Literal["S", "A", "B", "C", "D"]

# 实验判定（design.md §9.2）
Verdict = Literal[
    "exact-hit",      # 完全命中
    "partial-hit",    # 部分命中
    "direction-hit",  # 方向命中
    "timing-hit",     # 时间命中
    "miss",           # 未命中
    "ambiguous",      # 模糊
    "no-outcome",     # 无法验证
]


def now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# 问题
# ---------------------------------------------------------------------------

class Question(BaseModel):
    id: str = Field(default_factory=lambda: new_id("q"))
    text: str
    category: QuestionCategory = "other"
    askedAt: str = Field(default_factory=now_iso)
    horizon: str | None = None  # 用户关心的时间范围，如 "今年内"


# ---------------------------------------------------------------------------
# 计算层（事实）
# ---------------------------------------------------------------------------

class CalculationResult(BaseModel):
    """确定性引擎的结构化输出 —— 全系统的事实基准。

    data 内的结构由各体系自定义（四柱 dict / 卦象 dict / 牌阵 list …），
    但外壳统一：版本、引擎、输入快照、警告齐全。LLM 与报告只允许引用本结构。
    """
    systemId: str
    engine: str                 # 如 "xuan-shu/paipan.py"
    engineVersion: str          # 引擎脚本自身的版本标记
    inputSnapshot: dict[str, Any]   # 归一化后的输入（复现用）
    data: dict[str, Any]            # 体系特定的结构化结果
    rawText: str                    # CLI 原样文本（golden 一致性证据）
    warnings: list[str] = Field(default_factory=list)  # 节气边界/依赖缺失等提醒
    calculatedAt: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# 解释层（体系内解读，可追溯）
# ---------------------------------------------------------------------------

class RuleRef(BaseModel):
    ruleId: str                     # knowledge 库中的规则 id，如 liuyao/yongshen-caifu
    source: str                     # 出处描述，如 "《增删卜易》取用神章 / references/liuyao-guide.md §2"
    sourceLevel: SourceLevel


class CalcRef(BaseModel):
    """指向 CalculationResult.data 的字段路径，如 "yongShen.wangShuai"。"""
    path: str
    value: Any = None               # 渲染校验时由 report 层回填并核对


class Conclusion(BaseModel):
    claim: str                      # 断语本身（含"多有/恐/倾向"式限定词）
    reasoning: list[str]            # 推理链，逐步
    rules: list[RuleRef]
    calcRefs: list[CalcRef]
    # 极性（多体系对照的结构化依据，design.md §8/§11）：
    #   positive=吉象 / negative=忌象 / neutral=平 / symbolic=象征·自省（不入吉凶并论）
    polarity: Literal["positive", "negative", "neutral", "symbolic"] | None = None


class ReadingPoint(BaseModel):
    """白话转述引用既有结论编号（从 1 开始），不增加计算事实。"""
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=700)
    conclusionRefs: list[StrictInt] = Field(min_length=1, max_length=12)


class ReadingAction(BaseModel):
    """现实中的反思/信息收集建议，不是从盘面推出的预测。"""
    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=60)
    detail: str = Field(min_length=1, max_length=350)


class ReaderGuide(BaseModel):
    model_config = {"extra": "forbid"}
    answer: ReadingPoint
    points: list[ReadingPoint] = Field(min_length=1, max_length=4)
    actions: list[ReadingAction] = Field(min_length=1, max_length=3)
    followUpQuestions: list[str] = Field(min_length=1, max_length=3)
    mode: Literal["offline", "llm"] = "offline"


class InterpretationResult(BaseModel):
    systemId: str
    summary: str                                    # 一段话主旨
    conclusions: list[Conclusion] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)   # 两可点、卦象不明等
    limitations: list[str] = Field(default_factory=list)   # 体系局限（渲染时强制并入报告）
    interpreter: Literal["rule-engine", "llm"] = "rule-engine"
    model: str | None = None        # LLM 插槽启用时记录模型名
    readerGuide: ReaderGuide | None = None  # 兼容旧存档；白话展示层独立于事实/结论
    presentationNote: str | None = None
    interpretedAt: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------

class DivinationSession(BaseModel):
    """一次完整分析的持久化单元（design.md §5.3 扩展）。"""
    id: str = Field(default_factory=lambda: new_id("s"))
    question: Question
    systemId: str
    calculation: CalculationResult
    interpretation: InterpretationResult | None = None
    disclaimer: str = ""            # 渲染时写入，保证存档自带免责
    tags: list[str] = Field(default_factory=list)   # 研究标签（记录页筛选用）
    favorite: bool = False          # 收藏
    createdAt: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# 个人命盘库（design.md 扩展 · 跨体系快速重排的出生档案）
# ---------------------------------------------------------------------------

class ChartProfile(BaseModel):
    """用户保存的一份出生档案，供命局型体系（八字/紫微…）在多个页面上快速复用。"""
    id: str = Field(default_factory=lambda: new_id("p"))
    name: str                       # 档案名，如 "我的命盘" / "甲方"
    year: int
    month: int
    day: int
    hour: int | None = None
    gender: str | None = None       # 男 / 女
    longitude: float | None = None  # 出生地经度（真太阳时修正，可选）
    note: str = ""
    createdAt: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# 实验室（预测记录，design.md §9）
# ---------------------------------------------------------------------------

class ExperimentStatus(StrEnum):
    PENDING = "pending"        # 待验证（窗口未到或结果未录入）
    EVALUATED = "evaluated"    # 已录入真实结果并判定
    NO_OUTCOME = "no-outcome"  # 到期无果，无法验证


class Experiment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("e"))
    sessionId: str                  # 关联的占卜会话
    systemId: str
    questionText: str
    prediction: str                 # 锁定的预测内容（用户可读的自然语言）
    windowStart: str                # ISO 日期
    windowEnd: str                  # ISO 日期
    lockedAt: str = Field(default_factory=now_iso)
    blind: bool = False             # 盲测：锁定后不与盘局解读捆绑，减少后见偏差
    status: ExperimentStatus = ExperimentStatus.PENDING
    outcome: str | None = None      # 用户事后录入的真实结果
    verdict: Verdict | None = None  # 系统判定（判定逻辑可查看，见 experiment.py）
    verdictReasoning: str | None = None
    evaluatedAt: str | None = None


# ---------------------------------------------------------------------------
# 知识库条目（design.md §12/§13，第九原则）
# ---------------------------------------------------------------------------

class KnowledgeRule(BaseModel):
    id: str                         # 体系内唯一，如 "liuyao/yongshen-table"
    systemId: str
    tradition: str = "mainstream"   # 流派标签；冲突规则用不同 tradition 并列
    statement: str                  # 规则内容
    keywords: list[str] = Field(default_factory=list)  # 触发词（事项类别/术语）
    appliesTo: list[str] = Field(default_factory=list) # 适用场景标签，如 ["career","finance"]
    sourceLevel: SourceLevel
    source: str
    notes: str | None = None
    disputes: list[str] = Field(default_factory=list)  # 与其他流派的冲突说明


# ---------------------------------------------------------------------------
# 玄师对话（第二空间 · 基于术数 Session 的上下文增强讨论）
# ---------------------------------------------------------------------------

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    at: str = Field(default_factory=now_iso)


class ChatThread(BaseModel):
    """绑定一个 DivinationSession 的讨论串。Context = 该 session 的
    calculation + interpretation + 规则引用；对话本身只追加消息，不改计算事实。"""
    id: str = Field(default_factory=lambda: new_id("c"))
    sessionId: str
    title: str = ""                 # 默认取所问事项前若干字
    createdAt: str = Field(default_factory=now_iso)
    messages: list[ChatTurn] = Field(default_factory=list)
