"""
Agent - the orchestrating "mind" of Anviksha.

Ties together: knowledge base (your docs + web digests), the generative
language model trained on that knowledge, long-term memory/self-development,
and the autonomous explorer. Exposes a small, chat-oriented API used by both
the web UI and any other front end.
"""
import json
import os
import re
import time

from . import config
from .knowledge import KnowledgeBase
from .memory import MemoryStore
from .brain.lm import LanguageModel
from .brain.tokens import sentence_split
from .explorer import Explorer

# --- small-talk / meta lexicons -----------------------------------------
_GREET = {"hi", "hello", "hey", "yo", "namaste", "namaskar", "hola",
          "goodmorning", "goodafternoon", "goodevening", "salaam", "hiya", "howdy"}
_META = ["whoareyou", "whatareyou", "whatcanyoudo", "howdoyouwork", "aboutyou",
         "yourname", "whoare", "explainyourself", "howareyou", "whatsyourname"]
_OPEN = {"write", "poem", "story", "song", "create", "makeup", "compose", "imagine",
         "joke", "haiku", "rap", "parody"}

# Common English function words for topic extraction.
_QW = {"what", "how", "why", "when", "which", "who", "where", "does", "do", "is",
       "are", "can", "you", "tell", "me", "about", "explain", "define", "mean",
       "the", "a", "an", "of", "to", "for", "and", "or", "please", "could",
       "would", "should", "help", "with", "my", "in", "on", "it", "its", "that"}


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _topic(text):
    for t in re.findall(r"[a-z][a-z0-9]{1,25}", (text or "").lower()):
        if t not in _QW and len(t) > 2:
            return t
    return None


