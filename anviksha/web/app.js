/* ═══════════════════════════════════════════════════════════════
   Anviksha front-end — raise a curious mind.
   Talk to it (it learns from ordinary conversation), attach files,
   watch it explore the internet and grow. Zero dependencies.
   ═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const log = $("#chatlog");
  const input = $("#input");
  const sendBtn = $("#send");
  const form = $("#chatbar");
  const orb = $("#orb");

  let ST = null;                 // latest /api/stats payload
  let prevQuick = {};
  let attachments = [];          // [{name,size,data}]
  let busy = false;
  let greeted = false;
  let lastWebEvent = 0;

  /* ───────────── tiny helpers ───────────── */
  function http(path, method, body) {
    return fetch(path, {
      method: method || "GET",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then((r) => r.json());
  }
  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
  function md(text) {
    let h = escapeHtml(text);
    h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
    h = h.replace(/(^|[\s(>])\*([^*\n]+)\*/g, "$1<i>$2</i>");
    h = h.replace(/(https?:\/\/[^\s<&]+)/g,
      '<a href="$1" target="_blank" rel="noopener">$1</a>');
    return h;
  }
  function timeAgo(ts) {
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 5) return "now";
    if (s < 60) return Math.floor(s) + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }
  function fmtNum(n) { return (n == null ? 0 : n).toLocaleString(); }
  function fmtBytes(b) {
    if (b < 1024) return b + " B";
    if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
    return (b / 1048576).toFixed(1) + " MB";
  }
  function bufToB64(buf) {
    const bytes = new Uint8Array(buf);
    let bin = "";
    const CH = 0x8000;
    for (let i = 0; i < bytes.length; i += CH)
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    return btoa(bin);
  }

  /* ───────────── orb moods ───────────── */
  let moodTimer = null;
  function setOrb(state, mood, ms) {
    orb.className = "orb" + (state ? " " + state : "");
    if (ST && !ST.network && state !== "thinking" && state !== "exploring")
      orb.classList.add("offline");
    $("#orbmood").textContent = mood || "";
    if (moodTimer) clearTimeout(moodTimer);
    if (ms) moodTimer = setTimeout(() => setOrb("", "", 0), ms);
  }

  /* ───────────── toasts + confetti ───────────── */
  function toast(title, text, cls, ttl) {
    const el = document.createElement("div");
    el.className = "toast " + (cls || "");
    el.innerHTML = '<span class="tt">' + escapeHtml(title) + "</span>" +
      escapeHtml(text || "");
    el.onclick = () => kill();
    function kill() { el.classList.add("out"); setTimeout(() => el.remove(), 320); }
    $("#toasts").appendChild(el);
    setTimeout(kill, ttl || 5200);
    const box = $("#toasts");
    while (box.children.length > 4) box.firstChild.remove();
  }
  function confetti() {
    const colors = ["#5eead4", "#818cf8", "#fbbf24", "#f472b6", "#34d399", "#93c5fd"];
    for (let i = 0; i < 90; i++) {
      const c = document.createElement("div");
      c.className = "confetti";
      c.style.left = Math.random() * 100 + "vw";
      c.style.background = colors[i % colors.length];
      c.style.animationDuration = 1.6 + Math.random() * 2.2 + "s";
      c.style.animationDelay = Math.random() * 0.7 + "s";
      c.style.transform = "rotate(" + Math.random() * 360 + "deg)";
      document.body.appendChild(c);
      setTimeout(() => c.remove(), 4600);
    }
  }

  /* ───────────── chat messages ───────────── */
  function addMsg(text, who, opts) {
    opts = opts || {};
    const el = document.createElement("div");
    el.className = "msg " + who;
    const body = document.createElement("div");
    body.className = "body";
    if (who === "user" || who === "system") body.textContent = text;
    else body.innerHTML = md(text);
    el.appendChild(body);
    if (opts.badges && opts.badges.length) {
      const m = document.createElement("div");
      m.className = "meta";
      opts.badges.forEach((b) => {
        const s = document.createElement("span");
        s.className = "badge " + (b.cls || "");
        s.textContent = b.text;
        if (b.title) s.title = b.title;
        m.appendChild(s);
      });
      el.appendChild(m);
    }
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }
  function typingOn(label) {
    const el = document.createElement("div");
    el.className = "msg bot typing";
    el.innerHTML = '<span class="dots"><i></i><i></i><i></i></span> ' +
      '<span style="color:var(--muted);font-size:13px">' + escapeHtml(label || "thinking") + "…</span>";
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  /* ───────────── suggestions ───────────── */
  function renderSuggests() {
    const box = $("#suggests");
    box.innerHTML = "";
    let chips;
    const fresh = !ST || ST.knowledge.chunks < 3;
    if (fresh) {
      chips = ["hi! who are you?", "📎 attach a file to teach me",
        "go explore the internet", "what are you curious about?"];
    } else {
      chips = ["what did you learn from the internet?", "what are you curious about?",
        "what have you learned?", "go explore the internet", "wander randomly online",
        "reflect and grow"];
    }
    chips.forEach((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sugg";
      b.textContent = c;
      b.onclick = () => {
        if (c.startsWith("📎")) { $("#fileinput").click(); return; }
        input.value = c;
        send();
      };
      box.appendChild(b);
    });
  }

  /* ───────────── attachments ───────────── */
  function addFiles(fileList) {
    Array.from(fileList).forEach((f) => {
      if (f.size > 12 * 1024 * 1024) {
        toast("Too big 📎", f.name + " is over 12 MB - I can't carry that.", "web");
        return;
      }
      if (attachments.some((a) => a.name === f.name && a.size === f.size)) return;
      const reader = new FileReader();
      reader.onload = () => {
        attachments.push({ name: f.name, size: f.size, data: bufToB64(reader.result) });
        renderTray();
      };
      reader.readAsArrayBuffer(f);
    });
  }
  function renderTray() {
    const tray = $("#attachtray");
    tray.innerHTML = "";
    attachments.forEach((a, i) => {
      const c = document.createElement("span");
      c.className = "attchip";
      c.innerHTML = "📄 <span class='nm'>" + escapeHtml(a.name) + "</span>" +
        "<span class='sz'>" + fmtBytes(a.size) + "</span>";
      const x = document.createElement("span");
      x.className = "x"; x.textContent = "✕"; x.title = "remove";
      x.onclick = () => { attachments.splice(i, 1); renderTray(); };
      c.appendChild(x);
      tray.appendChild(c);
    });
  }
  $("#fileinput").addEventListener("change", (e) => {
    addFiles(e.target.files);
    e.target.value = "";
    input.focus();
  });
  $("#attachbtn").addEventListener("click", () => $("#fileinput").click());

  // drag & drop anywhere
  let dragDepth = 0;
  window.addEventListener("dragenter", (e) => {
    e.preventDefault(); dragDepth++;
    $("#dropoverlay").classList.add("on");
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("dragleave", (e) => {
    e.preventDefault();
    if (--dragDepth <= 0) { dragDepth = 0; $("#dropoverlay").classList.remove("on"); }
  });
  window.addEventListener("drop", (e) => {
    e.preventDefault(); dragDepth = 0;
    $("#dropoverlay").classList.remove("on");
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });

  /* ───────────── sending chat ───────────── */
  async function send() {
    const text = input.value.trim();
    if ((!text && !attachments.length) || busy) return;
    busy = true;
    input.value = "";
    resize();
    sendBtn.disabled = true;

    if (text) addMsg(text, "user");
    const attNote = attachments.slice();
    attNote.forEach((a) => addMsg("📎 attached " + a.name + " (" + fmtBytes(a.size) + ")", "system"));

    setOrb("thinking", "🤔");
    const typing = typingOn(attachments.length && !text ? "studying your files" : "thinking");

    try {
      const res = await http("/api/chat", "POST", { message: text, attachments });
      attachments = [];
      renderTray();
      typing.remove();

      const badges = [];
      if (res.grounded) badges.push({ cls: "grounded", text: "✓ from my knowledge", title: "answer grounded in what I learned" });
      const srcs = (res.facts_learned || []).map((f) => f.topic).filter(Boolean);
      if (res.files && res.files.length) badges.push({ cls: "file", text: "📚 " + res.files.filter(f=>f.ok).length + " file(s) studied" });
      if (res.xp_gained > 0) badges.push({ cls: "xp", text: "+" + res.xp_gained + " XP" });
      addMsg(res.reply || "…", "bot", { badges });

      handleMeta(res);
    } catch (e) {
      typing.remove();
      addMsg("(server hiccup — is Anviksha running?)", "bot");
    }
    busy = false;
    sendBtn.disabled = false;
    input.focus();
    refreshStats(); refreshActivity();
  }

  function handleMeta(res) {
    if (res.files) res.files.forEach((f) => {
      if (f.ok) {
        toast("📚 Studied “" + f.name + "”",
          f.passages + " passage(s) learned · +" + f.xp + " XP", "learn");
        setOrb("learning", "✨", 2600);
      } else {
        toast("📎 " + f.name, f.error || "couldn't read it", "web", 7000);
      }
    });
    (res.facts_learned || []).forEach((fl) => {
      toast("✨ Learned from you!", "“" + fl.fact.slice(0, 90) + "” · +" + fl.xp + " XP", "learn");
      setOrb("learning", "✨", 2600);
    });
    if (res.level_up) {
      confetti();
      toast("🎉 LEVEL UP!", "I grew into a " + res.level_up.stage +
        " (level " + res.level_up.level + ")!", "level", 9000);
    }
  }

  function resize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 150) + "px";
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); send(); });
  input.addEventListener("input", resize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  /* ───────────── tabs ───────────── */
  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tabpane").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      $("#tab-" + t.dataset.tab).classList.add("active");
      if (t.dataset.tab === "internet") { refreshJournal(); refreshCuriosity(); }
      if (t.dataset.tab === "brain") refreshBrain();
      if (t.dataset.tab === "progress") refreshStats();
      if (t.dataset.tab === "chat") input.focus();
    };
  });
  function activeTab() {
    const t = document.querySelector(".tab.active");
    return t ? t.dataset.tab : "chat";
  }

  /* ───────────── header ───────────── */
  function bump(id, val) {
    const el = $(id);
    if (!el) return;
    if (prevQuick[id] !== undefined && prevQuick[id] !== val) {
      el.parentElement.classList.add("bump");
      setTimeout(() => el.parentElement.classList.remove("bump"), 550);
    }
    prevQuick[id] = val;
    el.textContent = fmtNum(val);
  }
  function updateHeader() {
    if (!ST) return;
    const p = ST.progress;
    $("#lvlname").textContent = "Level " + p.level + " · " + p.stage;
    $("#xptext").textContent = fmtNum(p.xp) + " XP";
    $("#xpfill").style.width = (p.xp_next
      ? Math.max(2, Math.min(100, p.xp_progress)) : 100) + "%";
    $("#levelnext").textContent = p.xp_next
      ? (p.xp_next - p.xp) + " XP until the next stage"
      : "max stage reached — a truly wise mind ✨";
    const ageDays = Math.max(0, Math.floor(p.age_seconds / 86400));
    $("#stageline").textContent = p.stage.toLowerCase() + " · level " + p.level +
      " · " + (ageDays > 0 ? ageDays + " day(s) old" : "born " + timeAgo(Date.now()/1000 - p.age_seconds)) +
      (ST.user_name ? " · your friend " + ST.user_name : "");

    const pill = $("#netpill");
    if (ST.network) {
      pill.textContent = "🌐 online — I can explore!";
      pill.className = "netpill good";
    } else {
      pill.textContent = "🌐 offline — wonder journal ready";
      pill.className = "netpill bad";
    }
    bump("#qs-chunks", ST.knowledge.chunks);
    bump("#qs-mems", ST.memory.total);
    bump("#qs-pages", p.counters.web_page || 0);
    bump("#qs-curio", ST.curiosity.queued);
  }

  /* ───────────── progress tab ───────────── */
  const ORIGIN_META = {
    conversation: { color: "#34d399", label: "💬 conversation" },
    files:        { color: "#fbbf24", label: "📎 files" },
    internet:     { color: "#818cf8", label: "🌐 internet" },
    library:      { color: "#64748b", label: "📁 starter library" },
    other:        { color: "#f472b6", label: "✨ other" },
  };
  function card(ico, v, k, sub) {
    return '<div class="card"><div class="ico">' + ico + '</div><div class="v">' +
      fmtNum(v) + '</div><div class="k">' + escapeHtml(k) + "</div>" +
      (sub ? '<div class="sub2">' + escapeHtml(sub) + "</div>" : "") + "</div>";
  }
  function renderProgress() {
    if (!ST) return;
    const p = ST.progress, c = p.counters, o = ST.origins || {};
    const conv = o.conversation || {}, files = o.files || {}, web = o.internet || {}, lib = o.library || {};
    $("#statcards").innerHTML =
      card("🎯", p.xp, "experience points", "level " + p.level + " · " + p.stage) +
      card("💬", conv.chunks || 0, "learned from conversation", (c.fact_from_chat || 0) + " teaching moments") +
      card("📎", files.chunks || 0, "learned from files", (c.file_read || 0) + " file(s) studied") +
      card("🌐", web.chunks || 0, "learned from the internet", (c.web_page || 0) + " page(s) explored") +
      card("📚", ST.knowledge.chunks, "knowledge passages", (lib.chunks || 0) + " from starter library") +
      card("🧠", ST.memory.fact, "facts in long-term memory", ST.memory.total + " memories total") +
      card("💭", ST.curiosity.satisfied, "curiosities satisfied", ST.curiosity.queued + " still wondering") +
      card("📝", ST.version, "self-rewrites", "SELF.md versions");

    drawGrowth(p.series || []);
    drawDonut(o);

    // ladder
    const ladder = $("#ladder");
    ladder.innerHTML = "";
    (p.levels || []).forEach((L, i) => {
      const li = document.createElement("li");
      const done = p.xp >= L.xp && !(p.levels[i + 1] && p.xp >= p.levels[i + 1].xp) ? false : p.xp >= L.xp;
      li.className = done ? "done" : "";
      if (i + 1 === p.level) li.className = "now";
      li.innerHTML = '<span class="n">' + (done ? "✓" : i + 1) + "</span>" +
        escapeHtml(L.stage) + '<span class="xpneed">' + fmtNum(L.xp) + " XP</span>";
      ladder.appendChild(li);
    });

    // recent learning moments
    const rl = $("#recentlearn");
    rl.innerHTML = "";
    const ICON = { learned_from_chat: "💬", file_read: "📎", web_page: "🌐",
      gap_filled: "💭", evolve: "🧠", chat_turn: "" };
    (p.recent || []).filter(r => r.text).slice(0, 18).forEach((r) => {
      const li = document.createElement("li");
      li.innerHTML = '<span class="ic">' + (ICON[r.kind] || "✨") + "</span>" +
        '<span class="t">' + escapeHtml(r.text) + "</span>" +
        (r.xp ? '<span class="xpg">+' + r.xp + "</span>" : "") +
        '<span class="ago">' + timeAgo(r.ts) + "</span>";
      rl.appendChild(li);
    });
    if (!rl.children.length) rl.innerHTML = '<li class="empty">nothing learned yet — say something!</li>';

    // topic bubbles
    const bb = $("#topicbubbles");
    bb.innerHTML = "";
    const tags = ST.top_interests || [];
    tags.forEach((t) => {
      const s = document.createElement("span");
      s.className = "bubble";
      s.style.fontSize = Math.max(12, 17 - tags.indexOf(t)) + "px";
      s.innerHTML = escapeHtml(t);
      s.title = "an area I know things about";
      s.onclick = () => { input.value = "what do you know about " + t + "?"; 
        document.querySelector('.tab[data-tab="chat"]').click(); input.focus(); };
      s.style.cursor = "pointer";
      bb.appendChild(s);
    });
    if (!tags.length) bb.innerHTML = '<span class="empty">no interests yet — teach me things and interests will sprout</span>';
    $("#chart-hint").textContent = (p.series || []).length > 1 ? "" : "(grow a little more to see the curve!)";
  }

  function drawGrowth(series) {
    const cv = $("#growthchart");
    if (!cv) return;
    const ctx = cv.getContext("2d");
    const W = cv.width, H = cv.height, PAD = 34;
    ctx.clearRect(0, 0, W, H);
    // grid
    ctx.strokeStyle = "rgba(148,163,184,.12)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PAD / 2 + (H - PAD) * i / 4;
      ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - 8, y); ctx.stroke();
    }
    if (series.length < 2) {
      ctx.fillStyle = "#64748b";
      ctx.font = "13px sans-serif";
      ctx.fillText("keep chatting, attaching files and exploring — your growth curve will appear here", PAD, H / 2);
      return;
    }
    const keys = [["xp", "#5eead4"], ["chunks", "#818cf8"], ["mems", "#fbbf24"]];
    keys.forEach(([key, color]) => {
      const vals = series.map((s) => s[key] || 0);
      const max = Math.max(1, ...vals);
      ctx.beginPath();
      series.forEach((s, i) => {
        const x = PAD + (W - PAD - 10) * i / (series.length - 1);
        const y = H - PAD / 1.6 - (H - PAD) * (s[key] || 0) / max;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color; ctx.lineWidth = 2.2; ctx.stroke();
      // fill under
      ctx.lineTo(PAD + (W - PAD - 10), H - PAD / 1.6);
      ctx.lineTo(PAD, H - PAD / 1.6);
      ctx.closePath();
      ctx.fillStyle = color + "18"; ctx.fill();
    });
    // x labels
    ctx.fillStyle = "#64748b"; ctx.font = "10px sans-serif";
    const t0 = series[0].t, t1 = series[series.length - 1].t;
    ctx.fillText(new Date(t0 * 1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}), PAD, H - 6);
    ctx.fillText(new Date(t1 * 1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}), W - 60, H - 6);
  }

  function drawDonut(origins) {
    const cv = $("#donut");
    if (!cv) return;
    const ctx = cv.getContext("2d");
    const W = cv.width, H = cv.height, cx = W / 2, cy = H / 2, R = 78, r = 52;
    ctx.clearRect(0, 0, W, H);
    const rows = Object.keys(ORIGIN_META)
      .map((k) => ({ k, n: (origins[k] || {}).chunks || 0 }))
      .filter((x) => x.n > 0);
    const total = rows.reduce((a, b) => a + b.n, 0);
    const legend = $("#donutlegend");
    legend.innerHTML = "";
    if (!total) {
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7);
      ctx.strokeStyle = "#232c42"; ctx.lineWidth = R - r; ctx.stroke();
      legend.innerHTML = '<li class="empty">no knowledge yet</li>';
    } else {
      let a0 = -Math.PI / 2;
      rows.forEach((row) => {
        const a1 = a0 + 2 * Math.PI * row.n / total;
        ctx.beginPath();
        ctx.arc(cx, cy, (R + r) / 2, a0 + 0.03, a1 - 0.03);
        ctx.strokeStyle = ORIGIN_META[row.k].color;
        ctx.lineWidth = R - r;
        ctx.lineCap = "round";
        ctx.stroke();
        a0 = a1;
        const li = document.createElement("li");
        li.innerHTML = '<i style="background:' + ORIGIN_META[row.k].color + '"></i>' +
          ORIGIN_META[row.k].label + "<b>" + row.n + "</b>" +
          '<span class="pc">' + Math.round(100 * row.n / total) + "%</span>";
        legend.appendChild(li);
      });
    }
    ctx.fillStyle = "#e9edf5";
    ctx.font = "700 22px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(total), cx, cy + 2);
    ctx.fillStyle = "#64748b";
    ctx.font = "11px sans-serif";
    ctx.fillText("passages", cx, cy + 18);
    ctx.textAlign = "left";
  }

  /* ───────────── internet tab ───────────── */
  function renderNetPanel() {
    const el = $("#netstatuspanel");
    if (!el || !ST) return;
    if (ST.network) {
      el.innerHTML = '<span class="big" style="color:var(--good)">🌐 Internet reachable</span>' +
        '<span class="note">I explore on my own every ' + (ST.web_refresh_min || 10) +
        " minutes — chasing my wonder journal, my interests, and sometimes just wandering.</span>";
    } else {
      const q = (ST.curiosity && ST.curiosity.queued) || 0;
      el.innerHTML = '<span class="big" style="color:var(--warn)">🌐 Internet not reachable from here</span>' +
        '<span class="note">This environment blocks outbound access, so I can\'t browse right now — ' +
        "but I keep wondering! " + q + " topic(s) are queued in my journal, and the moment I'm online " +
        "(e.g. on your own machine) I'll chase them all by myself. Nothing below is faked.</span>";
    }
  }

  async function refreshJournal() {
    try {
      const j = await http("/api/journal");
      const ul = $("#journallist");
      ul.innerHTML = "";
      $("#journalcount").textContent = "(" + (j.pages_explored || 0) + " pages explored)";
      (j.journal || []).forEach((e) => {
        const li = document.createElement("li");
        li.innerHTML =
          '<div class="jhead"><span class="jtitle">' + escapeHtml(e.title || "?") + "</span>" +
          '<span class="jtopic">about: ' + escapeHtml(e.topic || "?") + "</span>" +
          '<span class="jmode">' + (e.mode === "wander" ? "🎈 wandered" : "🧭 explored") + "</span>" +
          '<span class="ago">' + timeAgo(e.ts) + "</span></div>" +
          '<div class="jdig">' + escapeHtml(e.digest || "") + "</div>" +
          '<div class="jlink"><a href="' + encodeURI(e.url || "#") + '" target="_blank" rel="noopener">🔗 ' +
          escapeHtml((e.url || "").replace(/^https?:\/\//, "").slice(0, 60)) + "</a>" +
          '<span class="jchunks">+' + (e.chunks || 0) + " passages learned</span></div>";
        ul.appendChild(li);
      });
      if (!ul.children.length)
        ul.innerHTML = '<li class="empty">nothing explored yet — press “Go explore” (needs internet access)</li>';
    } catch (e) { /* ignore */ }
  }

  async function refreshCuriosity() {
    try {
      const c = await http("/api/curiosity");
      const ul = $("#curiolist");
      ul.innerHTML = "";
      $("#curiocount").textContent = "(" + c.counts.queued + " wondering · " + c.counts.satisfied + " satisfied)";
      (c.items || []).forEach((it) => {
        const li = document.createElement("li");
        li.className = it.status === "satisfied" ? "satisfied" : it.reason;
        li.innerHTML =
          '<div><span class="topic">' + (it.status === "satisfied" ? "✅ " : "💭 ") +
          escapeHtml(it.topic) + "</span>" +
          (it.why ? '<div class="why">' + escapeHtml(it.why) + "</div>" : "") + "</div>" +
          '<span class="rtag">' + (it.status === "satisfied"
            ? "learned it!"
            : { gap: "🔥 asked & unknown", wonder: "wondering", interest: "interested", seed: "just curious" }[it.reason] || it.reason) +
          "</span>";
        ul.appendChild(li);
      });
      if (!ul.children.length)
        ul.innerHTML = '<li class="empty">my wonder journal is empty — ask me something I don\'t know!</li>';
    } catch (e) { /* ignore */ }
  }

  async function doExplore(mode, btn) {
    if (busy) return;
    btn.disabled = true;
    setOrb("exploring", "🧭");
    document.querySelector('.tab[data-tab="chat"]').click();
    const typing = typingOn(mode === "wander" ? "wandering around the internet" : "exploring the internet");
    try {
      const res = await http("/api/explore", "POST", { mode });
      typing.remove();
      if (res.ok && res.visits && res.visits.length) {
        const bits = res.visits.map((v) => "“" + v.title + "” (+" + v.chunks + " passages)").join(", ");
        addMsg("🌐 I " + (mode === "wander" ? "wandered around" : "went exploring") +
          " the internet and learned from " + res.visits.length + " page(s): " + bits +
          ". Filed in my 🌐 Internet journal!" + (res.xp ? " (+" + res.xp + " XP)" : ""),
          "bot", { badges: [{ cls: "xp", text: "🌐 explored" }] });
        toast("🌐 Back from exploring!", res.visits.length + " page(s) learned", "web");
        setOrb("learning", "✨", 2500);
      } else if (res.offline) {
        addMsg("🌐 I tried to go out but the internet isn't reachable from here. " +
          "My wonder journal is ready (" + ((res.topics || []).slice(0, 4).join(", ") || "so many topics") +
          "…) — on a machine with internet I'll chase them for real!", "bot");
        toast("🌐 Offline", "I can't reach the internet from this environment", "web", 7000);
        setOrb("", "💤", 2500);
      } else {
        addMsg("🌐 " + (res.error || "That trip didn't work out."), "bot");
        setOrb("", "", 0);
      }
    } catch (e) {
      typing.remove();
      addMsg("(exploration failed — server error)", "bot");
      setOrb("", "", 0);
    }
    btn.disabled = false;
    refreshStats(); refreshActivity(); refreshJournal(); refreshCuriosity();
  }
  $("#explorebtn").onclick = (e) => doExplore("curious", e.target);
  $("#wanderbtn").onclick = (e) => doExplore("wander", e.target);

  /* ───────────── brain tab ───────────── */
  function renderMarkdown(src) {
    const lines = (src || "").split("\n");
    let html = "", inList = false;
    const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
    lines.forEach((ln) => {
      if (/^#{1,2}\s/.test(ln)) { closeList(); html += "<h2>" + md(ln.replace(/^#+\s/, "")) + "</h2>"; }
      else if (/^[-*]\s/.test(ln)) { if (!inList) { html += "<ul>"; inList = true; } html += "<li>" + md(ln.replace(/^[-*]\s/, "")) + "</li>"; }
      else if (/^>\s?/.test(ln)) { closeList(); html += "<blockquote>" + md(ln.replace(/^>\s?/, "")) + "</blockquote>"; }
      else if (ln.trim()) { closeList(); html += "<div>" + md(ln) + "</div>"; }
    });
    closeList();
    return html;
  }
  async function refreshBrain() {
    if (!ST) return;
    const b = ST.brain, m = ST.memory;
    $("#braincards").innerHTML =
      card("🔤", b.lm_trained_tokens, "word-tokens my brain trained on", "n-gram language model, built from scratch") +
      card("📖", b.lm_vocab, "words in my vocabulary", "grows with everything I read") +
      card("🧩", m.total, "long-term memories", m.fact + " facts · " + m.skill + " skills · " + m.webnote + " web notes") +
      card("🪞", ST.version, "self-versions", "how often I rewrote who I am");

    const chips = $("#memchips");
    chips.innerHTML = "";
    [["fact", m.fact], ["skill", m.skill], ["preference", m.preference],
     ["webnote", m.webnote], ["reflection", m.reflection], ["experience", m.experience]]
      .forEach(([k, v]) => {
        if (v > 0) {
          const s = document.createElement("span");
          s.className = "chip"; s.textContent = v + " " + k.replace("note", "") + (v > 1 ? "s" : "");
          chips.appendChild(s);
        }
      });
    if (!chips.children.length) chips.innerHTML = '<span class="empty">no memories yet</span>';

    const sk = $("#skills");
    sk.innerHTML = "";
    (ST.skills || []).forEach((s) => {
      const li = document.createElement("li");
      li.innerHTML = '<span class="ic">▸</span><span class="t">' + escapeHtml(s) + "</span>";
      sk.appendChild(li);
    });
    if (!sk.children.length) sk.innerHTML = '<li class="empty">no skills noticed yet — ask me questions!</li>';

    $("#selfver").textContent = "v" + ST.version;
    try {
      const s = await http("/api/self");
      $("#selfdoc").innerHTML = s.text ? renderMarkdown(s.text)
        : '<span class="empty">I haven\'t written my SELF.md yet — it appears once I have memories to reflect on.</span>';
    } catch (e) { /* ignore */ }
  }
  $("#evolvebtn").onclick = async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "reflecting…";
    setOrb("learning", "🪞");
    try {
      const r = await http("/api/evolve", "POST", {});
      toast("🧠 Reflected!", "Self-instructions rewritten — now v" + r.version +
        " (+" + (r.xp_gained || 0) + " XP)", "learn", 7000);
      addMsg("🪞 I reflected on my " + r.memories + " memories and rewrote my self-instructions " +
        "(version " + r.version + ", +" + (r.xp_gained || 0) + " XP). See the 🧠 Brain tab!", "system");
    } catch (err) { toast("Reflection failed", String(err), "web"); }
    btn.disabled = false;
    btn.textContent = "✨ Reflect now";
    setOrb("", "", 0);
    refreshStats(); refreshActivity();
  };

  /* ───────────── activity rail ───────────── */
  async function refreshActivity() {
    try {
      const act = await http("/api/activity");
      const ul = $("#activity");
      const items = (act.ledger || []).slice(0, 22);
      $("#actcount").textContent = items.length ? "(" + items.length + ")" : "";
      const seen = ul.dataset.sig === items.map(i=>i.ts).join(",");
      ul.dataset.sig = items.map(i=>i.ts).join(",");
      ul.innerHTML = "";
      items.forEach((it) => {
        const li = document.createElement("li");
        const tag = it.kind || "refresh";
        li.innerHTML = '<span class="tag ' + escapeHtml(tag) + '">' + escapeHtml(tag) + "</span>" +
          "<span>" + escapeHtml(it.text || "") + "</span>" +
          '<span class="ago">' + timeAgo(it.ts) + "</span>";
        ul.appendChild(li);
      });
      // toast when the child learned online by itself while we watched
      (act.explorer || []).forEach((r) => {
        if (r.outcome === "learned" && r.ts > lastWebEvent && lastWebEvent > 0) {
          toast("🌐 learned online by itself!", (r.topic || "") + " — " + (r.detail || ""), "web", 6000);
          const nd = $("#netdot"); nd.hidden = false;
          setTimeout(() => { nd.hidden = true; }, 12000);
        }
        if (r.ts > lastWebEvent) lastWebEvent = r.ts;
      });
    } catch (e) { /* ignore */ }
  }

  /* ───────────── stats refresh ───────────── */
  async function refreshStats() {
    try {
      ST = await http("/api/stats");
      updateHeader();
      const tab = activeTab();
      if (tab === "progress") renderProgress();
      if (tab === "internet") renderNetPanel();
      if (tab === "brain") refreshBrain();
      if (!greeted) { greeted = true; greet(); renderSuggests(); }
      else renderSuggests();
    } catch (e) { /* server not up yet */ }
  }

  function greet() {
    const p = ST.progress;
    const knows = ST.knowledge.chunks > 2;
    const interests = (ST.top_interests || []).slice(0, 3).join(", ");
    let intro = "Namaste! I'm Anviksha — a " + p.stage.toLowerCase() +
      " (level " + p.level + ") raised entirely from scratch. ";
    intro += (knows && interests)
      ? "I already know " + ST.knowledge.chunks + " passages about things like " + interests + ". "
      : "My head is nearly empty right now — and the world is so interesting! ";
    intro += "Teach me by just talking normally (I notice when you tell me things), " +
      "hand me files with 📎, and send me exploring the internet — I keep a wonder " +
      "journal of everything I want to learn. Watch me grow on the 📈 Progress tab!";
    addMsg(intro, "bot");
    input.focus();
  }

  /* ───────────── boot ───────────── */
  setInterval(() => { if (!document.hidden) refreshActivity(); }, 4000);
  setInterval(() => { if (!document.hidden) refreshStats(); }, 8000);
  setInterval(() => {
    if (!document.hidden && activeTab() === "internet") { refreshJournal(); refreshCuriosity(); }
  }, 10000);
  refreshStats();
  refreshActivity();
})();
