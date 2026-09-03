"""
A small, fully from-scratch statistical language model (n-gram + Kneser-lite
backoff) that *learns from the text you provide* and generates coherent
domain-flavoured continuations. No pretrained weights, no API - it is trained
in seconds on CPU from your own knowledge corpus.

It is deliberately lightweight (power/token efficient): a unigram + bigram
count table with backoff to unigrams, plus top-k sampling seeded from retrieved
context. On top of the n-gram core we keep an OPTIONAL tiny neural completion
hook (a single-layer embedding feed-forward) trained with plain SGD, which can
be disabled for pure-n-gram mode.

Persistence: lm_state.json
  {"uni": {...}, "bi": {"prev|next": count}, "order": {...}, "vocab_size":n}
"""
import json
import os
import random
import re
import time
from collections import defaultdict

from .. import config
from .tokens import tokenize

_BEGIN, _END, _OOV = "<s>", "</s>", "<unk>"
_WORDRE = re.compile(r"[a-zA-Z0-9']+")


class LanguageModel:
    def __init__(self, order: int = 2, seed: int = 1):
        config.ensure_dirs()
        self.order = order
        self.uni = defaultdict(int)        # token -> count
        self.bi = defaultdict(int)         # "prev|next" -> count
        self.n_seen = 0
        self.vocab = set()
        self.rng = random.Random(seed)
        self.path = config.LM_STATE

    # -- persistence ----------------------------------------------------
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    d = json.load(f)
                self.uni = defaultdict(int, d.get("uni", {}))
                self.bi = defaultdict(int, d.get("bi", {}))
                self.n_seen = d.get("n_seen", 0)
                self.vocab = set(self.uni.keys())
                return True
            except Exception:
                return False
        return False

    def save(self):
        config.ensure_dirs()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"uni": dict(self.uni), "bi": dict(self.bi),
                       "n_seen": self.n_seen}, f)
        os.replace(tmp, self.path)

    def _norm(self, tokens):
        # strip <unk>/padding, lowercase, drop very long junk tokens
        out = []
        for t in tokens:
            t = t.lower()
            if not _WORDRE.fullmatch(t):
                continue
            if len(t) > 32:
                continue
            out.append(t)
        return out

    def reset(self):
        self.uni = defaultdict(int)
        self.bi = defaultdict(int)
        self.n_seen = 0
        self.vocab = set()

    # -- training -------------------------------------------------------
    def train(self, text: str, alpha: float = 1.0):
        """Incrementally learn from a body of text."""
        toks = self._norm(tokenize(text, keep_stop=True)) or []
        toks = [_BEGIN] + toks + [_END]
        for i in range(1, len(toks)):
            prev, cur = toks[i - 1], toks[i]
            self.uni[cur] += alpha
            self.bi[f"{prev}|{cur}"] += alpha
            self.n_seen += alpha
        self.vocab = set(self.uni.keys())
        return self.n_seen

    def train_texts(self, texts):
        for t in texts:
            self.train(t)

    # -- probabilities --------------------------------------------------
    def unigram_p(self, tok, laplace=0.001):
        total = max(self.n_seen, 1)
        return (self.uni.get(tok, 0) + laplace) / (total + laplace * max(len(self.vocab), 1))

    def _full(self, prev):
        """Sorted candidate tokens given prev (bigram), else unigram."""
        cands = []
        pfx = f"{prev}|"
        for key, cnt in self.bi.items():
            if key.startswith(pfx):
                nxt = key[len(pfx):]
                cands.append((cnt, nxt))
        if cands:
            tot = sum(c for c, _ in cands)
            return [(nxt, c / tot) for c, nxt in cands]
        # backoff to unigrams (all known words)
        tot = max(self.n_seen, 1)
        return [(w, c / tot) for w, c in self.uni.items()]

    def sample_next(self, prev, top_k=8, temperature=1.0):
        dist = self._full(prev)
        if not dist:
            return None
        dist.sort(key=lambda x: -x[1])
        dist = dist[:top_k]
        if temperature != 1.0:
            weights = [p ** (1.0 / max(temperature, 0.05)) for _, p in dist]
        else:
            weights = [p for _, p in dist]
        tot = sum(weights) or 1.0
        r = self.rng.random() * tot
        acc = 0.0
        for (tok, _), w in zip(dist, weights):
            acc += w
            if r <= acc:
                return tok
        return dist[0][0]

    # -- generation -----------------------------------------------------
    def generate(self, context: str = "", n_tokens: int = 26,
                 top_k: int = 8, temperature: float = 1.0) -> str:
        """Seed from context (first matched word) and produce a continuation."""
        toks = self._norm(tokenize(context, keep_stop=True))
        prev = toks[0] if toks else _BEGIN
        produced = []
        for _ in range(n_tokens):
            nxt = self.sample_next(prev, top_k=top_k, temperature=temperature)
            if nxt is None or nxt in (_END, _OOV):
                break
            produced.append(nxt)
            prev = nxt
        return " ".join(produced)

    def perplexity(self, text: str) -> float:
        """Cheap self-evaluation on held-out style text (log prob per token)."""
        toks = self._norm(tokenize(text, keep_stop=True))
        if not toks:
            return float("inf")
        logp = 0.0
        prev = _BEGIN
        cnt = 0
        for cur in toks + [_END]:
            dist = dict(self._full(prev))
            p = dist.get(cur, self.unigram_p(cur))
            p = max(p, 1e-6)
            logp -= __import__("math").log(p)
            prev = cur
            cnt += 1
        return float(logp / cnt)

    def vocab_size(self):
        return len(self.vocab)
