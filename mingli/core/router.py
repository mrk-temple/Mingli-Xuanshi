"""QuestionRouter —— 问题识别 → 体系推荐（design.md §7，第五原则）。

不做"哪个最准排行榜"。推荐依据是**信息模型匹配度**：
- 问题类型（career/decision/…）× 时间尺度（near-term/long-term）× 视角需求
  （事件成败 / 行动方向 / 心理象征 / 命局框架）→ 各体系的 strengths 打分。

Router 是确定性规则（关键词+类别表），可测试、可解释；每条推荐都带
"为什么推荐"的理由文本。LLM 只允许在"问题分类"环节做辅助（可选插槽），
不允许替代打分逻辑。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from mingli.core.models import Question, QuestionCategory
from mingli.systems.base import SystemProvider

# ---------------------------------------------------------------------------
# 问题分类（确定性关键词表；覆盖不到的落 other）
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[QuestionCategory, list[str]] = {
    "career": ["工作", "职业", "跳槽", "换工作", "离职", "升职", "面试", "事业", "创业", "岗位", "offer"],
    "relationship": ["感情", "恋爱", "婚姻", "对象", "分手", "复合", "表白", "相亲", "桃花"],
    "finance": ["财运", "投资", "赚钱", "收入", "理财", "买房", "卖房", "生意", "求财"],
    "study": ["考试", "学业", "考研", "考公", "学习", "升学", "论文", "录取"],
    "decision": ["该不该", "要不要", "选哪个", "怎么选", "是否适合", "适不适合", "二选一", "还是"],
    "timing": ["什么时候", "何时", "哪个月", "几月", "多久", "应期", "时间点"],
    "self": ["我的性格", "我是", "我适合什么", "天赋", "命格", "命盘", "运势如何", "今年运", "流年"],
}

# 时间尺度
_LONG_TERM_WORDS = ["这辈子", "一生", "命里", "先天", "命格", "大运", "流年", "今年运"]
_NEAR_TERM_WORDS = ["这次", "这件事", "明天", "下周", "这个月", "最近", "眼下", "马上"]

# 敏感域（safety 联动）
SENSITIVE_PATTERNS = [
    (r"(病|疾病|癌症|肿瘤|手术|怀孕|生育|吃药|治疗)", "medical"),
    (r"(投资|股票|基金|期货|炒币|加密货币|加仓|梭哈)", "investment"),
    (r"(官司|诉讼|起诉|被告|原告|合同纠纷|法律责任)", "legal"),
    (r"(赌博|赌钱|彩票|博彩)", "gambling"),
    (r"(自杀|轻生|不想活|自残)", "crisis"),
]
_CRISIS_PATTERN = r"(自杀|轻生|不想活|自残)"


@dataclass
class Classification:
    category: QuestionCategory
    horizon: str                      # near-term / long-term / unknown
    hasTiming: bool = False           # 含"何时/几月"类问法（时态修饰，非主题）
    sensitive: list[str] = field(default_factory=list)
    crisis: bool = False


def classify_question(text: str) -> Classification:
    """确定性分类：类别 + 时间尺度 + 时态修饰 + 敏感域标记。

    timing 视为"时态修饰"而非主题类：主题类（career/…）分数更高时主题胜出；
    否则（只问时间或为主题并列）落到 timing。
    """
    cat_scores: dict[QuestionCategory, int] = {}
    for cat, words in _CATEGORY_KEYWORDS.items():
        if cat == "timing":
            continue  # timing 独立计分，见下
        score = sum(1 for w in words if w in text)
        if score:
            cat_scores[cat] = score
    timing_score = sum(1 for w in _CATEGORY_KEYWORDS["timing"] if w in text)

    # 主题类：== 时并列任取第一个，但优先匹配更具体的主题
    if cat_scores:
        best = _prefer_topic(cat_scores)
        category: QuestionCategory = best
        has_timing = timing_score > 0
    else:
        category = "timing" if timing_score > 0 else "other"
        has_timing = timing_score > 0

    horizon = "unknown"
    if any(w in text for w in _LONG_TERM_WORDS):
        horizon = "long-term"
    elif any(w in text for w in _NEAR_TERM_WORDS):
        horizon = "near-term"
    # 明确问"何时"——near-term 或保持未知，不覆盖 long-term 语义
    if has_timing and horizon == "unknown":
        horizon = "near-term"

    sensitive = [tag for pat, tag in SENSITIVE_PATTERNS if re.search(pat, text)]
    crisis = bool(re.search(_CRISIS_PATTERN, text))
    return Classification(category=category, horizon=horizon,
                          hasTiming=has_timing, sensitive=sensitive, crisis=crisis)


_TOPIC_PREFERENCE = ["career", "relationship", "finance", "study", "decision", "self"]


def _prefer_topic(scores: dict[QuestionCategory, int]) -> QuestionCategory:
    """并列时按主题优先级取（decision 常与其他主题并列，保留主题为主类）。"""
    top_score = max(scores.values())
    tied = [c for c, s in scores.items() if s == top_score]
    if len(tied) == 1:
        return tied[0]
    for c in _TOPIC_PREFERENCE:
        if c in tied:
            return c
    return tied[0]


# ---------------------------------------------------------------------------
# 推荐
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    systemId: str
    systemName: str
    score: float
    reason: str          # 为什么这个体系适合这个问题（信息模型语言，不是准确度承诺）
    status: str


class QuestionRouter:
    def __init__(self, providers: list[SystemProvider]) -> None:
        self._providers = [p for p in providers if p.status == "active"]

    def recommend(self, question: Question | str, top_n: int = 4) -> tuple[Classification, list[Recommendation]]:
        """返回 (问题分类, 推荐列表)。推荐按匹配分降序；分数只表达信息模型匹配度。"""
        q = question if isinstance(question, Question) else Question(text=question)
        cls = classify_question(q.text)
        recs: list[Recommendation] = []
        for p in self._providers:
            score = p.recommend_for(q)
            if score <= 0:
                continue
            recs.append(Recommendation(
                systemId=p.id,
                systemName=p.name,
                score=round(score, 2),
                reason=self._reason_for(p, cls),
                status=p.status,
            ))
        recs.sort(key=lambda r: -r.score)
        return cls, recs[:top_n]

    def _reason_for(self, p: SystemProvider, cls: Classification) -> str:
        base = p.strengths
        if cls.horizon == "long-term" and "natal" in p.category:
            return f"{base}（你的问题涉及长期命局框架，与该体系'出生时刻定框架'的信息结构匹配）"
        if cls.horizon == "near-term" and "moment" in p.category:
            return f"{base}（你问的是当下具体之事，与该体系'起课断一事'的信息结构匹配）"
        return base

    @staticmethod
    def anti_recommendation(cls: Classification) -> str | None:
        """诚实的反建议：某些组合下提醒用户该体系不匹配（design.md §7 示例）。"""
        if cls.category == "career" and cls.horizon == "near-term":
            return "提示：八字等出生时刻型体系适合看长期命局框架，判断'这一次具体事件'建议优先用起课类体系（六爻/奇门/卜卦占星）。"
        if cls.crisis:
            return "检测到你可能正处于困境中。术数不能替代真实帮助——请考虑联系信任的人或专业心理援助热线（如全国心理援助热线 12356）。"
        return None
