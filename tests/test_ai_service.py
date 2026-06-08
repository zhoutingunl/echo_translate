import json

import pytest

from ai_service import AIService, AIError, _extract_text, _clean
from config import Config
from conftest import fake_completer


# ----------------------------------------------------------------- pure helpers
def test_extract_text_strips_thinking():
    resp = {"content": [{"type": "thinking", "thinking": "hmm"},
                        {"type": "text", "text": "你好"},
                        {"type": "text", "text": "世界"}]}
    assert _extract_text(resp) == "你好世界"
    assert _extract_text({}) == ""


def test_clean_strips_wrapping_quotes():
    assert _clean('  “译文”  ') == "译文"
    assert _clean('"hi"') == "hi"
    assert _clean("无引号") == "无引号"


# ------------------------------------------------------------- completer branch
def test_translate_with_completer(ai):
    r = ai.translate("Hello world", context=[("Hi", "嗨")],
                     glossary_lines="x", mode="meeting")
    assert r.text.startswith("译文") and r.model == "MiniMax-Text-01"
    assert r.fallback_used is False


def test_empty_inputs_are_noops(ai):
    assert ai.translate("   ").text == ""
    assert ai.retranslate("").text == ""
    assert ai.summarize("").text == ""


def test_completer_exception_becomes_aierror(config):
    def boom(system, user, model):
        raise ValueError("nope")
    svc = AIService(config, completer=boom)
    with pytest.raises(AIError):
        svc.translate("hi")
    assert svc.errors == 1


def test_summarize_uses_summary_prompt(ai):
    assert ai.summarize("一些中文").text.startswith("要点")


# --------------------------------------------------------------- HTTP transport
class FakeResp:
    def __init__(self, status, payload=None, lines=None):
        self.status_code = status
        self._payload = payload or {}
        self._lines = lines or []
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        return self._responses.pop(0)

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        return self._responses.pop(0)


def _http_config():
    return Config(minimax_api_key="k", minimax_model="MiniMax-Text-01",
                  minimax_fallback_model="MiniMax-M2", ai_retries=1)


def test_http_success():
    sess = FakeSession([FakeResp(200, {"content": [{"type": "text", "text": "结果"}]})])
    svc = AIService(_http_config(), session=sess)
    assert svc.translate("hi").text == "结果"


def test_http_429_falls_back_to_next_provider(monkeypatch):
    import ai_service
    monkeypatch.setattr(ai_service.time, "sleep", lambda *_: None)  # no real backoff
    sess = FakeSession([
        FakeResp(429),                                              # primary attempt 1
        FakeResp(429),                                              # primary attempt 2
        FakeResp(200, {"content": [{"type": "text", "text": "兜底"}]}),  # fallback ok
    ])
    cfg = _http_config()
    cfg.ai_retries = 2
    svc = AIService(cfg, session=sess)
    r = svc.translate("hi")
    assert r.text == "兜底" and r.fallback_used is True


def test_http_non200_then_all_fail_raises():
    sess = FakeSession([FakeResp(400, {"error": "bad"}), FakeResp(400, {"error": "bad"})])
    svc = AIService(_http_config(), session=sess)
    with pytest.raises(AIError):
        svc.translate("hi")


def test_hermes_completion_path():
    cfg = Config(minimax_api_key="", minimax_model="", minimax_fallback_model="",
                 hermes_enabled=True, hermes_model="MiniMax-M3")
    lines = ["event: token", 'data: {"text": "你"}',
             "event: token", 'data: {"text": "好"}',
             "event: done", 'data: {"session": {}}']
    lines = [s.encode("utf-8") for s in lines]
    sess = FakeSession([
        FakeResp(200, {"session": {"session_id": "s1"}}),   # session/new
        FakeResp(200, {"stream_id": "st1"}),                # chat/start
        FakeResp(200, lines=lines),                          # chat/stream (context mgr)
        FakeResp(200, {}),                                   # chat/cancel
    ])
    svc = AIService(cfg, session=sess)
    assert svc.translate("hi").text == "你好"
