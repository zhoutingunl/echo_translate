from asr_cloud import CloudASR, LANG_HINTS


class FakeRecognition:
    """Stand-in for dashscope Recognition; lets tests drive the callback."""
    def __init__(self, owner):
        self.owner = owner
        self.started = False
        self.frames = []
        self.stopped = False

    def start(self):
        self.started = True

    def send_audio_frame(self, pcm):
        self.frames.append(pcm)

    def stop(self):
        self.stopped = True


def _cloud(**kw):
    events = {"interim": [], "final": []}
    asr = CloudASR(
        api_key="k", source_lang=kw.get("source_lang", "English"),
        on_interim=lambda t: events["interim"].append(t),
        on_final=lambda t: events["final"].append(t),
        recognition_factory=lambda owner: FakeRecognition(owner))
    return asr, events


def test_lang_hint_mapping():
    asr, _ = _cloud(source_lang="Japanese")
    assert asr.lang == "ja"
    asr2, _ = _cloud(source_lang="Klingon")  # unknown -> default en
    assert asr2.lang == "en"
    assert LANG_HINTS["Korean"] == "ko"


def test_start_feed_stop_lifecycle():
    asr, _ = _cloud()
    asr.start()
    assert asr.started and asr._rec.started
    asr.feed(b"\x00\x01")
    asr.feed(b"\x02\x03")
    assert asr.frames == 2 and len(asr._rec.frames) == 2
    asr.stop()
    assert asr._rec.stopped and not asr.started


def test_handle_routes_interim_and_final():
    asr, events = _cloud()
    asr._handle("we are", False)
    asr._handle("we are building", False)
    asr._handle("we are building a system", True)
    asr._handle("   ", True)   # blank ignored
    assert events["interim"] == ["we are", "we are building"]
    assert events["final"] == ["we are building a system"]


def test_double_start_is_noop_and_feed_before_start_safe():
    asr, _ = _cloud()
    asr.feed(b"x")              # before start: ignored, no crash
    assert asr.frames == 0
    asr.start()
    rec = asr._rec
    asr.start()                 # second start must not replace the recognizer
    assert asr._rec is rec
    asr.stop()
    asr.stop()                  # double stop safe
