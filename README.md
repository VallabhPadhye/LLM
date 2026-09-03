# Anviksha · a small, self-developing learning assistant

Anviksha (अन्विक्षा — Sanskrit for *inquiry / exploration*) is a **custom,
from-scratch** language-learning assistant. It is not a wrapper around ChatGPT,
Claude, or any pretrained model. Its "brain" is a statistical language model
that is **trained on the knowledge you provide**, and it improves itself
through three autonomous learning loops:

1. **Knowledge loop** — text you give it (dropped in `data/knowledge/` or sent
   as `learn: <text>`) is chunked and indexed for fast, grounded answers.
2. **Memory loop** — every conversation is reflected on; durable facts,
   preferences and skills are extracted and stored with priorities that decay
   if they fall out of use.
3. **Self-development loop** — periodically it compacts what it has learned into
   a rewritten `data/store/SELF.md` "self-instruction" file and bumps its own
   version. You can watch it change who it is.

It also **browses the web by itself** (on a schedule or when asked), derives
"interests" from what it already knows, and digests pages into its knowledge
base and memory.

---

## Why it's cheap, power-efficient and token-light

| Requirement | How Anviksha meets it |
|---|---|
| **Low token / power use** | The generative core is a compact n-gram LM trained in seconds on CPU. Every reply targets a small token budget, dialogue context is bounded, and there is **no GPU and no paid API** — just the Python standard library. |
| **Learns from *your* knowledge** | Anything in `data/knowledge/` or taught via `learn:` becomes the corpus it is trained and answers from. |
| **Self-developing** | Autonomous reflection compacts memories into a rewritten `SELF.md`, and it can retrain its generative model as it grows. |
| **Explores the internet by itself** | A background agent picks topics from its own interests, browses Wikipedia (with a pluggable search provider), and digests pages. Budgets, timeouts, a domain denylist and graceful offline handling keep it safe and unattended. |

## Run it

```bash
# no install needed (Python 3.9+ standard library only)
python run.py
```

Open **http://localhost:8000** in your browser.

> On this Arena sandbox the HTTPS egress is blocked, so the *autonomous web
> browsing* reports itself gracefully offline here — but everything else
> (learning, memory, self-development, chat) works. On your own machine with
> normal internet the explorer browses for real.

### Give it knowledge
- **Files:** drop `.md` / `.txt` / `.rst` files into `data/knowledge/` (re-ingested
  at startup).
- **In chat:** type `learn: <paste your text>`.
- **Live:** paste into the *"Teach it"* box in the sidebar.

### Things to try
- *"what is overfitting?"* → grounded answer from your docs, with the source cited.
- *"learn: <your field's notes>"* then ask about them.
- *"go browse the internet"* → manual web-exploration pass.
- The **Reflect / self-upgrade** button (or just talk a lot) → watch the version
  in the sidebar tick up and read `data/store/SELF.md`.

## How it's built (code map)

```
anviksha/
  config.py        paths, safety budgets, knobs
  knowledge.py     ingest + chunk + index your docs (BM25 retrieval)
  memory.py        long-term memory, priorities/decay, SELF.md self-development
  explorer.py      autonomous web agent (topic inference + Wikipedia digest)
  agent.py         the "mind": routing, chat, learning orchestration
  server.py        dependency-free HTTP server + JSON API (stdlib only)
  web/             the chat UI (HTML/CSS/JS, no external CDN)
  brain/
    tokens.py      custom tokenizer (token-efficient)
    lm.py          from-scratch n-gram language model trained on your corpus
data/
  knowledge/       ← put your documents here
  store/           trained brain, memory, SELF.md, version (auto-generated)
```

## Honest limitations (please read)

- This is a **tiny learner**, not a ChatGPT/Claude-scale foundation model. It
  produces *domain-accurate, retrieved* answers about what you taught it — and
  honest "I don't know that yet" for the rest. Its *free-form* generation is
  simple and should not be used where you need a frontier model's fluency.
- A model that physically rewires itself as it chats isn't real in any model —
  including commercial ones. What Anviksha does is *learn durably and improve
  its instructions over time*, which is the honest version of that idea.
- Autonomous browsing needs real internet egress (works on your machine) and is
  intentionally budgeted (topics/queries/pages per run, denylist, timeouts).

## Extending
The backend model is pluggable: swap `Agent`'s `LanguageModel` for a larger
model (e.g. Ollama/local or any OpenAI-compatible API) and everything else —
knowledge ingestion, memory, self-development, web exploration, the UI — keeps
working unchanged.
