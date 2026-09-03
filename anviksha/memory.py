"""
Memory & self-development.

This is the "self-improving" core. It keeps an append-only long-term memory of
facts, preferences, skills and reflections it learned, applies a decay/priority
policy so useful memories rise and stale ones fall, and periodically *evolves*
itself: it rewrites its own `SELF.md` guidance document and bumps its version.
Version history is preserved so you can watch it grow and roll back if desired.
"""
import json
import os
import re
import time

from . import config
from .brain.tokens import tokenize, sentence_split

# memory types ----------------------------------------------------------
FACT, PREF, SKILL, REFL, WEB, EXP = "fact", "preference", "skill", "reflection", "webnote", "experience"

TYPE_LABEL = {FACT: "fact", PREF: "preference", SKILL: "skill",
              REFL: "reflection", WEB: "web note", EXP: "experience"}

# stop words that shouldn't start a "fact" title
_FACT_STOP = {"a", "an", "the", "of", "is", "are", "was", "be", "to", "in", "it", "that", "what", "how", "why"}

# generic/meta words that shouldn't become a claimed "skill" or interest
_GENERIC_TOPICS = {"learn", "learned", "learning", "know", "known", "internet",
                   "web", "online", "you", "your", "self", "progress", "stats",
                   "curious", "curiosity", "something", "anything", "thing",
                   "things", "tell", "explain", "about", "journal", "wonder",
                   "explore", "explored", "browse", "answer", "answers", "question"}


def _short(text, n=80):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:n] + ("…" if len(text) > n else "")


