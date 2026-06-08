import os

from db import Store
from models import Segment, FINAL


def _seg(sid, id, source, **kw):
    return Segment(id=id, session_id=sid, source=source, status=FINAL, **kw)


def test_sessions_create_end_list(store):
    store.create_session("s1", "English", "presentation", started_at=10.0)
    store.create_session("s2", "Japanese", "meeting", started_at=20.0)
    store.end_session("s1", ended_at=30.0)
    sessions = store.list_sessions()
    assert [s["id"] for s in sessions] == ["s2", "s1"]   # newest first
    assert sessions[1]["ended_at"] == 30.0


def test_segment_upsert_overwrites_on_revision(store):
    store.create_session("s1", "English", "presentation")
    seg = _seg("s1", 1, "storage", translation="存储")
    store.upsert_segment(seg)
    seg.source = "distributed storage"
    seg.translation = "分布式存储"
    seg.version = 2
    store.upsert_segment(seg)
    rows = store.get_segments("s1")
    assert len(rows) == 1 and rows[0]["translation"] == "分布式存储" and rows[0]["version"] == 2
    assert store.list_sessions()[0]["segment_count"] == 1


def test_events(store):
    store.log_event("s1", "subtitle_render")
    store.log_event("s1", "subtitle_render")
    store.log_event("s1", "subtitle_corrected", {"reason": "asr"})
    counts = store.event_counts()
    assert counts["subtitle_render"] == 2 and counts["subtitle_corrected"] == 1


def test_glossary_roundtrip(store):
    store.save_glossary({"Redis": "Redis", "Kafka": "Kafka"})
    assert store.load_glossary()["Redis"] == "Redis"
    store.delete_glossary_term("Kafka")
    assert "Kafka" not in store.load_glossary()


def test_metrics_save_latest(store):
    assert store.latest_metrics() is None
    store.save_metrics("s1", {"segments": 3})
    store.save_metrics("s1", {"segments": 7})
    assert store.latest_metrics()["segments"] == 7


def test_file_backed_store_creates_dir(tmp_path):
    path = os.path.join(str(tmp_path), "nested", "echo.db")
    s = Store(path)
    s.create_session("s1", "English", "presentation")
    s.close()
    assert os.path.exists(path)
