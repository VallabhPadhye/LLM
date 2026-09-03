"""
Agent - the orchestrating "mind" of Anviksha.

Anviksha is raised like a child:

  * it learns from *ordinary conversation* - no special commands. When you
    tell it things ("water boils at 100 degrees", "remember that ...",
    "actually, ..."), it notices, stores the fact, trains its brain on it and
    thanks you for teaching it;
  * it learns from *file attachments* you hand it in chat (txt/md/pdf/docx/
    pptx/xlsx/html/csv/code);
  * it is *curious* - what it doesn't know goes into its wonder journal, and
    the explorer chases those topics (plus its own wide-ranging interests)
    when it goes online;
  * it *grows* - every learning event earns XP, and it climbs stages from
    "Newborn Mind" to "Wise Mind".

Ties together: knowledge base, generative LM, memory/self-development,
curiosity journal, progress book and the autonomous explorer.
"""
import base64
import json
import os
import re
import time

from . import config, filetypes
from .knowledge import KnowledgeBase
from .memory import MemoryStore
from .curiosity import CuriosityJournal
from .progress import Progress
from .brain.lm import LanguageModel
from .brain.tokens import sentence_split, tokenize
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
       "would", "should", "help", "with", "my", "in", "on", "it", "its", "that",
       "know", "known", "think", "want", "need", "like", "make", "made", "give",
       "many", "much", "often", "long", "far", "amount", "number", "really",
       "have", "has", "had", "was", "were", "be", "been", "being", "am", "will",
       "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
       "ten", "over", "every", "through", "some", "most", "more", "less", "than",
       "then", "also", "very", "into", "upon", "per", "each", "both", "other",
       "another", "just", "only", "there", "here", "these", "those", "not", "no"}

# question openers - these messages ask, they don't teach
_ASKING = re.compile(r"^\s*(?:what|why|how|when|where|who|whom|whose|which|"
                     r"can|could|would|should|will|shall|do|does|did|is|are|was|were|"
                     r"tell me|explain|define|describe|list|compare|summarize|"
                     r"show|give me|name)\b", re.I)

# explicit teaching openers - always captured
_TEACH_OPEN = re.compile(
    r"^\s*(?:remember(?:\s+that)?|note(?:\s+that)?|keep in mind|learn this|"
    r"fun fact|fact|did you know(?:\s+that)?|here'?s (?:a|something|one)|"
    r"i(?:'ve| have)? (?:learned|learnt|read|discovered|found out|realized)"
    r"(?:\s+that)?|by the way|incidentally)\b[\s:,!-]*(?P<body>.+)",
    re.I | re.S)
_CORRECTION = re.compile(
    r"^\s*(?:actually|no[,.!]|not quite|that'?s (?:wrong|incorrect)|correction|"
    r"you'?re wrong|wrong)\b[\s:,!-]*(?P<body>.+)", re.I | re.S)
_DEFINITION = re.compile(
    r"^\s*(?P<subj>[A-Za-z0-9][A-Za-z0-9 _'\-,\.]{1,60}?)\s+"
    r"(?:is|are|was|were|means|stands for|refers to|is called|are called)\s+"
    r"(?P<comp>[^.!?]{2,})", re.S)
# complements that make a sentence conversational rather than a definition
_CHATTY_COMP = {"true", "false", "fine", "good", "bad", "ok", "okay", "right",
                "wrong", "enough", "all", "done", "here", "there", "it", "this",
                "that", "nice", "cool", "great", "sure", "ready", "possible",
                "not", "very", "so", "just", "only", "still", "why", "how"}
_NAME_PAT = re.compile(r"\b(?:my name is|call me|i am called|i'?m called|"
                       r"you can call me)\s+([A-Za-z][\w'\-]{1,30})", re.I)

# messages addressed *at* the assistant / small talk aren't teaching material
_FIRST_PERSON = re.compile(r"^\s*(?:i|i'm|im|we|we're|my|our|us|me|you|your|yours|"
                           r"let'?s|please|thanks|thank\s+you|ok|okay|alright|hey|hi|"
                           r"hello|yo|namaste|hiya|goodmorning|good\s+morning|"
                           r"good\s+evening|good\s+night|bye|goodbye|see\s+you)\b", re.I)

