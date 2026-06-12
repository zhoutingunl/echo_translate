/* EchoTranslate front-end controller.
 * - ASR: browser Web Speech API (Chrome/Edge) OR Bailian cloud ASR (Safari/Firefox
 *   fallback) — the latter streams 16kHz mono PCM over the WebSocket to the server.
 * - SpeechSynthesis for Chinese TTS.
 * - WebSocket to the server which runs the AI translation + revision pipeline;
 *   renders live subtitles and applies in-place corrections ([修正]).
 */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const subtitles = $("subtitles"), interimEl = $("interim");
  const micBtn = $("micBtn"), connEl = $("conn");
  let ws = null, sessionId = null, recog = null, listening = false;
  let ttsOn = false, spokenVersion = {}; // seg id -> last spoken version
  let cloudAvailable = false, activeBackend = null;
  // cloud-ASR audio capture handles
  let audioCtx = null, micStream = null, srcNode = null, procNode = null;

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hasWebSpeech = !!SR;
  const isChromium = /Chrome|Chromium|Edg\//.test(navigator.userAgent)
    && !/OPR\//.test(navigator.userAgent);

  // Resolve which ASR backend to use given the selector + capabilities.
  function resolveBackend() {
    const pref = $("asrSel") ? $("asrSel").value : "auto";
    if (pref === "webspeech") return hasWebSpeech ? "webspeech" : (cloudAvailable ? "cloud" : null);
    if (pref === "cloud") return cloudAvailable ? "cloud" : (hasWebSpeech ? "webspeech" : null);
    // auto: Chrome/Edge prefer the zero-latency Web Speech API; others -> cloud
    if (isChromium && hasWebSpeech) return "webspeech";
    if (cloudAvailable) return "cloud";
    return hasWebSpeech ? "webspeech" : null;
  }

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

  async function ensureSession(langCode, lang, asr) {
    if (!ws) await connect();
    sessionId = "s_" + Math.random().toString(36).slice(2, 10);
    spokenVersion = {};
    clearSubtitles();
    send({ action: "start", session_id: sessionId, source_lang: lang,
           mode: $("modeSel").value, asr: asr || "webspeech" });
  }

  // ------------------------------------------------------------- event router
  function handleEvent(ev) {
    switch (ev.type) {
      case "started":
        renderGlossary(ev.glossary);
        activeBackend = ev.asr;
        if (ev.asr === "cloud") interimEl.textContent = "（云端百炼 ASR 已就绪，请讲话…）";
        break;
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

  // ------------------------------------------------------------------- ASR
  function startMic() {
    const backend = resolveBackend();
    if (!backend) {
      alert("当前浏览器不支持 Web Speech API，且服务端未配置云端百炼 ASR。\n请用 Chrome/Edge，或改用「示例回放」。");
      return;
    }
    const langCode = $("langSel").value;
    const lang = $("langSel").selectedOptions[0].textContent.split(" →")[0];
    const live = () => { listening = true; micBtn.textContent = "⏹️ 停止"; micBtn.classList.add("live"); };
    ensureSession(langCode, lang, backend).then(() => {
      if (backend === "cloud") startCloudCapture().then(live).catch((err) => {
        console.warn(err); alert("无法获取麦克风：" + err.message); send({ action: "stop" });
      });
      else { startWebSpeech(langCode); live(); }
    });
  }

  function stopMic() {
    listening = false;
    if (recog) { try { recog.stop(); } catch (_) {} recog = null; }
    stopCloudCapture();
    send({ action: "stop" });
    micBtn.textContent = "🎙️ 开始聆听"; micBtn.classList.remove("live");
  }

  // --- browser Web Speech API (Chrome/Edge) ---
  function startWebSpeech(langCode) {
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
  }

  // --- Bailian cloud ASR: capture mic -> 16kHz mono PCM16 -> WebSocket (binary) ---
  async function startCloudCapture() {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    srcNode = audioCtx.createMediaStreamSource(micStream);
    procNode = audioCtx.createScriptProcessor(4096, 1, 1);
    const sink = audioCtx.createGain(); sink.gain.value = 0; // silent sink, no echo
    const inRate = audioCtx.sampleRate;
    procNode.onaudioprocess = (e) => {
      if (!listening || !ws || ws.readyState !== 1) return;
      const pcm = floatToPCM16(downsample(e.inputBuffer.getChannelData(0), inRate, 16000));
      ws.send(pcm); // binary ArrayBuffer
    };
    srcNode.connect(procNode); procNode.connect(sink); sink.connect(audioCtx.destination);
  }
  function stopCloudCapture() {
    if (procNode) { procNode.onaudioprocess = null; try { procNode.disconnect(); } catch (_) {} procNode = null; }
    if (srcNode) { try { srcNode.disconnect(); } catch (_) {} srcNode = null; }
    if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
    if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
  }
  function downsample(buf, inRate, outRate) {
    if (outRate >= inRate) return buf;
    const ratio = inRate / outRate, outLen = Math.floor(buf.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * ratio), end = Math.min(Math.floor((i + 1) * ratio), buf.length);
      let sum = 0, n = 0;
      for (let j = start; j < end; j++) { sum += buf[j]; n++; }
      out[i] = n ? sum / n : 0;
    }
    return out;
  }
  function floatToPCM16(f32) {
    const out = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out.buffer;
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

  // ------------------------------------------------------------- ASR backend UI
  async function loadConfig() {
    try {
      const cfg = await (await fetch("/api/config")).json();
      cloudAvailable = !!cfg.cloud_asr_available;
    } catch (_) { /* keep defaults */ }
    const sel = $("asrSel");
    if (!sel) return;
    const cloudLabel = cloudAvailable ? "云端百炼 (Bailian)" : "云端百炼 (未配置)";
    const auto = isChromium && hasWebSpeech ? "浏览器" : (cloudAvailable ? "云端百炼" : "浏览器");
    sel.innerHTML =
      `<option value="auto">自动（${auto}）</option>` +
      `<option value="webspeech"${hasWebSpeech ? "" : " disabled"}>浏览器 Web Speech</option>` +
      `<option value="cloud"${cloudAvailable ? "" : " disabled"}>${cloudLabel}</option>`;
  }

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

  loadConfig(); loadReplays(); loadGlossary(); connect();
})();
