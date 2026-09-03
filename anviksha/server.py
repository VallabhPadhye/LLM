"""
HTTP server for Anviksha - dependency-free (stdlib http.server).

API:
  GET  /                -> the web UI
  GET  /assets/<file>   -> static front-end assets
  POST /api/chat        {message}
  POST /api/learn       {text, source?}
  POST /api/explore     {topics?}
  POST /api/evolve
  GET  /api/status
  GET  /api/activity    -> memory ledger + explorer log (for the UI panel)

Runs on 0.0.0.0 and sends permissive CORS headers so it can be reached from a
preview tunnel host as well as localhost.
"""
import json
import os
import threading
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

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
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
                 ".png": "image/png"}.get(os.path.splitext(path)[1],
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
        p = self.path.split("?", 1)[0]
        if p == "/":
            return self._serve_static("index.html")
        if p.startswith("/assets/"):
            return self._serve_static(p[len("/assets/"):])
        if p == "/api/status":
            return self._send(200, _json(agent.status()))
        if p == "/api/activity":
            act = {"ledger": agent.memory.activity(limit=40),
                   "explorer": agent.explorer.last_runs(limit=15)}
            return self._send(200, _json(act))
        if p == "/api/self":
            return self._send(200, _json({"text": agent.memory.read_self() or ""}))
        return self._send(404, _json({"error": "not found"}))

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        body = self._read_body()
        if p == "/api/chat":
            msg = (body.get("message") or "").strip()
            if not msg:
                return self._send(400, _json({"error": "empty message"}))
            t0 = time.time()
            res = agent.chat(msg)
            res["elapsed_s"] = round(time.time() - t0, 2)
            return self._send(200, _json(res))
        if p == "/api/learn":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, _json({"error": "no text"}))
            n = agent.learn(text, source=body.get("source") or "user-paste")
            return self._send(200, _json({"stored": n,
                                          "total_chunks": agent.kb.count()}))
        if p == "/api/explore":
            topics = body.get("topics") or None
            res = agent.explorer.explore_once(topics=topics)
            return self._send(200, _json(res))
        if p == "/api/evolve":
            v = agent.memory.evolve(force=True)
            agent._retrain_if_empty()
            return self._send(200, _json({"version": v,
                                          "memories": agent.memory.count()}))
        return self._send(404, _json({"error": "not found"}))


def build_agent():
    global agent, _explore_thread
    agent = Agent()
    n = agent.ingest_knowledge_dir()
    if n:
        agent.memory._log("startup", f"ingested {n} knowledge file(s) from "
                                    f"data/knowledge")
    # accurate connectivity probe + an initial self-instruction if we have
    # anything learned but have never written a version yet.
    try:
        agent.explorer.net = agent.explorer._probe()
    except Exception:
        agent.explorer.net = False
    if agent.memory.count() > 0 and agent.memory.version() == 0:
        agent.memory.evolve(force=True)
    return agent


def main():
    config.ensure_dirs()
    build_agent()
    # start autonomous self-browsing in the background
    _explore_thread = start_autonomous(agent.explorer, agent.memory)
    srv = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    print(f"[anviksha] listening on http://{config.HOST}:{config.PORT}",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
