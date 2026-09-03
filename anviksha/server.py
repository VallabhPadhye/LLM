"""
HTTP server for Anviksha - dependency-free (stdlib http.server).

API:
  GET  /                -> the web UI
  GET  /assets/<file>   -> static front-end assets
  POST /api/chat        {message?, attachments? [{name,size,data(base64)}]}
  GET  /api/status      -> compact status (sidebar / header)
  GET  /api/stats       -> rich progress + learning statistics
  GET  /api/journal     -> what it learned from the internet
  GET  /api/curiosity   -> the wonder journal (queued + satisfied)
  GET  /api/activity    -> memory ledger + explorer log (live feed)
  GET  /api/self        -> SELF.md (evolving self-instructions)
  POST /api/explore     {mode?: curious|wander, topics?}
  POST /api/learn       {text, source?}   (compat; chat learning is automatic)
  POST /api/evolve      force a reflection / self-upgrade

Runs on 0.0.0.0 and sends permissive CORS headers so it can be reached from a
preview tunnel host as well as localhost.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .agent import Agent
from .explorer import start_autonomous

agent = None
_explore_thread = None


def _json(o):
    return json.dumps(o).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Anviksha/1.0"

    # -- CORS -----------------------------------------------------------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def log_message(self, *a):
        pass  # keep logs quiet

    # -- helpers --------------------------------------------------------
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self, max_bytes=None):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        cap = max_bytes or (int(config.ATTACH_MAX_TOTAL_BYTES * 1.45) + 1024)
        if length > cap:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _serve_static(self, rel):
        base = config.WEB_ASSETS
        path = os.path.normpath(os.path.join(base, rel))
        if not path.startswith(base):
            return self._send(403, b"forbidden", "text/plain")
        if not os.path.isfile(path):
            return self._send(404, b"not found", "text/plain")
        ctype = {".html": "text/html; charset=utf-8",
                 ".js": "application/javascript",
                 ".css": "text/css",
                 ".svg": "image/svg+xml",
                 ".png": "image/png",
                 ".ico": "image/x-icon"}.get(os.path.splitext(path)[1],
                                             "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self._send(200, body, ctype)

    # -- routing --------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            return self._get()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                return self._send(500, _json({"error": f"server error: {e}"}))
            except Exception:
                pass

    def _get(self):
        p = self.path.split("?", 1)[0]
        if p == "/" or p == "/index.html":
            return self._serve_static("index.html")
        if p.startswith("/assets/"):
            return self._serve_static(p[len("/assets/"):])
        if p == "/favicon.ico":
            return self._send(404, b"", "text/plain")
        if p == "/api/status":
            st = agent.status()
            st.pop("progress", None)          # header-level compactness
            return self._send(200, _json(st))
        if p == "/api/stats":
            return self._send(200, _json(agent.status()))
        if p == "/api/journal":
            return self._send(200, _json({
                "journal": agent.explorer.journal(limit=50),
                "pages_explored": int(agent.progress.counters.get("web_page", 0)),
                "network": agent.explorer.net}))
        if p == "/api/curiosity":
            return self._send(200, _json({
                "items": agent.curiosity.for_ui(limit=40),
                "counts": agent.curiosity.counts()}))
        if p == "/api/activity":
            act = {"ledger": agent.memory.activity(limit=40),
                   "explorer": agent.explorer.last_runs(limit=15)}
            return self._send(200, _json(act))
        if p == "/api/self":
            return self._send(200, _json({"text": agent.memory.read_self() or ""}))
        return self._send(404, _json({"error": "not found"}))

    def do_POST(self):
        try:
            return self._post()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                return self._send(500, _json({"error": f"server error: {e}"}))
            except Exception:
                pass

    def _post(self):
        p = self.path.split("?", 1)[0]
        body = self._read_body()
        if body is None:
            return self._send(413, _json({"error": "upload too large"}))
        if p == "/api/chat":
            msg = (body.get("message") or "").strip()
            atts = body.get("attachments") or []
            if not msg and not atts:
                return self._send(400, _json({"error": "empty message"}))
            t0 = time.time()
            res = agent.chat(msg, attachments=atts)
            res["elapsed_s"] = round(time.time() - t0, 2)
            return self._send(200, _json(res))
        if p == "/api/learn":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, _json({"error": "no text"}))
            n = agent.learn(text, source=body.get("source") or "chat:paste")
            return self._send(200, _json({"stored": n,
                                          "total_chunks": agent.kb.count()}))
        if p == "/api/explore":
            mode = "wander" if (body.get("mode") == "wander") else "curious"
            topics = body.get("topics") or None
            res = agent.explorer.explore_once(topics=topics, mode=mode)
            agent._snapshot()
            return self._send(200, _json(res))
        if p == "/api/evolve":
            v = agent.memory.evolve(force=True)
            agent._retrain_if_empty()
            award = agent.progress.award("evolve", amount=config.XP["evolve"],
                                         label=f"reflected and rewrote SELF.md (v{v})")
            agent._snapshot()
            return self._send(200, _json({"version": v,
                                          "memories": agent.memory.count(),
                                          "xp_gained": award["xp"],
                                          "level": award["level"],
                                          "stage": award["stage"]}))
        return self._send(404, _json({"error": "not found"}))


def build_agent():
    global agent
    agent = Agent()
    n = agent.ingest_knowledge_dir()
    if n:
        agent.memory._log("startup", f"ingested {n} knowledge file(s) from "
                                     f"data/knowledge")
        agent.progress.bump("library_chunks", n)
        agent._snapshot()
    # accurate connectivity probe + initial self-instruction if needed
    try:
        agent.explorer.net = agent.explorer._probe()
    except Exception:
        agent.explorer.net = False
    if agent.memory.count() > 0 and agent.memory.version() == 0:
        agent.memory.evolve(force=True)
    # a newborn mind already wonders about the world
    if not agent.curiosity.items:
        agent.curiosity.seed_fresh(4)
        agent.memory._log("curiosity", "woke up curious about: "
                          + ", ".join(agent.curiosity.pop_topics(4)))
    return agent


def main():
    global _explore_thread
    config.ensure_dirs()
    build_agent()

    def after_run(res):
        # keep the growth chart alive even when nobody is chatting
        try:
            agent._snapshot()
            if res.get("ok") and res.get("visits"):
                agent.memory.evolve()
        except Exception:
            pass

    _explore_thread = start_autonomous(agent.explorer, agent.memory,
                                       on_run=after_run)
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    print(f"[anviksha] listening on http://{config.HOST}:{config.PORT}",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
