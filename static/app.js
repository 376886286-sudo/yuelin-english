/* 英语口语陪练 · 前端应用(hash 路由,双模式) */
(() => {
  "use strict";

  const app = document.getElementById("app");
  const toastEl = document.getElementById("toast");

  /* ---------------- 工具 ---------------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path, opts = {}) {
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok && data.error) throw new Error(data.error);
    return data;
  }
  const postJSON = (path, body) => api(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });

  let toastTimer;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2200);
  }

  function speak(text, onEnd) {
    if (!text) { if (onEnd) setTimeout(onEnd, 0); return; }
    if (window.__azureOn) {
      fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      }).then((res) => {
        if (res.ok && (res.headers.get("content-type") || "").includes("audio")) {
          return res.blob().then((blob) => {
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            audio.onended = () => { URL.revokeObjectURL(url); if (onEnd) onEnd(); };
            audio.onerror = () => { URL.revokeObjectURL(url); if (onEnd) onEnd(); };
            audio.play().catch(() => { URL.revokeObjectURL(url); if (onEnd) onEnd(); });
          });
        }
        throw new Error("browser-fallback");
      }).catch(() => { browserSpeak(text, onEnd); });
      return;
    }
    browserSpeak(text, onEnd);
  }

  function browserSpeak(text, onEnd) {
    if (!("speechSynthesis" in window) || !text) { if (onEnd) setTimeout(onEnd, 0); return; }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US"; u.rate = 0.92; u.pitch = 1.05;
    u.onend = () => { if (onEnd) onEnd(); };
    u.onerror = () => { if (onEnd) onEnd(); };
    window.speechSynthesis.speak(u);
  }
  window.speak = speak; // 供模板内联 onclick(单词朗读)使用

  /* ---------------- 会话全局状态 ---------------- */
  let session = null;      // 后端会话
  let course = null;       // 当前课程
  let segTrack = [];       // 环节代号列表
  let callActive = false;  // 自动通话模式是否开启
  let sessionStart = 0;    // 会话开始时间戳(ms)

  /* ---------------- 路由 ---------------- */
  const routes = {
    "/": renderLaunch,
    "/learn": renderCourses,
    "/learn/s": renderSession,
    "/learn/done": renderDone,
    "/parent": renderPin,
    "/parent/dashboard": renderDashboard,
    "/parent/lessons": renderLessons,
    "/parent/review": renderReview,
    "/parent/records": renderRecords,
    "/parent/records/": renderRecordDetail,
    "/parent/settings": renderSettings,
  };

  function route() {
    const hash = location.hash.replace(/^#/, "") || "/";
    const parts = hash.split("/");
    let handler = routes[hash];
    if (!handler && hash.startsWith("/learn/s/")) { handler = routes["/learn/s"]; }
    if (!handler && hash.startsWith("/parent/records/")) { handler = routes["/parent/records/"]; }
    if (!handler) handler = renderLaunch;
    app.innerHTML = "";
    handler(parts);
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  /* ---------------- 启动页 ---------------- */
  function renderLaunch() {
    app.innerHTML = `
      <div class="launch">
        <div class="hero">
          <div class="logo">🗣️</div>
          <h1>悦琳英语口语</h1>
          <p>开口就有反馈 · 每天进步一点点</p>
        </div>
        <div class="mode-card learn" id="goLearn" role="button" tabindex="0">
          <div class="icon">📖</div>
          <div>
            <div class="t">开始练习</div>
            <div class="d">跟着 AI 老师开口说英语</div>
          </div>
          <div class="arrow">›</div>
        </div>
        <button class="parent-link" id="goParent">家长模式</button>
      </div>`;
    $("#goLearn").onclick = () => (location.hash = "/learn");
    $("#goParent").onclick = () => (location.hash = "/parent");
  }

  /* ---------------- 学习模式:课程列表 ---------------- */
  async function renderCourses() {
    app.innerHTML = `
      <div class="view">
        <nav class="glass nav">
          <button class="back" data-nav="/">‹ 返回</button>
          <div class="title">选择课程</div>
          <div class="spacer"></div>
          <button class="btn-ghost" data-nav="/parent">家长</button>
        </nav>
        <div class="content">
          <h2 class="page-title">今天练什么?</h2>
          <p class="page-sub caption">跟着 AI 教师,按教案一段一段开口说</p>
          <div class="course-grid" id="grid">加载中…</div>
        </div>
        <div class="glass cta-bar" id="ctaBar" style="display:none">
          <button class="btn btn-primary" id="startBtn" disabled>选择一个课程 · 开始练习</button>
        </div>
      </div>`;
    bindNav();
    try {
      const { courses } = await api("/api/lessons");
      const pack = await api("/api/review/pack");
      const reviewCount = (pack.pack?.errors || []).length;
      const grid = $("#grid");
      const ctaBar = $("#ctaBar");
      const startBtn = $("#startBtn");
      let selectedId = "";

      if (!courses.length) {
        grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="big">📚</div>还没有课程<br>请爸爸先在「家长模式」上传教案</div>`;
        return;
      }
      if (reviewCount > 0) {
        grid.insertAdjacentHTML("beforebegin", `<div class="card" style="margin-bottom:16px;display:flex;align-items:center;gap:12px">
          <div style="font-size:24px">📌</div>
          <div style="flex:1"><div style="font-weight:600">本次练习包含 ${reviewCount} 条易错点复习</div>
          <div class="caption">由爸爸在家长模式确认,练习完教案后自动追加</div></div>
        </div>`);
      }
      function updateSelection() {
        grid.querySelectorAll(".course-card").forEach((el) => {
          el.classList.toggle("selected", el.dataset.id === selectedId);
        });
        if (selectedId) {
          const c = courses.find((x) => x.id === selectedId);
          startBtn.disabled = false;
          startBtn.textContent = `开始练习 · Unit ${c?.unit || "?"} ${c?.title_zh || ""}`;
        } else {
          startBtn.disabled = true;
          startBtn.textContent = "选择一个课程 · 开始练习";
        }
      }
      const grads = [
        "linear-gradient(135deg,#3DB9FF,#8A5CFF)",
        "linear-gradient(135deg,#34D399,#3DB9FF)",
        "linear-gradient(135deg,#FBBF24,#F87171)",
        "linear-gradient(135deg,#A78BFA,#F472B6)",
      ];
      grid.innerHTML = courses.map((c, i) => {
        const segs = (c.segments || []).map((s) => `${s.code} ${s.minutes}′`).join(" · ");
        const g = grads[i % grads.length];
        return `
        <div class="course-card" data-id="${esc(c.id)}">
          <div class="emoji" style="background:${g}">📖</div>
          <div class="name">Unit ${esc(c.unit || "?")} ${esc(c.title_zh || "")}</div>
          <div class="meta">${esc(c.title_en || "")}</div>
          <div class="meta" style="margin-top:6px">${esc(segs || "三环节")}</div>
        </div>`;
      }).join("");
      if (ctaBar) ctaBar.style.display = "flex";
      grid.querySelectorAll(".course-card").forEach((el) => {
        el.onclick = () => { selectedId = (selectedId === el.dataset.id ? "" : el.dataset.id); updateSelection(); };
        // 鼠标追踪光晕
        el.addEventListener("mousemove", (e) => {
          const rect = el.getBoundingClientRect();
          const x = ((e.clientX - rect.left) / rect.width) * 100;
          const y = ((e.clientY - rect.top) / rect.height) * 100;
          el.style.setProperty("--mouse-x", x + "%");
          el.style.setProperty("--mouse-y", y + "%");
        });
      });
      startBtn.onclick = () => { if (selectedId) location.hash = `/learn/s/${selectedId}`; };
    } catch (e) { toast(e.message); }
  }

  /* ---------------- 学习模式:会话页(核心) ---------------- */
  async function renderSession(parts) {
    const courseId = parts[3];
    course = null; session = null;
    app.innerHTML = `
      <div class="view session-view">
        <nav class="glass nav">
          <button class="back" data-nav="/learn">‹ 课程</button>
          <div class="title" id="navTitle">加载课程…</div>
          <div class="spacer"></div>
          <div class="seg-track" id="segTrack"></div>
        </nav>
        <div class="seg-hero" id="segHero">
          <div class="seg-icon" id="segIcon">🤝</div>
          <div class="seg-info">
            <div class="seg-name" id="segName">加载中…</div>
            <div class="seg-meta" id="segMeta"></div>
          </div>
        </div>
        <div class="content" id="thread"></div>
        <div class="speak-stage" id="speakStage" data-stage="idle">
          <div class="stage-mic">
            <button class="big-mic-btn" id="bigMicBtn" aria-label="开始说话">
              <span class="big-mic-icon" id="bigMicIcon">🎙️</span>
            </button>
            <div class="stage-pulse" id="stagePulse"></div>
          </div>
          <div class="stage-text" id="stageText">点这里开始对话</div>
          <div class="stage-tip" id="stageTip">AI 老师说完后,你直接开口说英语</div>
          <div class="stage-actions" id="stageActions">
            <button class="btn-ghost" id="typeBtn">⌨️ 打字</button>
            <button class="btn btn-danger" id="endBtn">结束</button>
          </div>
        </div>
      </div>`;
    bindNav();
    try {
      const { course: c } = await api(`/api/lessons`).then((r) => ({ course: r.courses.find((x) => x.id === courseId) }));
      if (!c) throw new Error("课程不存在");
      course = c;
      segTrack = (c.segments || []).map((s) => s.code);
      $("#navTitle").textContent = `Unit ${c.unit || ""} ${c.title_zh || ""}`;
      renderSegTrack(0);
      const res = await postJSON("/api/chat/session", { course_id: courseId });
      session = res.session;
      sessionStart = Date.now();
      if (res.review_count > 0) segTrack.push("REVIEW");
      renderSegTrack(0);
      if (res.review_count > 0) {
        const thread = $("#thread");
        const tip = document.createElement("div");
        tip.className = "seg-banner";
        tip.style.margin = "8px 0";
        tip.textContent = `练习完教案后,还有 ${res.review_count} 条易错点复习(家长已确认)`;
        thread.appendChild(tip);
      }
      // 录音舞台在模板里默认显示,这里只做防御性兜底
      $("#speakStage")?.classList.add("ready");
      try {
        const st = await api("/api/status");
        window.__azureOn = !!(st.azure && st.azure.enabled);
      } catch (e) { window.__azureOn = false; }
      bindSpeak();
      addAIMessage(res.ai_message, res.segment);
      updateSegment(res.segment);
    } catch (e) { toast(e.message); }
  }

  function updateSegment(segment) {
    if (!segment) return;
    const seg = (course.segments || []).find((s) => s.code === segment.code);
    if (seg) {
      $("#segName").textContent = seg.name_zh || segment.code;
      $("#segMeta").textContent = `${segment.code} · ${seg.minutes} 分钟`;
      $("#segIcon").textContent = segIcon(segment.code);
    } else if (segment.code === "REVIEW") {
      $("#segName").textContent = "复习往期易错点";
      $("#segMeta").textContent = "REVIEW · 巩固练习";
      $("#segIcon").textContent = "🔁";
    }
  }

  function segIcon(code) {
    const map = { MEET: "🤝", FEEL: "😊", FIND: "🔍", TEST: "📝", COLOR: "🎨", EAT: "🍎", COUNT: "🔢" };
    return map[code] || "📖";
  }

  function renderSegTrack(idx) {
    $("#segTrack").innerHTML = segTrack.map((code, i) =>
      `<div class="seg-dot ${i < idx ? "done" : i === idx ? "active" : ""}" title="${esc(code)}"></div>`).join("");
  }

  function addAIMessage(text, segment) {
    const thread = $("#thread");
    let segBanner = "";
    if (segment && segment.code === "REVIEW") {
      segBanner = `<div class="seg-banner">复习环节 · 往期易错点</div>`;
    } else if (segment && (course.segments || []).find((s) => s.code === segment.code)) {
      segBanner = `<div class="seg-banner">环节 ${esc(segment.code)} · ${esc(segment.name_zh)} · ${esc(segment.minutes)} 分钟</div>`;
    }
    const div = document.createElement("div");
    div.className = "msg ai";
    div.innerHTML = `
      <div class="avatar">🤖</div>
      <div class="bubble">
        ${segBanner}
        <div class="txt">${esc(text)}</div>
        <button class="bubble-translate" aria-label="查看中文意思"><span class="tr-icon">💡</span><span class="tr-text">看中文</span></button>
        <div class="bubble-zh" hidden></div>
        <div class="actions"><button class="replay">🔊 再听一遍</button></div>
      </div>`;
    thread.appendChild(div);
    $(`.replay`, div).onclick = () => speak(text, () => {});
    const trBtn = $(`.bubble-translate`, div);
    const trBox = $(`.bubble-zh`, div);
    trBtn.onclick = () => {
      const show = trBox.hidden;
      trBox.hidden = !show;
      trBtn.querySelector(".tr-text").textContent = show ? "收起" : "看中文";
      if (show && !trBox.textContent) trBox.textContent = "（中文翻译将在开启 DeepSeek 后自动生成）";
    };
    speak(text, () => {
      if (callActive && session && !session.done && window.__scheduleListen) {
        window.__scheduleListen();
      }
    });
    thread.scrollTop = thread.scrollHeight;
  }

  function addStudentMessage(text, feedback) {
    const thread = $("#thread");
    const div = document.createElement("div");
    div.className = "msg student";
    const words = (feedback?.words || []).map((w) =>
      `<span class="word ${w.label}" title="得分 ${w.score}">${esc(w.word)}</span>`).join("");
    div.innerHTML = `
      <div class="avatar">😊</div>
      <div class="bubble">
        <div class="txt">${esc(text)}</div>
        ${feedback ? `<div class="word-feedback">${words}</div>` : ""}
      </div>`;
    thread.appendChild(div);
    thread.scrollTop = thread.scrollHeight;
  }

  function bindSpeak() {
    const stage = $("#speakStage");
    const bigBtn = $("#bigMicBtn");
    const bigIcon = $("#bigMicIcon");
    const stageText = $("#stageText");
    const stageTip = $("#stageTip");
    const stageActions = $("#stageActions");
    const endBtn = $("#endBtn");
    const typeBtn = $("#typeBtn");

    // 简易打字弹窗(避免重写原 typeBar 逻辑)
    let typeBar = null, typeInput = null, typeSend = null;

    let recognition = null;
    let recorder = null;     // 录音管理器(Azure 真实链路)
    let finalText = "";
    let handled = false;

    function stopCall() {
      callActive = false;
      if (recognition) { try { recognition.stop(); } catch (e) {} }
      if (recorder) { stopRecorder(recorder); recorder = null; }
    }

    bigBtn.onclick = () => {
      if (callActive) return;
      callActive = true;
      setStage("listening");
      if (!initRecognition()) return;
      scheduleListen();
    };

    endBtn.onclick = () => { stopCall(); finishSession(); };

    typeBtn.onclick = () => {
      if (!typeBar) {
        typeBar = document.createElement("div");
        typeBar.className = "glass speak-bar";
        typeBar.id = "typeBar";
        typeBar.innerHTML = `
          <input type="text" id="typeInput" placeholder="悦琳说的话(英文),回车发送…" style="flex:1;font-size:16px">
          <button class="btn btn-primary" id="typeSend">发送</button>`;
        stage.parentNode.insertBefore(typeBar, stage.nextSibling);
        typeInput = typeBar.querySelector("#typeInput");
        typeSend = typeBar.querySelector("#typeSend");
        typeSend.onclick = () => {
          const v = (typeInput.value || "").trim();
          typeInput.value = "";
          if (v) { stopCall(); sendText(v, null); }
        };
        typeInput.addEventListener("keydown", (e) => { if (e.key === "Enter") typeSend.click(); });
      }
      typeBar.style.display = "flex";
      typeInput.focus();
    };

    /* ---- Azure 真实链路:录音 16kHz WAV → 上传识别 ---- */
    function initRecordRecognition() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        bigIcon.textContent = "⌨️";
        stageText.textContent = "打字模式";
        stageTip.textContent = "麦克风不可用,点「打字」输入";
        return false;
      }
      return true;
    }

    function startRecordListen() {
      if (!callActive) return;
      setStage("listening");
      handled = false;
      navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        if (!callActive) { stream.getTracks().forEach((t) => t.stop()); return; }
        const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(4096, 1, 1);
        const chunks = [];
        proc.onaudioprocess = (e) => { chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
        const gain = ctx.createGain(); gain.gain.value = 0; // 防回声:录音不进扬声器
        const analyser = ctx.createAnalyser(); analyser.fftSize = 1024;
        source.connect(proc); proc.connect(gain); gain.connect(ctx.destination);
        source.connect(analyser);
        const level = new Uint8Array(analyser.fftSize);
        let silenceMs = 0;
        const rec = { stream, ctx, source, proc, gain, analyser, chunks, stopped: false };
        recorder = rec;
        // 静音 1.6 秒 = 说完,自动结束(替代 Web Speech 的自动 end)
        rec.silTimer = setInterval(() => {
          analyser.getByteTimeDomainData(level);
          let max = 0;
          for (let i = 0; i < level.length; i++) { const v = Math.abs(level[i] - 128); if (v > max) max = v; }
          if (max < 12) { silenceMs += 200; if (silenceMs >= 1600) finishRecord(rec); }
          else { silenceMs = 0; }
        }, 200);
        // 单句硬上限 12 秒
        rec.hardTimer = setTimeout(() => finishRecord(rec), 12000);
      }).catch(() => {
        toast("麦克风不可用,请用打字输入");
        setStage("listening");
      });
    }

    function stopRecorder(rec) {
      if (!rec || rec.stopped) return;
      rec.stopped = true;
      clearInterval(rec.silTimer); clearTimeout(rec.hardTimer);
      try { rec.source.disconnect(); rec.proc.disconnect(); rec.gain.disconnect(); rec.analyser.disconnect(); } catch (e) {}
      rec.stream.getTracks().forEach((t) => t.stop());
      try { rec.ctx.close(); } catch (e) {}
    }

    function wavBlob(chunks) {
      let len = 0;
      chunks.forEach((c) => { len += c.length; });
      const pcm = new Int16Array(len);
      let off = 0;
      for (const c of chunks) for (let i = 0; i < c.length; i++) pcm[off++] = (c[i] < 0 ? c[i] * 0x8000 : c[i] * 0x7fff) | 0;
      const ab = new ArrayBuffer(44 + pcm.length * 2);
      const dv = new DataView(ab);
      const wstr = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
      wstr(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); wstr(8, "WAVE");
      wstr(12, "fmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
      dv.setUint32(24, 16000, true); dv.setUint32(28, 32000, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
      wstr(36, "data"); dv.setUint32(40, pcm.length * 2, true);
      new Int16Array(ab, 44).set(pcm);
      return new Blob([ab], { type: "audio/wav" });
    }

    function finishRecord(rec) {
      stopRecorder(rec);
      if (recorder === rec) recorder = null;
      if (!callActive || handled) return;
      handled = true;
      const blob = wavBlob(rec.chunks);
      if (blob.size < 2000) { // 太短 = 没说,重新听
        setStage("listening"); scheduleListen(); return;
      }
      setStage("thinking");
      sendAudio(blob).catch((err) => { toast(err.message); setStage("listening"); scheduleListen(); });
    }

    /* ---- 兜底:浏览器 Web Speech 识别 ---- */
    function initRecognition() {
      if (window.__azureOn) return initRecordRecognition();
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) {
        bigIcon.textContent = "⌨️";
        stageText.textContent = "打字模式";
        stageTip.textContent = "本浏览器不支持语音识别,点「打字」输入";
        return false;
      }
      recognition = new SR();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.continuous = false;
      recognition.maxAlternatives = 1;
      recognition.onstart = () => {
        handled = false;
        setStage("listening");
      };
      recognition.onresult = (e) => { finalText = (e.results[0][0].transcript || "").trim(); };
      recognition.onerror = () => { if (callActive && !handled) { handled = true; setStage("listening"); scheduleListen(); } };
      recognition.onend = async () => {
        if (!callActive || handled) return;
        handled = true;
        if (finalText) {
          const text = finalText; finalText = "";
          setStage("thinking");
          try { await sendText(text, null); }
          catch (err) { toast(err.message); setStage("listening"); scheduleListen(); }
        } else {
          setStage("listening");
          scheduleListen();
        }
      };
      return true;
    }

    function scheduleListen() {
      if (!callActive) return;
      setStage("listening");
      setTimeout(() => {
        if (!callActive) return;
        if (window.__azureOn) {
          startRecordListen();
        } else if (recognition && recognition.state !== "running") {
          try { recognition.start(); } catch (e) {}
        }
      }, 450);
    }
    window.__scheduleListen = scheduleListen;

    function setStage(name) {
      stage.setAttribute("data-stage", name);
      if (name === "idle") {
        bigIcon.textContent = "🎙️";
        stageText.textContent = "点这里开始对话";
        stageTip.textContent = "AI 老师说完后,你直接开口说英语";
        stageActions.style.display = "none";
      } else if (name === "listening") {
        bigIcon.textContent = "🎤";
        stageText.textContent = "正在听你说…";
        stageTip.textContent = "说完停顿一下,AI 老师会自动接话";
        stageActions.style.display = "flex";
      } else if (name === "thinking") {
        bigIcon.textContent = "⏳";
        stageText.textContent = "AI 老师思考中…";
        stageTip.textContent = "稍等一下,看老师怎么回应";
        stageActions.style.display = "flex";
      } else if (name === "done") {
        bigIcon.textContent = "🎉";
        stageText.textContent = "完成啦!";
        stageTip.textContent = "正在准备练习总结…";
        stageActions.style.display = "none";
      }
    }
    window.__setStage = setStage;
  }

  function expectedSentence() {
    if (!course || !course.segments) return "";
    const seg = course.segments[Math.min(session?.segment_idx ?? 0, course.segments.length - 1)];
    if (!seg) return "";
    const b = (seg?.dialogue || []).find(([r]) => r === "B");
    return (b && b[1]) || (seg?.patterns || [])[0] || "";
  }

  async function sendAudio(blob) {
    const fd = new FormData();
    fd.append("audio", blob, "speech.wav");
    fd.append("expected", expectedSentence());
    const r = await api("/api/recognize", { method: "POST", body: fd });
    const text = (r.text || "").trim();
    if (!text) { toast("没听清,再说一次好吗?"); return false; }
    await sendText(text, r.feedback || null);
    return true;
  }

  async function sendText(text, feedback) {
    if (!text || !session) return;
    addStudentMessage(text, feedback);
    setStage("thinking");
    try {
      const r = await postJSON("/api/chat/reply", { session, text, words: feedback ? feedback.words : undefined });
      session = r.session;
      if (r.feedback && !feedback) {
        // 打字链路没有真实词评,这里补插后端返回的逐词结果
        const lastMsg = [...$("#thread").querySelectorAll(".msg.student")].pop();
        const words = (r.feedback.words || []).map((w) =>
          `<span class="word ${w.label}" title="得分 ${w.score}" onclick="speak('${esc(w.word)}')">${esc(w.word)}</span>`).join("");
        if (lastMsg) lastMsg.querySelector(".bubble").insertAdjacentHTML("beforeend", `<div class="word-feedback">${words}</div>`);
      }
      // 鼓励反馈
      const encourage = r.encouragement || (r.grade ? encourageFor(r.grade) : "👍 收到!");
      appendEncourage(encourage);
      // 环节评级卡片(环节切换时)
      if (r.grade) showGradeCard(r.grade, r.segment_name);
      renderSegTrack(session.segment_idx);
      updateSegment(r.ai_message.segment);
      addAIMessage(r.ai_message.text, r.ai_message.segment);
      if (session.done) {
        setStage("done");
        setTimeout(() => finishSession(), 2500);
      } else {
        setStage("listening");
      }
    } catch (e) {
      toast(e.message);
      setStage("listening");
    }
  }

  function encourageFor(grade) {
    const map = {
      A: "🌟 完美!发音清晰又准确",
      B: "👍 很棒!继续保持",
      C: "💪 不错,再练一次会更好",
      D: "🌱 没关系,多说就熟悉了",
    };
    return map[grade] || "👍 收到!";
  }

  function appendEncourage(text) {
    const thread = $("#thread");
    const div = document.createElement("div");
    div.className = "encourage-msg";
    div.innerHTML = `<span>${esc(text)}</span>`;
    thread.appendChild(div);
    thread.scrollTop = thread.scrollHeight;
  }

  function showGradeCard(grade, name) {
    const thread = $("#thread");
    const reason = {
      A: "发音和节奏都很棒",
      B: "整体不错,继续保持",
      C: "有几个词需要再练练",
      D: "这一段有点难,慢慢来",
    }[grade] || "";
    const div = document.createElement("div");
    div.className = `grade-card grade-${grade}`;
    div.innerHTML = `
      <div class="grade-head">
        <div class="grade-icon">${grade}</div>
        <div class="grade-info">
          <div class="grade-label">本环节完成</div>
          <div class="grade-name">${esc(name || "")}</div>
        </div>
      </div>
      <div class="grade-reason">${esc(reason)}</div>`;
    thread.appendChild(div);
    thread.scrollTop = thread.scrollHeight;
  }

  async function finishSession() {
    try {
      const durationMin = sessionStart ? Math.round((Date.now() - sessionStart) / 60000) : 0;
      const r = await postJSON("/api/summary", { session, duration_min: Math.max(1, durationMin) });
      session = null;
      location.hash = "/learn/done";
    } catch (e) { toast(e.message); }
  }

  /* ---------------- 学习模式:完成页 ---------------- */
  function renderDone() {
    app.innerHTML = `
      <div class="launch">
        <div class="hero" style="animation:fadeIn .4s">
          <div style="font-size:56px;margin-bottom:8px">🎉</div>
          <h1>太棒了!</h1>
          <p style="font-size:18px;max-width:420px;margin:12px auto 0">You took your time and kept speaking.<br>That is real progress.</p>
        </div>
        <div class="mode-card learn" id="again" style="width:300px">
          <div class="icon">📖</div>
          <div><div class="t">再练一次</div><div class="d">回到课程列表</div></div>
        </div>
        <div class="mode-card parent" id="home" style="width:300px">
          <div class="icon">🏠</div>
          <div><div class="t">回到首页</div><div class="d">练习完成,记录已自动保存</div></div>
        </div>
      </div>`;
    $("#again").onclick = () => (location.hash = "/learn");
    $("#home").onclick = () => (location.hash = "/");
  }

  /* ---------------- 家长模式:PIN ---------------- */
  const PIN_MAX_TRIES = 5;
  const PIN_LOCK_MS = 30000;

  function renderPin() {
    if (sessionStorage.getItem("parent_ok")) { location.hash = "/parent/dashboard"; return; }
    let pin = "";
    let errorCount = 0;
    let lockUntil = Number(sessionStorage.getItem("pin_lock_until") || 0);

    function remainingSec() {
      const ms = lockUntil - Date.now();
      return ms > 0 ? Math.ceil(ms / 1000) : 0;
    }
    function lockedHtml() {
      const sec = remainingSec();
      const total = PIN_LOCK_MS / 1000; // 30
      const circumference = 2 * Math.PI * 52; // ~326.73
      const offset = circumference * (1 - sec / total);
      return `
        <div class="pin-lock-ring">
          <svg viewBox="0 0 120 120">
            <defs>
              <linearGradient id="lockGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#3DB9FF"/>
                <stop offset="100%" stop-color="#8A5CFF"/>
              </linearGradient>
            </defs>
            <circle class="bg-circle" cx="60" cy="60" r="52"/>
            <circle class="fg-circle" cx="60" cy="60" r="52"
              stroke-dasharray="${circumference}"
              stroke-dashoffset="${offset}"/>
          </svg>
          <div class="lock-icon">🔒</div>
          <div class="lock-countdown" id="lockCountdown">${sec}</div>
        </div>
        <h2 class="page-title" style="text-align:center">已锁定</h2>
        <p class="page-sub caption" style="text-align:center">连续输错 ${PIN_MAX_TRIES} 次,请等待 <b>${sec}</b> 秒后重试</p>
        <button class="btn-ghost" data-nav="/" style="margin-top:24px">‹ 返回首页</button>`;
    }
    function startCountdown() {
      if (remainingSec() <= 0) { location.hash = "/parent"; return; }
      const el = $("#lockCountdown");
      const circle = document.querySelector(".fg-circle");
      if (!el || !circle) return;
      const total = PIN_LOCK_MS / 1000;
      const circumference = 2 * Math.PI * 52;
      const t = setInterval(() => {
        const sec = remainingSec();
        if (sec <= 0) { clearInterval(t); location.hash = "/parent"; return; }
        el.textContent = sec;
        const offset = circumference * (1 - sec / total);
        circle.setAttribute("stroke-dashoffset", offset);
      }, 1000);
    }

    if (lockUntil > Date.now()) {
      app.innerHTML = `<div class="view"><div class="content center">${lockedHtml()}</div></div>`;
      bindNav();
      startCountdown();
      return;
    }

    app.innerHTML = `
      <div class="view"><div class="content center">
        <div class="pin-logo">👨‍👧</div>
        <h2 class="page-title" style="text-align:center">家长模式</h2>
        <p class="page-sub caption" style="text-align:center">输入 4 位 PIN(默认 1234)</p>
        <div class="pin-dots" id="dots">
          <div class="pin-dot" id="dot0"></div><div class="pin-dot" id="dot1"></div>
          <div class="pin-dot" id="dot2"></div><div class="pin-dot" id="dot3"></div>
        </div>
        <div class="pin-keypad" id="pad"></div>
        <button class="btn-ghost" data-nav="/" style="margin-top:24px">‹ 返回首页</button>
      </div></div>`;
    bindNav();
    const pad = $("#pad");
    const keys = ["1","2","3","4","5","6","7","8","9","","0","⌫"];
    pad.innerHTML = keys.map((k) => k ? `<button type="button" class="pin-key" data-k="${esc(k)}">${esc(k)}</button>` : `<div></div>`).join("");
    function renderDots() { for (let i = 0; i < 4; i++) $("#dot" + i).classList.toggle("filled", i < pin.length); }
    async function submit() {
      try {
        const r = await api("/api/parent/verify", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: `pin=${encodeURIComponent(pin)}` });
        if (r.ok) {
          errorCount = 0;
          sessionStorage.removeItem("pin_lock_until");
          sessionStorage.setItem("parent_ok", "1");
          location.hash = "/parent/dashboard";
          return;
        }
        throw new Error("PIN 不正确");
      } catch (e) {
        errorCount++;
        if (errorCount >= PIN_MAX_TRIES) {
          lockUntil = Date.now() + PIN_LOCK_MS;
          sessionStorage.setItem("pin_lock_until", String(lockUntil));
          location.hash = "/parent";
          return;
        }
        toast(`${e.message || "PIN 不正确"},还可试 ${PIN_MAX_TRIES - errorCount} 次`);
        pin = "";
        renderDots();
      }
    }
    pad.querySelectorAll(".pin-key").forEach((b) => {
      b.addEventListener("click", () => {
        const k = b.dataset.k;
        if (k === "⌫") { pin = pin.slice(0, -1); }
        else if (pin.length < 4) { pin += k; }
        renderDots();
        if (pin.length === 4) submit();
      });
    });
  }

  /* ---------------- 家长模式:仪表盘 ---------------- */
  async function renderDashboard() {
    if (!requireParent()) return;
    app.innerHTML = parentShell("仪表盘", `
      <div class="metric-grid stagger-metrics">
        <div class="metric"><div class="label">本周练习次数</div><div class="value" id="mCount">–</div></div>
        <div class="metric"><div class="label">本周时长(分)</div><div class="value" id="mMin">–</div></div>
        <div class="metric"><div class="label">平均评级</div><div class="value" id="mGrade">–</div></div>
      </div>
      <div class="section">
        <h3>最近会话</h3>
        <div class="list stagger-list" id="recent"></div>
      </div>`);
    bindParentNav();
    try {
      const { records } = await api("/api/sessions");
      $("#mCount").textContent = records.length || 0;
      $("#mMin").textContent = records.reduce((s, r) => s + (r.duration_min || 0), 0) || 0;
      const grades = records.flatMap((r) => Object.values(r.segments_grades || {}));
      $("#mGrade").textContent = grades.length ? grades[0] : "–";
      $("#recent").innerHTML = records.length ? records.slice(0, 5).map((r) => `
        <div class="row" data-id="${esc(r.id)}">
          <div class="main"><div class="t">${esc(r.course_title)}</div><div class="d">${esc(r.date)} · ${esc(r.duration_min || 0)} 分钟</div></div>
          <div class="right">${gradeChips(r.segments_grades)}</div>
        </div>`).join("")
        : `<div class="empty" style="padding:24px">暂无练习记录</div>`;
      $("#recent").querySelectorAll(".row").forEach((el) => el.onclick = () => (location.hash = "/parent/records/" + el.dataset.id));
    } catch (e) { toast(e.message); }
  }

  function gradeChips(grades) {
    return Object.entries(grades || {}).map(([code, g]) =>
      `<span class="badge ${esc(g)}">${esc(code)} ${esc(g)}</span>`).join(" ");
  }

  /* ---------------- 家长模式:教案库(上传) ---------------- */
  async function renderLessons() {
    if (!requireParent()) return;
    let preview = null;
    app.innerHTML = parentShell("教案库", `
      <div class="section">
        <h3>上传教案</h3>
        <p class="caption" style="margin-bottom:12px">支持 TXT / MD / DOCX / DOC / PDF / 图片(PNG·JPG),可多选。DeepSeek 解析后确认入库。</p>
        <input type="file" id="fileInput" multiple accept=".txt,.md,.docx,.doc,.pdf,.png,.jpg,.jpeg,.webp" style="display:none">
        <div class="dropzone" id="dropzone">
          <div class="big">📤</div>
          <div>点击或拖入教案文件</div>
          <div class="caption">TXT · MD · DOCX · DOC · PDF · 图片</div>
        </div>
      </div>
      <div class="section" id="previewBox" style="display:none">
        <h3>解析预览</h3>
        <div class="card" id="preview"></div>
        <div style="display:flex;gap:12px;margin-top:12px">
          <button class="btn btn-primary" id="confirmBtn">确认入库</button>
          <button class="btn btn-secondary" id="cancelBtn">取消</button>
        </div>
      </div>
      <div class="section">
        <h3>课程库</h3>
        <div id="courseToolbar" style="display:none;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap">
          <span id="toolbarCount" style="font-size:14px;color:var(--text-2)">已选 0 个</span>
          <button class="btn btn-danger" id="batchDel" style="padding:6px 16px;font-size:13px">删除选中</button>
        </div>
        <div class="list stagger-list" id="courseList"></div>
      </div>`, false, false);
    bindParentNav();
    const dz = $("#dropzone");
    const fi = $("#fileInput");
    dz.onclick = () => fi.click();
    fi.onchange = () => uploadFiles(fi.files);
    ["dragover", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => {
      e.preventDefault();
      if (ev === "drop") uploadFiles(e.dataTransfer.files);
    }));
    dz.addEventListener("dragover", () => dz.classList.add("drag"));
    dz.addEventListener("dragleave", () => dz.classList.remove("drag"));

    async function uploadFiles(files) {
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        try {
          toast(`解析 ${f.name}…`);
          const r = await api("/api/lessons/upload", { method: "POST", body: fd });
          preview = r.preview;
          const pb = $("#previewBox"); if (pb) pb.style.display = "block";
          $("#preview").innerHTML = previewHtml(preview);
        } catch (e) { toast(e.message); }
      }
    }
    $("#confirmBtn").onclick = async () => {
      if (!preview) return;
      try {
        const r = await postJSON("/api/lessons", { lesson: preview });
        toast("课程已入库");
        const pb2 = $("#previewBox"); if (pb2) pb2.style.display = "none";
        renderCoursesList();
      } catch (e) { toast(e.message); }
    };
    $("#cancelBtn").onclick = () => { preview = null; const pb3 = $("#previewBox"); if (pb3) pb3.style.display = "none"; };
    renderCoursesList();

    function previewHtml(p) {
      if (p.image_pending) {
        return `<div class="caption" style="color:var(--text-2)">🖼️ <b>${esc(p.source)}</b><br>图片教案已保存。接入 DeepSeek 视觉后自动解析,当前为待处理状态。</div>`;
      }
      const segs = (p.segments || []).map((s) =>
        `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:0.5px solid var(--border)">
          <span class="badge B">${esc(s.code)}</span>
          <span>${esc(s.name_zh)} · ${s.minutes} 分钟</span>
          <span class="caption" style="margin-left:auto">${esc((s.patterns || [])[0] || "")}</span>
        </div>`).join("");
      return `
        <div style="font-size:18px;font-weight:600">Unit ${esc(p.unit || "?")} ${esc(p.title_zh)}</div>
        <div class="caption" style="margin:4px 0 12px">${esc(p.title_en)} · ${esc(p.source)}</div>
        ${segs || `<div class="caption">未识别到环节,可确认后手动检查</div>`}`;
    }

    async function renderCoursesList() {
      const { courses } = await api("/api/lessons");
      const checked = new Set();
      const toolbar = $("#courseToolbar");
      const countEl = $("#toolbarCount");
      const batchDel = $("#batchDel");

      function updateToolbar() {
        if (checked.size > 0) {
          toolbar.style.display = "flex";
          countEl.textContent = `已选 ${checked.size} 个`;
        } else {
          toolbar.style.display = "none";
        }
      }

      batchDel.onclick = () => {
        if (!confirm(`确认删除已选的 ${checked.size} 个课程?`)) return;
        Promise.all([...checked].map((id) => api("/api/lessons/" + id, { method: "DELETE" })))
          .then(() => { toast("已删除"); renderCoursesList(); })
          .catch((e) => toast(e.message));
      };

      if (!courses.length) {
        $("#courseList").innerHTML = `<div class="empty" style="padding:24px">还没有课程,先上传教案吧</div>`;
        toolbar.style.display = "none";
        return;
      }
      $("#courseList").innerHTML = courses.map((c) => `
        <div class="row" data-cid="${esc(c.id)}">
          <label class="row-check" onclick="event.stopPropagation()">
            <input type="checkbox" data-cid="${esc(c.id)}">
          </label>
          <div class="main"><div class="t">Unit ${esc(c.unit || "?")} ${esc(c.title_zh)}</div>
          <div class="d">${esc(c.title_en || "")} · ${esc(c.source || "")}</div></div>
          <div class="right">
            <button class="btn-ghost" data-del="${esc(c.id)}" style="color:var(--weak)">删除</button>
          </div>
        </div>`).join("");

      // 行点击 → 勾选/取消
      $("#courseList").querySelectorAll(".row").forEach((row) => {
        row.onclick = (e) => {
          if (e.target.closest("[data-del]")) return;  // 不拦截删除按钮
          const cb = row.querySelector("input[type=checkbox]");
          cb.checked = !cb.checked;
          cb.dispatchEvent(new Event("change"));
        };
      });

      // checkbox 变化 → 更新选中集
      $("#courseList").querySelectorAll("input[type=checkbox]").forEach((cb) => {
        cb.addEventListener("change", () => {
          if (cb.checked) checked.add(cb.dataset.cid);
          else checked.delete(cb.dataset.cid);
          updateToolbar();
        });
      });

      // 单行删除
      $("#courseList").querySelectorAll("[data-del]").forEach((b) => {
        b.onclick = async (e) => {
          e.stopPropagation();
          if (!confirm("确认删除该课程?")) return;
          await api("/api/lessons/" + b.dataset.del, { method: "DELETE" });
          renderCoursesList();
        };
      });
    }
  }

  /* ---------------- 家长模式:易错点复习(家长确认) ---------------- */
  async function renderReview() {
    if (!requireParent()) return;
    app.innerHTML = parentShell("易错点复习", `
      <div class="section">
        <h3>往期易错点</h3>
        <p class="caption" style="margin-bottom:12px">从历史跟读记录中提取。勾选后确认,下节课练习完教案会自动追加这些复习。最多 6 条。</p>
        <div class="list stagger-list" id="errorList">加载中…</div>
      </div>
      <div style="display:flex;gap:12px;margin-bottom:32px">
        <button class="btn btn-primary" id="savePack">确认并保存复习包</button>
        <button class="btn btn-secondary" id="clearPack">清空复习</button>
      </div>
      <div class="section">
        <h3>当前复习包</h3>
        <div class="list stagger-list" id="curPack"></div>
      </div>`, false, false);
    bindParentNav();
    let allErrors = [];
    let selected = new Set();
    try {
      const [r1, r2] = await Promise.all([api("/api/review/errors"), api("/api/review/pack")]);
      allErrors = r1.errors || [];
      (r2.pack?.errors || []).forEach((e) => selected.add(e.text + e.drill));
      renderList();
    } catch (e) { toast(e.message); }

    function renderList() {
      const list = $("#errorList");
      if (!allErrors.length) {
        list.innerHTML = `<div class="empty" style="padding:32px"><div class="big">📝</div>暂无历史记录<br>等孩子练过一次之后,这里会出现易错点</div>`;
        return;
      }
      list.innerHTML = allErrors.map((e, i) => {
        const key = e.text + e.drill;
        return `
        <div class="row" data-i="${i}">
          <input type="checkbox" id="cb${i}" style="width:20px;height:20px;accent-color:var(--accent)" ${selected.has(key) ? "checked" : ""}>
          <div class="main">
            <div class="t">${esc(e.text)}</div>
            <div class="d">${esc(e.drill || "整句跟读复习")} · 来自 ${esc(e.source)}</div>
          </div>
        </div>`;
      }).join("");
      list.querySelectorAll(".row").forEach((row) => {
        row.onclick = (ev) => {
          if (ev.target.type === "checkbox") return;
          const cb = $("#cb" + row.dataset.i);
          cb.checked = !cb.checked;
        };
      });
    }
    $("#savePack").onclick = async () => {
      const picked = allErrors.filter((e, i) => $("#cb" + i)?.checked);
      if (!picked.length) { toast("请先勾选要复习的内容"); return; }
      try {
        await postJSON("/api/review/pack", { errors: picked });
        toast("复习包已保存,下节课生效");
        const r2 = await api("/api/review/pack");
        renderCur(r2.pack);
      } catch (e) { toast(e.message); }
    };
    $("#clearPack").onclick = async () => {
      try {
        await postJSON("/api/review/pack", { errors: [] });
        toast("复习包已清空");
        renderCur({ errors: [] });
      } catch (e) { toast(e.message); }
    };
    function renderCur(pack) {
      $("#curPack").innerHTML = (pack.errors || []).length
        ? pack.errors.map((e) => `<div class="row"><div class="main"><div class="t">${esc(e.text)}</div><div class="d">${esc(e.drill || "")}</div></div></div>`).join("")
        : `<div class="empty" style="padding:20px">当前未设置复习内容</div>`;
    }
    renderCur((await api("/api/review/pack")).pack);
  }

  /* ---------------- 家长模式:会话记录 ---------------- */
  async function renderRecords() {
    if (!requireParent()) return;
    app.innerHTML = parentShell("会话记录", `
      <div class="list stagger-list" id="records"></div>`);
    bindParentNav();
    try {
      const { records } = await api("/api/sessions");
      $("#records").innerHTML = records.length ? records.map((r) => `
        <div class="row" data-id="${esc(r.id)}">
          <div class="main"><div class="t">${esc(r.course_title)}</div>
          <div class="d">${esc(r.date)} · ${esc(r.duration_min || 0)} 分钟</div></div>
          <div class="right">${gradeChips(r.segments_grades)}</div>
        </div>`).join("") : `<div class="empty" style="padding:32px"><div class="big">📝</div>暂无会话记录</div>`;
      $("#records").querySelectorAll(".row").forEach((el) => el.onclick = () => (location.hash = "/parent/records/" + el.dataset.id));
    } catch (e) { toast(e.message); }
  }

  async function renderRecordDetail(parts) {
    if (!requireParent()) return;
    const id = parts[3];
    app.innerHTML = parentShell("记录详情", `<div id="detail">加载中…</div>`, true);
    bindParentNav();
    try {
      const { record } = await api(`/api/sessions/${id}`);
      const lines = (record.student_lines || []).map((l) => `<div class="row"><div class="main"><div class="t">${esc(l)}</div></div></div>`).join("");
      const weakLines = (record.weak_lines || []).map((l) => `<div class="row"><div class="main"><div class="t">${esc(l)}</div><div class="d">发音需加强,已进入易错点候选</div></div></div>`).join("");
      $("#detail").innerHTML = `
        <div class="card" style="margin-bottom:16px">
          <div style="font-size:18px;font-weight:600">${esc(record.course_title)}</div>
          <div class="caption" style="margin:4px 0 12px">${esc(record.date)} · ${esc(record.duration_min || 0)} 分钟</div>
          <div class="grades-row">${gradeChips(record.segments_grades)}</div>
        </div>
        <div class="section"><h3>悦琳说过的句子</h3><div class="list">${lines || `<div class="empty" style="padding:20px">暂无摘录</div>`}</div></div>
        ${weakLines ? `<div class="section"><h3>说错/待加强的句子</h3><div class="list">${weakLines}</div></div>` : ""}
        <div class="section"><h3>易错点总结</h3>
          <div class="card" style="padding:16px 20px">${(record.summary?.error_points || []).map((p) => `<div style="padding:4px 0">· ${esc(p)}</div>`).join("")}</div>
        </div>
        <div class="section"><h3>复习计划</h3>
          <div class="list">${Object.entries(record.review_plan || {}).map(([d, v]) => `<div class="row"><div class="main"><div class="t">${esc(d)}</div><div class="d">${esc(v)}</div></div></div>`).join("")}</div>
        </div>
        <div class="section"><h3>总结</h3>
          <div class="card" style="padding:16px 20px;color:var(--text-2)">${esc(record.closing || "")}</div>
        </div>`;
    } catch (e) { toast(e.message); }
  }

  /* ---------------- 家长模式:设置 ---------------- */
  async function renderSettings() {
    if (!requireParent()) return;
    app.innerHTML = parentShell("设置", `
      <div class="section">
        <h3>API 配置</h3>
        <p class="caption" style="margin-bottom:12px">Key 只保存在本机后端 .env,浏览器不接触。保存后需重启服务生效。</p>
        <div class="card">
          <div class="form-group"><label>DeepSeek API Key</label><input type="text" id="dk" placeholder="sk-..."></div>
          <div class="form-group"><label>Azure 语音 Key</label><input type="text" id="ak" placeholder="azure speech key"></div>
          <div class="form-group"><label>Azure 区域</label><input type="text" id="ar" placeholder="eastasia" value="eastasia"></div>
          <button class="btn btn-primary" id="saveKeys">保存 Key</button>
        </div>
      </div>
      <div class="section">
        <h3>学员信息</h3>
        <div class="list" id="studentInfo"></div>
      </div>
      <div class="section">
        <h3>用量(本月)</h3>
        <div class="card" id="usage">加载中…</div>
      </div>`);
    bindParentNav();
    try {
      const cfg = await api("/api/config");
      $("#studentInfo").innerHTML = `
        <div class="row"><div class="main"><div class="t">${esc(cfg.student?.name || "悦琳")}</div><div class="d">${esc(cfg.student?.grade || "")} · ${esc(cfg.student?.level || "")}</div></div></div>
        <div class="row"><div class="main"><div class="t">服务状态</div><div class="d">DeepSeek: ${cfg.deepseek ? "已配置" : "mock"} · Azure: ${cfg.azure ? "已配置" : "mock"}</div></div></div>`;
      const u = await api("/api/usage");
      $("#usage").innerHTML = `
        <div class="metric-grid" style="margin:0">
          <div class="metric"><div class="label">识别(秒)</div><div class="value">${Math.round(u.usage.stt_seconds || 0)}</div></div>
          <div class="metric"><div class="label">合成(字符)</div><div class="value">${Math.round(u.usage.tts_chars || 0)}</div></div>
        </div>`;
    } catch (e) { toast(e.message); }
    $("#saveKeys").onclick = async () => {
      try {
        await postJSON("/api/config/keys", { deepseek_key: $("#dk").value, azure_key: $("#ak").value, azure_region: $("#ar").value });
        toast("已保存,重启服务后生效");
      } catch (e) { toast(e.message); }
    };
  }

  /* ---------------- 家长外壳 ---------------- */
  function parentShell(title, body, back = false, noCta = true) {
    return `
      <div class="view">
        <nav class="glass nav">
          ${back ? `<button class="back" data-nav="/parent/records">‹ 返回</button>` : `<button class="back" data-nav="/">‹ 首页</button>`}
          <div class="title">${esc(title)}</div>
          <div class="spacer"></div>
        </nav>
        <div class="content${noCta ? " no-cta" : ""}">
          <div class="tabbar">
            ${[["📊 仪表盘", "/parent/dashboard"], ["📚 教案库", "/parent/lessons"], ["📌 易错点", "/parent/review"], ["💬 会话记录", "/parent/records"], ["⚙ 设置", "/parent/settings"]]
              .map(([t, h]) => `<button class="tab-btn" data-nav="${h}">${t}</button>`).join("")}
          </div>
          ${body}
        </div>
      </div>`;
  }

  function requireParent() {
    if (sessionStorage.getItem("parent_ok")) return true;
    location.hash = "/parent";
    return false;
  }

  function bindNav() {
    app.querySelectorAll("[data-nav]").forEach((el) => {
      el.onclick = () => { location.hash = el.dataset.nav; };
    });
  }
  function bindParentNav() {
    app.querySelectorAll("[data-nav]").forEach((el) => {
      el.onclick = () => { location.hash = el.dataset.nav; };
    });
    app.querySelectorAll(".tabbar .tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.nav === location.hash);
    });
  }

  /* ---------------- 启动 ---------------- */
  route();
})();
