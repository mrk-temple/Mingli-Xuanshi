"""综合分析层（第二层）测试 —— 红线圈住：绝不产百分比/综合分；无 key 优雅降级；知识检索命中。"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")


class TestKnowledgeRetrieval:
    def test_question_hits_relevant_rules(self):
        from mingli.core.knowledge import load_knowledge
        kb = load_knowledge()
        hits = kb.search_by_question("我该不该换工作", limit=30)
        # 白话问句应能命中相关规则（经同义词映射），而非零命中
        assert hits, "换工作问句应命中至少一条规则"

    def test_question_hits_relationship_rules(self):
        from mingli.core.knowledge import load_knowledge
        kb = load_knowledge()
        hits = kb.search_by_question("我这段感情能成吗", limit=30)
        # 经同义词映射，感情问句应命中含"官星"关键词的十神断律规则
        assert hits, "感情问句应命中至少一条规则"
        assert any("shishen" in r.id or "官星" in r.keywords for r in hits), hits

    def test_unrelated_question_zero_hit(self):
        from mingli.core.knowledge import load_knowledge
        kb = load_knowledge()
        assert kb.search_by_question("量子力学是什么") == []

    def test_retrieval_respects_source_level(self):
        from mingli.core.knowledge import load_knowledge
        kb = load_knowledge()
        hits = kb.search_by_question("考试能不能过", limit=30)
        for r in hits:
            assert r.sourceLevel in ("S", "A", "B", "C", "D")


class TestSynthesisRedLines:
    def test_sanitize_rejects_percentage(self):
        from mingli.core.interpret.llm import _sanitize_synthesis
        bad = {"responses": [{"systemId": "liuyao", "answer": "x"}],
               "action": "y", "divergence": [], "notes": ["三术一致故 92% 必成"]}
        with pytest.raises(RuntimeError) as e:
            _sanitize_synthesis(bad)
        assert "百分比" in str(e.value) or "92%" in str(e.value)

    def test_sanitize_accepts_valid(self):
        from mingli.core.interpret.llm import _sanitize_synthesis
        ok = {"responses": [{"systemId": "liuyao", "systemName": "六爻", "answer": "有反复"}],
              "divergence": ["分歧"], "action": "三个月内观察结果", "notes": []}
        _sanitize_synthesis(ok)  # 不应抛错

    def test_sanitize_requires_action_and_responses(self):
        from mingli.core.interpret.llm import _sanitize_synthesis
        with pytest.raises(RuntimeError):
            _sanitize_synthesis({"responses": [{"answer": "x"}]})   # 缺 action
        with pytest.raises(RuntimeError):
            _sanitize_synthesis({"responses": "not-a-list", "action": "y"})  # 缺 responses 列表


class TestSynthesisNoKey:
    def test_synthesize_no_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from mingli.core.interpret.llm import synthesize_with_llm
        with pytest.raises(RuntimeError) as e:
            synthesize_with_llm("q", None, [], [])
        assert "ANTHROPIC" in str(e.value).upper() or "key" in str(e.value).lower()
