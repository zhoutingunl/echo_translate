"""EchoTranslate web app — HTTP routes, WebSocket pipeline, replay demo.

Run with ``python app.py`` (threaded Werkzeug + flask-sock WebSocket). ASR is either
the browser's Web Speech API (Chrome/Edge) or — for Safari/Firefox — Bailian cloud
ASR, fed by 16 kHz PCM streamed as binary WebSocket frames. TTS is the browser's
SpeechSynthesis. This server runs the AI translation + revision pipeline and streams
subtitles/corrections back over ``/ws``.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import uuid
import wave
from dataclasses import dataclass

from flask import Flask, Response, jsonify, render_template, request

from flask_sock import Sock

from ai_service import AIService
from asr_cloud import CloudASR
from config import Config, load_config
from dashboard import build_dashboard
from db import Store
import export
from glossary import Glossary
from metrics import MetricsCollector
from pipeline import SessionPipeline
from replay import REPLAY_SCRIPTS

# cap on the PCM we buffer per session for multimedia export (~30 min @16k mono)
MAX_AUDIO_BYTES = 60 * 1024 * 1024
# above this we don't inline the audio into the HTML (offer separate .wav instead)
MAX_INLINE_AUDIO = 40 * 1024 * 1024

DEFAULT_GLOSSARY = {
    "Kubernetes": "Kubernetes", "Kafka": "Kafka", "Redis": "Redis",
    "Hermes": "Hermes", "Docker": "Docker", "GPU": "GPU", "API": "API",
}


@dataclass
class AppState:
    config: Config
    ai: AIService
    store: Store
    metrics: MetricsCollector
    glossary_seed: dict[str, str]
    audio_dir: str


def _dl(content, mimetype: str, filename: str, *, inline: bool = False) -> Response:
    disp = "inline" if inline else "attachment"
    return Response(content, mimetype=mimetype.split(";")[0],
                    headers={"Content-Type": mimetype,
                             "Content-Disposition": f'{disp}; filename="{filename}"'})


def _save_wav(path: str, pcm: bytes, sample_rate: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit PCM
        w.setframerate(sample_rate)
        w.writeframes(pcm)


def create_app(config: Config | None = None, *, ai: AIService | None = None,
               store: Store | None = None) -> tuple[Flask, AppState]:
    cfg = config or load_config()
    store = store if store is not None else Store(cfg.db_path)
    ai = ai or AIService(cfg)
    metrics = MetricsCollector()

    # seed glossary: persisted terms win over defaults
    seed = dict(DEFAULT_GLOSSARY)
    seed.update(store.load_glossary())
    store.save_glossary(seed)

    audio_dir = os.path.join(os.path.dirname(cfg.db_path) or ".", "audio")
    state = AppState(config=cfg, ai=ai, store=store, metrics=metrics,
                     glossary_seed=seed, audio_dir=audio_dir)

    app = Flask(__name__)
    app.config["ECHO"] = state
    sock = Sock(app)
    app.register_blueprint(build_dashboard(metrics, store))

    # ------------------------------------------------------------------ pages
    @app.route("/")
    def index():
        return render_template("index.html",
                               languages=cfg.languages,
                               revision_window=cfg.revision_window_sec)

    @app.route("/api/config")
    def api_config():
        return jsonify(cfg.public_dict())

    @app.route("/api/glossary", methods=["GET", "POST", "DELETE"])
    def api_glossary():
        if request.method == "GET":
            return jsonify(store.load_glossary())
        body = request.get_json(silent=True) or {}
        if request.method == "POST":
            term = (body.get("term") or "").strip()
            if not term:
                return jsonify({"error": "term required"}), 400
            tr = (body.get("translation") or term).strip()
            store.save_glossary({term: tr})
            return jsonify({"ok": True, "term": term, "translation": tr})
        # DELETE
        term = (body.get("term") or "").strip()
        store.delete_glossary_term(term)
        return jsonify({"ok": True})

    @app.route("/api/replay")
    def api_replay():
        return jsonify(REPLAY_SCRIPTS)

    @app.route("/api/history")
    def api_history_list():
        return jsonify(store.list_sessions(limit=50))

    @app.route("/api/history/<session_id>")
    def api_history(session_id: str):
        return jsonify(store.get_segments(session_id))

    @app.route("/api/export/<session_id>/info")
    def api_export_info(session_id: str):
        segs = store.get_segments(session_id)
        wav = os.path.join(state.audio_dir, f"{session_id}.wav")
        return jsonify({"count": len(segs), "has_audio": os.path.exists(wav),
                        "formats": ["html", "srt", "md", "csv", "txt"]
                        + (["wav"] if os.path.exists(wav) else [])})

    @app.route("/api/export/<session_id>.<fmt>")
    def api_export(session_id: str, fmt: str):
        segs = store.get_segments(session_id)
        if not segs:
            return ("no such session", 404)
        sess = store.get_session(session_id) or {}
        t0 = sess.get("started_at") or (segs[0].get("t_recognized") or 0.0)
        base = f"echo_{session_id}"
        wav_path = os.path.join(state.audio_dir, f"{session_id}.wav")

        if fmt == "srt":
            return _dl(export.to_srt(segs, t0), "application/x-subrip", base + ".srt")
        if fmt == "md":
            return _dl(export.to_markdown(segs), "text/markdown; charset=utf-8", base + ".md")
        if fmt == "csv":
            return _dl(export.to_csv(segs), "text/csv; charset=utf-8", base + ".csv")
        if fmt == "txt":
            return _dl(export.to_text(segs), "text/plain; charset=utf-8", base + ".txt")
        if fmt == "wav":
            if not os.path.exists(wav_path):
                return ("no audio for this session", 404)
            with open(wav_path, "rb") as f:
                return _dl(f.read(), "audio/wav", base + ".wav")
        if fmt == "html":
            audio_uri, note = None, ""
            if request.args.get("audio", "1") != "0" and os.path.exists(wav_path):
                if os.path.getsize(wav_path) <= MAX_INLINE_AUDIO:
                    with open(wav_path, "rb") as f:
                        audio_uri = "data:audio/wav;base64," + base64.b64encode(f.read()).decode()
                else:
                    note = "音频较大，未内嵌；可单独下载 .wav 字幕同步文件。"
            doc = export.to_html(segs, t0=t0, title=f"EchoTranslate · {session_id}",
                                 audio_data_uri=audio_uri, audio_note=note)
            return _dl(doc, "text/html; charset=utf-8", base + ".html", inline=True)
        return ("unknown format", 400)

    # -------------------------------------------------------------- websocket
    @sock.route("/ws")
    def ws(ws):  # pragma: no cover - exercised via the browser / manual run
        _serve_ws(ws, state)

    return app, state


def _serve_ws(ws, state: AppState) -> None:
    """One translation session per WebSocket connection.

    Text frames carry JSON control/transcript messages; binary frames carry 16 kHz
    mono PCM audio for the cloud (Bailian) ASR path. ``emit`` is lock-guarded because
    the cloud ASR callback runs on the dashscope SDK's own thread.
    """
    pipeline: SessionPipeline | None = None
    cloud: CloudASR | None = None
    audio_buf = bytearray()       # PCM captured this session (for multimedia export)
    audio_sid: str | None = None
    send_lock = threading.Lock()

    def emit(ev: dict) -> None:
        with send_lock:
            ws.send(json.dumps(ev, ensure_ascii=False))

    def stop_cloud() -> None:
        nonlocal cloud
        if cloud is not None:
            cloud.stop()
            cloud = None

    def flush_audio() -> None:
        """Persist the captured PCM as a WAV so it can back the multimedia export."""
        nonlocal audio_sid
        if audio_sid and audio_buf:
            try:
                _save_wav(os.path.join(state.audio_dir, f"{audio_sid}.wav"),
                          bytes(audio_buf), state.config.asr_sample_rate)
            except Exception:
                pass
        audio_buf.clear()
        audio_sid = None

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break

            # binary frame -> PCM audio for the cloud ASR (also buffered for export)
            if isinstance(raw, (bytes, bytearray)):
                if cloud is not None:
                    cloud.feed(bytes(raw))
                    if len(audio_buf) < MAX_AUDIO_BYTES:
                        audio_buf += raw
                continue

            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            action = msg.get("action")

            if action == "start":
                stop_cloud()
                sid = msg.get("session_id") or uuid.uuid4().hex[:12]
                source_lang = msg.get("source_lang", "English")
                glossary = Glossary(dict(state.glossary_seed))
                glossary.update(state.store.load_glossary())
                pipeline = SessionPipeline(
                    sid, state.ai, state.config, store=state.store, glossary=glossary,
                    mode=msg.get("mode", "presentation"), source_lang=source_lang,
                    emit=emit, shared_metrics=state.metrics)
                pipeline.track("audio_start")
                # cloud ASR fallback: stream binary PCM -> Bailian -> pipeline
                if msg.get("asr") == "cloud" and state.config.cloud_asr_available:
                    audio_buf.clear()
                    audio_sid = sid
                    pl = pipeline  # bind this instance (callback runs on SDK thread)

                    def _cloud_final(text: str, pl=pl) -> None:
                        pl.on_final(text)
                        emit({"type": "metrics", "data": pl.snapshot()})
                    cloud = CloudASR(
                        api_key=state.config.dashscope_api_key,
                        model=state.config.dashscope_asr_model,
                        sample_rate=state.config.asr_sample_rate,
                        source_lang=source_lang,
                        on_interim=pipeline.on_interim, on_final=_cloud_final)
                    cloud.start()
                    pipeline.track("asr_cloud_start")
                emit({"type": "started", "session_id": sid,
                      "asr": "cloud" if cloud else "webspeech",
                      "glossary": glossary.terms})
                continue

            if pipeline is None:
                emit({"type": "error", "message": "send 'start' first"})
                continue

            if action == "interim":
                pipeline.on_interim(msg.get("text", ""))
            elif action == "final":
                pipeline.on_final(msg.get("text", ""), t_audio=msg.get("t_audio", 0.0))
                emit({"type": "metrics", "data": pipeline.snapshot()})
            elif action == "revise":
                ev = pipeline.asr.revise(int(msg.get("seg_id", 0)), msg.get("text", ""))
                if ev and ev.segment is not None:
                    pipeline._retranslate(ev.segment, reason="asr")
                    emit({"type": "metrics", "data": pipeline.snapshot()})
            elif action == "mode":
                pipeline.set_mode(msg.get("mode", "presentation"))
            elif action == "glossary_add":
                pipeline.add_glossary_term(msg.get("term", ""), msg.get("translation"))
            elif action == "summarize":
                pipeline.summarize()
            elif action == "stop":
                stop_cloud()
                flush_audio()
                pipeline.track("audio_stop")
                pipeline.close()
                emit({"type": "metrics", "data": pipeline.snapshot()})
                pipeline = None
    finally:
        stop_cloud()
        flush_audio()


def main() -> None:  # pragma: no cover
    app, state = create_app()
    cfg = state.config
    print(f"EchoTranslate on http://{cfg.host}:{cfg.port}  (dashboard: /dashboard)")
    if not cfg.has_ai_key:
        print("  ⚠️  MINIMAX_API_KEY not set — translations will fail. Copy .env.example -> .env")
    app.run(host=cfg.host, port=cfg.port, debug=cfg.debug, threaded=True)


if __name__ == "__main__":  # pragma: no cover
    main()
