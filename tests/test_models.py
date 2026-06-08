from models import Segment, INTERIM, FINAL


def test_latency_ms():
    seg = Segment(id=1, session_id="s", source="hi", t_audio=1000.0, t_translated=1001.5)
    assert seg.latency_ms == 1500.0
    # missing timestamps -> 0
    assert Segment(id=2, session_id="s", source="x").latency_ms == 0.0


def test_to_dict_includes_rounded_latency():
    seg = Segment(id=1, session_id="s", source="hi", status=FINAL,
                  t_recognized=1000.0, t_audio=1000.0, t_translated=1000.873)
    d = seg.to_dict()
    assert d["status"] == FINAL and d["latency_ms"] == 873.0
    assert d["id"] == 1 and d["source"] == "hi"
