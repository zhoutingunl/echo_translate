#!/usr/bin/env python3.11
"""Record an end-to-end demo walkthrough of EchoTranslate.

Drives the REAL UI in Chromium via Playwright and records a video + storyboard
screenshots. Uses the built-in replay (which runs the real AI translation +
correction pipeline), so it needs no microphone.

Usage:
    python3.11 demo/record_demo.py            # assumes server on $BASE or :8000
Env:
    BASE   base url (default http://127.0.0.1:8000)
    OUTDIR output directory (default demo/output)
"""
from __future__ import annotations

import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
OUTDIR = os.environ.get("OUTDIR", os.path.join(os.path.dirname(__file__), "output"))
SHOTS = os.path.join(OUTDIR, "shots")
os.makedirs(SHOTS, exist_ok=True)

step_no = 0
_t0 = [None]            # video-relative clock origin
timeline: list[dict] = []   # [{"t": sec_from_video_start, "caption": "..."}]

# A subtitle overlay rendered INTO the page, so captions are baked into the
# recorded video natively (this ffmpeg build has no subtitles/drawtext filter).
_OVERLAY_JS = """
() => {
  let el = document.getElementById('__demo_cap');
  if (!el) {
    el = document.createElement('div');
    el.id = '__demo_cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:36px;transform:translateX(-50%);'
      + 'max-width:78%;padding:10px 20px;background:rgba(0,0,0,0.68);color:#fff;'
      + 'font:600 23px/1.45 -apple-system,\\'PingFang SC\\',sans-serif;border-radius:12px;'
      + 'z-index:99999;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.45);';
    document.body.appendChild(el);
  }
  return true;
}
"""


def shot(page, name: str) -> None:
    global step_no
    step_no += 1
    path = os.path.join(SHOTS, f"{step_no:02d}_{name}.png")
    page.screenshot(path=path)
    print(f"  📸 {os.path.basename(path)}")


def cap(page, text: str) -> None:
    """Show a narration caption on-page and mark its video-relative time."""
    page.evaluate(_OVERLAY_JS)
    page.evaluate("t => document.getElementById('__demo_cap').textContent = t", text)
    t = 0.0 if _t0[0] is None else max(0.0, time.time() - _t0[0])
    timeline.append({"t": round(t, 2), "caption": text})
    print(f"  💬 [{t:5.1f}s] {text}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            record_video_dir=OUTDIR,
            record_video_size={"width": 1366, "height": 900},
        )
        page = ctx.new_page()
        _t0[0] = time.time()   # video recording started at context creation ≈ now

        print("→ open subtitle page")
        page.goto(BASE)
        page.wait_for_selector("text=已连接", timeout=10000)
        cap(page, "EchoTranslate：实时把英文音频翻成中文字幕")
        time.sleep(1.4)
        shot(page, "home")

        print("→ start replay: 技术分享")
        page.select_option("#replaySel", "tech_talk")
        time.sleep(0.6)
        page.click("#replayBtn")

        # first Chinese subtitle
        page.wait_for_selector(".seg .seg-zh", timeout=30000)
        cap(page, "边说边译，无需等整句说完")
        time.sleep(1.4)
        shot(page, "first_subtitles")

        # the auto-correction (字幕回滚) — wait for a [修正] badge
        print("→ wait for auto-correction (字幕回滚)")
        page.wait_for_selector(".seg.corrected .badge", timeout=40000)
        cap(page, "自动纠错：存储 修正为 分布式存储")
        time.sleep(1.4)
        shot(page, "correction_1")

        # let the rest of the talk + second correction play out
        try:
            page.wait_for_function(
                "document.querySelectorAll('.seg.corrected').length >= 2", timeout=40000)
        except Exception:
            pass
        cap(page, "缓存 修正为 分布式缓存，最近几秒字幕可回滚")
        time.sleep(1.6)
        shot(page, "correction_2")

        # add a glossary term live
        print("→ add glossary term (Pulsar)")
        cap(page, "术语记忆：Kubernetes 等保持原样，不被音译")
        page.fill("#gTerm", "Pulsar")
        page.fill("#gTrans", "Pulsar")
        page.click("#gAdd")
        time.sleep(1.6)
        shot(page, "glossary")

        # summary (replay auto-triggers it at the end)
        print("→ wait for AI summary (会议纪要)")
        try:
            page.wait_for_selector("#summaryBox:not(.hidden)", timeout=40000)
            page.wait_for_function(
                "document.getElementById('summaryText').textContent.length > 5", timeout=20000)
        except Exception:
            page.click("#summaryBtn")
            page.wait_for_selector("#summaryBox:not(.hidden)", timeout=20000)
        cap(page, "一键生成中文会议纪要")
        time.sleep(1.2)
        page.eval_on_selector("#summaryBox", "el => el.scrollIntoView({block:'center'})")
        time.sleep(1.0)
        shot(page, "summary")

        # QoS dashboard
        print("→ open QoS dashboard")
        page.goto(BASE + "/dashboard")
        page.wait_for_selector(".metric", timeout=10000)
        # wait until a latency value has populated
        page.wait_for_function(
            "[...document.querySelectorAll('.metric .value')].some(e => /ms|%|\\d/.test(e.textContent) && e.textContent.trim() !== '–')",
            timeout=10000)
        cap(page, "QoS 看板：延迟、成功率、术语命中率，全部达标")
        time.sleep(2.5)  # let one poll cycle refresh + checks render
        shot(page, "dashboard")
        page.eval_on_selector("#sessions", "el => el.scrollIntoView({block:'center'})")
        time.sleep(2.0)
        shot(page, "dashboard_history")

        time.sleep(1.2)
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()

    with open(os.path.join(OUTDIR, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    print(f"✅ timeline: {os.path.join(OUTDIR, 'timeline.json')}")

    if video and os.path.exists(video):
        final = os.path.join(OUTDIR, "echo_translate_demo.webm")
        os.replace(video, final)
        print(f"\n✅ video: {final}")
    print(f"✅ screenshots: {SHOTS}")


if __name__ == "__main__":
    main()
