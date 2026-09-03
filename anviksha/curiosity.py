"""
Curiosity - Anviksha's wonder journal.

A child doesn't browse the web with a search strategy; it follows whatever it
is curious about. This module keeps a persistent queue of topics the mind
*wants to learn*:

  - "gap"      things the user asked that it didn't know  (highest priority)
  - "wonder"   follow-up questions born while reading a page
  - "interest" topics derived from what it already knows
  - "seed"     the innate, wide-ranging curiosity of a newborn mind

Persisted in data/store/curiosity.json.
"""
import json
import os
import random
import re
import threading
import time

from . import config

REASON_PRIORITY = {"gap": 1.0, "wonder": 0.75, "interest": 0.55, "seed": 0.35}
REASON_LABEL = {"gap": "someone asked me and I didn't know",
                "wonder": "I wondered about this while reading",
                "interest": "it connects to something I know",
                "seed": "just curious!"}


def _norm_topic(t: str) -> str:
    t = re.sub(r"\s+", " ", (t or "").strip().lower())
    t = re.sub(r"[^a-z0-9 \-']+", "", t)
    return t[:80]


class CuriosityJournal:
    def __init__(self, path: str = None):
        config.ensure_dirs()
        self.path = path or config.CURIOSITY_FILE
        self._lock = threading.Lock()
        self.items = []
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    d = json.load(f)
                self.items = d.get("items", []) or []
            except Exception:
                self.items = []

    def _save(self):
        config.ensure_dirs()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"items": self.items[-config.CURIOSITY_MAX_ITEMS:]}, f)
        os.replace(tmp, self.path)

    # -- writing ---------------------------------------------------------
    def push(self, topic: str, reason: str = "wonder", why: str = "",
             priority: float = None):
        """Add a topic to the wonder journal (deduplicates)."""
        topic = _norm_topic(topic)
        if not topic or len(topic) < 3:
            return None
        prio = REASON_PRIORITY.get(reason, 0.5) if priority is None else float(priority)
        with self._lock:
            for it in self.items:
                if it["topic"] == topic and it["status"] == "queued":
                    # already curious - strengthen the itch
                    it["priority"] = min(1.0, it.get("priority", 0.5) + 0.1)
                    if REASON_PRIORITY.get(reason, 0) > REASON_PRIORITY.get(it.get("reason"), 0):
                        it["reason"], it["why"] = reason, why
                    self._save()
                    return it
            it = {"id": f"c{int(time.time() * 1000)}-{len(self.items)}",
                  "topic": topic, "reason": reason, "why": why,
                  "ts": time.time(), "priority": prio, "status": "queued"}
            self.items.append(it)
            if len(self.items) > config.CURIOSITY_MAX_ITEMS:
                self.items = self.items[-config.CURIOSITY_MAX_ITEMS:]
            self._save()
            return it

    def satisfy(self, topic: str, url: str = "", title: str = ""):
        """Mark queued curiosities about `topic` as satisfied. Returns count."""
        topic = _norm_topic(topic)
        n = 0
        with self._lock:
            for it in self.items:
                if it["status"] != "queued":
                    continue
                if it["topic"] == topic or topic in it["topic"] or it["topic"] in topic:
                    it["status"] = "satisfied"
                    it["satisfied_ts"] = time.time()
                    it["url"], it["title"] = url, title
                    n += 1
            if n:
                self._save()
        return n

    # -- reading ---------------------------------------------------------
    def queued(self):
        out = [it for it in self.items if it.get("status") == "queued"]
        out.sort(key=lambda it: (-it.get("priority", 0), it.get("ts", 0)))
        return out

    def pop_topics(self, n: int):
        """The n topics it is most curious about right now."""
        return [it["topic"] for it in self.queued()[:n]]

    def satisfied(self, limit=20):
        out = [it for it in self.items if it.get("status") == "satisfied"]
        out.sort(key=lambda it: -it.get("satisfied_ts", 0))
        return out[:limit]

    def counts(self):
        q = self.queued()
        by = {}
        for it in q:
            by[it["reason"]] = by.get(it["reason"], 0) + 1
        return {"queued": len(q), "satisfied": sum(1 for i in self.items
                                                   if i.get("status") == "satisfied"),
                "by_reason": by}

    def seed_fresh(self, n: int = None, avoid=()):
        """Sprinkle innate, wide-ranging curiosity (a child's random wonders)."""
        n = n or config.CURIOSITY_SEED_PER_RUN
        have = {it["topic"] for it in self.items} | {_norm_topic(a) for a in avoid}
        pool = [t for t in config.SEED_WONDERS if _norm_topic(t) not in have]
        random.shuffle(pool)
        added = []
        for t in pool[:n]:
            it = self.push(t, reason="seed", why=REASON_LABEL["seed"])
            if it:
                added.append(it["topic"])
        return added

    def for_ui(self, limit=40):
        rows = []
        for it in self.queued()[:limit]:
            rows.append({"topic": it["topic"], "reason": it["reason"],
                         "why": it.get("why", ""), "status": "queued",
                         "priority": it.get("priority", 0.5), "ts": it.get("ts", 0),
                         "label": REASON_LABEL.get(it["reason"], "")})
        for it in self.satisfied(limit=12):
            rows.append({"topic": it["topic"], "reason": it["reason"],
                         "why": it.get("why", ""), "status": "satisfied",
                         "priority": it.get("priority", 0.5),
                         "ts": it.get("satisfied_ts", 0),
                         "url": it.get("url", ""), "title": it.get("title", ""),
                         "label": REASON_LABEL.get(it["reason"], "")})
        return rows
