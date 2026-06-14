import export

SEGS = [
    {"source": "Hello everyone.", "translation": "大家好。", "corrected": 0,
     "t_recognized": 100.0, "t_translated": 101.0},
    {"source": "We use Redis | cache.", "translation": "我们用 Redis 缓存。", "corrected": 1,
     "t_recognized": 103.0, "t_translated": 104.0},
]
T0 = 99.0


def test_spans_are_contiguous_and_monotonic():
    spans = export._spans(SEGS, T0)
    assert spans[0][0] == 0.0
    assert spans[0][1] == 1.0           # 100 - 99
    assert spans[1][0] == spans[0][1]   # contiguous
    assert spans[1][1] > spans[1][0]


def test_srt_ts_and_clock():
    assert export._srt_ts(3661.5) == "01:01:01,500"
    assert export._srt_ts(-5) == "00:00:00,000"
    assert export._clock(75) == "01:15"


def test_to_text_marks_corrections():
    txt = export.to_text(SEGS)
    assert "EN: Hello everyone." in txt and "中: 大家好。" in txt
    assert "[修正]" in txt   # second segment corrected


def test_to_csv_header_and_rows():
    out = export.to_csv(SEGS)
    lines = out.strip().splitlines()
    assert lines[0].startswith("index,english,chinese")
    assert len(lines) == 3
    assert "大家好。" in out


def test_to_markdown_escapes_pipes():
    md = export.to_markdown(SEGS)
    assert "| 英文 (English) | 中文 |" in md
    assert "Redis \\| cache" in md   # pipe escaped so table stays valid
    assert "✎修正" in md


def test_to_srt_is_bilingual_and_timed():
    srt = export.to_srt(SEGS, T0)
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "Hello everyone." in srt and "大家好。" in srt
    mono = export.to_srt(SEGS, T0, bilingual=False)
    assert "大家好。" not in mono


def test_to_html_plain_has_no_player():
    doc = export.to_html(SEGS, t0=T0, audio_note="无音频")
    assert "<audio" not in doc
    assert "Hello everyone." in doc and "大家好" in doc
    assert "修正" in doc and "无音频" in doc
    assert "&lt;" not in doc or "Redis" in doc   # html-escaped content present


def test_to_html_with_audio_has_player_and_sync():
    doc = export.to_html(SEGS, t0=T0, audio_data_uri="data:audio/wav;base64,AAAA")
    assert '<audio id="aud"' in doc
    assert "timeupdate" in doc and "data-start" in doc
