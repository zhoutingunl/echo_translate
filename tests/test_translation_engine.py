from glossary import Glossary
from models import Segment, FINAL
from translation_engine import TranslationEngine, PRESENTATION, MEETING


def _seg(id, source):
    return Segment(id=id, session_id="s", source=source, status=FINAL,
                   source_lang="English", t_recognized=1000.0)


def test_translate_segment_fills_fields(ai, clock):
    eng = TranslationEngine(ai, Glossary({"Redis": "Redis"}), clock=clock)
    seg = _seg(1, "We use Redis")
    eng.translate_segment(seg)
    assert seg.translation.startswith("译文")
    assert seg.glossary_hits == 1
    assert seg.t_translated == 1000.0
    assert eng.last_result is not None


def test_context_pairs_limit_and_order(ai):
    eng = TranslationEngine(ai, context_segments=2)
    segs = [_seg(1, "a"), _seg(2, "b"), _seg(3, "c")]
    for s in segs[:2]:
        s.translation = "t" + s.source
    pairs = eng.context_pairs(segs, before=segs[2])
    assert pairs == [("a", "ta"), ("b", "tb")]
    # untranslated finals are skipped
    assert eng.context_pairs(segs, before=segs[1]) == [("a", "ta")]


def test_set_mode_normalizes():
    eng = TranslationEngine(None)
    eng.set_mode(MEETING)
    assert eng.mode == MEETING
    eng.set_mode("garbage")
    assert eng.mode == PRESENTATION


def test_correcting_bumps_version(ai):
    eng = TranslationEngine(ai)
    seg = _seg(1, "hello")
    eng.translate_segment(seg, correcting=True)
    assert seg.corrected is True and seg.version == 2
