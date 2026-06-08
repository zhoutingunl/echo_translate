from asr_engine import ASRIngestor, NEW, REVISE, INTERIM_PREVIEW, _is_extension
from models import FINAL


def test_interim_preview_does_not_commit(clock):
    asr = ASRIngestor("s", clock=clock)
    ev = asr.ingest("we are", is_final=False)
    assert ev.kind == INTERIM_PREVIEW and ev.interim_text == "we are"
    assert asr.segments == []
    # blank text
    assert asr.ingest("   ", is_final=False).interim_text == ""


def test_final_creates_segment_with_timestamps(clock):
    asr = ASRIngestor("s", clock=clock)
    ev = asr.ingest("Hello world.", is_final=True)
    assert ev.kind == NEW
    seg = ev.segment
    assert seg.id == 1 and seg.status == FINAL
    assert seg.t_recognized == 1000.0 and seg.t_audio == 1000.0


def test_is_extension_cases():
    assert _is_extension("storage", "distributed storage") is True
    assert _is_extension("we are", "we are building") is True
    assert _is_extension("", "x") is False
    assert _is_extension("totally different", "nothing alike here") is False


def test_in_window_extension_revises_in_place(clock):
    # suffix growth (the recognizer extending an utterance) is auto-merged
    asr = ASRIngestor("s", revision_window_sec=5.0, clock=clock)
    asr.ingest("storage system", is_final=True)
    clock.tick(2.0)
    ev = asr.ingest("distributed storage system", is_final=True)
    assert ev.kind == REVISE
    assert len(asr.segments) == 1 and asr.segments[0].version == 2


def test_out_of_window_extension_is_new_segment(clock):
    asr = ASRIngestor("s", revision_window_sec=5.0, clock=clock)
    asr.ingest("storage system", is_final=True)
    clock.tick(10.0)
    ev = asr.ingest("distributed storage system", is_final=True)
    assert ev.kind == NEW and len(asr.segments) == 2


def test_explicit_revise(clock):
    asr = ASRIngestor("s", clock=clock)
    asr.ingest("first", is_final=True)
    ev = asr.revise(1, "first corrected")
    assert ev.kind == REVISE and asr.segments[0].source == "first corrected"
    assert asr.revise(99, "x") is None
