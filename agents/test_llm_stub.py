"""Proves LLMPolicy works against an OpenAI-shaped endpoint and degrades safely. No real network calls.

    python agents/test_llm_stub.py
"""

import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import DEFAULT_MEMORY, run_story  # noqa: E402
from llm import LLMPolicy  # noqa: E402
from sweep import validate  # noqa: E402

MODE = {"v": "good"}
SEEN = {"requests": 0, "auth_ok": 0, "director": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        SEEN["requests"] += 1
        if self.headers.get("Authorization") == "Bearer test-key" and self.path.endswith("/chat/completions"):
            SEEN["auth_ok"] += 1
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        mode = MODE["v"]
        if mode == "hang":
            time.sleep(1.0)
        elif mode == "slow" and SEEN["requests"] % MODE.get("every", 15) == 0:
            time.sleep(MODE.get("delay", 2.0))  # an occasional slow model reply; the answer is still valid
        if mode == "http500":
            self.send_response(500)
            self.end_headers()
            return
        system = body["messages"][0]["content"]
        user = body["messages"][1]["content"]
        if mode == "garbage":
            content = "I think the best option is the first one, probably!"
        elif "invent ONE twist" in system:
            SEEN["director"] += 1
            obs = json.loads(user)
            fires = obs.get("fires") or {}
            room = max(fires, key=fires.get) if fires else "3-kitchen"
            content = json.dumps({"twist": "A gas line in the wall hisses and the flames lunge.",
                                  "effect": {"kind": "fire_surge", "target": room}, "reasoning": "Raise the stakes where it is already burning."})
        else:
            opts = re.findall(r"^(\d+): (.*)$", user, flags=re.M)
            sane = [int(i) for i, label in opts if "order every robot out" not in label and "give up on" not in label]
            pick = sane[SEEN["requests"] % len(sane)] if sane else 0
            content = json.dumps({"choice": pick, "utterance": "Copy that.", "reasoning": f"Stub model picked option {pick}.", "confidence": 0.8})
        out = json.dumps({"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 120, "completion_tokens": 30}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def run(mode, timeout=5.0, seed=11):
    MODE["v"] = mode
    pol = LLMPolicy(api_key="test-key", model="stub-model", base_url=f"http://127.0.0.1:{PORT}/v1", timeout=timeout)
    t0 = time.time()
    res = run_story(seed, dict(DEFAULT_MEMORY), pol)
    llm_events = [e for e in res["events"] if e.get("model") == "stub-model"]
    return res, pol, llm_events, time.time() - t0


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 0), Handler)
    PORT = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ok = True

    res, pol, llm_events, dt = run("good")
    errs = validate(res)
    has_meta = any(e.get("latency_ms") is not None and e.get("tokens_in") == 120 for e in llm_events)
    free = [t for t in res["stats"]["twists"] if t.startswith("free:")]
    print(f"[good]    policy={res['policy']} calls={pol.calls} fallbacks={pol.fallbacks} llm-events={len(llm_events)} "
          f"latency/tokens recorded={has_meta} free-form twists={free or 'none'} bearer ok={SEEN['auth_ok']}/{SEEN['requests']} "
          f"director calls={SEEN['director']} validation={'OK' if not errs else errs[:3]} ({dt:.1f}s)")
    ok &= res["policy"] == "llm" and pol.calls > 50 and len(llm_events) > 20 and has_meta and not errs and SEEN["auth_ok"] == SEEN["requests"]

    for mode, timeout in (("garbage", 5.0), ("http500", 5.0), ("hang", 0.15)):
        res, pol, llm_events, dt = run(mode, timeout=timeout, seed=11 if mode != "hang" else 4)
        errs = validate(res)
        print(f"[{mode:7}] policy={res['policy']} calls={pol.calls} fallbacks={pol.fallbacks} llm-events={len(llm_events)} "
              f"run still finished: ending={res['ending']} validation={'OK' if not errs else errs[:3]} last_error={pol.last_error!r} ({dt:.1f}s)")
        ok &= pol.fallbacks > 0 and len(llm_events) == 0 and not errs and res["ending"] is not None

    # no key => pure heuristic, no network at all
    before = SEEN["requests"]
    res = run_story(11, dict(DEFAULT_MEMORY), LLMPolicy(api_key="", model="", base_url=f"http://127.0.0.1:{PORT}/v1"))
    print(f"[no key]  policy={res['policy']} network requests made={SEEN['requests'] - before}")
    ok &= res["policy"] == "heuristic" and SEEN["requests"] == before
    print("\nLLM STUB TESTS:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
