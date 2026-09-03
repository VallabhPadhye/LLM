"""
Anviksha - configuration & runtime paths.

Everything defaults to the repo-local `data/` directory so the whole system
runs without any external dependencies or services. Paths are created lazily.
"""
import os

# Repo root = parent of this package's directory.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# --- data subdirectories ------------------------------------------------
KNOWLEDGE_DIR  = os.path.join(DATA, "knowledge")   # user-provided knowledge (markdown/txt)
STORE_DIR      = os.path.join(DATA, "store")       # trained brain, indexes, memories
WEB_DIR        = os.path.join(DATA, "web")         # autonomous web-exploration logs/cache
WEB_ASSETS     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# --- persistent artifacts -----------------------------------------------
KNOWLEDGE_INDEX = os.path.join(STORE_DIR, "knowledge_index.json")
LM_STATE        = os.path.join(STORE_DIR, "lm_state.json")      # trained n-gram brain weights
MEMORY_FILE     = os.path.join(STORE_DIR, "memory.jsonl")       # long-term memory (append-only)
LEDGER_FILE     = os.path.join(STORE_DIR, "ledger.jsonl")       # activity feed shown in the UI
SELF_FILE       = os.path.join(STORE_DIR, "SELF.md")            # evolving self-instructions
VERSION_FILE    = os.path.join(STORE_DIR, "version.json")       # self-development versioning
INTENTS_FILE    = os.path.join(STORE_DIR, "intents.json")

# --- behaviour ----------------------------------------------------------
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")

# Internet exploration budget (safe defaults even when fully autonomous).
WEB_MAX_QUERIES_PER_RUN = int(os.environ.get("ANVIKSHA_QUERIES", "3"))
WEB_MAX_PAGES_PER_RUN   = int(os.environ.get("ANVIKSHA_PAGES", "4"))
WEB_PAGE_MAX_CHARS      = 6000      # trim fetched pages before digestion
WEB_REFRESH_MINUTES     = int(os.environ.get("ANVIKSHA_REFRESH_MIN", "30"))

# Topic inference: how many knowledge tags to draw "interests" from.
AUTO_INTEREST_TAGS      = 5
AUTO_INTEREST_MIN_CONF  = 0.20      # ignore very weak interests

# Long-term memory policy.
MEMORY_DECAY_PER_DAY    = 0.15      # priority decays if unused
MEMORY_TOP_FOR_EVOLVE   = 12
MAX_REPLY_TOKENS_EST    = 240       # target reply length (token-efficient by design)

def ensure_dirs() -> None:
    for d in (KNOWLEDGE_DIR, STORE_DIR, WEB_DIR):
        os.makedirs(d, exist_ok=True)
