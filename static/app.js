/* EchoTranslate front-end controller.
 * - browser Web Speech API for ASR, SpeechSynthesis for Chinese TTS
 * - WebSocket to the server which runs the AI translation + revision pipeline
 * - renders live subtitles and applies in-place corrections ([修正])
 */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const subtitles = $("subtitles"), interimEl = $("interim");
  const micBtn = $("micBtn"), connEl = $("conn");
  let ws = null, sessionId = null, recog = null, listening = false;
  let ttsOn = false, spokenVersion = {}; // seg id -> last spoken version

  // ---------------------------------------------------------------- WebSocket
  function connect() {
    return new Promise((resolve) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => { setConn(true); resolve(); };
      ws.onclose = () => { setConn(false); ws = null; };
      ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
    });
  }
  function setConn(on) {
    connEl.textContent = on ? "已连接" : "未连接";
    connEl.className = "pill " + (on ? "pill-on" : "pill-off");
  }
  function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }

  async function ensureSession(langCode, lang) {
    if (!ws) await connect();
    sessionId = "s_" + Math.random().toString(36).slice(2, 10);
    spokenVersion = {};
    clearSubtitles();
    send({ action: "start", session_id: sessionId,
           source_lang: lang, mode: $("modeSel").value });
  }

  // ------------------------------------------------------------- event router
  function handleEvent(ev) {
    switch (ev.type) {
      case "started": renderGlossary(ev.glossary); break;
      case "interim": interimEl.textContent = ev.text ? "… " + ev.text : ""; break;
      case "segment": upsertSegment(ev.segment, false); interimEl.textContent = ""; break;
      case "revision": upsertSegment(ev.segment, true, ev.previous); break;
      case "metrics": renderMetrics(ev.data); break;
      case "summary": showSummary(ev.text); break;
      case "error": console.warn("server:", ev.message); break;
    }
  }

  // -------------------------------------------------------------- subtitle DOM
  function clearSubtitles() { subtitles.innerHTML = ""; }
  function segEl(id) { return document.getElementById("seg-" + id); }

  function upsertSegment(seg, corrected, previous) {
    let el = segEl(seg.id);
    if (!el) {
      el = document.createElement("div");
      el.id = "seg-" + seg.id;
      el.className = "seg";
      el.innerHTML = `<div class="seg-src"></div><div class="seg-zh"></div>`;
      subtitles.appendChild(el);
    }
    el.querySelector(".seg-src").textContent = seg.source;
    const zh = el.querySelector(".seg-zh");
    zh.innerHTML = "";
    zh.appendChild(document.createTextNode(seg.translation || "…"));
    if (corrected || seg.corrected) {
      el.classList.add("corrected");
      const badge = document.createElement("span");
      badge.className = "badge"; badge.textContent = "修正";
      zh.appendChild(badge);
      el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
      if (previous && previous !== seg.translation) {
        let prevEl = el.querySelector(".seg-prev");
        if (!prevEl) { prevEl = document.createElement("div"); prevEl.className = "seg-prev"; el.appendChild(prevEl); }
        prevEl.textContent = previous;
      }
    }
    subtitles.scrollTop = subtitles.scrollHeight;
    speak(seg);
  }

  // --------------------------------------------------------------------- TTS
  function speak(seg) {
    if (!ttsOn || !seg.translation) return;
    if (spokenVersion[seg.id] === seg.version) return; // already spoke this version
    spokenVersion[seg.id] = seg.version;
    try {
      const u = new SpeechSynthesisUtterance(seg.translation);
      u.lang = "zh-CN"; u.rate = 1.05;
      window.speechSynthesis.speak(u);
    } catch (_) { /* TTS unsupported */ }
  }

  // ----------------------------------------------------------------- metrics
  function renderMetrics(m) {
    if (!m) return;
    $("mAvg").textContent = m.latency_ms.avg ? Math.round(m.latency_ms.avg) + " ms" : "–";
    $("mP95").textContent = m.latency_ms.p95 ? Math.round(m.latency_ms.p95) + " ms" : "–";
    $("mSucc").textContent = (m.translation_success_rate * 100).toFixed(0) + "%";
    $("mCorr").textContent = m.corrections;
    $("mGlo").textContent = (m.glossary_hit_rate * 100).toFixed(0) + "%";
  }
  function showSummary(text) {
    $("summaryBox").classList.remove("hidden");
    $("summaryText").textContent = text || "（无内容）";
  }

  // ------------------------------------------------------------- Web Speech ASR
  function startMic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("当前浏览器不支持 Web Speech API，请使用 Chrome，或改用「示例回放」。"); return; }
    const langCode = $("langSel").value;
    const lang = $("langSel").selectedOptions[0].textContent.split(" →")[0];
    ensureSession(langCode, lang).then(() => {
      recog = new SR();
      recog.lang = langCode; recog.continuous = true; recog.interimResults = true;
      recog.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) send({ action: "final", text: r[0].transcript.trim() });
          else interim += r[0].transcript;
        }
        if (interim) { interimEl.textContent = "… " + interim; send({ action: "interim", text: interim }); }
      };
      recog.onend = () => { if (listening) recog.start(); }; // auto-restart while live
      recog.onerror = (e) => console.warn("ASR error", e.error);
      recog.start();
      listening = true; micBtn.textContent = "⏹️ 停止"; micBtn.classList.add("live");
    });
  }
  function stopMic() {
    listening = false;
    if (recog) { recog.stop(); recog = null; }
    send({ action: "stop" });
    micBtn.textContent = "🎙️ 开始聆听"; micBtn.classList.remove("live");
  }

  // ----------------------------------------------------------------- replay
  let replayScripts = {};
  async function loadReplays() {
    replayScripts = await (await fetch("/api/replay")).json();
    const sel = $("replaySel"); sel.innerHTML = "";
    for (const [key, s] of Object.entries(replayScripts)) {
      const o = document.createElement("option"); o.value = key; o.textContent = s.title; sel.appendChild(o);
    }
  }
  async function playReplay() {
    const script = replayScripts[$("replaySel").value];
    if (!script) return;
    if (listening) stopMic();
    await ensureSession(script.lang_code, script.source_lang);
    $("replayBtn").disabled = true;
    for (const step of script.steps) {
      await sleep(step.t);
      if (step.action === "interim") { interimEl.textContent = "… " + step.text; send({ action: "interim", text: step.text }); }
      else if (step.action === "final") send({ action: "final", text: step.text });
      else if (step.action === "revise") send({ action: "revise", seg_id: step.seg, text: step.text });
    }
    await sleep(600); send({ action: "summarize" });
    $("replayBtn").disabled = false;
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ---------------------------------------------------------------- glossary
  async function loadGlossary() { renderGlossary(await (await fetch("/api/glossary")).json()); }
  function renderGlossary(map) {
    const ul = $("glossaryList"); ul.innerHTML = "";
    Object.entries(map || {}).sort().forEach(([term, tr]) => {
      const li = document.createElement("li");
      li.innerHTML = `<span><b>${term}</b> → ${tr}</span>`;
      const del = document.createElement("button"); del.className = "del"; del.textContent = "×";
      del.onclick = async () => { await fetch("/api/glossary", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ term }) }); loadGlossary(); };
      li.appendChild(del); ul.appendChild(li);
    });
  }
  async function addGlossary() {
    const term = $("gTerm").value.trim(); if (!term) return;
    const translation = $("gTrans").value.trim();
    await fetch("/api/glossary", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ term, translation }) });
    send({ action: "glossary_add", term, translation });
    $("gTerm").value = ""; $("gTrans").value = ""; loadGlossary();
  }

  // ------------------------------------------------------------------- wiring
  micBtn.onclick = () => (listening ? stopMic() : startMic());
  $("ttsChk").onchange = (e) => { ttsOn = e.target.checked; if (!ttsOn) window.speechSynthesis.cancel(); };
  $("modeSel").onchange = (e) => send({ action: "mode", mode: e.target.value });
  $("replayBtn").onclick = playReplay;
  $("summaryBtn").onclick = () => send({ action: "summarize" });
  $("gAdd").onclick = addGlossary;

  loadReplays(); loadGlossary(); connect();
})();
