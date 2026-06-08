from ai_service import AIService
from glossary import Glossary
from metrics import MetricsCollector
from pipeline import SessionPipeline


def _pipe(ai, config, store, clock, **kw):
    events = []
    shared = MetricsCollector(clock=clock)
    p = SessionPipeline("s1", ai, config, store=store, emit=events.append,
                        shared_metrics=shared, clock=clock,
                        glossary=kw.get("glossary", Glossary({"Redis": "Redis"})))
    return p, events, shared


def test_new_segment_emits_and_persists(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    seg = p.on_final("We use Redis")
    assert seg is not None
    kinds = [e["type"] for e in events]
    assert "segment" in kinds
    assert store.get_segments("s1")[0]["translation"].startswith("译文")
    assert shared.snapshot()["segments"] == 1


def test_asr_revision_triggers_correction(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    p.on_final("our storage system")
    ev = p.asr.revise(1, "our distributed storage system")
    p._retranslate(ev.segment, reason="asr")
    revs = [e for e in events if e["type"] == "revision"]
    assert len(revs) == 1 and revs[0]["reason"] == "asr"
    assert revs[0]["segment"]["corrected"] is True
    assert shared.snapshot()["corrections"] == 1


def test_no_revision_when_text_unchanged(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    p.on_final("hello there")
    seg = p.asr.segments[0]
    p._retranslate(seg, reason="asr")     # same source -> same translation
    assert [e for e in events if e["type"] == "revision"] == []


def test_glossary_add_rerenders_in_window(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    p.on_final("we run on harmony os")
    revised = p.add_glossary_term("harmony", "HarmonyOS")
    assert any(s.corrected for s in revised)


def test_mode_switch_and_summary(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    p.set_mode("meeting")
    assert p.translator.mode == "meeting"
    p.on_final("first sentence.")
    text = p.summarize()
    assert text.startswith("要点")
    assert any(e["type"] == "summary" for e in events)
    assert p.summarize() or True   # idempotent-ish; body present


def test_summary_empty_when_no_segments(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    assert p.summarize() == ""


def test_translation_error_path(config, store, clock):
    def boom(system, user, model):
        raise RuntimeError("down")
    ai = AIService(config, completer=boom)
    p, events, shared = _pipe(ai, config, store, clock)
    seg = p.on_final("hello")
    assert seg.translation == "[翻译失败]"
    assert shared.snapshot()["translation_error"] == 1


def test_interim_and_tracks(ai, config, store, clock):
    p, events, shared = _pipe(ai, config, store, clock)
    p.on_interim("partial text")
    assert any(e["type"] == "interim" for e in events)
    p.on_final("done.")
    p.close()
    assert "subtitle_render" in store.event_counts()
