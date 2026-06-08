"""QoS dashboard (§13).

A Flask blueprint exposing:

* ``GET /dashboard``       — the live metrics page
* ``GET /dashboard/data``  — JSON snapshot (process-wide live metrics + persisted
  history) polled by the page

It reads the process-wide :class:`MetricsCollector` (live QoS) and the
:class:`Store` (session history / 埋点 counts), so it works whether or not a
session is currently streaming.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from db import Store
from metrics import MetricsCollector

# QoS targets from design.md §12 — shown next to live values as pass/fail.
TARGETS = {
    "e2e_p95_ms": 3000,      # P95 字幕生成延迟 < 3s
    "e2e_avg_ms": 2000,      # 平均 < 2s
    "rtf": 1.0,              # 实时率 < 1
    "translation_success_rate": 0.95,
    "glossary_hit_rate": 0.95,
}


def build_dashboard(metrics: MetricsCollector, store: Store) -> Blueprint:
    bp = Blueprint("dashboard", __name__)

    @bp.route("/dashboard")
    def dashboard_page():
        return render_template("dashboard.html")

    @bp.route("/dashboard/data")
    def dashboard_data():
        return jsonify(dashboard_payload(metrics, store))

    return bp


def dashboard_payload(metrics: MetricsCollector, store: Store) -> dict:
    snap = metrics.snapshot()
    lat = snap["latency_ms"]
    checks = {
        "e2e_p95": _check(lat["p95"], TARGETS["e2e_p95_ms"], lower_is_better=True,
                          skip=lat["p95"] == 0),
        "e2e_avg": _check(lat["avg"], TARGETS["e2e_avg_ms"], lower_is_better=True,
                          skip=lat["avg"] == 0),
        "rtf": _check(snap["rtf"], TARGETS["rtf"], lower_is_better=True,
                      skip=snap["rtf"] == 0),
        "translation_success_rate": _check(snap["translation_success_rate"],
                                           TARGETS["translation_success_rate"],
                                           lower_is_better=False, skip=snap["segments"] == 0),
        "glossary_hit_rate": _check(snap["glossary_hit_rate"], TARGETS["glossary_hit_rate"],
                                    lower_is_better=False, skip=snap["glossary_present"] == 0),
    }
    return {
        "live": snap,
        "targets": TARGETS,
        "checks": checks,
        "sessions": store.list_sessions(limit=20),
        "event_counts": store.event_counts(),
    }


def _check(value: float, target: float, *, lower_is_better: bool, skip: bool = False) -> dict:
    if skip:
        passed = None
    elif lower_is_better:
        passed = value <= target
    else:
        passed = value >= target
    return {"value": value, "target": target, "pass": passed}
