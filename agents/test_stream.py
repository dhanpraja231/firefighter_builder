"""End-to-end test of the live SSE endpoint. Starts its own server on a FREE port (never 8787), uses a throwaway
memory file and a recorder instead of Postgres, so agents/memory.json is never touched.

    python agents/test_stream.py
"""

import hashlib
import http.client
import json
import os
import sys
import tempfile
import threading
import time
from http.server import HTTPServer, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import orchestrator  # noqa: E402
import server  # noqa: E402
import test_llm_stub as stub  # noqa: E402

REAL_MEMORY = Path(__file__).parent / "memory.json"
INITIAL = {"runs": 19, "child_losses": 0, "cautious_briefing": True, "bolt_prob": 0.4, "found_prob": 0.7}
RESULTS = []
PG_CALLS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' -- ' + str(detail)) if detail != '' else ''}")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def read_sse(resp, t0, stop_after_events=None):
    """Parse an SSE body into [(event_name, data_or_None, arrival_wall_seconds_since_t0, is_comment)]."""
    msgs, name, data_lines = [], "message", []
    while True:
        raw = resp.readline()
        if not raw:
            break
        line = raw.decode("utf-8").rstrip("\r\n")
        now = time.monotonic() - t0
        if line.startswith(":"):
            msgs.append(("ping", line, now, True))
        elif line == "":
            if data_lines:
                msgs.append((name, json.loads("\n".join(data_lines)), now, False))
                if stop_after_events and sum(1 for m in msgs if m[0] == "message") >= stop_after_events:
                    return msgs
            name, data_lines = "message", []
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    return msgs


def open_stream(port, query, timeout=120):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    t0 = time.monotonic()
    conn.request("GET", "/stream?" + query)
    return conn, conn.getresponse(), t0


def reset_memory(path):
    Path(path).write_text(json.dumps(INITIAL))


def pacing_violations(msgs, lead, speed, tol=0.05):
    return [(m[1]["seq"], round(m[2], 3), round((m[1]["t_sim"] - lead) / speed, 3))
            for m in msgs if m[0] == "message" and m[2] < (m[1]["t_sim"] - lead) / speed - tol]


