"""
Autonomous Web Explorer - the part of Anviksha that behaves like a curious
child let loose on the internet.

It decides *by itself* what to look at, in this order of eagerness:
  1. gaps     - things the user asked that it didn't know (burning questions)
  2. wonders  - follow-up questions born while reading a previous page
  3. interests- topics derived from what it already knows
  4. seeds    - the innate wide-ranging curiosity of a newborn mind
                (dinosaurs, black holes, honeybees, music, ancient Egypt...)

It also has a "wander" mode: like a child clicking random links, it fetches
random Wikipedia articles and digests whatever it finds.

Everything it learns online goes to:
  - the knowledge base   (chunks, source "web:<title>")
  - long-term memory     (web notes with URLs)
  - the web journal      (data/web/journal.jsonl - shown in the UI)
  - the progress book    (XP + growth series)

Safety & honesty: query/page budgets per run, per-page character caps, short
timeouts, a denylist, and graceful "offline" reporting when egress is blocked
(nothing is ever faked as learned).
"""
import html as _html
import json
import os
import random
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

from . import config
from .brain.tokens import tokenize, sentence_split

DENYLIST_DOMAINS = {"example.com"}
_UA = "Mozilla/5.0 (compatible; Anviksha/1.0 self-learning-assistant)"
_TIMEOUT = 7

# words a child wouldn't find "wonder-worthy" when chaining curiosities
_BORING = set("""the a an of and or in on at to for with from by is are was were
be been this that these those it its as into over under about after before
between during without within also more most other some such many much main
first second third new old one two three four five ten hundred thousand
see also references external links further reading notes sources
category article page wiki wikipedia edition version published national
united states india world war century bc ad early modern late great small
large known used named made found given called general common popular
important significant related similar various several different often
usually sometimes always never however therefore although because while
during since until unless according based instead regardless typically""".split())


def network_available() -> bool:
    """Cheap reachability probe; returns False when egress is blocked."""
    try:
        s = socket.create_connection(("8.8.8.8", 53), 2)
        s.close()
        return True
    except Exception:
        return False


def _fetch(url: str, timeout: int = _TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw


def _html_to_text(raw: bytes) -> str:
    text = raw.decode("utf-8", "ignore")
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


class _ProviderResult:
    def __init__(self, ok, title="", text="", url="", error=""):
        self.ok = ok; self.title = title; self.text = text
        self.url = url; self.error = error


class WikipediaProvider:
    name = "wikipedia"

    def search(self, query, limit=3):
        url = ("https://en.wikipedia.org/w/api.php?action=opensearch"
               "&search=" + urllib.parse.quote(query) +
               "&limit=" + str(limit) + "&format=json")
        try:
            data = json.loads(_fetch(url))
            titles = data[1] if len(data) > 1 else []
            links = data[3] if len(data) > 3 else []
            return list(zip(titles, links))
        except Exception:
            return []

    def random_titles(self, n=1):
        url = ("https://en.wikipedia.org/w/api.php?action=query&list=random"
               f"&rnnamespace=0&rnlimit={n}&format=json")
        try:
            data = json.loads(_fetch(url))
            return [p.get("title", "") for p in
                    data.get("query", {}).get("random", []) if p.get("title")]
        except Exception:
            return []

    def fetch(self, title_or_url):
        url = title_or_url
        if not url.startswith("http"):
            url = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts"
                   "&explaintext=1&titles=" + urllib.parse.quote(title_or_url) +
                   "&format=json&redirects=1")
        try:
            if "api.php" in url:
                data = json.loads(_fetch(url))
                pages = list(data.get("query", {}).get("pages", {}).values())
                if not pages or "-1" in str(pages[0].get("pageid", "")):
                    return _ProviderResult(False, error="page not found")
                title = pages[0].get("title", "")
                text = pages[0].get("extract", "")
                canonical = ("https://en.wikipedia.org/wiki/"
                             + urllib.parse.quote(title.replace(" ", "_")))
                return _ProviderResult(True, title=title, text=text, url=canonical)
            else:
                title = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
                text = _html_to_text(_fetch(url))
                return _ProviderResult(True, title=title, text=text, url=url)
        except Exception as e:
            return _ProviderResult(False, error=str(e))


