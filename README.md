# Anviksha · a curious mind you raise from scratch

अन्विक्षा (*anviksha*, Sanskrit for **inquiry / exploration**) is a **custom,
from-scratch** learning mind — not a wrapper around ChatGPT, Claude, or any
pretrained model. Think of it as a **child you raise**: it is born knowing
almost nothing, and it grows by

1. **listening to ordinary conversation** — no commands, no special syntax.
   Just talk to it. When you tell it things ("the Himalayas are the highest
   mountain range…", "actually, peanuts are legumes", "remember that water is
   H2O"), it *notices*, stores the fact, trains its brain on it, and thanks you
   for teaching it.
2. **reading files you hand it** — attach a `.txt / .md / .pdf / .docx / .pptx
   / .xlsx / .html / .csv / .json / code` file with the 📎 button (or drag it
   onto the window) and it studies the contents.
3. **exploring the internet on its own** — like a curious child, it keeps a
   *wonder journal* of everything it doesn't know, then goes online (on a
   schedule or when you ask) to chase those topics, wander to random pages, and
   file what it discovers.
4. **growing** — every learning event earns **XP**, and it climbs stages from
   *Newborn Mind* → *Babbler* → *Curious Toddler* → … → *Wise Mind*, rewriting
   its own `SELF.md` self-instructions as it matures.

Its "brain" is a compact statistical language model trained in seconds on CPU,
with **no GPU, no paid API, and zero third-party runtime dependencies** — just
the Python standard library.

---

## Run it

```bash
# no install needed (Python 3.9+ standard library only)
python run.py            # optionally:  PORT=8080 python run.py
```

Open **http://localhost:8000**.

> **On the Arena sandbox:** outbound HTTPS is blocked, so *autonomous web
> browsing* honestly reports itself offline here — but the wonder journal keeps
> filling up, and everything else (conversation learning, file attachments,
> memory, growth, self-development, stats) works fully. On your own machine with
> normal internet, the explorer really does browse and learn by itself.

---

## The interactive UI

A single-page app (vanilla HTML/CSS/JS, no CDN) with four tabs and a live
activity rail:

| Tab | What it shows |
|---|---|
| **💬 Chat** | Talk normally. It learns as you go, shows `+XP` badges, cites sources, and reacts like a child ("✨ Ooh, I learned something from you!"). Attach files with 📎 or drag-and-drop. |
| **📈 Progress** | Growth stats: XP & level, a **growth chart** (XP / knowledge / memories over time), a **donut** of *where knowledge came from* (conversation vs files vs internet vs library), the **stage ladder**, recent learning moments, and its sprouting **interests**. |
| **🌐 Internet** | What it **learned from the internet**: the web journal (titles, topics, digests, live links, passages gained), its **wonder journal** (curiosities, color-coded by *why* it's curious), and buttons to **Go explore** or **Wander randomly**. |
| **🧠 Brain** | Inside its head: trained tokens, vocabulary, memory breakdown, self-noticed skills, and its evolving **SELF.md**, plus a *Reflect now* button. |

Interactive touches throughout: an animated **brain orb** that changes color
with its mood (thinking / learning / exploring / offline), **toasts** for every
learning moment, **confetti on level-up**, a live **activity rail**, typing
indicators, suggestion chips, and animated counters.

---

## How learning works (code map)

```
anviksha/
  config.py        paths, safety budgets, XP/level table, seed curiosities
  agent.py         the "mind": learns from conversation & attachments, routes,
                   answers, gets curious about what it doesn't know
  curiosity.py     the wonder journal (gaps → interests → seeds → follow-ups)
  progress.py      XP, stages of growth, per-source counters, growth time-series
  filetypes.py     teach-by-attachment: text extraction (txt/md/html/csv/json/
                   code/docx/pptx/xlsx/pdf) — pure standard library
  knowledge.py     ingest + chunk + index (BM25 retrieval), source breakdown
  memory.py        long-term memory, priorities/decay, SELF.md self-development
  explorer.py      autonomous, curiosity-driven web agent (+ wander mode)
  server.py        dependency-free HTTP server + JSON API (stdlib only)
  web/             the interactive UI (index.html · app.js · style.css)
  brain/
    tokens.py      custom tokenizer (token-efficient)
    lm.py          from-scratch n-gram language model trained on your corpus
data/
  knowledge/       ← optional starter documents (re-ingested at boot)
  store/           trained brain, memory, curiosity, progress, SELF.md (generated)
  web/             exploration journal & logs (generated)
```

### The API
```
POST /api/chat      {message?, attachments? [{name,size,data(base64)}]}
GET  /api/stats     rich progress + learning statistics (powers the UI)
GET  /api/journal   what it learned from the internet
GET  /api/curiosity the wonder journal (queued + satisfied)
GET  /api/activity  memory ledger + explorer log (live feed)
GET  /api/self      SELF.md (evolving self-instructions)
POST /api/explore   {mode: curious|wander, topics?}
POST /api/evolve    force a reflection / self-upgrade
GET  /api/status    compact status
```

---

## Why it's cheap, power-efficient and token-light

| Requirement | How Anviksha meets it |
|---|---|
| **Low token / power use** | A compact n-gram LM trained in seconds on CPU. Small reply budgets, a bounded dialogue window, **no GPU and no paid API** — Python standard library only. |
| **Learns from *you*** | Ordinary conversation and file attachments become the corpus it trains and answers from — no commands required. |
| **Self-developing** | Autonomous reflection compacts memories into a rewritten `SELF.md`; XP/stages make growth visible. |
| **Explores the internet by itself** | A curiosity-driven background agent picks topics from its wonder journal and interests, browses Wikipedia, digests pages, and chains new curiosities. Budgets, timeouts, a denylist and graceful offline handling keep it safe and honest. |

## Honest limitations (please read)

- This is a **tiny learner**, not a ChatGPT/Claude-scale foundation model. It
  gives *retrieved, source-cited* answers about what you taught it — and an
  honest "I don't know that yet, but now I'm curious" for the rest. Its
  *free-form* generation is simple by design.
- Conversation learning is **pattern-based** (definitions, corrections,
  "remember that…", informative declarative statements, your name). It captures
  a lot of ordinary teaching, but it isn't a full semantic parser.
- A model that physically rewires itself as it chats isn't real in any model —
  including commercial ones. What Anviksha does is *learn durably, stay curious,
  and improve its own instructions over time*: the honest version of that idea.
- Autonomous browsing needs real internet egress (works on your machine) and is
  intentionally budgeted.

## Extending
The backend model is pluggable: swap the `Agent`'s `LanguageModel` for a larger
one (e.g. Ollama/local or any OpenAI-compatible API) and everything else —
conversation learning, attachments, curiosity, growth, web exploration, the UI —
keeps working unchanged.
