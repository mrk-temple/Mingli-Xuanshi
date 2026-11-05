"""KnowledgeBase —— 结构化规则库（第九原则：来源必存）。

规则以 YAML 维护在 mingli/knowledge/ 下，每条规则必须带 sourceLevel(S/A/B/C/D)
与 source。同 id 不同 tradition 的规则并存表示流派冲突——检索时全部返回，
由 interpret 层按"当前配置流派"选用并在报告展示冲突，禁止 LLM 悄悄调和。
"""
from __future__ import annotations

import glob
import os
from typing import Any

from mingli.core.models import KnowledgeRule

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")

_VALID_LEVELS = {"S", "A", "B", "C", "D"}

# 白话提问 → 规则传统术语的轻量同义词映射（供 search_by_question）
# 让「换工作」这类白话能命中规则里的「官星/财星/求财」等传统关键词。
# 保持克制：只映射用户观星最常问的几类，不做完整词典。
# 检索逻辑按映射后的词 + 问句原词同时打分。
_BAIHUA_SYNONYMS: dict[str, list[str]] = {
    "工作": ["官星", "官运", "求官", "事业"],
    "事业": ["官星", "官运", "求官"],
    "换工作": ["官星", "跳槽"],
    "跳槽": ["官星"],
    "升职": ["官星", "官运"],
    "求职": ["官星", "官运", "用神"],
    "面试": ["用神", "官星"],
    "钱": ["财星", "财", "求财"],
    "赚钱": ["财星", "求财", "偏财"],
    "财运": ["财星", "求财", "偏财"],
    "投资": ["财星", "偏财"],
    "生意": ["财星", "求财"],
    "感情": ["妻财", "官鬼", "官星", "婚配"],
    "恋爱": ["妻财", "官鬼"],
    "婚姻": ["妻财", "官鬼", "婚配", "婚姻", "官星"],
    "结婚": ["官鬼", "婚姻"],
    "对象": ["妻财", "官鬼"],
    "伴侣": ["妻财", "官鬼"],
    "学业": ["印绶", "正印", "文书", "考试"],
    "考试": ["印绶", "文书", "官星"],
    "读书": ["正印", "印绶", "文书"],
    "考研": ["印绶", "文书", "正印"],
    "房子": ["父母", "文书"],
    "买房": ["父母", "文书"],
    "官司": ["官鬼", "官星", "诉讼"],
    "诉讼": ["官鬼", "官星"],
    "病": ["医药", "子孙", "消灾"],
    "健康": ["子孙", "医药"],
    "合作伙伴": ["兄弟", "比劫"],
    "合伙": ["兄弟", "比劫", "劫财"],
    "竞争": ["劫财", "兄弟", "比肩"],
    "长辈": ["父母", "印绶"],
    "家人": ["父母"],
    "子女": ["子孙"],
    "怀孕": ["子孙", "子女"],
    "出行": ["驿马", "大安"],
    "时机": ["应期", "太岁", "动爻", "变卦"],
    "方向": ["应期", "世应", "生克"],
}


class KnowledgeBase:
    def __init__(self, rules: list[KnowledgeRule]) -> None:
        self._rules = rules
        self._by_system: dict[str, list[KnowledgeRule]] = {}
        self._by_id: dict[str, KnowledgeRule] = {}
        for r in rules:
            self._by_system.setdefault(r.systemId, []).append(r)
            # 同 id 不同流派：保留首个，conflicts() 负责并列展示
            self._by_id.setdefault(r.id, r)

    # ---- 查询 ----

    def for_system(self, system_id: str) -> list[KnowledgeRule]:
        return self._by_system.get(system_id, [])

    def get_rule(self, rule_id: str) -> KnowledgeRule | None:
        return self._by_id.get(rule_id)

    def conflicts(self, rule_id: str) -> list[KnowledgeRule]:
        """同主题（id 去掉流派后缀）下所有流派版本。"""
        base = rule_id.split("@")[0]
        return [r for r in self._rules if r.id.split("@")[0] == base]

    def search(self, system_id: str, keywords: list[str], applies_to: list[str] | None = None) -> list[KnowledgeRule]:
        """按触发词/场景标签检索，命中数降序。interpret 层的规则检索入口。"""
        kws = [k.lower() for k in keywords]
        scored: list[tuple[int, KnowledgeRule]] = []
        for r in self.for_system(system_id):
            if applies_to and not (set(applies_to) & set(r.appliesTo)):
                continue
            score = 0
            hay = (r.statement + " " + " ".join(r.keywords)).lower()
            for k in kws:
                if k and k in hay:
                    score += 1
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored]

    def search_by_question(
        self,
        question_text: str,
        system_ids: list[str] | None = None,
        limit: int = 12,
        min_score: int = 1,
    ) -> list[KnowledgeRule]:
        """跨体系检索：从用户问句提取候选词，与各规则 keywords 交集打分。

        供「综合分析层」使用：把命中的规则条目喂给 LLM 作为知识依据。
        - system_ids 为 None 时跨全部体系；
        - 与现有 search() 不同：本方法按问句自动提词，不要求调用方预分关键词；
        - 命中 = 规则关键词出现在问句里，或经白话同义词映射(_BAIHUA_SYNONYMS)命中，
          e.g. 「换工作」→ 官星/官运。
        """
        expanded = _expand_question(question_text)
        hits: dict[str, tuple[int, KnowledgeRule]] = {}
        for r in self._rules:
            if system_ids and r.systemId not in system_ids:
                continue
            score = sum(1 for k in r.keywords if k and k in expanded)
            if score >= min_score:
                key = r.id.split("@")[0]
                prev = hits.get(key)
                if prev is None or score > prev[0]:
                    hits[key] = (score, r)
        ranked = sorted(hits.values(), key=lambda kv: (-kv[0], kv[1].systemId))
        return [r for _, r in ranked[:limit]]


def load_knowledge(dir_path: str | None = None) -> KnowledgeBase:
    """从 YAML 目录加载全部规则文件。文件格式见 knowledge/README.md。"""
    d = dir_path or _KNOWLEDGE_DIR
    rules: list[KnowledgeRule] = []
    for path in sorted(glob.glob(os.path.join(d, "*.yaml"))):
        with open(path, encoding="utf-8") as f:
            import yaml
            data = yaml.safe_load(f) or {}
        for item in data.get("rules", []):
            level = item.get("sourceLevel")
            if level not in _VALID_LEVELS:
                raise ValueError(f"{path}: 规则 {item.get('id')} sourceLevel 非法: {level!r}（须为 S/A/B/C/D）")
            rules.append(KnowledgeRule(
                id=item["id"],
                systemId=item["systemId"],
                tradition=item.get("tradition", "mainstream"),
                statement=item["statement"],
                keywords=item.get("keywords", []),
                appliesTo=item.get("appliesTo", []),
                sourceLevel=level,
                source=item["source"],
                notes=item.get("notes"),
                disputes=item.get("disputes", []),
            ))
    return KnowledgeBase(rules)


def rule_to_dict(r: KnowledgeRule) -> dict[str, Any]:
    return r.model_dump()


def _expand_question(question_text: str) -> str:
    """把白话问句展开为「原词 + 传统同义词」，供规则关键词命中。

    例：「我该不该换工作」→ 命中 _BAIHUA_SYNONYMS['工作'/'换工作']，
    追加 官星/官运/事业/跳槽 等传统词，使规则的 keywords 能落上。
    """
    tokens = {question_text}
    for bai, trad in _BAIHUA_SYNONYMS.items():
        if bai in question_text:
            tokens.update(trad)
    return " ".join(t for t in tokens if t)
