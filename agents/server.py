"""Tiny local HTTP server so the web app's Play button triggers a real
orchestrator run -- stdlib only, no pip install needed. With FF_API_URL set,
each run is sent to the event API and debriefed into lessons for the next run.

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

import api_client
import llm
from orchestrator import after_run, build_run, build_sql, load_memory, write_to_postgres


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

        try:
            events, info, run_id = build_run(seed)
        except Exception as exc:  # keep the demo alive even if a beat errors
            self._json(500, {"error": str(exc)})
            return
        if llm.enabled():
            llm.enrich_run(events)  # Runware voices the scripted lines; decisions already came from the LLM

        postgres_error = None
        lessons = []
        try:
            if api_client.enabled():
                # The event API writes to Postgres and runs Bruin when the run ends.
                api_client.post_run(events, seed, run_id, notes="orchestrator run")
                lessons = after_run(info, run_id)  # debrief -> lessons for the next run
            else:
                write_to_postgres(build_sql(events, seed, run_id))
        except Exception as exc:  # the browser still gets to play the run
            postgres_error = str(exc)

        lost = sum(1 for st, _ in info["outcomes"].values() if st == "lost")
        memory = {"runs": info["runs"], "saved": info["saved"], "total": len(info["outcomes"]),
                  "lessons_used": info["lessons_used"], "lessons_written": len(lessons),
                  # fields the web app already reads
                  "cautious_briefing": info["lessons_used"] > 0, "child_losses": lost, "bolt_prob": 0, "found_prob": 0}
        self._json(200, {
            "seed": seed,
            "run_id": run_id,
            "run_number": info["runs"],
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
