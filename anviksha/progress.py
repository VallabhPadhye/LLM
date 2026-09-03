"""
Progress - the growth book of a young mind.

Tracks XP (experience points), the current stage of development, per-source
counters ("what did I learn from conversation / files / the internet") and a
time series used to draw growth charts in the UI.

Persisted in data/store/progress.json:
  {"xp":int, "born":ts, "counters":{...}, "series":[{t,xp,chunks,mems,pages,facts}],
   "level_events":[{ts,level,stage}], "recent":[{ts,kind,text,xp}]}
"""
import json
import os
import threading
import time

from . import config

_SERIES_CAP = 1200
_RECENT_CAP = 60


class Progress:
    def __init__(self, path: str = None):
        config.ensure_dirs()
        self.path = path or config.PROGRESS_FILE
        self._lock = threading.Lock()
        self.xp = 0
        self.born = time.time()
        self.counters = {}
        self.series = []
        self.level_events = []
        self.recent = []          # recent learning moments (for the UI feed)
        self._last_snapshot = 0.0
        self._last_state = None
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    d = json.load(f)
                self.xp = int(d.get("xp", 0))
                self.born = float(d.get("born", time.time()))
                self.counters = d.get("counters", {}) or {}
                self.series = d.get("series", []) or []
                self.level_events = d.get("level_events", []) or []
                self.recent = d.get("recent", []) or []
            except Exception:
                pass

    def _save(self):
        config.ensure_dirs()
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"xp": self.xp, "born": self.born,
                       "counters": self.counters, "series": self.series,
                       "level_events": self.level_events,
                       "recent": self.recent[-_RECENT_CAP:]}, f)
        os.replace(tmp, self.path)

    # -- levels ---------------------------------------------------------
    def level_info(self, xp: int = None):
        """Return (level_number, stage_name, xp_floor, xp_next_or_None)."""
        xp = self.xp if xp is None else xp
        lvl, stage, floor = 1, config.LEVELS[0][1], 0
        for i, (need, name) in enumerate(config.LEVELS):
            if xp >= need:
                lvl, stage, floor = i + 1, name, need
        nxt = None
        if lvl < len(config.LEVELS):
            nxt = config.LEVELS[lvl][0]
        return lvl, stage, floor, nxt

    # -- awarding -------------------------------------------------------
    def bump(self, counter: str, by: int = 1):
        with self._lock:
            self.counters[counter] = int(self.counters.get(counter, 0)) + by

    def award(self, kind: str, amount: int = None, label: str = ""):
        """
        Add XP for a learning event. `kind` indexes config.XP.
        Returns {"xp": gained, "leveled_up": bool, "level": n, "stage": name}.
        """
        gained = int(amount if amount is not None else config.XP.get(kind, 0))
        with self._lock:
            before_lvl = self.level_info()[0]
            if gained:
                self.xp += gained
            self.counters[kind] = int(self.counters.get(kind, 0)) + 1
            after = self.level_info()
            leveled = after[0] > before_lvl
            if leveled:
                self.level_events.append({"ts": time.time(), "level": after[0],
                                          "stage": after[1]})
            if label or gained:
                self.recent.append({"ts": time.time(), "kind": kind,
                                    "text": label[:140], "xp": gained})
                self.recent = self.recent[-_RECENT_CAP:]
            self._save()
        return {"xp": gained, "leveled_up": leveled,
                "level": after[0], "stage": after[1]}

    # -- time series ----------------------------------------------------
    def snapshot(self, chunks: int, memories: int, pages: int, facts: int,
                 force: bool = False):
        """Append a growth-series point if the state changed (rate-limited)."""
        now = time.time()
        state = (self.xp, chunks, memories, pages, facts)
        with self._lock:
            changed = state != self._last_state
            if not force:
                # changed state: sample at most every 5s; idle: every 5 min
                floor = 5 if changed else 300
                if now - self._last_snapshot < floor:
                    return
            self._last_snapshot = now
            self._last_state = state
            self.series.append({"t": int(now), "xp": self.xp, "chunks": chunks,
                                "mems": memories, "pages": pages, "facts": facts})
            if len(self.series) > _SERIES_CAP:
                # downsample: keep every other point beyond the recent 400
                head = self.series[:-400]
                tail = self.series[-400:]
                self.series = head[::2] + tail
            self._save()

    # -- summary for the UI ----------------------------------------------
    def stats(self, extra: dict = None):
        lvl, stage, floor, nxt = self.level_info()
        c = self.counters
        out = {
            "xp": self.xp,
            "level": lvl,
            "stage": stage,
            "xp_floor": floor,
            "xp_next": nxt,
            "xp_progress": (round(100.0 * (self.xp - floor) / max(1, (nxt or floor + 1) - floor))
                            if nxt else 100),
            "age_seconds": int(time.time() - self.born),
            "level_events": self.level_events[-12:],
            "recent": list(reversed(self.recent[-30:])),
            "counters": dict(c),
            "series": self.series[-400:],
            "levels": [{"xp": need, "stage": name} for need, name in config.LEVELS],
        }
        if extra:
            out.update(extra)
        return out
