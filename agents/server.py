"""Tiny local HTTP server for the story engine -- stdlib only, no pip install.

    python3 agents/server.py            # http://127.0.0.1:8787

    GET /stream?seed=N&policy=heuristic|llm&speed=1&lead=4   LIVE story as Server-Sent Events
    GET/POST /run?seed=N&policy=...                          whole run as one JSON document (tests, Bruin/Postgres)
    GET /memory                                              the learning memory

`seed` is optional (random if omitted, so every Play is a different story).

/stream message shapes (each message ends with a blank line):
    event: start
    data: {"seed": 5, "run_id": "...", "policy": "heuristic", "lead": 4.0, "speed": 1.0}

    data: {<event: seq, t_sim, agent_id, agent_role, type, payload, reasoning, confidence, model, ...>}

    : ping                                   (keepalive comment, only when nothing was sent for 10 s)

    event: end
    data: {"ending": "...", "policy": "...", "stats": {...}, "run_number": 21, "memory": {...}, "duration": 143.0}

    event: error   (engine crashed; nothing is saved)
    data: {"error": "..."}

Pacing: with W = wall seconds since the stream started, an event is sent no earlier than
W >= (t_sim - lead) / speed, so the viewer always has `lead` seconds of lookahead. If the engine is slower
(an LLM call), the event goes out as soon as it is ready. The engine itself runs only a few sim-seconds ahead
of what has been sent, so agent decisions are made as the story advances, not up front.
A client disconnect stops the engine without saving memory or writing Postgres.
"""

import json
import queue
import random as _random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from engine import iter_run
from orchestrator import build_sql, build_story, default_policy, load_memory, save_memory, write_to_postgres

LEAD = 4.0          # seconds of lookahead the viewer gets
HORIZON = 6.0       # sim-seconds the engine may run ahead of the lookahead window
PING_EVERY = 10.0   # keepalive interval (wall seconds)
ACTIVE = {"streams": 0, "producers": 0}   # live counters (handy for tests/monitoring)
_ACTIVE_LOCK = threading.Lock()


def _bump(key, delta):
    with _ACTIVE_LOCK:
        ACTIVE[key] += delta


def _num(qs, name, default, lo, hi):
    try:
        return max(lo, min(hi, float(qs.get(name, [default])[0])))
    except (TypeError, ValueError):
        return default


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
        qs = parse_qs(parsed.query)
        if parsed.path == "/memory" and self.command == "GET":
            self._json(200, load_memory())
            return
        if parsed.path == "/stream" and self.command == "GET":
            self._stream(qs)
            return
        if parsed.path != "/run":
            self._json(404, {"error": "not found"})
            return

        seed_param = qs.get("seed", [None])[0]
        seed = int(seed_param) if seed_param else _random.randint(1, 1_000_000)
        policy = qs.get("policy", [None])[0]
        policy = policy if policy in ("heuristic", "llm") else None

        memory = load_memory()
        try:
            story = build_story(seed, memory, policy)  # the agents decide everything
        except Exception as exc:  # keep the demo alive even if a beat errors
            self._json(500, {"error": str(exc)})
            return
        events, memory, run_id = story["events"], story["memory"], story["run_id"]
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
            "ending": story["ending"],
            "policy": story["policy"],
            "stats": story["stats"],
            "postgres_error": postgres_error,
        })

    # -- live story over Server-Sent Events -----------------------------------
    def _stream(self, qs):
        seed_param = qs.get("seed", [None])[0]
        try:
            seed = int(seed_param) if seed_param else _random.randint(1, 1_000_000)
        except ValueError:
            self._json(400, {"error": "seed must be an integer"})
            return
        policy = qs.get("policy", [None])[0]
        policy = policy if policy in ("heuristic", "llm") else default_policy()
        lead = _num(qs, "lead", LEAD, 0.0, 60.0)
        speed = _num(qs, "speed", 1.0, 0.01, 1000.0)

        memory = load_memory()  # private copy: only saved if this run completes
        run = iter_run(seed, memory, policy)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()

        t0 = time.monotonic()
        last_write = [t0]
        stop = threading.Event()
        q = queue.Queue()
        it = iter(run)

        def write(text):
            self.wfile.write(text.encode("utf-8"))
            self.wfile.flush()
            last_write[0] = time.monotonic()

        def ping_if_due():
            if time.monotonic() - last_write[0] >= PING_EVERY:
                write(": ping\n\n")

        def produce():
            _bump("producers", 1)
            try:
                for ev in it:
                    if stop.is_set():
                        return
                    q.put(("ev", ev))
                    # stay only a little ahead of what the viewer has been sent
                    while not stop.is_set() and ev["t_sim"] > (time.monotonic() - t0) * speed + lead + HORIZON:
                        time.sleep(0.05)
                q.put(("done", None))
            except Exception as exc:  # noqa: BLE001 - report to the client instead of dying silently
                q.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                it.close()
                _bump("producers", -1)

        _bump("streams", 1)
        try:
            write("event: start\ndata: " + json.dumps(
                {"seed": seed, "run_id": run.run_id, "policy": run.policy, "lead": lead, "speed": speed}) + "\n\n")
            threading.Thread(target=produce, daemon=True).start()
            while True:
                try:
                    kind, payload = q.get(timeout=1.0)
                except queue.Empty:
                    ping_if_due()
                    continue
                if kind == "error":
                    write("event: error\ndata: " + json.dumps({"error": payload}) + "\n\n")
                    return
                if kind == "done":
                    break
                due = (payload["t_sim"] - lead) / speed
                while True:
                    w = time.monotonic() - t0
                    if w >= due:
                        break
                    time.sleep(min(due - w, 0.25))
                    ping_if_due()
                write("data: " + json.dumps(payload) + "\n\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return  # client went away: nothing saved, nothing written to Postgres
        finally:
            stop.set()
            _bump("streams", -1)

        # Normal completion: same post-run work as /run, but never let it fail the stream.
        res = run.result
        try:
            save_memory(run.memory)
        except Exception:  # noqa: BLE001
            pass
        try:
            write("event: end\ndata: " + json.dumps({
                "ending": res["ending"], "policy": res["policy"], "stats": res["stats"],
                "run_number": run.memory["runs"], "memory": run.memory, "duration": res["stats"]["duration"],
            }) + "\n\n")
        except OSError:
            pass
        try:
            write_to_postgres(build_sql(res["events"], seed, run.run_id))
        except Exception:  # noqa: BLE001 - best effort, the story already played
            pass

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


def main(port=8787):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"story server on http://127.0.0.1:{port}  (GET /stream?seed=N live SSE, GET/POST /run?seed=N, GET /memory)")
    server.serve_forever()


if __name__ == "__main__":
    main()
