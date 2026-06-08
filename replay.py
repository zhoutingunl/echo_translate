"""Scripted replay transcripts for a reliable, reproducible demo.

These are **not** fake results: replay only substitutes the *source* text that
would normally come from the microphone. Every translation and every correction is
produced by the real AI pipeline at run time. Replay exists so the demo can
deterministically exercise the auto-correction path (ASR revisions + glossary)
without depending on flaky live audio.

Each step is one of:
  {"t": ms_after_previous, "action": "final",  "text": "..."}            -> new segment
  {"t": ms,                "action": "revise", "seg": <id>, "text": "..."} -> correct a segment
  {"t": ms,                "action": "interim","text": "..."}            -> volatile preview
"""
from __future__ import annotations

REPLAY_SCRIPTS = {
    "tech_talk": {
        "title": "技术分享：分布式存储系统",
        "source_lang": "English",
        "lang_code": "en-US",
        "steps": [
            {"t": 300,  "action": "interim", "text": "hello everyone"},
            {"t": 700,  "action": "final",  "text": "Hello everyone, welcome to today's tech talk."},
            {"t": 1200, "action": "interim", "text": "today we focus on our storage"},
            {"t": 900,  "action": "final",  "text": "Today we focus on our storage system."},
            # ASR correction: storage -> distributed storage (design.md §10)
            {"t": 1600, "action": "revise", "seg": 2,
             "text": "Today we focus on our distributed storage system."},
            {"t": 1100, "action": "final",  "text": "It uses Kafka for the message queue."},
            {"t": 1300, "action": "final",  "text": "And Redis as the cache layer."},
            # translation correction: cache -> distributed cache (design.md §10)
            {"t": 1500, "action": "revise", "seg": 4,
             "text": "And Redis as the distributed cache layer."},
            {"t": 1200, "action": "final",  "text": "The whole platform runs on Kubernetes."},
            {"t": 1000, "action": "final",  "text": "Thank you, let's start the demo."},
        ],
    },
    "conference": {
        "title": "国际会议：AI 与实时系统",
        "source_lang": "English",
        "lang_code": "en-US",
        "steps": [
            {"t": 400,  "action": "final",  "text": "Good morning. Let's talk about latency."},
            {"t": 1200, "action": "final",  "text": "Real time systems must keep the delay low."},
            {"t": 1300, "action": "final",  "text": "We measure the P95 and P99 latency."},
            {"t": 1200, "action": "final",  "text": "The GPU handles the heavy inference."},
            {"t": 1400, "action": "revise", "seg": 4,
             "text": "The GPU cluster handles the heavy inference."},
            {"t": 1200, "action": "final",  "text": "That is the key to a good user experience."},
        ],
    },
}
