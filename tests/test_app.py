import json

import pytest

from app import create_app, _serve_ws
from db import Store
from ai_service import AIService
from conftest import fake_completer


@pytest.fixture
def app_state(config):
    ai = AIService(config, completer=fake_completer)
    app, state = create_app(config, ai=ai, store=Store(":memory:"))
    return app, state


def test_index_and_config_no_key_leak(app_state):
    app, state = app_state
    c = app.test_client()
    assert c.get("/").status_code == 200
    cfg = c.get("/api/config").get_json()
    assert "minimax_api_key" not in cfg
    assert "en-US" in cfg["languages"]


def test_glossary_rest_crud(app_state):
    app, _ = app_state
    c = app.test_client()
    assert "Kubernetes" in c.get("/api/glossary").get_json()
    assert c.post("/api/glossary", json={"term": ""}).status_code == 400
    r = c.post("/api/glossary", json={"term": "Pulsar"}).get_json()
    assert r["translation"] == "Pulsar"
    c.delete("/api/glossary", json={"term": "Pulsar"})
    assert "Pulsar" not in c.get("/api/glossary").get_json()


def test_replay_and_history_routes(app_state):
    app, _ = app_state
    c = app.test_client()
    assert "tech_talk" in c.get("/api/replay").get_json()
    assert c.get("/api/history").status_code == 200
    assert c.get("/api/history/none").get_json() == []


# ---- WebSocket handler driven by a fake socket ----
class FakeWS:
    def __init__(self, msgs):
        self.inbox = [json.dumps(m) for m in msgs]
        self.sent = []

    def receive(self):
        return self.inbox.pop(0) if self.inbox else None

    def send(self, s):
        self.sent.append(json.loads(s))


def test_ws_requires_start_first(app_state):
    _, state = app_state
    ws = FakeWS([{"action": "final", "text": "hi"}, {"action": "garbage"}])
    _serve_ws(ws, state)
    assert any(e["type"] == "error" for e in ws.sent)


class FakeCloudASR:
    """Replaces app.CloudASR: a couple of fed frames trigger interim + final."""
    last = None

    def __init__(self, *, api_key, model, sample_rate, source_lang, on_interim, on_final):
        self.on_interim, self.on_final = on_interim, on_final
        self.fed, self.started, self.stopped = 0, False, False
        FakeCloudASR.last = self

    def start(self):
        self.started = True

    def feed(self, pcm):
        self.fed += 1
        if self.fed == 1:
            self.on_interim("we use redis")
        elif self.fed == 2:
            self.on_final("we use redis")

    def stop(self):
        self.stopped = True


def test_ws_cloud_asr_path(config, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "CloudASR", FakeCloudASR)
    config.dashscope_api_key = "test-key"  # enables the cloud branch
    ai = AIService(config, completer=fake_completer)
    flask_app, state = create_app(config, ai=ai, store=Store(":memory:"))

    ws = FakeWS([
        {"action": "start", "session_id": "c", "source_lang": "English", "asr": "cloud"},
    ])
    # binary PCM frames pass through verbatim; FakeWS.receive returns them as bytes
    ws.inbox += [b"\x00\x01\x02\x03", b"\x04\x05\x06\x07",
                 json.dumps({"action": "stop"})]
    _serve_ws(ws, state)
    types = [e["type"] for e in ws.sent]
    started = next(e for e in ws.sent if e["type"] == "started")
    assert started["asr"] == "cloud"
    assert "interim" in types and "segment" in types
    assert FakeCloudASR.last.started and FakeCloudASR.last.stopped


def test_ws_full_session(app_state):
    _, state = app_state
    msgs = [
        {"action": "start", "session_id": "demo", "source_lang": "English", "mode": "presentation"},
        {"action": "interim", "text": "we use"},
        {"action": "final", "text": "we use redis"},
        {"action": "revise", "seg_id": 1, "text": "we use redis cluster"},
        {"action": "mode", "mode": "meeting"},
        {"action": "glossary_add", "term": "Pulsar", "translation": "Pulsar"},
        {"action": "summarize"},
        {"action": "stop"},
    ]
    ws = FakeWS(msgs)
    # feed a non-JSON line to cover the parse-guard; receive() returns None at end
    ws.inbox.insert(1, "not-json")
    _serve_ws(ws, state)
    types = [e["type"] for e in ws.sent]
    assert "started" in types and "segment" in types
    assert "revision" in types and "summary" in types and "metrics" in types
