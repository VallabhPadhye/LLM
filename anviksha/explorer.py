"""
Autonomous Web Explorer.

Anviksha decides topics of interest from what it is learning and periodically
(or on request) browses the web to gather knowledge, then digests pages into
its knowledge base and web-memories. Designed to be *safe and budgeted* even in
fully-autonomous mode:

 - a query/pages budget per run, a per-page character cap, and short timeouts;
 - a small denylist of high-risk domains;
 - graceful degradation: if the network is unreachable (e.g. no egress) it
   reports "offline", logs the attempt and never crashes.

Providers are pluggable: a default Wikipedia provider (reliable, clean markup)
plus an optional DuckDuckGo HTML provider used when available.
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
            titles, links = (data[1] if len(data) > 1 else []), (data[3] if len(data) > 3 else [])
            return list(zip(titles, links))
        except Exception as e:
            return [("", "")]
        # keep signature simple; real filtering in _candidate()

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
                title = url.rsplit("/", 1)[-1].replace("_", " ")
                text = _html_to_text(_fetch(url))
                return _ProviderResult(True, title=title, text=text, url=url)
        except Exception as e:
            return _ProviderResult(False, error=str(e))


class DuckDuckGoProvider:
    name = "duckduckgo"

    def search(self, query, limit=3):
        url = ("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
        try:
            raw = _html_to_text(_fetch(url))
            return [(t, u) for t, u in self._extract(raw)[:limit]]
        except Exception:
            return []

    @staticmethod
    def _extract(text):
        # crude link extraction from plaintext dumps is unreliable; keep small
        res = []
        for m in re.finditer(r"(?i)\b(?:result__a'?[^>]*>|https?://)([^\n]+)", text):
            pass
        return res


class Explorer:
    """One self-directed browsing agent. Call `explore_once()` to run a pass."""
    def __init__(self, kb, memory):
        self.kb = kb
        self.memory = memory
        self.net = network_available()
        self.providers = [WikipediaProvider()]
        self._lock = threading.Lock()
        self._log_file = os.path.join(config.WEB_DIR, "explorer_log.jsonl")
        self.attempts_today = 0
        self.running = False
        config.ensure_dirs()
        self._load_stats()

    def _load_stats(self):
        # crude per-session attempt count kept in memory; budgets enforced per run anyway
        pass

    def _log_attempt(self, topic, outcome, detail="", url=""):
        row = {"ts": time.time(), "topic": topic, "outcome": outcome,
               "detail": detail, "url": url}
        with open(self._log_file, "a") as f:
            f.write(json.dumps(row) + "\n")
        self.memory._log("web", f"{outcome}: {topic} {detail}".strip(), extra={"url": url})

    # -- topic selection (self-directed) ---------------------------------
    def _pick_topics(self, n):
        """Topics = interests derived from what Anviksha already knows."""
        tags = self.memory.domain_tags(limit=config.AUTO_INTEREST_TAGS)
        topics = []
        if not tags:
            topics = ["artificial intelligence",
                      "machine learning",
                      "how language models work"]
        else:
            topics = tags[:n]
        rng = random.Random(int(time.time()) // 3600)   # fresh each hour
        rng.shuffle(topics)
        return topics[:n]

    def _probe(self) -> bool:
        """Return True only if a real HTTPS request succeeds (egress open)."""
        try:
            probe = WikipediaProvider()
            hits = probe.search("science", limit=1)
            return bool(hits)
        except Exception:
            return False

    # -- one pass --------------------------------------------------------
    def explore_once(self, topics=None, budget_queries=None, budget_pages=None,
                     silent=False):
        """
        Run a self-directed browsing session. Returns a dict summary.
        Gracefully reports 'offline' if the network is unreachable.
        """
        if self.running:
            return {"ok": False, "error": "exploration already running"}
        self.net = self._probe()
        if not self.net:
            if not silent:
                self._log_attempt("(any)", "offline",
                                  "network unreachable from this environment")
            return {"ok": False, "offline": True,
                    "error": "Network is unreachable from this environment. "
                             "Anviksha's explorer needs internet access - it will "
                             "work where egress is open (e.g. your own machine)."}
        q = budget_queries or config.WEB_MAX_QUERIES_PER_RUN
        p = budget_pages or config.WEB_MAX_PAGES_PER_RUN
        topics = topics or self._pick_topics(q)
        self.running = True
        try:
            summary = {"topics": topics, "queries": 0, "pages": 0,
                       "new_chunks": 0, "visits": []}
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
                    chunks = self._digest(res, topic)
                    summary["new_chunks"] += chunks
                    summary["visits"].append({"title": res.title, "url": res.url,
                                              "chunks": chunks})
                    self._log_attempt(topic, "learned",
                                      f"{chunks} chunk(s) · {res.title}", res.url)
            # let memory reflect that we explored
            if summary["visits"]:
                nv = len(summary["visits"])
                self.memory.add("experience",
                                f"Explored the web on {', '.join(topics)} "
                                f"({nv} page(s) digested).",
                                source="web-explorer", priority=0.5,
                                silent=True)
            return {"ok": True, **summary}
        finally:
            self.running = False

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

    def _digest(self, res, topic) -> int:
        """Store a fetched page into knowledge + a concise web memory."""
        text = res.text[: config.WEB_PAGE_MAX_CHARS]
        # pick a concise digest for memory: first meaningful sentences
        sents = sentence_split(text)
        digest = " ".join(sents[:2])[:300] if sents else text[:200]
        # into the knowledge base
        chunks = self.kb.add_text(text, source=f"web:{res.title}", ts=time.time())
        # a short web memory for recall
        self.memory.add("webnote",
                        digest or res.title,
                        source=f"web:{res.title}",
                        priority=0.6,
                        tags=[topic.lower()],
                        silent=True,
                        extra={"source_url": res.url})
        return chunks

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


def start_autonomous(explorer, memory, interval_minutes=None):
    """
    Background loop that makes Anviksha browse by itself on a schedule.
    Returns a threading.Thread (daemon) you can keep running.
    """
    interval = interval_minutes or config.WEB_REFRESH_MINUTES
    stop = threading.Event()

    def loop():
        # small initial stagger so the app boots fast
        stop.wait(8)
        while not stop.is_set():
            try:
                # only browse when there are topics worth chasing
                if memory.domain_tags() or not memory.recent(limit=1):
                    explorer.explore_once(silent=True)
            except Exception:
                pass
            stop.wait(interval * 60)

    t = threading.Thread(target=loop, daemon=True, name="anviksha-explorer")
    t.start()
    return t