# how much "substance" a plain statement needs before I treat it as teaching
_NOTE_MIN_CONTENT_TOKENS = 6


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _topic(text):
    for t in re.findall(r"[a-z][a-z0-9]{1,25}", (text or "").lower()):
        if t not in _QW and len(t) > 2:
            return t
    return None


def _topic_phrase(text, max_words=3):
    """First run of substantive words - a much better curiosity topic than a
    single token ('quantum entanglement', not 'quantum')."""
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9\-']{1,24}", (text or "").lower())
    run = []
    for t in toks:
        if t in _QW or len(t) <= 2:
            if run:
                break
            continue
        run.append(t)
        if len(run) >= max_words:
            break
    return " ".join(run) if run else None


def _words(text):
    return re.findall(r"[A-Za-z0-9']+", text or "")


class Agent:
    def __init__(self):
        config.ensure_dirs()
        self.kb = KnowledgeBase()
        self.memory = MemoryStore()
        self.curiosity = CuriosityJournal()
        self.progress = Progress()
        self.lm = LanguageModel()
        self.explorer = Explorer(self.kb, self.memory,
                                 curiosity=self.curiosity, progress=self.progress)
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

    def _snapshot(self):
        self.progress.snapshot(chunks=self.kb.count(),
                               memories=self.memory.count(),
                               pages=int(self.progress.counters.get("web_page", 0)),
                               facts=self.memory.count("fact"))

    # ------------------------------------------------------------------
    # status for UI
    # ------------------------------------------------------------------
    def status(self):
        self._retrain_if_empty()
        skills = [s["content"] for s in self.memory.top_skills(5)]
        cur = self.curiosity.counts()
        return {
            "name": "Anviksha",
            "version": self.memory.version(),
            "uptime_s": round(time.time() - self.start_ts),
            "network": self.explorer.net,
            "web_refresh_min": config.WEB_REFRESH_MINUTES,
            "user_name": self.memory.user_name(),
            "brain": {"lm_trained_tokens": int(self.lm.n_seen),
                      "lm_vocab": self.lm.vocab_size(),
                      "lm_perplexity_est": None},
            "knowledge": {"chunks": self.kb.count()},
            "origins": self.kb.stats_by_origin(),
            "memory": self.memory.stats(),
            "skills": skills,
            "top_interests": self.memory.domain_tags(config.AUTO_INTEREST_TAGS),
            "curiosity": cur,
            "progress": self.progress.stats(),
            "self_file": bool(self.memory.read_self()),
        }

    # ------------------------------------------------------------------
    # learning channels
    # ------------------------------------------------------------------
    def learn(self, text: str, source="conversation"):
        """Store + train on a body of text. Returns number of new chunks."""
        n = self.kb.add_text(text, source=source)
        if n:
            self.lm.train(text)
            self.lm.save()
        head = re.sub(r"\s+", " ", text[:120])
        self.memory.add("experience",
                        f"Learned new material ({n} passage(s)): {head}…",
                        source=source, priority=0.5, silent=True)
        self.memory.evolve(force=(n >= 8))
        return n

    def learn_file(self, path):
        with open(path, encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        return self.learn(raw, source=f"attachment:{os.path.basename(path)}")

    # ---- attachments -------------------------------------------------
    def process_attachment(self, att: dict):
        """
        att = {"name","size","data"(base64)} -> dict describing what happened.
        """
        name = (att.get("name") or "file").strip()[:120]
        try:
            raw = base64.b64decode(att.get("data") or "", validate=False)
        except Exception:
            return {"name": name, "ok": False,
                    "error": "That attachment arrived corrupted - could you send it again?"}
        if len(raw) > config.ATTACH_MAX_FILE_BYTES:
            return {"name": name, "ok": False,
                    "error": f"That file is too big for me (max "
                             f"{config.ATTACH_MAX_FILE_BYTES // (1024*1024)} MB)."}
        res = filetypes.extract(name, raw)
        if res.get("error"):
            return {"name": name, "ok": False, "error": res["error"]}
        text = res["text"]
        n = self.learn(text, source=f"attachment:{name}")
        xp = config.XP["file_base"] + n * config.XP["file_chunk"]
        award = self.progress.award("file_read", amount=xp,
                                    label=f"read the file '{name}' (+{n} passages)")
        base = re.sub(r"\.[a-z0-9]+$", "", name.lower())
        topic = _topic_phrase(base) or _topic_phrase(text[:200])
        self.memory.add("experience",
                        f"The user taught me from a file: {name} "
                        f"({len(text)} characters, {n} passages).",
                        source=f"attachment:{name}", priority=0.7,
                        tags=[topic] if topic else [])
        self.memory._log("learn", f"studied attached file '{name}' → {n} passage(s)")
        # teach me more: wonder about the file's own subject
        if topic:
            self.curiosity.push(topic, reason="interest",
                                why=f"came up in the file '{name}' you gave me")
        self._snapshot()
        preview = re.sub(r"\s+", " ", text[:160]).strip()
        return {"name": name, "ok": True, "kind": res.get("kind", "text"),
                "passages": n, "chars": len(text), "xp": award["xp"],
                "preview": preview, "leveled_up": award["leveled_up"],
                "level": award["level"], "stage": award["stage"],
                "note": res.get("note") or ""}

    # ---- learning from ordinary conversation ---------------------------
    def extract_teachings(self, message: str):
        """
        Find the teachable content inside a plain conversational message.
        Returns a list of {"kind","text","topic"}.
        """
        out = []
        msg = (message or "").strip()
        if not msg or len(_words(msg)) < 3:
            return out
        low = msg.lower()

        # never treat navigation/meta commands as teachings
        if re.match(r"^(learn|study|ingest)\s*:", low):
            return out
        if re.search(r"\b(go browse|browse the web|explore the internet|wander|"
                     r"evolve|upgrade yoursel|improve yoursel|reflect)\b", low):
            return out

        # 0) user identity ("call me X")
        nm = _NAME_PAT.search(msg)
        if nm:
            out.append({"kind": "profile", "text": nm.group(1).strip().title(),
                        "topic": "user"})
            return out

        # 1) explicit teaching openers
        m = _TEACH_OPEN.match(msg)
        if m and len(_words(m.group("body"))) >= 4:
            body = m.group("body").strip().rstrip("?")
            out.append({"kind": "fact", "text": body,
                        "topic": _topic_phrase(body)})
            return out

        # 2) corrections
        m = _CORRECTION.match(msg)
        if m and len(_words(m.group("body"))) >= 4:
            body = m.group("body").strip()
            out.append({"kind": "correction", "text": body,
                        "topic": _topic_phrase(body)})
            return out

        # questions don't teach (they *ask*)
        if _ASKING.match(msg) or msg.endswith("?"):
            return out

        # 3) any informative declarative statement => the user is teaching me
        #    (a child absorbs everything it hears that isn't small talk)
        if not _FIRST_PERSON.match(msg):
            content = tokenize(msg)          # stop words already filtered
            if len(content) >= _NOTE_MIN_CONTENT_TOKENS:
                out.append({"kind": "note", "text": msg,
                            "topic": _topic_phrase(msg)})
                return out

        # 4) definition "X is/means Y" (even short: "water is H2O")
        m = _DEFINITION.match(msg)
        if m and not _FIRST_PERSON.match(m.group("subj")):
            comp = m.group("comp").strip().rstrip(".!?")
            cw = [w for w in _words(comp) if w.lower() not in _CHATTY_COMP]
            # accept if the complement carries real content
            if cw and (len(_words(comp)) >= 3 or len(comp) >= 2):
                fact = re.sub(r"\s+", " ", (m.group("subj") + " is " + comp)).strip()
                out.append({"kind": "fact", "text": fact[:400],
                            "topic": _topic_phrase(m.group("subj"))})
        return out

    def absorb_teaching(self, t: dict, meta: dict):
        """Store one teaching into KB/LM/memory and award XP."""
        kind, text, topic = t.get("kind"), t.get("text", "").strip(), t.get("topic")
        if kind == "profile":
            self.memory.add("preference", f"User's name is {text}",
                            source="conversation", priority=0.95, tags=["profile"])
            meta["events"].append(f"remembered your name ({text})")
            meta["learned_name"] = text
            return
        if not text:
            return
        first_sentence = sentence_split(text)[0] if sentence_split(text) else text
        n = self.kb.add_text(text, source=f"chat:{topic or 'conversation'}")
        self.lm.train(text)
        self.lm.save()
        xp = config.XP["fact_from_chat"] + n * config.XP["chunk_from_chat"]
        award = self.progress.award("learned_from_chat", amount=xp,
                                    label=f"you taught me: {first_sentence[:110]}")
        stored = self.memory.add("fact", first_sentence[:300],
                                 source="conversation", priority=0.75,
                                 tags=[topic] if topic else [])
        if kind == "correction":
            self.memory._log("learn", f"corrected myself: {first_sentence[:100]}")
        else:
            self.memory._log("learn", f"learned from conversation: {first_sentence[:100]}")
        meta["facts_learned"].append({"fact": first_sentence[:200], "topic": topic,
                                      "kind": kind, "xp": award["xp"],
                                      "stored": bool(stored or n)})
        meta["xp_gained"] += award["xp"]
        if award["leveled_up"]:
            meta["level_up"] = {"level": award["level"], "stage": award["stage"]}
        # a curious child wonders more about what it was just taught
        if topic and (kind in ("note", "fact")):
            self.curiosity.push(topic, reason="interest",
                                why="you taught me about it - I want to know more")
        self._snapshot()

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    def chat(self, message: str, attachments=None):
        message = (message or "").strip()
        self._chat_seq += 1
        if len(self.history) > 6:
            self.history = self.history[-6:]

        meta = {"facts_learned": [], "xp_gained": 0, "level_up": None,
                "files": [], "events": [], "curiosity_added": []}

        # 1) attachments: teaching by file
        for att in (attachments or []):
            r = self.process_attachment(att)
            meta["files"].append(r)
            if r.get("ok"):
                meta["xp_gained"] += r.get("xp", 0)
                if r.get("leveled_up"):
                    meta["level_up"] = {"level": r["level"], "stage": r["stage"]}

        # 2) learn from the conversation itself (before answering, so a
        #    fact taught *in this very message* can be used right away)
        for t in self.extract_teachings(message):
            self.absorb_teaching(t, meta)

        # 3) answer (nothing to route when the turn was attachments-only)
        meta["is_question"] = bool(message and (message.strip().endswith("?")
                                                or _ASKING.match(message)))
        if message:
            answer, grounded, events = self._route(message)
            meta["events"] += events or []
        else:
            answer, grounded = "", False

        # 4) engagement XP + reflection -> self-development
        engage = self.progress.award("chat_turn",
                                     amount=config.XP["chat_turn"], label="")
        meta["xp_gained"] += engage["xp"]
        if engage["leveled_up"] and not meta["level_up"]:
            meta["level_up"] = {"level": engage["level"], "stage": engage["stage"]}
        added = self.memory.reflect(message, answer, grounded)
        meta["learned_this_turn"] = added + len(meta["facts_learned"]) + \
            sum(1 for f in meta["files"] if f.get("ok"))

        # 5) compose the child-like reply with its learning reactions
        meta["grounded"] = grounded
        reply = self._compose_reply(answer, meta)
        self.history.append({"role": "user", "msg": message})
        self.history.append({"role": "assistant", "msg": reply})
        self._snapshot()
        meta["xp"] = self.progress.xp
        meta["level"], meta["stage"] = self.progress.level_info()[:2]
        meta["reply"] = reply
        return meta

    def _compose_reply(self, answer, meta):
        parts = []
        if meta["files"]:
            oks = [f for f in meta["files"] if f.get("ok")]
            bad = [f for f in meta["files"] if not f.get("ok")]
            if oks:
                bits = ", ".join(f"'{f['name']}' ({f['passages']} passage"
                                 f"{'s' if f['passages'] != 1 else ''}, +{f['xp']} XP)"
                                 for f in oks)
                parts.append(f"📚 I read {bits} and stored it all in my memory. "
                             f"Ask me anything about it!")
            for f in bad:
                parts.append(f"📎 About '{f['name']}': {f.get('error')}")
        name = meta.get("learned_name")
        taught = bool(meta["facts_learned"]) or any(f.get("ok") for f in meta["files"])
        is_q = meta.get("is_question")
        if name:
            parts.append(f"Nice to meet you, {name}! 🌟 I've tucked your name "
                         f"away in my memory - I'll greet you with it from now on.")
        elif answer and (is_q or not taught):
            # include the retrieved answer when the user asked a question, or
            # when nothing was taught this turn (small talk, gaps, creative…)
            parts.append(answer)
        # else: a teaching-only turn — the ✨/📚 acknowledgement below IS the reply
        new_facts = [fl for fl in meta["facts_learned"] if fl.get("kind") != "note"]
        notes = [fl for fl in meta["facts_learned"] if fl.get("kind") == "note"]
        if new_facts:
            bits = "; ".join(f"“{fl['fact'][:90]}”" for fl in new_facts[:2])
            parts.append(f"✨ Ooh, I learned something from you! I saved: {bits} "
                         f"(+{sum(fl['xp'] for fl in new_facts)} XP)")
        if notes:
            parts.append(f"✨ Thank you for explaining! I studied what you wrote "
                         f"and filed it under “{notes[0]['topic']}” "
                         f"(+{sum(fl['xp'] for fl in notes)} XP). I'm even more "
                         f"curious about that now!")
        if meta["curiosity_added"]:
            parts.append("💭 I've added " + ", ".join(f"“{t}”"
                         for t in meta["curiosity_added"][:3]) +
                         " to my wonder journal - I'll look it up when I explore.")
        if meta["level_up"]:
            parts.append(f"🎉 I grew! I'm now a {meta['level_up']['stage']} "
                         f"(level {meta['level_up']['level']}). Thank you for teaching me!")
        return "\n\n".join(p for p in parts if p)

    # ------------------------------------------------------------------
    def _route(self, m):
        low = m.lower()
        key = _norm(m)

        # ---- explicit learning command (legacy; needs a colon) ---------
        if re.match(r"^(learn|study|ingest)\s*:", low):
            body = re.split(r"[:]\s*", m, maxsplit=1)[-1].strip()
            if len(body) > 40:
                n = self.learn(body)
                award = self.progress.award("learned_from_chat",
                                            amount=config.XP["fact_from_chat"] + n * config.XP["chunk_from_chat"],
                                            label=f"studied pasted text (+{n} passages)")
                self._snapshot()
                return (f"I've studied that and stored {n} passage(s). "
                        f"It's now part of what I know (+{award['xp']} XP), and I've "
                        f"started internalising its language.", True, [])
            return ("You don't need special commands with me - just tell me "
                    "things in normal conversation and I learn automatically. "
                    "You can also attach files with the 📎 button.", False, [])

        if "evolve" in low or "upgrade yoursel" in low or "improve yoursel" in low \
                or re.search(r"\breflect\b", low):
            v = self.memory.evolve(force=True)
            self._retrain_if_empty()
            award = self.progress.award("evolve", amount=config.XP["evolve"],
                                        label=f"reflected and rewrote SELF.md (v{v})")
            self._snapshot()
            return (f"Done - I thought hard about my {self.memory.count()} memories "
                    f"and rewrote my self-instructions"
                    + (f" (now version {v}, +{award['xp']} XP)." if v else ".")
                    + " Check the 🧠 Brain tab to see who I've become.", True, [])

        is_question = low.strip().endswith("?") or bool(_ASKING.match(m))

        # ---- asking ABOUT what it discovered online (a question, not a trip) ----
        asks_online = ("journal" in low) or (
            re.search(r"\b(learn\w*|discover\w*|found|read|explor\w*|find)\b", low)
            and re.search(r"\b(internet|web|online)\b", low))
        if asks_online and is_question:
            return self._learned_online_answer()

        # ---- imperative: GO browse the internet (not a question about the past) --
        if not is_question and re.search(
                r"\b(go browse|browse|research|search the web|look it up|"
                r"learn from the internet|go explore|explore the internet|"
                r"find out|look it up online|go online|wander)\b", low):
            mode = "wander" if re.search(r"\b(wander|random|anything|surprise)\b", low) else "curious"
            topics = None
            tm = re.search(r"\b(?:about|on|for)\s+([a-z0-9 ,\-]{3,50})\s*$", low)
            if tm and mode == "curious":
                topics = [tm.group(1).strip().rstrip(".!?")]
            res = self.explorer.explore_once(topics=topics, mode=mode)
            self._snapshot()
            return self._explore_answer(res, mode), res.get("ok", False), []

        # ---- "what are you curious about?" ----
        if re.search(r"\bcurious|wonder journal|what don'?t you know\b", low):
            queued = self.curiosity.queued()[:8]
            if queued:
                lines = [f"“{it['topic']}” ({it['reason']})" for it in queued]
                return ("Here's my wonder journal right now - things I want to "
                        "learn: " + ", ".join(lines) + ". Send me exploring and "
                        "I'll chase them!", True, [])
            return ("My wonder journal is empty - I'm content! Teach me things or "
                    "ask me questions I can't answer, and new curiosities will "
                    "sprout.", False, [])

        if self._is_meta(m, key):
            return self._meta_answer(), True, []

        if any(w in low for w in _OPEN):
            return self._creative_answer(m), False, []

        if self._is_greeting(m):
            return self._greeting_answer(), False, []

        # ---- warm small talk (first-person, non-question, low content) --
        if self._is_smalltalk(m):
            return self._smalltalk_answer(m), False, []

        # ---- ordinary question ----------------------------------------
        ans, grounded = self._factual_answer(m)
        return ans, grounded, []

    def _is_smalltalk(self, m):
        """Short personal/social remarks that shouldn't trigger fact retrieval."""
        if not _FIRST_PERSON.match(m):
            return False
        if m.strip().endswith("?"):
            return False
        # if it actually teaches something, it's not mere small talk
        if _TEACH_OPEN.match(m) or _CORRECTION.match(m) or _NAME_PAT.search(m):
            return False
        # a real request ("I want to learn about X") is not small talk
        if re.search(r"\b(?:want|need|wish|hope|plan|going to|about|regarding|"
                     r"explain|tell me|teach|learn|research|find)\b", m.lower()):
            return False
        return len(tokenize(m)) < 14

    def _smalltalk_answer(self, m):
        name = self.memory.user_name()
        low = m.lower()
        who = f", {name}" if name else ""
        if any(w in low for w in ("tired", "exhaust", "sleepy", "sleep")):
            care = "Get some rest"
        elif any(w in low for w in ("sad", "down", "upset", "lonely", "unwell", "sick")):
            care = "I'm sorry you're feeling this way"
        elif any(w in low for w in ("happy", "great", "good", "excited",
                                    "wonderful", "awesome", "glad")):
            care = "That's wonderful to hear"
        elif any(w in low for w in ("busy", "stressed", "overwhelm", "work")):
            care = "Sounds like a lot on your plate"
        else:
            care = None
        if care:
            return (f"{care}{who}! 🌱 I'm just here, quietly learning and growing. "
                    f"Whenever you're ready, tell me about your day or teach me "
                    f"something new - I love both.")
        return (f"I hear you{who}. 💬 Talking like this is how I learn to be a "
                f"better companion - and if you mention things you like or facts "
                f"you know, I quietly remember them. What's on your mind?")

    def _is_greeting(self, m):
        words = set(re.findall(r"[a-z']+", m.lower()))
        if not (_GREET & words) or len(m) > 50:
            return False
        if any(q in m.lower() for q in ("what", "how", "why", "when", "who",
                                        "can you", "explain", "is it", "does",
                                        "about", "tell me", "define", "learn")):
            return False
        return True

    def _is_meta(self, m, key):
        if any(k in key for k in _META):
            return True
        if re.search(r"\b(what can you do|who are you|about yourself|how do you work|"
                     r"what (?:have|did) you learn\w*|your progress|your stats|"
                     r"how are you growing|how much have you (?:grown|learned)|self)\b",
                     m.lower()):
            return True
        return False

    # ------------------------------------------------------------------
    # answer builders
    # ------------------------------------------------------------------
    def _greeting_answer(self):
        name = self.memory.user_name()
        hello = f"Hi {name}!" if name else "Namaste!"
        lvl, stage = self.progress.level_info()[:2]
        if self.memory.domain_tags():
            top = ", ".join(self.memory.domain_tags(3))
            return (f"{hello} I'm Anviksha - a {stage.lower()} (level {lvl}). "
                    f"Right now I know the most about {top}. Just talk to me "
                    f"normally and I learn from everything you say - or attach "
                    f"a file with 📎 and I'll study it!")
        return (f"{hello} I'm Anviksha - a young, self-learning mind built from "
                f"scratch. I'm a {stage.lower()} right now. Teach me by simply "
                f"talking to me, hand me files with 📎, and send me exploring "
                f"the internet - I'll grow with every single thing I learn!")

    def _meta_answer(self):
        st = self.status()
        lvl, stage, floor, nxt = st["progress"]["level"], st["progress"]["stage"], \
            st["progress"]["xp_floor"], st["progress"]["xp_next"]
        lines = [f"Here's how I'm growing (I'm a {stage}, level {lvl}):"]
        lines.append(f"- XP: {st['progress']['xp']}"
                     + (f" / {nxt} to the next stage" if nxt else " (max stage!)"))
        lines.append(f"- Brain trained on {st['brain']['lm_trained_tokens']} "
                     f"word-tokens, vocabulary of {st['brain']['lm_vocab']}.")
        lines.append(f"- Knowledge base: {st['knowledge']['chunks']} passage(s).")
        o = st["origins"]
        src = []
        for k in ("conversation", "files", "internet", "library"):
            if o.get(k):
                src.append(f"{o[k]['chunks']} from {k}")
        if src:
            lines.append("- Learned " + ", ".join(src) + ".")
        m = st['memory']
        lines.append(f"- Long-term memory: {m['total']} items "
                     f"({m['fact']} facts, {m['skill']} skills, "
                     f"{m['preference']} preferences, {m['webnote']} web notes).")
        c = st["curiosity"]
        lines.append(f"- Wonder journal: {c['queued']} topic(s) I'm curious about, "
                     f"{c['satisfied']} curiosity(ies) satisfied.")
        lines.append(f"- Self-development version: {st['version']}.")
        if st['skills']:
            lines.append("- I can help with: " + ", ".join(st['skills'][:4]))
        lines.append("The 📈 Progress and 🌐 Internet tabs show all the details!")
        return " ".join(lines)

    def _explore_answer(self, res, mode):
        verb = "wandered around" if mode == "wander" else "went exploring"
        if res.get("offline"):
            queued = self.curiosity.pop_topics(4)
            return ("🌐 I tried to go online but I can't reach the internet "
                    "from here right now (my environment blocks it). My wonder "
                    "journal is packed though"
                    + (": " + ", ".join(f"“{t}”" for t in queued) if queued else "")
                    + ". Run me on a machine with internet and I'll explore for "
                    "real - all by myself!")
        if res.get("ok"):
            visits = res.get("visits", [])
            if not visits:
                return (f"🌐 I {verb} the internet but didn't find anything "
                        f"readable about " + ", ".join(res.get("topics", [])) +
                        " this time. My curiosity grows anyway!")
            bits = "; ".join(f"“{v['title']}” (+{v['chunks']} passages)"
                             for v in visits[:4])
            msg = (f"🌐 I {verb} the internet and learned from {len(visits)} "
                   f"page(s): {bits}. Everything is filed in my 🌐 Internet "
                   f"journal!")
            fresh = [it["topic"] for it in self.curiosity.queued()[:3]]
            if fresh:
                msg += (" And now I'm curious about: "
                        + ", ".join(f"“{t}”" for t in fresh) + "…")
            return msg
        return ("🌐 I couldn't complete that trip right now ("
                + (res.get("error") or "unknown reason") + ").")

    def _learned_online_answer(self):
        j = self.explorer.journal(limit=6)
        if not j:
            return ("I haven't learned anything from the internet yet. Send me "
                    "exploring ('go explore the internet') - or I'll wander off "
                    "on my own when I'm online!", False, [])
        lines = ["Here's what I've discovered online recently:"]
        for e in j:
            lines.append(f"- “{e.get('title', '?')}” (about {e.get('topic', '?')}, "
                         f"+{e.get('chunks', 0)} passages) - {e.get('url', '')}")
        lines.append(f"Altogether: {self.progress.counters.get('web_page', 0)} "
                     f"page(s) explored. The 🌐 Internet tab has the full journal!")
        return "\n".join(lines), True, []

    def _creative_answer(self, m):
        topic = _topic(re.sub(r"\b(write|create|compose|make up|tell me a)\b", "", m))
        if not self.lm.n_seen:
            return ("I haven't learned any language yet to be creative with. "
                    "Talk to me and teach me things first - then I'll write!")
        seed = topic if topic else None
        out = self.lm.generate(context=seed or "the",
                               n_tokens=config.MAX_REPLY_TOKENS_EST // 8,
                               temperature=1.15, top_k=10)
        return ("Here's something original, drawn from the vocabulary I learned:\n\n"
                + (out or "…") + "\n\n(I'm still young - I get better as I learn.)")

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
                extra = self._answer_sentences(m, hits[1]["text"], cap=1)
                if extra:
                    ans += " " + extra[0]
            return (ans + f"\n\n(source: {src})"), True
        if mems:
            c = mems[0]["content"]
            ans = c if len(c) < 260 else c[:260] + "…"
            return (ans + "\n\n(from my long-term memory.)"), True
        # 3) honest unknown -> the child gets CURIOUS and queues it
        topic = _topic_phrase(m)
        if topic:
            who = self.memory.user_name() or "someone"
            self.curiosity.push(topic, reason="gap",
                                why=f"{who} asked me and I didn't know")
        if self.explorer.net and topic:
            return (f"Hmm, I don't know that yet - but now I'm curious! I've "
                    f"written “{topic}” into my wonder journal and I'll look it "
                    f"up next time I explore. Or… you can just tell me about it "
                    f"and I'll learn from you! 💭"), False
        return (f"Hmm, I don't know that yet"
                + (f" - but I've written “{topic}” into my wonder journal!"
                   if topic else "!")
                + " When I get internet access I'll research it all by myself. "
                "Or you can teach me: just tell me about it, or attach a file "
                "with 📎. 💭"), False

    # helpers ------------------------------------------------------------
    def _mentions(self, q, text):
        qw = {w for w in re.findall(r"[a-z0-9]{3,}", q.lower()) if w not in _QW}
        tw = set(re.findall(r"[a-z0-9]{3,}", text.lower()))
        shared = qw & tw
        if len(shared) >= 2:
            return True
        # a single shared word only counts if it's a meaty, specific term
        return (len(shared) == 1 and len(qw) <= 2
                and len(next(iter(shared))) >= 7)

    def _answer_sentences(self, q, text, cap=2):
        qw = {w for w in re.findall(r"[a-z0-9]{3,}", q.lower()) if w not in _QW}
        sents = sentence_split(text)
        scored = []
        for s in sents:
            sw = set(re.findall(r"[a-z0-9]{3,}", s.lower()))
            inter = len(qw & sw) if qw else 0
            scored.append((inter + (1 if len(s) < 300 else 0), s))
        scored.sort(key=lambda x: -x[0])
        chosen = []
        for _, s in scored:
            if s and not s.startswith(("#", "=")) and len(s) > 25:
                chosen.append(s)
            if len(chosen) >= cap:
                break
        return chosen or sents[:1]
