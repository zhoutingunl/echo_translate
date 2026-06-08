from models import Segment, FINAL, INTERIM
from revision_engine import RevisionWindow


def _seg(id, source, t_recognized, status=FINAL):
    return Segment(id=id, session_id="s", source=source, status=status,
                   t_recognized=t_recognized)


def test_in_window_and_revisable(clock):
    rw = RevisionWindow(window_sec=5.0, clock=clock)
    seg = _seg(1, "hi", 1000.0)
    assert rw.in_window(seg) and rw.revisable(seg)
    clock.tick(6.0)
    assert not rw.in_window(seg) and not rw.revisable(seg)


def test_interim_not_revisable(clock):
    rw = RevisionWindow(window_sec=5.0, clock=clock)
    seg = _seg(1, "hi", 1000.0, status=INTERIM)
    assert rw.revisable(seg) is False


def test_glossary_targets(clock):
    rw = RevisionWindow(window_sec=5.0, clock=clock)
    segs = [_seg(1, "use Redis here", 1000.0), _seg(2, "no term", 1000.0),
            _seg(3, "more redis stuff", 1000.0)]
    hits = rw.glossary_targets(segs, "Redis")
    assert [s.id for s in hits] == [1, 3]


def test_mark_corrected():
    seg = _seg(1, "x", 1000.0)
    RevisionWindow.mark_corrected(seg)
    assert seg.corrected is True and seg.version == 2