if __name__ == "__main__":
    tmpdir = tempfile.mkdtemp()
    mem_path = Path(tmpdir) / "memory.json"
    orchestrator.MEMORY_PATH = mem_path
    server.write_to_postgres = lambda sql: PG_CALLS.append(len(sql))
    real_before = sha(REAL_MEMORY)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"test server on free port {port} (not 8787)\n")

    # ---- 1. normal live stream, fast clock --------------------------------------------------------------------
    print("1) /stream?seed=5&speed=20")
    reset_memory(mem_path)
    LEAD, SPEED = 4.0, 20.0
    conn, resp, t0 = open_stream(port, f"seed=5&speed={SPEED:g}")
    ctype, cors = resp.getheader("Content-Type"), resp.getheader("Access-Control-Allow-Origin")
    msgs = read_sse(resp, t0)
    conn.close()
    wall = time.monotonic() - t0
    evs = [m for m in msgs if m[0] == "message"]
    start = next((m for m in msgs if m[0] == "start"), None)
    end = next((m for m in msgs if m[0] == "end"), None)
    check("Content-Type is text/event-stream, CORS open", ctype == "text/event-stream" and cors == "*", f"{ctype}, {cors}")
    check("first message is `event: start` with {seed, run_id, policy, lead}", msgs[0][0] == "start" and
          {"seed", "run_id", "policy", "lead"} <= set(start[1]), start[1] if start else None)
    check("events arrive in seq order 1..N, t_sim non-decreasing",
          [m[1]["seq"] for m in evs] == list(range(1, len(evs) + 1)) and
          all(a[1]["t_sim"] <= b[1]["t_sim"] for a, b in zip(evs, evs[1:])), f"{len(evs)} events")
    viol = pacing_violations(msgs, LEAD, SPEED)
    check("pacing: arrival_wall >= (t_sim - lead)/speed for every event", not viol, viol[:3])
    expected_total = (evs[-1][1]["t_sim"] - LEAD) / SPEED
    check("not dumped at once: stream lasted about as long as the story / speed", wall >= expected_total - 0.1,
          f"wall {wall:.1f}s, story {evs[-1][1]['t_sim']:.0f}s / {SPEED:g} - lead = {expected_total:.1f}s")
    check("early events are sent immediately (lookahead): first event within 1s", evs[0][2] < 1.0, f"{evs[0][2]:.2f}s")
    check("`event: end` carries ending, policy, stats, run_number, memory, duration",
          end is not None and {"ending", "policy", "stats", "run_number", "memory", "duration"} <= set(end[1]), sorted(end[1]) if end else None)
    check("end.duration equals the last event's t_sim", end[1]["duration"] == evs[-1][1]["t_sim"], end[1]["duration"])
    check("memory saved after normal completion (runs 19 -> 20), Postgres write attempted once",
          json.loads(mem_path.read_text())["runs"] == 20 and len(PG_CALLS) == 1, f"pg calls={len(PG_CALLS)}")
    stream5 = [m[1] for m in evs]
    stream5_ending = end[1]["ending"]
    first_seed5 = json.dumps(stream5, sort_keys=True)

    # ---- 2. a different seed is a different story -------------------------------------------------------------
    print("\n2) second stream, different seed")
    reset_memory(mem_path)
    conn, resp, t0 = open_stream(port, "seed=9&speed=40")
    msgs9 = read_sse(resp, t0)
    conn.close()
    ev9 = [m[1] for m in msgs9 if m[0] == "message"]
    end9 = next(m for m in msgs9 if m[0] == "end")[1]
    check("seed 9 events differ from seed 5 events", json.dumps(ev9, sort_keys=True) != first_seed5)
    check("different seeds, different story (ending or rescue order)",
          end9["ending"] != stream5_ending or end9["stats"]["rescue_order"] != end[1]["stats"]["rescue_order"],
          f"seed5: {stream5_ending} {end[1]['stats']['rescue_order'][:3]} | seed9: {end9['ending']} {end9['stats']['rescue_order'][:3]}")

    # ---- 3. /run still works and tells the same story as the stream --------------------------------------------
    print("\n3) /run still works")
    reset_memory(mem_path)
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request("GET", "/run?seed=5&policy=heuristic")
    r = c.getresponse()
    body = json.loads(r.read())
    c.close()
    check("/run returns 200 JSON with events, ending, policy, stats, run_number",
          r.status == 200 and {"events", "ending", "policy", "stats", "run_number", "run_id"} <= set(body), r.status)
    check("/run events are identical to the live stream for the same seed + memory",
          json.dumps(body["events"], sort_keys=True) == first_seed5 and body["ending"] == stream5_ending)

    # ---- 4. client disconnect mid-stream: no memory write, no Postgres, engine stops ---------------------------
    print("\n4) client disconnects mid-stream")
    reset_memory(mem_path)
    before_mem, before_pg = sha(mem_path), len(PG_CALLS)
    conn, resp, t0 = open_stream(port, "seed=6&speed=5")
    partial = read_sse(resp, t0, stop_after_events=12)
    resp.close()  # abrupt close mid-stream, like a closed browser tab (no `end` message was read)
    conn.close()
    deadline = time.time() + 20
    while time.time() < deadline and (server.ACTIVE["streams"] or server.ACTIVE["producers"]):
        time.sleep(0.2)
    check("got a partial stream before disconnecting", sum(1 for m in partial if m[0] == "message") >= 12)
    check("server stopped the stream and the engine thread cleanly", server.ACTIVE == {"streams": 0, "producers": 0}, dict(server.ACTIVE))
    check("memory file unchanged by the aborted run", sha(mem_path) == before_mem)
    check("no Postgres write for the aborted run", len(PG_CALLS) == before_pg, f"pg calls {before_pg} -> {len(PG_CALLS)}")

    # ---- 5. slow LLM reply just delays later events -------------------------------------------------------------
    print("\n5) LLM policy with an occasionally slow (2 s) model reply")
    llm_srv = HTTPServer(("127.0.0.1", 0), stub.Handler)
    threading.Thread(target=llm_srv.serve_forever, daemon=True).start()
    saved_env = {k: os.environ.get(k) for k in ("RUNWARE_API_KEY", "RUNWARE_MODEL", "RUNWARE_BASE_URL")}
    os.environ.update({"RUNWARE_API_KEY": "test-key", "RUNWARE_MODEL": "stub-model",
                       "RUNWARE_BASE_URL": f"http://127.0.0.1:{llm_srv.server_address[1]}/v1"})
    stub.MODE.update({"v": "slow", "every": 15, "delay": 2.0})
    stub.SEEN.update({"requests": 0, "auth_ok": 0, "director": 0})
    reset_memory(mem_path)
    conn, resp, t0 = open_stream(port, "seed=5&policy=llm&speed=20")
    requests_at_10th_event = None
    msgs_llm, name, dl = [], "message", []
    while True:
        raw = resp.readline()
        if not raw:
            break
        line = raw.decode().rstrip("\r\n")
        now = time.monotonic() - t0
        if line == "":
            if dl:
                msgs_llm.append((name, json.loads("\n".join(dl)), now, False))
                if name == "message" and sum(1 for m in msgs_llm if m[0] == "message") == 10:
                    requests_at_10th_event = stub.SEEN["requests"]
            name, dl = "message", []
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            dl.append(line[5:].strip())
    conn.close()
    evs_l = [m for m in msgs_llm if m[0] == "message"]
    start_l = next(m for m in msgs_llm if m[0] == "start")[1]
    end_l = next((m for m in msgs_llm if m[0] == "end"), None)
    gaps = [b[2] - a[2] for a, b in zip(evs_l, evs_l[1:])]
    total_requests = stub.SEEN["requests"]
    check("start message reports policy=llm", start_l["policy"] == "llm", start_l)
    check("order intact despite slow replies (seq 1..N, t_sim non-decreasing)",
          [m[1]["seq"] for m in evs_l] == list(range(1, len(evs_l) + 1)) and
          all(a[1]["t_sim"] <= b[1]["t_sim"] for a, b in zip(evs_l, evs_l[1:])), f"{len(evs_l)} events")
    check("pacing still respected", not pacing_violations(msgs_llm, LEAD, 20.0))
    check("a slow reply delayed later events (largest gap >= 1.5 s)", max(gaps) >= 1.5, f"largest gap {max(gaps):.1f}s")
    check("agent calls happen as the story advances, not up front",
          requests_at_10th_event is not None and requests_at_10th_event < 0.5 * total_requests,
          f"{requests_at_10th_event} requests when event #10 arrived, {total_requests} by the end")
    check("events carry the model that decided them", any(m[1].get("model") == "stub-model" for m in evs_l))
    check("stream ends cleanly with an `end` message", end_l is not None and end_l[1]["policy"] == "llm")
    stub.MODE["v"] = "good"
    llm_srv.shutdown()
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    # ---- wrap up ------------------------------------------------------------------------------------------------
    srv.shutdown()
    srv.server_close()
    print()
    check("real agents/memory.json was never touched by these tests", sha(REAL_MEMORY) == real_before)
    print(f"\nSTREAM TESTS: {'PASS' if all(RESULTS) else 'FAIL'} ({sum(RESULTS)}/{len(RESULTS)} checks)")
    sys.exit(0 if all(RESULTS) else 1)
