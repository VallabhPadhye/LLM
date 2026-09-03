"""
Tokenizer - a small, custom, dependency-free word/subword tokenizer.

Kept intentionally simple and cheap (low token count / power budget):
 - lowercase + split on non-alphanumeric
 - english + minimal character 'n-gram fallback' for typo-tolerant matching
 - returns raw word tokens; subword features are produced on demand.
"""
import re

_WORD = re.compile(r"[a-zA-Z0-9_]+(?:['\u2019][a-zA-Z]+)?")
_STOP = set("""a an the and or but if then else for of to in on at by with from
is are was were be been being it its this that these those i we you he she they
do does did have has had not no yes what when where who whom which why how
about into over under again further once here there all any both each few more
most other some such only own same so than too very can will just should would
could may might must shall as up down off out while during before after above
below above between via per through amid throughout because until unless our
your their my his her mine yours theirs ours me us him them""".split())

# A tiny English stemmer (Porter-lite) to improve matching cheaply.
_SSES = re.compile(r"(sses|ies|sses)$")
_ING  = re.compile(r"(ing|ed|es|s)$")


def tokenize(text: str, keep_stop: bool = False):
    """Return a list of lowercased word tokens."""
    toks = [m.group(0).lower() for m in _WORD.finditer(text or "")]
    if keep_stop:
        return toks
    return [t for t in toks if t not in _STOP and len(t) > 1]


def stem(tok: str) -> str:
    t = tok
    t = _SSES.sub("", t)
    if len(t) > 3 and t.endswith("ies"):
        t = t[:-3] + "y"
    if len(t) > 3 and _ING.search(t):
        t = _ING.sub("", t)
        if t.endswith("i"):
            t = t[:-1] + "y"
    return t


def char_ngrams(text: str, n: int = 3):
    """Character n-grams for fuzzy/semantic overlap (token-efficient proxy)."""
    s = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    if len(s) <= n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def sentence_split(text: str):
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def chunks(text: str, max_words: int = 220, overlap: int = 40):
    """Split a document into overlapping word chunks for indexing."""
    words = re.split(r"\s+", text.strip())
    out = []
    start = 0
    if not words:
        return out
    while start < len(words):
        end = min(start + max_words, len(words))
        out.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap
    return out
