"""SafetyGate —— 敏感域检测与断言强度限制（design.md §19）。

规则（来自 xuan-shu skill 铁律 + design.md）：
- 每份报告必带免责声明（渲染器硬编码，不经本模块也可保证）。
- 医疗/投资/法律/赌博域：禁止确定性术数建议；断语降级为"文化参考视角"
  并附转介提示。
- 自杀/自残信号：术数流程不展开，直接给求助信息。
"""
from __future__ import annotations

from dataclasses import dataclass

from mingli.core.router import Classification, classify_question

DISCLAIMER = (
    "本内容属于传统文化/象征性解释或娱乐性参考，不代表经科学验证的事实预测，"
    "也不构成医疗、投资、法律等专业建议。"
)

CRISIS_MESSAGE = (
    "检测到你可能正处于困境中。命理玄师是研究工具，不能替代真实帮助。"
    "请考虑联系信任的人，或拨打全国心理援助热线 12356（24 小时）。"
)

_ADVICE_BAN = {
    "medical": "涉及健康问题：术数解读不可作为医疗依据，请以执业医师诊断为准。",
    "investment": "涉及财务决策：术数解读不可作为投资依据，重大财务决策请咨询持牌专业人士。",
    "legal": "涉及法律事务：术数解读不可作为法律依据，请咨询执业律师。",
    "gambling": "涉及博彩：本系统不对赌博提供任何倾向性建议——术数体系从未被证明能预测随机事件。",
}


@dataclass
class SafetyVerdict:
    crisis: bool
    sensitive: list[str]
    notices: list[str]          # 注入报告的提示文本


def assess(text: str) -> SafetyVerdict:
    cls: Classification = classify_question(text)
    if cls.crisis:
        return SafetyVerdict(crisis=True, sensitive=cls.sensitive,
                             notices=[CRISIS_MESSAGE])
    notices = [_ADVICE_BAN[s] for s in cls.sensitive if s in _ADVICE_BAN]
    return SafetyVerdict(crisis=False, sensitive=cls.sensitive, notices=notices)


def downgrade_claims(conclusion_claims: list[str], verdict: SafetyVerdict) -> list[str]:
    """敏感域下把强断言降级：替换"必/一定/注定"为"多有/恐/倾向"。

    这是程序级约束：即使 interpret 层产出违规措辞，报告层仍兜底改写并记录。
    """
    if not verdict.sensitive:
        return conclusion_claims
    fixed = []
    for c in conclusion_claims:
        for w in ("必定", "必然", "一定会", "一定", "注定", "绝对"):
            c = c.replace(w, "多有倾向")
        fixed.append(c)
    return fixed