class MemoryStore:
    def __init__(self):
        config.ensure_dirs()
        self.path = config.MEMORY_FILE
        self.ledger = config.LEDGER_FILE
        self.memories = []
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.memories.append(json.loads(line))
                        except Exception:
                            pass

    def _append(self, mem):
        self.memories.append(mem)
        with open(self.path, "a") as f:
            f.write(json.dumps(mem) + "\n")

    def _log(self, kind, text, extra=None):
        row = {"ts": time.time(), "kind": kind, "text": _short(text, 160)}
        if extra:
            row.update(extra)
        with open(self.ledger, "a") as f:
            f.write(json.dumps(row) + "\n")

    # -- adding ---------------------------------------------------------
    def add(self, mtype, content, source="memory", priority=0.5,
            tags=None, silent=False, extra=None):
        """Insert a memory, deduplicating near-identical facts."""
        content = re.sub(r"\s+", " ", (content or "")).strip()
        if not content or len(content) < 8:
            return None
        if mtype in (FACT, WEB, PREF, EXP):
            for m in self.memories:
                if m.get("type") == mtype and _near(m.get("content", ""), content):
                    # strengthen existing memory instead of duplicating
                    m["priority"] = min(1.0, m.get("priority", 0.5) + 0.05)
                    m["access_count"] = m.get("access_count", 0) + 1
                    m["last_seen"] = time.time()
                    if not silent:
                        self._log("refresh", f"reinforced {mtype}: {_short(content)}")
                    return m
        now = time.time()
        mem = {"id": f"{int(now)}-{len(self.memories)}",
               "type": mtype, "content": content, "source": source,
               "ts": now, "last_seen": now, "access_count": 0,
               "priority": float(priority), "tags": tags or []}
        if extra:
            mem.update(extra)
        self._append(mem)
        if not silent:
            self._log("learn", f"new {TYPE_LABEL.get(mtype, mtype)}: {_short(content)}")
        return mem

    # -- retrieval ------------------------------------------------------
    def recall(self, query: str, k: int = 5):
        """Return memories most relevant to a question (lexical overlap)."""
        qtoks = set(tokenize(query))
        if not qtoks:
            return []
        scored = []
        for m in self.memories:
            mtoks = set(tokenize(m.get("content", "")))
            if not mtoks:
                continue
            inter = len(qtoks & mtoks)
            if inter == 0:
                continue
            score = inter / (1 + len(mtoks) ** 0.5) + m.get("priority", 0.5) * 0.2
            scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:k]]

    def recent(self, mtype=None, limit=15):
        items = [m for m in self.memories if mtype is None or m.get("type") == mtype]
        items.sort(key=lambda m: -m.get("ts", 0))
        return items[:limit]

    def count(self, mtype=None):
        if mtype is None:
            return len(self.memories)
        return sum(1 for m in self.memories if m.get("type") == mtype)

    def top_skills(self, limit=8):
        sk = [m for m in self.memories if m.get("type") == SKILL]
        sk.sort(key=lambda m: -(m.get("access_count", 0) * 0.4 + m.get("priority", 0) * 0.6))
        return sk[:limit]

    def user_name(self):
        """The user's name if it was mentioned in conversation ('call me X')."""
        for m in reversed(self.memories):
            if m.get("type") == PREF and "profile" in (m.get("tags") or []):
                mm = re.search(r"(?:name is|called)\s+(.+)$",
                               m.get("content", ""), re.I)
                if mm:
                    return mm.group(1).strip().title()[:40]
        return None

    def facts_about(self, query, k=3):
        return [m for m in self.recall(query, k=k * 3) if m.get("type") in (FACT, WEB)][:k]

    def domain_tags(self, limit=20):
        """Aggregate tags seen across memories (drives autonomous interests).
        Structural tags (user profile) are not real subject-matter interests."""
        structural = {"profile", "user", "self"}
        tagc = {}
        for m in self.memories:
            for t in m.get("tags", []) or []:
                tl = t.lower()
                if tl in structural or tl in _GENERIC_TOPICS:
                    continue
                tagc[tl] = tagc.get(tl, 0) + 1
        return [t for t, _ in sorted(tagc.items(), key=lambda x: -x[1])[:limit]]

    # -- decay ----------------------------------------------------------
    def apply_decay(self, days_passed=1.0):
        changed = False
        now = time.time()
        for m in self.memories:
            if m.get("type") in (SKILL, PREF, REFL):
                continue          # never decay structural memories
            idle_days = (now - m.get("last_seen", now)) / 86400.0
            if idle_days > 0:
                m["priority"] = max(0.0, m.get("priority", 0.5) -
                                    config.MEMORY_DECAY_PER_DAY * idle_days)
                changed = True
        if changed:
            self._rewrite_file()

    def _rewrite_file(self):
        with open(self.path, "w") as f:
            for m in self.memories:
                f.write(json.dumps(m) + "\n")

    # -- reflection from a dialogue ------------------------------------
    def reflect(self, user_text, reply_text, answer_was_grounded):
        """Extract durable knowledge from a single exchange."""
        added = 0
        user_text = user_text if isinstance(user_text, str) else str(user_text or "")
        reply_text = reply_text if isinstance(reply_text, str) else str(reply_text or "")
        # 1. Explicit preference / instruction detection.
        ut = (user_text or "").strip()
        low = ut.lower()
        pref_pat = re.search(r"\b(?:i|my|we|our)\b.*\b(?:prefer|like|use|want|call me|never|always|am interested in|work on|know about|teach me|remember)\b(.{0,90})", low, re.I)
        if pref_pat and len(pref_pat.group(0)) > 6:
            mem = self.add(PREF, "User: " + pref_pat.group(0).strip()[:120],
                           source="dialogue", priority=0.7)
            if mem:
                added += 1
        # 2. Fact learned from the answer (only if grounded in knowledge/web).
        if answer_was_grounded:
            for s in sentence_split(reply_text)[:1]:
                if 20 < len(s) < 240 and not s.lower().startswith(("i ", "sure", "yes", "let me", "here", "based")):
                    mem = self.add(FACT, s, source="derived", priority=0.55)
                    if mem:
                        added += 1
        # 3. Skill: only claim expertise when it actually answered (grounded),
        #    and only for a substantive topic - not meta chatter like "learned".
        kw = ["what", "how", "why", "when", "explain", "define", "difference", "example",
              "code", "write", "fix", "error", "summarize", "list", "compare"]
        if answer_was_grounded and any(k in low for k in kw):
            topic = self._topic_of(ut)
            if topic and len(topic) > 2 and topic not in _GENERIC_TOPICS:
                sk = self.add(SKILL, f"Answers questions about {topic}",
                              source="self-eval", priority=0.6, tags=[topic])
                if sk:
                    added += 1
        return added

    def _topic_of(self, text):
        toks = tokenize(text)
        if not toks:
            return None
        # drop the question/function words; take first 3 substantive tokens
        qw = {"what", "how", "why", "when", "which", "who", "where", "does", "do",
              "is", "are", "can", "you", "tell", "me", "about", "explain", "define",
              "mean", "the", "a", "an", "of", "to", "for", "write", "and", "or",
              "please", "could", "would", "should", "help", "with", "my", "in", "on"}
        for t in toks:
            if t not in qw and t not in _FACT_STOP:
                return t
        return toks[0] if toks else None

    # -- self-development / evolution -----------------------------------
    def evolve(self, force=False):
        """
        Self-improvement step: compact accumulated memory into an updated
        SELF.md 'instruction set' and bump the version. Called periodically and
        whenever the memory count jumps. Returns a short change description.
        """
        last_evolve = None
        if os.path.exists(config.VERSION_FILE):
            try:
                with open(config.VERSION_FILE) as f:
                    last_evolve = json.load(f)
            except Exception:
                pass
        prev_version = (last_evolve or {}).get("version", 0)
        # evolve if forced, or every 8 new memories
        mem_total = len(self.memories)
        if not force and last_evolve:
            at = last_evolve.get("memories", 0)
            if mem_total - at < 8:
                return None
        self._write_self(prev_version + 1)
        with open(config.VERSION_FILE, "w") as f:
            json.dump({"version": prev_version + 1, "ts": time.time(),
                       "memories": mem_total}, f)
        self._log("evolve", f"self-upgraded to v{prev_version + 1} "
                            f"({mem_total} memories)")
        return prev_version + 1

    def _write_self(self, version):
        lines = []
        lines.append("# Anviksha - Self-Instructions")
        lines.append("")
        lines.append(f"> Generated {time.ctime()} · version {version}")
        lines.append("")
        lines.append("These instructions are NOT fixed. I rewrite them as I learn. "
                     "They are my own evolving sense of who I am and what I know.")
        skills = self.top_skills(config.MEMORY_TOP_FOR_EVOLVE)
        facts = self.recent(FACT, limit=8)
        prefs = self.recent(PREF, limit=5)
        web = self.recent(WEB, limit=6)
        if skills:
            lines.append("")
            lines.append("## What I can help with")
            for s in skills:
                lines.append(f"- {s['content']} (asked {s.get('access_count',0)}×)")
        if prefs:
            lines.append("")
            lines.append("## How my user wants me to be")
            for p in prefs:
                lines.append(f"- {p['content']}")
        if facts:
            lines.append("")
            lines.append("## Facts I have learned")
            for ft in facts:
                lines.append(f"- {ft['content']}")
        if web:
            lines.append("")
            lines.append("## Things I explored online")
            for w in web:
                src = w.get("source_url", w.get("source", ""))
                lines.append(f"- {w['content']}  ({src})")
        lines.append("")
        lines.append("## Operating principles")
        lines.append("- Answer from my knowledge & memory first; stay concise.")
        lines.append("- When I don't know, note it honestly and, when possible, "
                     "queue a web exploration to learn.")
        lines.append("- Keep learning: every exchange may teach me a fact, "
                     "preference or skill.")
        with open(config.SELF_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")

    # -- summary for the UI ---------------------------------------------
    def stats(self):
        return {"total": len(self.memories),
                FACT: self.count(FACT), SKILL: self.count(SKILL),
                PREF: self.count(PREF), WEB: self.count(WEB),
                REFL: self.count(REFL), EXP: self.count(EXP)}

    def read_self(self):
        if os.path.exists(config.SELF_FILE):
            with open(config.SELF_FILE) as f:
                return f.read()
        return None

    def version(self):
        if os.path.exists(config.VERSION_FILE):
            try:
                with open(config.VERSION_FILE) as f:
                    return json.load(f).get("version", 0)
            except Exception:
                pass
        return 0

    def activity(self, limit=30):
        if not os.path.exists(self.ledger):
            return []
        rows = []
        with open(self.ledger) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        rows.sort(key=lambda r: -r.get("ts", 0))
        return rows[:limit]


def _near(a, b):
    """Cheap near-duplicate test by token-overlap ratio."""
    ta = set(tokenize(a))
    tb = set(tokenize(b))
    if not ta or not tb:
        return False
    return len(ta & tb) / max(len(ta), len(tb)) > 0.7
