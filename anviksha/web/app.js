/* Anviksha front-end - talk, watch it learn and grow. */
(function () {
  const log = document.getElementById("chatlog");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const form = document.getElementById("chatbar");

  const qs = (s) => document.querySelector(s);
  let lastActivity = 0;

  function http(path, method, body) {
    return fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then((r) => r.json());
  }

  function addMsg(text, who, meta) {
    const el = document.createElement("div");
    el.className = "msg " + who;
    el.textContent = text;
    if (meta && meta.source) {
      const s = document.createElement("span");
      s.className = "src";
      s.textContent = meta.source;
      el.appendChild(s);
    }
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function timeAgo(ts) {
    const s = Math.max(0, (Date.now() / 1000) - ts);
    if (s < 5) return "now";
    if (s < 60) return Math.floor(s) + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }

  function fmtMem(m) {
    const map = { fact: "facts", skill: "skills", preference: "prefs",
                  webnote: "web", reflection: "reflections", experience: "exp" };
    return (map[m.type] || m.type) + ":" + m.total;
  }

  async function refreshStatus() {
    try {
      const st = await http("/api/status", "GET");
      qs("#ver").textContent = st.version;
      qs("#tok").textContent = st.brain.lm_trained_tokens.toLocaleString();
      qs("#vocab").textContent = st.brain.lm_vocab.toLocaleString();
      qs("#chunks").textContent = st.knowledge.chunks.toLocaleString();

      const chips = document.getElementById("memchips");
      chips.innerHTML = "";
      for (const key of ["fact", "skill", "preference", "webnote"]) {
        if (st.memory[key]) {
          const c = document.createElement("span");
          c.className = "chip";
          c.textContent = st.memory[key] + " " + key.replace("note", "");
          chips.appendChild(c);
        }
      }
      const sk = document.getElementById("skills");
      sk.innerHTML = st.skills.length ? "" : "<li>(none yet — teach me)</li>";
      st.skills.forEach((s) => {
        const li = document.createElement("li");
        li.textContent = s;
        sk.appendChild(li);
      });

      const online = document.getElementById("online");
      const orb = document.getElementById("orb");
      if (st.network) {
        online.textContent = "● internet: online — auto-browsing enabled";
        online.className = "online good";
        orb.classList.remove("dim");
        const note = qs("#netnote");
        note.className = "netnote ok";
        note.textContent = "Network reachable — I can browse the web to learn.";
      } else {
        online.textContent = "● internet: offline (will auto-browse when connected)";
        online.className = "online";
        orb.classList.add("dim");
        qs("#netnote").textContent = "";
      }
    } catch (e) { /* ignore */ }
  }

  async function refreshActivity() {
    try {
      const act = await http("/api/activity", "GET");
      const ul = document.getElementById("activity");
      ul.innerHTML = "";
      const items = (act.ledger || []).slice(0, 18);
      qs("#actcount").textContent = "(" + items.length + ")";
      const kindTag = {
        learn: "learn", refresh: "refresh", evolve: "evolve", web: "web",
        startup: "startup", experience: "exp", webnote: "web",
      };
      items.forEach((it) => {
        const li = document.createElement("li");
        const tag = kindTag[it.kind] || "refresh";
        li.innerHTML = '<span class="tag ' + tag + '">' + tag + "</span> " +
          escapeHtml(it.text) + ' <span style="float:right;color:#5b6b82">' +
          timeAgo(it.ts) + "</span>";
        ul.appendChild(li);
      });
    } catch (e) {}
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    resize();
    addMsg(text, "user");
    sendBtn.disabled = true;
    const typing = addMsg("thinking…", "bot typing");
    try {
      const res = await http("/api/chat", "POST", { message: text });
      typing.remove();
      addMsg(res.reply, "bot");
      if (res.learned_this_turn > 0) {
        refreshStatus(); refreshActivity();
      }
    } catch (e) {
      typing.remove();
      addMsg("(server error — is Anviksha running?)", "bot");
    }
    sendBtn.disabled = false;
    input.focus();
  }

  function resize() { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; }

  form.addEventListener("submit", (e) => { e.preventDefault(); send(); });
  input.addEventListener("input", resize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  document.getElementById("learnbtn").addEventListener("click", async () => {
    const box = document.getElementById("learnbox");
    const text = box.value.trim();
    if (!text) return;
    sendBtn.disabled = true;
    const res = await http("/api/learn", "POST", { text });
    box.value = "";
    sendBtn.disabled = false;
    addMsg("(taught: stored " + res.stored + " passage(s) — total now " +
      res.total_chunks + ")", "bot");
    refreshStatus(); refreshActivity();
  });

  document.getElementById("explorebtn").addEventListener("click", async () => {
    const btn = document.getElementById("explorebtn");
    btn.disabled = true;
    addMsg("(browsing the web to learn…)", "bot typing");
    const res = await http("/api/explore", "POST", {});
    btn.disabled = false;
    log.querySelectorAll(".msg.bot.typing").forEach((e) => e.remove());
    if (res.ok) {
      addMsg("Browsed " + (res.visits ? res.visits.length : 0) + " page(s) on: " +
        (res.topics || []).join(", ") + ". Learned " + res.new_chunks +
        " new passage(s).", "bot");
    } else {
      addMsg("Browse failed: " + (res.error || "unknown") + " — topics I'd chase: " +
        (res.topics || ["AI"]).join(", "), "bot");
    }
    refreshStatus(); refreshActivity();
  });

  document.getElementById("evolvebtn").addEventListener("click", async () => {
    const btn = document.getElementById("evolvebtn");
    btn.disabled = true;
    const res = await http("/api/evolve", "POST", {});
    btn.disabled = false;
    addMsg("(reflected & rewrote my self-instructions — now version " +
      res.version + ")", "bot");
    refreshStatus(); refreshActivity();
  });

  setInterval(refreshActivity, 6000);
  setInterval(refreshStatus, 20000);
  refreshStatus();
  refreshActivity();

  // intro bubble
  setTimeout(() => {
    addMsg("Namaste. I'm Anviksha — a small self-learning mind built from scratch. " +
      "I learn from the knowledge you give me, improve my own instructions over time, " +
      "and explore the web to grow. Try: “what do you know about X”, " +
      "“learn: <paste text>”, or press “Browse the web”.", "bot");
    input.focus();
  }, 300);
})();
