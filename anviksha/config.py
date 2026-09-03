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
PROGRESS_FILE   = os.path.join(STORE_DIR, "progress.json")      # XP / level / growth series
CURIOSITY_FILE  = os.path.join(STORE_DIR, "curiosity.json")     # the wonder journal
JOURNAL_FILE    = os.path.join(WEB_DIR, "journal.jsonl")        # what it learned online

# --- behaviour ----------------------------------------------------------
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")

# Internet exploration budget (safe defaults even when fully autonomous).
WEB_MAX_QUERIES_PER_RUN = int(os.environ.get("ANVIKSHA_QUERIES", "3"))
WEB_MAX_PAGES_PER_RUN   = int(os.environ.get("ANVIKSHA_PAGES", "4"))
WEB_PAGE_MAX_CHARS      = 6000      # trim fetched pages before digestion
WEB_REFRESH_MINUTES     = int(os.environ.get("ANVIKSHA_REFRESH_MIN", "10"))

# Topic inference: how many knowledge tags to draw "interests" from.
AUTO_INTEREST_TAGS      = 5
AUTO_INTEREST_MIN_CONF  = 0.20      # ignore very weak interests

# Curiosity (child-like wonder).
CURIOSITY_MAX_ITEMS     = 200       # cap on the wonder journal
CURIOSITY_SEED_PER_RUN  = 2         # fresh "just curious" topics per exploration run
CURIOSITY_FOLLOWUPS     = 2         # follow-up wonders derived per digested page

# Long-term memory policy.
MEMORY_DECAY_PER_DAY    = 0.15      # priority decays if unused
MEMORY_TOP_FOR_EVOLVE   = 12
MAX_REPLY_TOKENS_EST    = 240       # target reply length (token-efficient by design)

# Attachments (teaching by file).
ATTACH_MAX_FILE_BYTES   = 12 * 1024 * 1024    # 12 MB per file
ATTACH_MAX_TOTAL_BYTES  = 25 * 1024 * 1024    # 25 MB per request

# --- growth: XP levels ("stages of childhood" for the mind) --------------
# (xp_needed_for_this_level, stage_name)
LEVELS = [
    (0,     "Newborn Mind"),
    (120,   "Babbler"),
    (350,   "Curious Toddler"),
    (800,   "Question Machine"),
    (1600,  "Young Explorer"),
    (3200,  "Bright Student"),
    (6000,  "Knowledge Seeker"),
    (11000, "Wise Mind"),
]

# XP awards per kind of learning event.
XP = {
    "chat_turn":        2,    # every exchange keeps the mind active
    "fact_from_chat":  20,    # a fact taught in ordinary conversation
    "chunk_from_chat":  4,    # a passage indexed from conversation
    "file_base":       30,    # an attachment was read
    "file_chunk":       6,    # per passage indexed from an attachment
    "web_page":        40,    # a page explored on the internet
    "web_chunk":        3,    # per passage indexed from the web
    "gap_filled":      25,    # curiosity satisfied: something it didn't know
    "evolve":          60,    # self-instructions rewritten
}

# --- seed curiosities: the diverse interests of a newborn mind ----------
SEED_WONDERS = [
    # nature & animals
    "honeybees", "dinosaurs", "octopus intelligence", "migration of monarch butterflies",
    "how trees talk to each other", "deep sea creatures", "why cats purr",
    "the largest animals on earth", "how birds navigate", "bioluminescence",
    # space & earth
    "the solar system", "black holes", "why the sky is blue", "how rainbows form",
    "volcanoes", "the moon landing", "aurora borealis", "exoplanets",
    "how seasons work", "the water cycle",
    # body & mind
    "how the human brain learns", "memory and the hippocampus", "why we dream",
    "how the immune system works", "the five senses", "why we sleep",
    # history & culture
    "ancient Egypt", "the invention of writing", "the silk road",
    "history of mathematics", "ancient indian science", "the library of alexandria",
    "how paper was invented", "history of tea", "the printing press",
    # art & music
    "how music affects the brain", "origin of musical instruments", "cave paintings",
    "how colors are named in different languages", "poetry forms around the world",
    # science & technology
    "how language models work", "photosynthesis", "how the internet works",
    "the structure of atoms", "gravity", "evolution by natural selection",
    "how computers calculate", "electricity", "dna", "how rockets escape gravity",
    "the periodic table", "how vaccines work", "climate and oceans",
    "how bread rises", "why onions make us cry", "how chocolate is made",
    "origins of the alphabet", "how maps are made", "why ice floats",
    "how ants build colonies", "the speed of light", "prime numbers",
    "how glass is made", "why stars twinkle", "how earthquakes happen",
]

def ensure_dirs() -> None:
    for d in (KNOWLEDGE_DIR, STORE_DIR, WEB_DIR):
        os.makedirs(d, exist_ok=True)
