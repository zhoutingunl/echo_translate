/* QoS dashboard — polls /dashboard/data and renders live metrics vs targets. */
(() => {
  "use strict";
  const fmtMs = (v) => (v ? Math.round(v) + " ms" : "–");
  const pct = (v) => (v * 100).toFixed(1) + "%";

  function cls(pass) { return pass === null ? "na" : pass ? "ok" : "bad"; }
  function mark(pass) { return pass === null ? "—" : pass ? "✅ 达标" : "❌ 未达标"; }

  function metricCard(label, value, check, fmtTarget) {
    const c = check || { pass: null };
    const edge = c.pass === null ? "" : (c.pass ? " ok-edge" : " bad-edge");
    return `<div class="metric${edge}">
      <div class="label">${label}</div>
      <div class="value ${cls(c.pass)}">${value}</div>
      <div class="target ${cls(c.pass)}">${fmtTarget ? "目标 " + fmtTarget + " · " : ""}${mark(c.pass)}</div>
    </div>`;
  }

  async function refresh() {
    let d;
    try { d = await (await fetch("/dashboard/data")).json(); } catch (_) { return; }
    const m = d.live, c = d.checks;
    document.getElementById("metrics").innerHTML = [
      metricCard("字幕延迟 (avg)", fmtMs(m.latency_ms.avg), c.e2e_avg, "< 2000 ms"),
      metricCard("P95 延迟", fmtMs(m.latency_ms.p95), c.e2e_p95, "< 3000 ms"),
      metricCard("P99 延迟", fmtMs(m.latency_ms.p99), null),
      metricCard("RTF 实时率", m.rtf || "–", c.rtf, "< 1.0"),
      metricCard("翻译成功率", pct(m.translation_success_rate), c.translation_success_rate, "> 95%"),
      metricCard("术语命中率", pct(m.glossary_hit_rate), c.glossary_hit_rate, "> 95%"),
      metricCard("纠错次数 / 字幕数", `${m.corrections} / ${m.segments}`, null),
      metricCard("纠错率", pct(m.correction_rate), null),
      metricCard("累计翻译字数", m.total_target_chars, null),
      metricCard("翻译调用 P95", fmtMs(m.translate_ms.p95), null),
    ].join("");

    const sb = document.querySelector("#sessions tbody");
    sb.innerHTML = (d.sessions || []).map((s) =>
      `<tr><td>${s.id}</td><td>${s.source_lang || ""}</td><td>${s.mode || ""}</td><td>${s.segment_count}</td><td>${s.started_at ? new Date(s.started_at * 1000).toLocaleString() : ""}</td></tr>`
    ).join("") || `<tr><td colspan="5" class="muted">暂无会话</td></tr>`;

    const eb = document.querySelector("#events tbody");
    const ev = d.event_counts || {};
    eb.innerHTML = Object.keys(ev).length
      ? Object.entries(ev).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")
      : `<tr><td colspan="2" class="muted">暂无埋点</td></tr>`;
  }

  refresh();
  setInterval(refresh, 2000);
})();
