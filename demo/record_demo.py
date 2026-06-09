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

import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
OUTDIR = os.environ.get("OUTDIR", os.path.join(os.path.dirname(__file__), "output"))
SHOTS = os.path.join(OUTDIR, "shots")
os.makedirs(SHOTS, exist_ok=True)

step_no = 0


def shot(page, name: str) -> None:
    global step_no
    step_no += 1
    path = os.path.join(SHOTS, f"{step_no:02d}_{name}.png")
    page.screenshot(path=path)
    print(f"  📸 {os.path.basename(path)}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            record_video_dir=OUTDIR,
            record_video_size={"width": 1366, "height": 900},
        )
        page = ctx.new_page()

        print("→ open subtitle page")
        page.goto(BASE)
        page.wait_for_selector("text=已连接", timeout=10000)
        time.sleep(1.0)
        shot(page, "home")

        print("→ start replay: 技术分享")
        page.select_option("#replaySel", "tech_talk")
        time.sleep(0.6)
        page.click("#replayBtn")

        # first Chinese subtitle
        page.wait_for_selector(".seg .seg-zh", timeout=30000)
        time.sleep(1.2)
        shot(page, "first_subtitles")

        # the auto-correction (字幕回滚) — wait for a [修正] badge
        print("→ wait for auto-correction (字幕回滚)")
        page.wait_for_selector(".seg.corrected .badge", timeout=40000)
        time.sleep(1.0)
        shot(page, "correction_1")

        # let the rest of the talk + second correction play out
        try:
            page.wait_for_function(
                "document.querySelectorAll('.seg.corrected').length >= 2", timeout=40000)
        except Exception:
            pass
        time.sleep(1.2)
        shot(page, "correction_2")

        # add a glossary term live
        print("→ add glossary term (Pulsar)")
        page.fill("#gTerm", "Pulsar")
        page.fill("#gTrans", "Pulsar")
        page.click("#gAdd")
        time.sleep(1.0)
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
        time.sleep(1.2)
        page.eval_on_selector("#summaryBox", "el => el.scrollIntoView({block:'center'})")
        time.sleep(0.6)
        shot(page, "summary")

        # QoS dashboard
        print("→ open QoS dashboard")
        page.goto(BASE + "/dashboard")
        page.wait_for_selector(".metric", timeout=10000)
        # wait until a latency value has populated
        page.wait_for_function(
            "[...document.querySelectorAll('.metric .value')].some(e => /ms|%|\\d/.test(e.textContent) && e.textContent.trim() !== '–')",
            timeout=10000)
        time.sleep(2.5)  # let one poll cycle refresh + checks render
        shot(page, "dashboard")
        page.eval_on_selector("#sessions", "el => el.scrollIntoView({block:'center'})")
        time.sleep(1.5)
        shot(page, "dashboard_history")

        time.sleep(1.0)
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()

    if video and os.path.exists(video):
        final = os.path.join(OUTDIR, "echo_translate_demo.webm")
        os.replace(video, final)
        print(f"\n✅ video: {final}")
    print(f"✅ screenshots: {SHOTS}")


if __name__ == "__main__":
    main()
