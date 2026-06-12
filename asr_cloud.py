"""Bailian / DashScope streaming ASR — the browser ASR fallback.

Chrome / Edge use the browser's Web Speech API by default (zero latency). Safari /
Firefox have no usable Web Speech API, so their audio is streamed as 16 kHz mono PCM
to the server, which forwards it to Bailian (DashScope ``paraformer-realtime-v2``)
and feeds the incremental transcripts back into the same translation pipeline.

This wraps ``dashscope.audio.asr.Recognition``. The recognizer is created through a
factory so unit tests inject a fake and run with no SDK / network. The dashscope
import is lazy, so importing this module never requires the SDK to be installed.
"""
from __future__ import annotations

from typing import Callable, Optional

# source-language label (as used by the pipeline) -> paraformer language hint
LANG_HINTS = {"English": "en", "Japanese": "ja", "Korean": "ko", "Chinese": "zh"}


class CloudASR:
    def __init__(self, *, api_key: str, model: str = "paraformer-realtime-v2",
                 sample_rate: int = 16000, source_lang: str = "English",
                 on_interim: Optional[Callable[[str], None]] = None,
                 on_final: Optional[Callable[[str], None]] = None,
                 recognition_factory: Optional[Callable[["CloudASR"], object]] = None) -> None:
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.lang = LANG_HINTS.get(source_lang, "en")
        self._on_interim = on_interim or (lambda t: None)
        self._on_final = on_final or (lambda t: None)
        self._factory = recognition_factory
        self._rec = None
        self.started = False
        self.frames = 0

    # called by the recognizer callback for every transcript update
    def _handle(self, text: str, is_end: bool) -> None:
        text = (text or "").strip()
        if not text:
            return
        (self._on_final if is_end else self._on_interim)(text)

    def start(self) -> None:
        if self.started:
            return
        factory = self._factory or self._default_factory
        self._rec = factory(self)
        self._rec.start()
        self.started = True

    def feed(self, pcm: bytes) -> None:
        if self._rec is not None and self.started and pcm:
            self._rec.send_audio_frame(pcm)
            self.frames += 1

    def stop(self) -> None:
        if self._rec is not None and self.started:
            try:
                self._rec.stop()
            except Exception:
                pass
            finally:
                self.started = False

    # ------------------------------------------------------ real dashscope glue
    def _default_factory(self, owner: "CloudASR"):  # pragma: no cover - needs SDK
        import dashscope
        from dashscope.audio.asr import (Recognition, RecognitionCallback,
                                         RecognitionResult)
        dashscope.api_key = self.api_key
        handle = owner._handle

        class _CB(RecognitionCallback):
            def on_event(self, result):
                try:
                    sentence = result.get_sentence()
                except Exception:
                    return
                if isinstance(sentence, dict) and sentence.get("text"):
                    handle(sentence["text"], RecognitionResult.is_sentence_end(sentence))

            def on_error(self, result):
                pass

        return Recognition(model=self.model, format="pcm",
                           sample_rate=self.sample_rate, callback=_CB(),
                           language_hints=[self.lang])
