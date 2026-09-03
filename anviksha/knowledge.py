"""
KnowledgeBase - ingests *your* provided knowledge and a growing body of
explorer-collected material, chunking + indexing it for cheap retrieval.

Persistent artifact: knowledge_index.json
  {"chunks":[{"id","text","source","ts","tokens":[]}], "meta":{"docs":n}}
"""
import json
import math
import os
import time
from collections import defaultdict

from . import config
from .brain.tokens import tokenize, stem, chunks as split_chunks


class KnowledgeBase:
    def __init__(self, path: str = None):
        config.ensure_dirs()
        self.path = path or config.KNOWLEDGE_INDEX
        self.chunks = []
        self._df = defaultdict(int)      # token -> num chunks containing it
        self._n = 0
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                self.chunks = data.get("chunks", [])
                self._rebuild_stats()
            except Exception:
                self.chunks = []

    def _save(self):
        config.ensure_dirs()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"chunks": self.chunks, "meta": {"docs": len(self.chunks),
                                                       "ts": time.time()}}, f)
        os.replace(tmp, self.path)

    def _rebuild_stats(self):
        self._df = defaultdict(int)
        for c in self.chunks:
            for t in set(c.get("tokens", [])):
                self._df[t] += 1
        self._n = len(self.chunks)

    # -- ingestion ------------------------------------------------------
    def add_text(self, text: str, source: str = "knowledge", ts: float = None):
        """Add text to the KB. Returns number of new chunks created."""
        text = (text or "").strip()
        if not text:
            return 0
        ts = ts if ts is not None else time.time()
        added = 0
        for ctext in split_chunks(text):
            toks = [stem(t) for t in tokenize(ctext)]
            if len(toks) < 6:      # too small to be useful as its own chunk
                continue
            cid = f"{source}::{int(ts)}::{len(self.chunks)}"
            self.chunks.append({"id": cid, "text": ctext, "source": source,
                                "ts": ts, "tokens": toks})
            for t in set(toks):
                self._df[t] += 1
            added += 1
        self._n = len(self.chunks)
        self._save()
        return added

    def add_document(self, raw: str, source: str = "knowledge"):
        return self.add_text(raw, source=source)

    # -- retrieval (BM25 + bonus) --------------------------------------
    def _token_freqs(self, tokens):
        freqs = defaultdict(int)
        for t in tokens:
            freqs[t] += 1
        return freqs

    def query(self, text: str, k: int = 5) -> list:
        """Return up to k chunks sorted by relevance. Pure-Python BM25."""
        if not self.chunks:
            return []
        qtoks = [stem(t) for t in tokenize(text)]
        if not qtoks:
            return []
        qf = self._token_freqs(qtoks)
        k1, b = 1.2, 0.75
        avgdl = sum(len(c["tokens"]) for c in self.chunks) / self._n
        scores = []
        for c in self.chunks:
            doclen = len(c["tokens"])
            cf = self._token_freqs(c["tokens"])
            idf_sum = 0.0
            for q, qc in qf.items():
                f = cf.get(q, 0)
                if f == 0:
                    continue
                df = self._df.get(q, 0)
                idf = math.log(1 + (self._n - df + 0.5) / (df + 0.5))
                tf = f * (k1 + 1) / (f + k1 * (1 - b + b * doclen / avgdl))
                idf_sum += idf * tf
            if idf_sum > 0:
                scores.append((idf_sum, c))
        scores.sort(key=lambda x: -x[0])
        return [c for _, c in scores[:k]]

    def all_chunk_texts(self):
        return [c["text"] for c in self.chunks]

    def count(self):
        return self._n

    # -- where did my knowledge come from? -------------------------------
    @staticmethod
    def origin_of(source: str) -> str:
        s = (source or "").lower()
        if s.startswith("web:"):
            return "internet"
        if s.startswith("attachment:") or s.startswith("file:"):
            return "files"
        if s.startswith("chat"):
            return "conversation"
        if s.startswith("knowledge:"):
            return "library"
        return "other"

    def stats_by_origin(self):
        """Chunks + word counts grouped by learning channel."""
        out = {}
        for c in self.chunks:
            o = self.origin_of(c.get("source", ""))
            row = out.setdefault(o, {"chunks": 0, "words": 0, "sources": {}})
            row["chunks"] += 1
            row["words"] += len(c.get("tokens", []))
            src = c.get("source", "")
            row["sources"][src] = row["sources"].get(src, 0) + 1
        for row in out.values():
            top = sorted(row["sources"].items(), key=lambda x: -x[1])
            row["top_sources"] = [{"source": s, "chunks": n} for s, n in top[:8]]
            del row["sources"]
        return out

    def recent_chunks(self, limit=25):
        rows = sorted(self.chunks, key=lambda c: -c.get("ts", 0))[:limit]
        return [{"ts": c.get("ts", 0), "source": c.get("source", ""),
                 "origin": self.origin_of(c.get("source", "")),
                 "preview": c.get("text", "")[:180],
                 "words": len(c.get("tokens", []))} for c in rows]
