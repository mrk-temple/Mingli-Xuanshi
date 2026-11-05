"""白话展示层的引用边界、降级、存档兼容与 Web 集成。"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mingli.core import llm_config
from mingli.core.interpret.llm import interpret_with_llm
from mingli.core.interpret.rules import resolve_path, verify_conclusion
from mingli.core.knowledge import load_knowledge
from mingli.core.models import DivinationSession, Question, ReaderGuide
from mingli.core.reading import display_guide, enrich_with_llm, offline_guide, validate_guide
from mingli.core.report import ReportError, render_markdown
from mingli.core.session import ChatStore, ExperimentStore, ProfileStore, SessionStore
from mingli.systems.bootstrap import get_registry


@pytest.fixture()
def reading():
    kb = load_knowledge()
    p = get_registry().get("tarot")
    calc = p.calculate({"spread": "three", "seed": 42})
    q = Question(text="我正在考虑换工作，应该先确认哪些条件？", category="career")
    interp = p.interpret(calc, q, kb)
    return calc, q, interp, kb


def _response() -> dict:
    return {
        "answer": {"text": "牌面不能判断换工作是否成功，可先整理选择条件。", "conclusionRefs": [1]},
        "points": [{"text": "这张牌可作为反思线索；你有哪些信息需要确认？", "conclusionRefs": [2]}],
        "actions": [{"title": "核对岗位", "detail": "列出目标岗位的要求，与自己的作品比较。"}],
        "followUpQuestions": ["你最在意岗位的哪个条件？"],
    }


def test_llm_enriches_without_replacing_facts_or_claims(reading, monkeypatch):
    calc, q, interp, kb = reading
    before_calc = calc.model_dump_json()
    claims = [c.claim for c in interp.conclusions]
    seen = {}

    def fake_call(prompt, content, **kwargs):
        seen.update(json.loads(content))
        return json.dumps(_response(), ensure_ascii=False)

    monkeypatch.setattr("mingli.core.interpret.llm._call_llm", fake_call)
    guide = enrich_with_llm(calc, q, interp, kb)
    assert guide.mode == "llm"
    assert guide.answer.conclusionRefs == [1]
    assert calc.model_dump_json() == before_calc
    assert [c.claim for c in interp.conclusions] == claims
    assert seen["question"] == q.text and seen["rules"]


@pytest.mark.parametrize("ref", [0, -1, 999])
def test_dangling_guide_reference_rejected(reading, monkeypatch, ref):
    calc, q, interp, kb = reading
    response = _response()
    response["answer"]["conclusionRefs"] = [ref]
    monkeypatch.setattr("mingli.core.interpret.llm._call_llm", lambda *a, **kw: json.dumps(response))
    with pytest.raises(RuntimeError, match="引用与措辞"):
        enrich_with_llm(calc, q, interp, kb)


@pytest.mark.parametrize("bad", ["成功率92%", "百分之九十会成功", "你一定会被录取", "这事注定如此"])
def test_probability_and_absolute_claims_rejected(reading, bad):
    _, _, interp, _ = reading
    response = _response()
    response["points"][0]["text"] = bad
    assert validate_guide(ReaderGuide.model_validate(response), interp)


@pytest.mark.parametrize("bad", ["牌面说明你情绪受阻。", "按现有趋势接下来会失利？", "过去位代表行动；你的选择是什么。"])
def test_symbolic_reading_cannot_assert_user_state_or_future(reading, bad):
    _, _, interp, _ = reading
    response = _response()
    response["points"][0]["text"] = bad
    response["mode"] = "llm"
    assert validate_guide(ReaderGuide.model_validate(response), interp)


@pytest.mark.parametrize("text", ["可以借它回想一下有哪些信息需要核实，而不是替你预示结果。",
                                   "它邀请你核实职责边界，不会预示你是否成功。"])
def test_symbolic_reflection_and_negated_prediction_are_allowed(reading, text):
    _, _, interp, _ = reading
    response = _response()
    response["points"][0]["text"] = text
    response["mode"] = "llm"
    assert not validate_guide(ReaderGuide.model_validate(response), interp)


@pytest.mark.parametrize("path", ["cards[-1]", "cards[bad]", "cards[100]", "cards[0", "cards[0]oops", "cards[0].missing"])
def test_malformed_calculation_path_fails_closed(reading, path):
    calc, _, _, _ = reading
    assert resolve_path(calc.data, path) == (False, None)


def test_missing_calc_refs_rejected(reading):
    calc, _, interp, _ = reading
    interp.conclusions[0].calcRefs = []
    assert verify_conclusion(interp.conclusions[0], calc)


def test_unknown_rule_fails_before_model_call(reading, monkeypatch):
    calc, q, interp, kb = reading
    interp.conclusions[0].rules[0].ruleId = "tarot/invented@school"
    monkeypatch.setattr("mingli.core.interpret.llm._call_llm", lambda *a, **kw: pytest.fail("不应调用模型"))
    with pytest.raises(RuntimeError, match="证据校验"):
        enrich_with_llm(calc, q, interp, kb)


def test_unknown_guide_fields_rejected():
    response = _response()
    response["calculation"] = {"changed": True}
    with pytest.raises(ValidationError):
        ReaderGuide.model_validate(response)


@pytest.mark.parametrize("ref", [True, 1.0, "1"])
def test_guide_reference_requires_integer_without_coercion(ref):
    response = _response()
    response["answer"]["conclusionRefs"] = [ref]
    with pytest.raises(ValidationError):
        ReaderGuide.model_validate(response)


def test_llm_rule_suffix_cannot_match_another_tradition(reading, monkeypatch):
    calc, q, _, kb = reading
    llm_config.save({"api_key": "fake-for-test"})
    payload = {"summary": "test", "conclusions": [{"claim": "test", "reasoning": ["test"],
               "rules": ["tarot/wubu-jiedu@invented"], "calcRefs": ["cards"]}]}
    monkeypatch.setattr("mingli.core.interpret.llm._call_llm", lambda *a, **kw: json.dumps(payload))
    with pytest.raises(RuntimeError, match="未知规则"):
        interpret_with_llm("tarot", calc, q, kb)


def test_report_rejects_unknown_catalog_rule(reading):
    calc, q, interp, _ = reading
    interp.conclusions[0].rules[0].ruleId = "tarot/wubu-jiedu@invented"
    with pytest.raises(ReportError, match="规则引用无法核验"):
        render_markdown(DivinationSession(question=q, systemId="tarot", calculation=calc, interpretation=interp))


def test_malformed_json_rejected(reading, monkeypatch):
    calc, q, interp, kb = reading
    monkeypatch.setattr("mingli.core.interpret.llm._call_llm", lambda *a, **kw: "not json")
    with pytest.raises(RuntimeError, match="格式无效"):
        enrich_with_llm(calc, q, interp, kb)


def test_invalid_guide_blocks_report(reading):
    calc, q, interp, _ = reading
    interp.readerGuide = ReaderGuide.model_validate(_response())
    interp.readerGuide.answer.conclusionRefs = [99]
    with pytest.raises(ReportError):
        render_markdown(DivinationSession(question=q, systemId="tarot", calculation=calc, interpretation=interp))


def test_old_session_displays_offline_and_exports_readable_guide(reading):
    calc, q, interp, _ = reading
    old = DivinationSession(question=q, systemId="tarot", calculation=calc, interpretation=interp)
    old = DivinationSession.model_validate_json(old.model_dump_json())
    guide = display_guide(calc, q, old.interpretation)
    assert guide.mode == "offline" and "岗位" in guide.actions[0].detail
    md = render_markdown(old)
    assert "先用白话回答" in md and "五大未证假设" in md
    assert old.interpretation.readerGuide is None  # 浏览不改写旧记录


def test_sensitive_guide_replaces_ai_advice_without_mutation(reading):
    calc, _, interp, _ = reading
    q = Question(text="投资股票要不要加仓？", category="finance")
    interp.readerGuide = ReaderGuide.model_validate(_response())
    original = interp.model_dump_json()
    guide = display_guide(calc, q, interp)
    assert "持牌" in guide.actions[0].detail
    assert "盘面不构成" in guide.points[0].text
    assert interp.model_dump_json() == original


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import mingli.web.app as webapp
    monkeypatch.setattr(webapp, "_sessions", SessionStore(root=str(tmp_path / "sessions")))
    monkeypatch.setattr(webapp, "_experiments", ExperimentStore(root=str(tmp_path / "experiments")))
    monkeypatch.setattr(webapp, "_profiles", ProfileStore(root=str(tmp_path / "profiles")))
    monkeypatch.setattr(webapp, "_chats", ChatStore(root=str(tmp_path / "chats")))
    monkeypatch.setenv("MINGLI_INTERPRETER", "rule-engine")
    return TestClient(webapp.app)


def test_web_llm_failure_visible_and_no_provider_secrets(client, monkeypatch):
    import mingli.web.app as webapp
    llm_config.save({"interpreter": "llm", "api_key": "fake-for-test"})

    def fail(*a):
        raise RuntimeError("provider error contains secret-test-marker")

    monkeypatch.setattr(webapp, "enrich_with_llm", fail)
    r = client.post("/generate/tarot", data={"q": "换工作前先确认什么？", "seed": "42"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"])
    assert "已使用离线阅读指引" in page.text and "先用白话回答" in page.text
    assert "secret-test-marker" not in page.text


def test_web_invalid_guide_hides_conclusions_and_evidence(client, reading):
    import mingli.web.app as webapp
    calc, q, interp, _ = reading
    interp.readerGuide = ReaderGuide.model_validate(_response())
    interp.readerGuide.answer.conclusionRefs = [99]
    interp.conclusions[0].claim = "INVALID-CONCLUSION-MARKER"
    session = DivinationSession(question=q, systemId="tarot", calculation=calc, interpretation=interp)
    webapp._sessions.save(session)
    page = client.get(f"/session/{session.id}")
    assert "已隐藏结论与白话建议" in page.text
    assert "INVALID-CONCLUSION-MARKER" not in page.text
    assert 'id="evidence-data"' not in page.text


def test_mimo_key_file_reads_only_mimo_and_unquotes(tmp_path):
    path = tmp_path / "api.txt"
    path.write_text('Mimo API Key : "mimo-test-secret"\nJina API Key : other-test-secret', encoding="utf-8")
    llm_config.save({"provider": "mimo", "api_key_file": str(path)})
    assert llm_config.api_key() == "mimo-test-secret"
    assert "api_key" not in llm_config.load()


def test_mimo_key_file_is_not_used_for_other_provider(tmp_path, monkeypatch):
    path = tmp_path / "api.txt"
    path.write_text('Mimo API Key : "mimo-test-secret"', encoding="utf-8")
    llm_config.save({"provider": "openai-compatible", "api_key_file": str(path)})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_config.api_key() is None


def test_bazi_offline_guide_remains_structural():
    p = get_registry().get("bazi")
    calc = p.calculate({"year": 1990, "month": 5, "day": 12, "hour": 0})
    q = Question(text="能不能换工作？", category="career")
    interp = p.interpret(calc, q, load_knowledge())
    guide = offline_guide(calc, q, interp)
    assert "不能据此判断" in guide.answer.text
    assert not validate_guide(guide, interp)