class Explorer:
    """One self-directed browsing agent. Call `explore_once()` to run a pass."""
    def __init__(self, kb, memory, curiosity=None, progress=None):
        self.kb = kb
        self.memory = memory
        self.curiosity = curiosity
        self.progress = progress
        self.net = network_available()
        self.provider = WikipediaProvider()
        self.providers = [self.provider]
        self._lock = threading.Lock()
        self._log_file = os.path.join(config.WEB_DIR, "explorer_log.jsonl")
        config.ensure_dirs()

    # -- logging ----------------------------------------------------------
    def _log_attempt(self, topic, outcome, detail="", url=""):
        row = {"ts": time.time(), "topic": topic, "outcome": outcome,
               "detail": detail, "url": url}
        with open(self._log_file, "a") as f:
            f.write(json.dumps(row) + "\n")
        self.memory._log("web", f"{outcome}: {topic} {detail}".strip(),
                         extra={"url": url})

    def _journal_write(self, entry):
        with open(config.JOURNAL_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def journal(self, limit=40):
        """What it has learned from the internet (newest first)."""
        if not os.path.exists(config.JOURNAL_FILE):
            return []
        rows = []
        with open(config.JOURNAL_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        rows.sort(key=lambda r: -r.get("ts", 0))
        return rows[:limit]

    # -- topic selection (self-directed, child-like) ----------------------
    def _pick_topics(self, n):
        """Curiosity queue first; then interests; then innate seed wonders."""
        topics = []
        if self.curiosity:
            topics += self.curiosity.pop_topics(n * 2)
        tags = self.memory.domain_tags(limit=config.AUTO_INTEREST_TAGS)
        for t in tags:
            if t not in topics:
                topics.append(t)
        # a newborn mind is curious about *everything*: sprinkle fresh seeds
        if self.curiosity:
            fresh = self.curiosity.seed_fresh(config.CURIOSITY_SEED_PER_RUN,
                                              avoid=topics)
            topics += [t for t in fresh if t not in topics]
        if not topics:
            topics = random.sample(config.SEED_WONDERS, k=min(3, len(config.SEED_WONDERS)))
        rng = random.Random()
        # keep gaps first (they matter most), shuffle the rest
        head = [t for t in topics[:2]]
        tail = topics[2:]
        rng.shuffle(tail)
        return (head + tail)[:n]

    def _probe(self) -> bool:
        """Return True only if a real HTTPS request succeeds (egress open)."""
        try:
            hits = self.provider.search("science", limit=1)
            return bool(hits)
        except Exception:
            return False

    # -- one exploration pass ----------------------------------------------
    def explore_once(self, topics=None, mode="curious", budget_queries=None,
                     budget_pages=None, silent=False):
        """
        Run a self-directed browsing session.
        mode="curious" -> follow the wonder journal / interests
        mode="wander"  -> fetch random pages like a child clicking links
        Gracefully reports 'offline' when egress is blocked.
        """
        if self.running_now():
            return {"ok": False, "error": "I'm already exploring - one trip at a time!"}
        self.net = self._probe()
        if not self.net:
            queued = self.curiosity.pop_topics(5) if self.curiosity else []
            if not silent:
                self._log_attempt("(any)", "offline",
                                  "network unreachable from this environment")
            return {"ok": False, "offline": True, "topics": queued,
                    "error": ("I can't reach the internet from here right now. "
                              "My wonder journal is ready though - the moment I "
                              "get connectivity I'll chase: "
                              + (", ".join(queued) if queued else "anything and everything")
                              + ".")}
        q = budget_queries or config.WEB_MAX_QUERIES_PER_RUN
        p = budget_pages or config.WEB_MAX_PAGES_PER_RUN
        self._running = True
        try:
            if mode == "wander":
                return self._wander(max_pages=p)
            topics = topics or self._pick_topics(q)
            summary = {"ok": True, "mode": mode, "topics": topics,
                       "queries": 0, "pages": 0, "new_chunks": 0, "visits": []}
            for topic in topics:
                if summary["queries"] >= q:
                    break
                hits = self._provider_search(topic)
                summary["queries"] += 1
                if not hits:
                    self._log_attempt(topic, "no-results")
                    continue
                for title, url in hits:
                    if summary["pages"] >= p:
                        break
                    if any(d in url for d in DENYLIST_DOMAINS):
                        continue
                    res = self._provider_fetch(url, title)
                    summary["pages"] += 1
                    if not res.ok or len(res.text) < 40:
                        self._log_attempt(topic, "skip", res.error, url)
                        continue
                    chunks = self._digest(res, topic, mode="curious")
                    summary["new_chunks"] += chunks
                    summary["visits"].append({"title": res.title, "url": res.url,
                                              "chunks": chunks, "topic": topic})
                    self._log_attempt(topic, "learned",
                                      f"{chunks} chunk(s) · {res.title}", res.url)
                    break      # one good page per topic, like a child skimming
            if summary["visits"]:
                nv = len(summary["visits"])
                self.memory.add("experience",
                                f"Explored the web on {', '.join(topics)} "
                                f"({nv} page(s) digested).",
                                source="web-explorer", priority=0.5, silent=True)
                self.memory._log("web", f"came back from exploring {nv} page(s): "
                                 + ", ".join(v["title"] for v in summary["visits"]))
            return summary
        finally:
            self._running = False

    _running = False

    def running_now(self):
        return self._running

    def _wander(self, max_pages=3):
        """Child-like wandering: random articles, digested with delight."""
        titles = self.provider.random_titles(max_pages)
        summary = {"ok": True, "mode": "wander", "topics": titles,
                   "queries": 0, "pages": 0, "new_chunks": 0, "visits": []}
        for title in titles:
            if summary["pages"] >= max_pages:
                break
            res = self.provider.fetch(title)
            summary["pages"] += 1
            if not res.ok or len(res.text) < 40:
                self._log_attempt(title, "skip", res.error)
                continue
            chunks = self._digest(res, title.lower(), mode="wander")
            summary["new_chunks"] += chunks
            summary["visits"].append({"title": res.title, "url": res.url,
                                      "chunks": chunks, "topic": title})
            self._log_attempt(title, "learned",
                              f"{chunks} chunk(s) · wandered onto {res.title}",
                              res.url)
        if summary["visits"]:
            self.memory.add("experience",
                            f"Wandered the web and stumbled upon "
                            f"{', '.join(v['title'] for v in summary['visits'])}.",
                            source="web-explorer", priority=0.45, silent=True)
            self.memory._log("web", "wandered and found: "
                             + ", ".join(v["title"] for v in summary["visits"]))
        return summary

    def _provider_search(self, topic):
        hits = []
        for prov in self.providers:
            try:
                hits = prov.search(topic)
            except Exception:
                hits = []
            if hits:
                break
        out, seen = [], set()
        for t, u in hits:
            if t and u and u.startswith("http") and u not in seen:
                seen.add(u)
                out.append((t, u))
            if len(out) >= 4:
                break
        return out

    def _provider_fetch(self, url, title):
        for prov in self.providers:
            try:
                res = prov.fetch(url if url.startswith("http") else title)
                if res.ok and res.text:
                    return res
            except Exception:
                continue
        return _ProviderResult(False, error="fetch failed")

    # -- digestion ----------------------------------------------------------
    def _digest(self, res, topic, mode="curious") -> int:
        """Store a fetched page into knowledge + memory + journal + XP."""
        text = res.text[: config.WEB_PAGE_MAX_CHARS]
        sents = [s for s in sentence_split(text) if 30 < len(s) < 300]
        digest = " ".join(sents[:2])[:300] if sents else text[:200]
        key_points = [{"text": s[:200]} for s in sents[1:4]]

        chunks = self.kb.add_text(text, source=f"web:{res.title}", ts=time.time())
        self.memory.add("webnote", digest or res.title,
                        source=f"web:{res.title}", priority=0.6,
                        tags=[topic.lower()], silent=True,
                        extra={"source_url": res.url})

        # the wonder journal entry (shown in the UI's Internet tab)
        entry = {"ts": time.time(), "mode": mode, "topic": topic,
                 "title": res.title, "url": res.url, "digest": digest,
                 "chunks": chunks, "key_points": [k["text"] for k in key_points]}
        self._journal_write(entry)

        # curiosity bookkeeping + XP
        filled = 0
        if self.curiosity:
            filled = self.curiosity.satisfy(topic, url=res.url, title=res.title)
            for follow in self._followup_wonders(text, topic, res.title):
                self.curiosity.push(follow, reason="wonder",
                                    why=f"popped up while I was reading about {topic}")
        if self.progress:
            self.progress.award("web_page",
                                config.XP["web_page"] + chunks * config.XP["web_chunk"],
                                label=f"explored '{res.title}' online (+{chunks} passages)")
            if filled:
                self.progress.award("gap_filled",
                                    amount=config.XP["gap_filled"] * filled,
                                    label=f"curiosity satisfied: {topic}")
        return chunks

    def _followup_wonders(self, text, topic, title):
        """Chain curiosity: find capitalized phrases worth wondering about."""
        out = []
        try:
            counts = {}
            for m in re.finditer(r"\b([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{2,}){0,2})\b",
                                 text[: config.WEB_PAGE_MAX_CHARS]):
                ph = m.group(1).strip()
                low = ph.lower()
                if low in _BORING or low == topic.lower() or low == title.lower():
                    continue
                if any(w.lower() in _BORING for w in ph.split()):
                    continue
                if len(ph) < 5 or ph.lower().startswith(title.lower()[:8]):
                    continue
                counts[low] = counts.get(low, 0) + 1
            known = set(self.memory.domain_tags(limit=60))
            ranked = sorted(counts.items(), key=lambda x: -x[1])
            for ph, c in ranked:
                if c >= 2 and ph not in known:
                    out.append(ph)
                if len(out) >= config.CURIOSITY_FOLLOWUPS:
                    break
        except Exception:
            pass
        return out

    def last_runs(self, limit=15):
        if not os.path.exists(self._log_file):
            return []
        rows = []
        with open(self._log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        rows.sort(key=lambda r: -r.get("ts", 0))
        return rows[:limit]


def start_autonomous(explorer, memory, interval_minutes=None, on_run=None):
    """
    Background loop: the child keeps wandering off to learn on its own.
    Every 3rd run is a random "wander" pass; the rest follow its curiosities.
    Returns a threading.Thread (daemon).
    """
    interval = interval_minutes or config.WEB_REFRESH_MINUTES
    stop = threading.Event()

    def loop():
        stop.wait(8)
        i = 0
        while not stop.is_set():
            try:
                mode = "wander" if (i % 3 == 2) else "curious"
                res = explorer.explore_once(mode=mode, silent=True)
                if on_run:
                    try:
                        on_run(res)
                    except Exception:
                        pass
            except Exception:
                pass
            i += 1
            stop.wait(interval * 60)

    t = threading.Thread(target=loop, daemon=True, name="anviksha-explorer")
    t.start()
    return t
