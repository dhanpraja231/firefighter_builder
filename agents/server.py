"""Tiny local HTTP server so the web app's Play button triggers a real
orchestrator run -- stdlib only, no pip install needed.

    python3 agents/server.py            # serves http://127.0.0.1:8787

    GET/POST /run?seed=N -> {"seed", "run_number", "memory", "events": [...]}

`seed` is optional (a random one is picked if omitted, so repeat clicks are
different attempts). Memory persists in agents/memory.json between calls --
that's the whole learning loop: run #2 reads what run #1 wrote.
"""

import json
import random as _random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from orchestrator import build_run, build_sql, load_memory, save_memory, write_to_postgres


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        parsed = urlparse(self.path)
        if parsed.path == "/memory" and self.command == "GET":
            self._json(200, load_memory())
            return
        if parsed.path != "/run":
            self._json(404, {"error": "not found"})
            return

        qs = parse_qs(parsed.query)
        seed_param = qs.get("seed", [None])[0]
        seed = int(seed_param) if seed_param else _random.randint(1, 1_000_000)

        memory = load_memory()
        try:
            events, memory, run_id = build_run(seed, memory)
        except Exception as exc:  # keep the demo alive even if a beat errors
            self._json(500, {"error": str(exc)})
            return
        save_memory(memory)

        postgres_error = None
        try:
            write_to_postgres(build_sql(events, seed, run_id))
        except Exception as exc:  # Bruin write is best-effort -- the browser still gets to play the run
            postgres_error = str(exc)

        self._json(200, {
            "seed": seed,
            "run_id": run_id,
            "run_number": memory["runs"],
            "memory": memory,
            "events": events,
            "postgres_error": postgres_error,
        })

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - quiet by default
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8787), Handler)
    print("orchestrator server on http://127.0.0.1:8787  (GET/POST /run?seed=N, GET /memory)")
    server.serve_forever()


if __name__ == "__main__":
    main()
