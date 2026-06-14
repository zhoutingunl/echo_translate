"""Transcript export — bilingual documents and a synced multimedia page.

Renders a session's segments (English source + Chinese translation + timeline) to:

* ``to_text``     — plain bilingual text
* ``to_csv``      — spreadsheet columns
* ``to_markdown`` — a side-by-side table (英文 | 中文)
* ``to_srt``      — bilingual subtitles (EN line + 中 line), timed to the audio
* ``to_html``     — a self-contained page: side-by-side transcript, and — when an
  audio data-URI is supplied — an embedded player whose playback highlights the
  current line and where clicking a line seeks the audio (the "multimedia 文档").

All functions are pure (segments in, string out), so they unit-test without a DB.
Timings are derived relative to ``t0`` (the session start); subtitles are made
contiguous so the document reads cleanly even though ASR commit times only
approximate sentence boundaries.
"""
from __future__ import annotations

import csv
import html
import io
from typing import Optional


def _spans(segments: list[dict], t0: float) -> list[tuple[float, float]]:
    """Contiguous (start, end) seconds for each segment, relative to ``t0``."""
    spans: list[tuple[float, float]] = []
    prev_end = 0.0
    for s in segments:
        rec = s.get("t_recognized") or 0.0
        end = (rec - t0) if rec else (prev_end + 3.0)
        end = max(end, prev_end + 0.6)
        spans.append((round(prev_end, 2), round(end, 2)))
        prev_end = end
    return spans


def _srt_ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def _clock(t: float) -> str:
    t = max(0.0, t)
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def to_text(segments: list[dict]) -> str:
    out = []
    for s in segments:
        mark = " [修正]" if s.get("corrected") else ""
        out.append(f"EN: {s.get('source', '')}{mark}")
        out.append(f"中: {s.get('translation', '')}")
        out.append("")
    return "\n".join(out)


def to_csv(segments: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["index", "english", "chinese", "corrected", "t_recognized", "t_translated"])
    for i, s in enumerate(segments, 1):
        w.writerow([i, s.get("source", ""), s.get("translation", ""),
                    int(bool(s.get("corrected"))), s.get("t_recognized", ""),
                    s.get("t_translated", "")])
    return buf.getvalue()


def to_markdown(segments: list[dict], *, title: str = "EchoTranslate 双语对照") -> str:
    lines = [f"# {title}", "", "| # | 英文 (English) | 中文 |", "|---|---|---|"]
    for i, s in enumerate(segments, 1):
        en = (s.get("source", "") or "").replace("|", "\\|")
        zh = (s.get("translation", "") or "").replace("|", "\\|")
        if s.get("corrected"):
            zh += " ✎修正"
        lines.append(f"| {i} | {en} | {zh} |")
    return "\n".join(lines) + "\n"


def to_srt(segments: list[dict], t0: float, *, bilingual: bool = True) -> str:
    spans = _spans(segments, t0)
    out = []
    for i, (s, (start, end)) in enumerate(zip(segments, spans), 1):
        out.append(str(i))
        out.append(f"{_srt_ts(start)} --> {_srt_ts(end)}")
        out.append(s.get("source", ""))
        if bilingual:
            out.append(s.get("translation", ""))
        out.append("")
    return "\n".join(out)


def to_html(segments: list[dict], *, t0: float, title: str = "EchoTranslate 导出",
            audio_data_uri: Optional[str] = None, audio_note: str = "") -> str:
    spans = _spans(segments, t0)
    rows = []
    for s, (start, end) in zip(segments, spans):
        en = html.escape(s.get("source", "") or "")
        zh = html.escape(s.get("translation", "") or "")
        badge = '<span class="mk">修正</span>' if s.get("corrected") else ""
        rows.append(
            f'<div class="row" data-start="{start}" data-end="{end}" tabindex="0">'
            f'<div class="tc">{_clock(start)}</div>'
            f'<div class="en">{en}</div>'
            f'<div class="zh">{zh}{badge}</div></div>')
    has_audio = bool(audio_data_uri)
    player = (f'<audio id="aud" controls src="{audio_data_uri}"></audio>'
              if has_audio else
              (f'<p class="note">{html.escape(audio_note)}</p>' if audio_note else ""))
    sync_js = _SYNC_JS if has_audio else ""
    return _HTML_TMPL.format(
        title=html.escape(title), count=len(segments), player=player,
        rows="\n".join(rows), sync_js=sync_js,
        audio_hint=("点击任意一句可跳转音频；播放时自动高亮当前句。" if has_audio
                    else "本会话无服务端音频（浏览器原生识别不上传音频），仅文本对照。"))


_SYNC_JS = """
  const aud = document.getElementById('aud');
  const rows = [...document.querySelectorAll('.row')];
  rows.forEach(r => r.addEventListener('click', () => {
    aud.currentTime = parseFloat(r.dataset.start) + 0.01; aud.play();
  }));
  aud.addEventListener('timeupdate', () => {
    const t = aud.currentTime; let cur = null;
    for (const r of rows) {
      const a = parseFloat(r.dataset.start), b = parseFloat(r.dataset.end);
      if (t >= a && t < b) { cur = r; break; }
    }
    rows.forEach(r => r.classList.toggle('active', r === cur));
    if (cur) cur.scrollIntoView({ block: 'nearest' });
  });
"""

_HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --line:#e3e6ee; --mut:#6b7385; --acc:#2f6bff; --hl:#fff5d6; }}
  body {{ margin:0; font:15px/1.6 -apple-system,"PingFang SC","Segoe UI",sans-serif; color:#1a1f2b; background:#f6f8fc; }}
  header {{ padding:18px 24px; background:#fff; border-bottom:1px solid var(--line); position:sticky; top:0; }}
  h1 {{ margin:0; font-size:18px; }} .sub {{ color:var(--mut); font-size:13px; margin-top:4px; }}
  #aud {{ width:100%; margin-top:12px; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:18px 24px; }}
  .head {{ display:grid; grid-template-columns:64px 1fr 1fr; gap:14px; color:var(--mut); font-size:12px; padding:0 12px 8px; }}
  .row {{ display:grid; grid-template-columns:64px 1fr 1fr; gap:14px; padding:10px 12px; border-radius:10px; cursor:pointer; }}
  .row:hover {{ background:#eef2fb; }} .row.active {{ background:var(--hl); }}
  .tc {{ color:var(--mut); font-variant-numeric:tabular-nums; font-size:13px; }}
  .en {{ color:#33415c; }} .zh {{ font-size:16px; }}
  .mk {{ font-size:11px; background:#ffb454; color:#3a2400; border-radius:5px; padding:0 6px; margin-left:6px; }}
  .note {{ color:var(--mut); font-size:13px; margin:10px 0 0; }}
</style></head><body>
<header>
  <h1>🎧 {title}</h1>
  <div class="sub">{count} 句 · {audio_hint}</div>
  {player}
</header>
<div class="wrap">
  <div class="head"><div>时间</div><div>英文 (English)</div><div>中文</div></div>
  {rows}
</div>
<script>{sync_js}</script>
</body></html>
"""
