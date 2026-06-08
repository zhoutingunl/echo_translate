from dashboard import dashboard_payload, _check, build_dashboard, TARGETS
from flask import Flask
from metrics import MetricsCollector


def test_check_pass_fail_skip():
    assert _check(1000, 3000, lower_is_better=True)["pass"] is True
    assert _check(4000, 3000, lower_is_better=True)["pass"] is False
    assert _check(0.99, 0.95, lower_is_better=False)["pass"] is True
    assert _check(0.5, 0.95, lower_is_better=False)["pass"] is False
    assert _check(0, 3000, lower_is_better=True, skip=True)["pass"] is None


def test_payload_skips_when_no_data(store):
    payload = dashboard_payload(MetricsCollector(), store)
    assert payload["checks"]["e2e_p95"]["pass"] is None
    assert payload["targets"] == TARGETS
    assert payload["sessions"] == []


def test_payload_with_data(store):
    m = MetricsCollector()
    m.record_translation(end_to_end_ms=1000, translate_ms=900,
                         glossary_present=1, glossary_preserved=1)
    store.create_session("s1", "English", "presentation")
    store.log_event("s1", "subtitle_render")
    payload = dashboard_payload(m, store)
    assert payload["live"]["segments"] == 1
    assert payload["checks"]["translation_success_rate"]["pass"] is True
    assert payload["event_counts"]["subtitle_render"] == 1


def test_blueprint_routes(store):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.register_blueprint(build_dashboard(MetricsCollector(), store))
    c = app.test_client()
    assert c.get("/dashboard").status_code == 200
    assert c.get("/dashboard/data").status_code == 200
    assert "live" in c.get("/dashboard/data").get_json()