class Agent:
    def __init__(self):
        config.ensure_dirs()
        self.kb = KnowledgeBase()
        self.memory = MemoryStore()
        self.lm = LanguageModel()
        self.explorer = Explorer(self.kb, self.memory)
        self.history = []                 # small bounded dialogue window
        self._chat_seq = 0
        self.start_ts = time.time()

    # ------------------------------------------------------------------
    # onboarding / maintenance
    # ------------------------------------------------------------------
    def ingest_knowledge_dir(self):
        """Load every text/markdown file the user dropped into data/knowledge."""
        added_docs = 0
        if not os.path.isdir(config.KNOWLEDGE_DIR):
            return 0
        for fn in sorted(os.listdir(config.KNOWLEDGE_DIR)):
            fp = os.path.join(config.KNOWLEDGE_DIR, fn)
            if not os.path.isfile(fp) or fn.startswith("."):
                continue
            if not fn.lower().endswith((".txt", ".md", ".markdown", ".rst")):
                continue
            try:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                if self.kb.add_text(raw, source=f"knowledge:{fn}") > 0:
                    added_docs += 1
            except Exception:
                continue
        self._retrain_if_empty()
        return added_docs

    def _retrain_if_empty(self):
        """Train the generative model on available knowledge once (cold start)."""
        if self.lm.n_seen > 0:
            return
        self.lm.load()                # may already carry trained weights on disk
        if self.lm.n_seen > 0:
            return
        texts = self.kb.all_chunk_texts()[:200]
        texts += [m["content"] for m in self.memory.recent(limit=60)]
        if texts:
            self.lm.train_texts(texts)
            self.lm.save()

    # ------------------------------------------------------------------
    # status for UI
    # ------------------------------------------------------------------
    def status(self):
        self._retrain_if_empty()
        skills = [s["content"] for s in self.memory.top_skills(5)]
        return {
            "name": "Anviksha",
            "version": self.memory.version(),
            "uptime_s": round(time.time() - self.start_ts),
            "network": self.explorer.net,
            "brain": {"lm_trained_tokens": int(self.lm.n_seen),
                      "lm_vocab": self.lm.vocab_size(),
                      "lm_perplexity_est": None},
            "knowledge": {"chunks": self.kb.count()},
            "memory": self.memory.stats(),
            "skills": skills,
            "top_interests": self.memory.domain_tags(config.AUTO_INTEREST_TAGS),
            "self_file": bool(self.memory.read_self()),
        }

    # ------------------------------------------------------------------
    # learning
    # ------------------------------------------------------------------
    def learn(self, text: str, source="user-knowledge"):
        n = self.kb.add_text(text, source=source)
        if n:
            self.lm.train(text)
            self.lm.save()
        # remember that we learned
        head = re.sub(r"\s+", " ", text[:120])
        self.memory.add("experience",
                        f"Learned new material ({n} passage(s)): {head}…",
                        source=source, priority=0.5, silent=True)
        self.memory.evolve(force=(n >= 8))
        return n

    def learn_file(self, path):
        with open(path, encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        return self.learn(raw, source=f"file:{os.path.basename(path)}")

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    def chat(self, message: str):
        message = (message or "").strip()
        self._chat_seq += 1
        # bound the dialogue window for token/power efficiency
        if len(self.history) > 6:
            self.history = self.history[-6:]

        answer, grounded, events = self._route(message)
        # reflection -> self-development
        added = self.memory.reflect(message, answer, grounded)
        self.history.append({"role": "user", "msg": message})
        self.history.append({"role": "assistant", "msg": answer})
        return {"reply": answer, "grounded": grounded,
                "learned_this_turn": added, "events": events or []}

    def _route(self, m):
        low = m.lower()
        key = _norm(m)

        # ---- explicit learning / self-improvement commands ------------
        if re.match(r"^(learn|study|remember|ingest)\b[: ]", low):
            body = re.split(r"[:]\s*", m, maxsplit=1)[-1].strip()
            if len(body) > 40:
                n = self.learn(body)
                return (f"I've studied that and stored {n} passage(s). "
                        f"It's now part of what I know, and I've started "
                        f"internalising its language.", True, [])
            return ("Tell me what you'd like me to learn - paste the text "
                    "after 'learn:' or drop a file into data/knowledge.", False, [])

        if "evolve" in low or "upgrade yoursel" in low or "improve yoursel" in low:
            v = self.memory.evolve(force=True)
            self._retrain_if_empty()
            return (f"Done - I reflected on my {self.memory.count()} memories and "
                    f"rewrote my self-instructions"
                    + (f" (now version {v})." if v else ".")
                    + " Open the 'SELF.md' file to see who I've become.", True, [])

        if self._is_meta(m, key):
            return self._meta_answer(), True, []

        if re.search(r"\b(go browse|browse|research|search the web|look it up|"
                     r"learn from the internet|go explore|explore the internet)\b", low):
            if not self.explorer.net:
                self.explorer.net = __import__("anviksha.explorer",
                                               fromlist=["network_available"]).network_available()
            res = self.explorer.explore_once()
            if res.get("offline"):
                return (res["error"] + " On your own machine (with internet) I "
                        "would browse topics like "
                        + ", ".join(res.get("topics") or ["AI"]) + " now.",
                        False, [])
            if res.get("ok"):
                return (f"Browsed {len(res.get('visits', []))} page(s) on: "
                        + ", ".join(res.get("topics", [])) + f". "
                        f"Learned {res.get('new_chunks', 0)} new passage(s).",
                        True, [])
            return ("I couldn't complete that browse right now.", False, [])

        if any(w in low for w in _OPEN):
            return self._creative_answer(m), False, []

        if self._is_greeting(m):
            return self._greeting_answer(), False, []

        # ---- ordinary question ----------------------------------------
        ans, grounded = self._factual_answer(m)
        return ans, grounded, []

    def _is_greeting(self, m):
        words = set(re.findall(r"[a-z']+", m.lower()))
        if not (_GREET & words) or len(m) > 50:
            return False
        # don't swallow an actual question that merely opens with "hi"
        if any(q in m.lower() for q in ("what", "how", "why", "when", "who",
                                        "can you", "explain", "is it", "does",
                                        "about", "tell me", "define", "learn")):
            return False
        return True

    def _is_meta(self, m, key):
        if any(k in key for k in _META):
            return True
        if re.search(r"\b(what can you do|who are you|about yourself|how do you work|"
                     r"what have you learned|self)\b", m.lower()):
            return True
        return False

    # ------------------------------------------------------------------
    # answer builders
    # ------------------------------------------------------------------
    def _greeting_answer(self):
        if self.memory.domain_tags():
            top = ", ".join(self.memory.domain_tags(3))
            return (f"Namaste! I'm Anviksha. I've been learning and currently "
                    f"know the most about {top}. Ask me anything - or tell me "
                    f"'learn: <text>' and I'll study it.")
        return ("Namaste! I'm Anviksha - a small, self-learning assistant built "
                "from scratch. Right now I'm an empty mind waiting for knowledge. "
                "Paste text with 'learn: <content>' or drop files into "
                "data/knowledge and I'll begin learning.")

    def _meta_answer(self):
        st = self.status()
        lines = ["Here's my current state of mind:"]
        lines.append(f"- Brain trained on {st['brain']['lm_trained_tokens']} "
                     f"word-tokens, vocabulary of {st['brain']['lm_vocab']}.")
        lines.append(f"- Knowledge base: {st['knowledge']['chunks']} passage(s).")
        m = st['memory']
        lines.append(f"- Long-term memory: {m['total']} items "
                     f"({m['fact']} facts, {m['skill']} skills, "
                     f"{m['preference']} preferences, "
                     f"{m['webnote']} web notes).")
        lines.append(f"- Self-development version: {st['version']}.")
        if st['skills']:
            lines.append("- I can help with: " + ", ".join(st['skills']))
        else:
            lines.append("- No skills yet - teach me and I'll grow.")
        return " ".join(lines)

    def _creative_answer(self, m):
        topic = _topic(re.sub(r"\b(write|create|compose|make up|tell me a)\b", "", m))
        if not self.lm.n_seen:
            return ("I haven't learned any language yet to be creative with. "
                    "Give me material first (learn: <text>), then I'll write.")
        seed = topic if topic else None
        out = self.lm.generate(context=seed or "the", n_tokens=config.MAX_REPLY_TOKENS_EST // 8,
                               temperature=1.15, top_k=10)
        return ("Here's something original, drawn from the vocabulary I learned:\n\n"
                + (out or "…") + "\n\n(Early-stage model - it learns as you teach it.)")

    def _factual_answer(self, m):
        # 1) knowledge base first
        hits = self.kb.query(m, k=3)
        # 2) long-term memory second
        mems = self.memory.recall(m, k=3)
        if hits:
            top = hits[0]["text"]
            sents = self._answer_sentences(m, top)
            src = hits[0]["source"]
            ans = (" ".join(sents) if sents else top[:300])
            if len(hits) > 1 and self._mentions(m, hits[1]["text"]):
                ans += " " + self._answer_sentences(m, hits[1]["text"], cap=1)[0]
            return (ans + f"\n\n(source: {src})"), True
        if mems:
            c = mems[0]["content"]
            ans = c if len(c) < 260 else c[:260] + "…"
            return (ans + "\n\n(from my long-term memory.)"), True
        # 3) honestly unknown -> queue learning / offer web search
        topic = _topic(m)
        return (f"I don't have that in my knowledge yet. " +
                (f"I can look up '{topic}' online" if topic and self.explorer.net
                 else "I can look it up online once internet is available") +
                " - or you can teach me with 'learn: <content>'."), False

    # helpers ------------------------------------------------------------
    def _mentions(self, q, text):
        qw = {w for w in re.findall(r"[a-z0-9]{3,}", q.lower()) if w not in _QW}
        tw = set(re.findall(r"[a-z0-9]{3,}", text.lower()))
        return bool(qw & tw) and len(qw) > 1

    def _answer_sentences(self, q, text, cap=2):
        qw = {w for w in re.findall(r"[a-z0-9]{3,}", q.lower()) if w not in _QW}
        sents = sentence_split(text)
        scored = []
        for s in sents:
            sw = set(re.findall(r"[a-z0-9]{3,}", s.lower()))
            inter = len(qw & sw) if qw else 0
            scored.append((inter + (1 if len(s) < 300 else 0), s))
        scored.sort(key=lambda x: -x[0])
        # return the best few, skipping headings/noise
        chosen = []
        for _, s in scored:
            if s and not s.startswith(("#", "=")) and len(s) > 25:
                chosen.append(s)
            if len(chosen) >= cap:
                break
        return chosen or sents[:1]
