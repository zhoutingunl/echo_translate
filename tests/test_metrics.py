from metrics import MetricsCollector, percentile


def test_percentile_edges():
    assert percentile([], 95) == 0.0
    assert percentile([5], 95) == 5
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4], 100) == 4


def test_record_translation_and_snapshot(clock):
    m = MetricsCollector(clock=clock)
    m.record_translation(end_to_end_ms=1000, translate_ms=900, source_chars=10,
                         target_chars=8, glossary_present=2, glossary_preserved=2)
    clock.tick(1.0)
    m.record_translation(end_to_end_ms=2000, translate_ms=1100, source_chars=5,
                         target_chars=4, glossary_present=1, glossary_preserved=0)
    snap = m.snapshot()
    assert snap["segments"] == 2
    assert snap["translation_success_rate"] == 1.0
    assert snap["glossary_hit_rate"] == round(2 / 3, 4)
    assert snap["latency_ms"]["avg"] == 1500.0
    assert snap["total_target_chars"] == 12


def test_error_and_correction(clock):
    m = MetricsCollector(clock=clock)
    m.record_translation(end_to_end_ms=0, translate_ms=0, success=False)
    m.record_translation(end_to_end_ms=500, translate_ms=400)
    m.record_correction()
    snap = m.snapshot()
    assert snap["translation_error"] == 1
    assert snap["translation_success_rate"] == 0.5
    assert snap["corrections"] == 1
    assert snap["correction_rate"] == round(1 / 2, 4)


def test_rtf_uses_elapsed(clock):
    m = MetricsCollector(clock=clock)
    m.record_translation(end_to_end_ms=1000, translate_ms=1000)  # t=1000
    clock.tick(4.0)
    m.record_translation(end_to_end_ms=1000, translate_ms=1000)  # t=1004, elapsed 4s
    # processing 2s over 4s elapsed -> rtf 0.5
    assert m.rtf() == 0.5
    assert MetricsCollector().rtf() == 0.0  # no data


def test_track_events():
    m = MetricsCollector()
    m.track("subtitle_render")
    m.track("subtitle_render")
    assert m.snapshot()["events"]["subtitle_render"] == 2


def test_empty_glossary_hit_rate_defaults_to_one():
    assert MetricsCollector().snapshot()["glossary_hit_rate"] == 1.0
