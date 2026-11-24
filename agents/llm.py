"""Runware LLM calls for the agents, with the observability fields the event log needs.

The orchestrator's rules decide what each agent does. This module asks the LLM,
in character, why the agent did it and what it says, and records the model,
latency and token counts on the event, so the dashboard and Bruin metrics show
real LLM telemetry.

    export RUNWARE_API_KEY=...          # or put it in the repo's .env (gitignored)
    export FF_LLM_MODEL=google:gemma@4-31b   # optional
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
URL = "https://api.runware.ai/v1/chat/completions"
MODEL = os.environ.get("FF_LLM_MODEL", "google:gemma@4-31b")
LLM_TYPES = {"decide", "act", "speak", "request_approval"}
ROLE_FILES = {"commander": "commander", "scout": "scout", "suppression": "hose", "rescue": "rescue"}


def _load_env_file():
    env = HERE.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env_file()


def enabled() -> bool:
    return bool(os.environ.get("RUNWARE_API_KEY"))


def _personas() -> dict:
    out = {}
    for f in (HERE / "personas").glob("*.json"):
        d = json.loads(f.read_text())
        ids = [d["agent_id"]] if d.get("agent_id") else [a.get("agent_id") for a in d.get("agents", [])]
        for i in filter(None, ids):
            out[i] = d
    return out


PERSONAS = _personas()


def system_prompt(agent_id: str, role: str) -> str:
    if role == "victim":
        persona = json.dumps(PERSONAS.get(agent_id, {}), indent=1)
        who = f"You are {agent_id}, a resident trapped in a burning apartment block at night.\nPersona:\n{persona}"
    else:
        f = HERE / "roles" / f"{ROLE_FILES.get(role, role)}.md"
        brief = f.read_text() if f.exists() else ""
        who = (f"You are {agent_id}, a firefighting robot or the AI commander in a burning apartment block at night. "
               f"Use a calm, professional, radio-style voice.\nRole brief:\n{brief}")
    return (who + "\n\nThe film is documentary style. You will be told what you just did. Reply with JSON only: "
            '{"reasoning": one or two plain sentences on why, in first person, '
            '"utterance": what you say out loud (one short line, or null if you say nothing), '
            '"confidence": number from 0 to 1}')


def _context(events: list[dict], upto: int, n: int = 6) -> str:
    lines = []
    for e in events[max(0, upto - n):upto]:
        p = e.get("payload") or {}
        bit = p.get("utterance") or " ".join(str(x) for x in (p.get("action"), p.get("target")) if x) \
            or p.get("victim_status") or json.dumps(p.get("world") or "")[:80]
        lines.append(f"t={e['t_sim']}s {e['agent_id']} {e['type']}: {bit}")
    return "\n".join(lines) or "(start of the incident)"


def call(system: str, user: str, max_tokens: int = 200) -> dict:
    """One Runware chat call. Returns text plus model, latency_ms, tokens_in, tokens_out."""
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0.8,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['RUNWARE_API_KEY']}", "Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    usage = data.get("usage") or {}
    return {
        "text": data["choices"][0]["message"].get("content") or "",
        "model": data.get("model", MODEL),
        "latency_ms": round((time.monotonic() - t0) * 1000),
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
    }


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def enrich_event(events: list[dict], i: int) -> None:
    e = events[i]
    p = e.get("payload") or {}
    did = {"speak": f"You are about to speak. The script line is: {p.get('utterance')!r}. Say it your own way.",
           "decide": f"You decided: {p.get('action')} {p.get('target') or ''}.",
           "act": f"You did: {p.get('action')} on {p.get('target')}" + (" (a risky action the human approved)." if p.get("risky") else "."),
           "request_approval": f"You are asking the human operator to approve: {p.get('action')} on {p.get('target')}"
                               f" by {p.get('actor')}."}[e["type"]]
    user = f"What happened just before:\n{_context(events, i)}\n\nNow, at t={e['t_sim']}s: {did}"
    try:
        r = call(system_prompt(e["agent_id"], e["agent_role"]), user)
    except (urllib.error.URLError, TimeoutError, KeyError) as exc:
        e["payload"] = {**p, "llm_error": str(exc)[:200]}
        return
    out = _parse(r["text"])
    if out.get("reasoning"):
        e["reasoning"] = str(out["reasoning"])
    if e["type"] == "speak" and out.get("utterance"):
        e["payload"] = {**p, "utterance": str(out["utterance"]), "script_utterance": p.get("utterance")}
    if isinstance(out.get("confidence"), (int, float)):
        e["confidence"] = max(0.0, min(1.0, float(out["confidence"])))
    e.update(model=r["model"], latency_ms=r["latency_ms"], tokens_in=r["tokens_in"], tokens_out=r["tokens_out"])


def enrich_run(events: list[dict], workers: int = 8) -> list[dict]:
    """Fill reasoning, utterances and LLM telemetry on every decide/act/speak/request_approval event.

    Calls run in parallel; each one sees the scripted events before it as context.
    """
    idx = [i for i, e in enumerate(events) if e["type"] in LLM_TYPES and e.get("latency_ms") is None
           and not (e["payload"] or {}).get("choice") and not (e["payload"] or {}).get("voiced")
           and not (e["type"] == "act" and (e["payload"] or {}).get("risky"))]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda i: enrich_event(events, i), idx))
    return events


# ---------- decisions and debriefs ----------

def _lessons_block(lessons: list[dict], history: str) -> str:
    lines = []
    if history:
        lines.append(f"Track record: {history}")
    for l in lessons:
        tag = {"approve": "from a run the human approved: keep doing what worked",
               "decline": "PRIORITY, from a run the human declined: fix this"}.get(l.get("verdict"), "from an unreviewed run")
        lines.append(f"- [{tag}] {l['lesson']}")
    return ("What earlier runs taught this team:\n" + "\n".join(lines)) if lines else ""


def choose(agent_id: str, role: str, observation: str, options: list[dict], lessons: list[dict], history: str) -> dict:
    """Ask the LLM to pick one of `options` ([{id, label}]). Always returns a valid choice."""
    system = system_prompt(agent_id, role).split("\n\nThe film is documentary style.")[0] + (
        "\n\nYou are making a real decision. Lives depend on it and the building will collapse on a deadline. "
        'Reply with JSON only: {"choice": one option id exactly as given, "reasoning": one or two sentences, first person, '
        '"utterance": a short radio line or null, "confidence": number from 0 to 1}')
    user = "\n\n".join(filter(None, [
        _lessons_block(lessons, history),
        "Situation:\n" + observation,
        "Options:\n" + "\n".join(f"- {o['id']}: {o['label']}" for o in options),
    ]))
    ids = {o["id"] for o in options}
    tel = {"model": None, "latency_ms": 0, "tokens_in": 0, "tokens_out": 0}
    err = None
    for _ in range(2):
        try:
            r = call(system, user, max_tokens=220)
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            err = f"call failed: {exc}"[:200]
            continue
        tel = {"model": r["model"], "latency_ms": tel["latency_ms"] + r["latency_ms"],
               "tokens_in": (tel["tokens_in"] or 0) + (r["tokens_in"] or 0),
               "tokens_out": (tel["tokens_out"] or 0) + (r["tokens_out"] or 0)}
        out = _parse(r["text"])
        if str(out.get("choice")) in ids:
            conf = out.get("confidence")
            return {**tel, "choice": str(out["choice"]), "reasoning": out.get("reasoning"),
                    "utterance": out.get("utterance") or None,
                    "confidence": max(0.0, min(1.0, float(conf))) if isinstance(conf, (int, float)) else None}
        err = f"invalid choice {out.get('choice')!r}"
    return {**tel, "choice": options[0]["id"], "reasoning": f"(no valid LLM choice, fell back to the first option: {err})",
            "utterance": None, "confidence": None, "error": err}


def rule_choose(agent_id, role, observation, options, lessons, history) -> dict:
    """Baseline policy without an LLM: always the first option (nearest victim, first approach)."""
    return {"choice": options[0]["id"], "reasoning": f"Rule: first option ({options[0]['label']}).",
            "utterance": None, "confidence": None}


def debrief(outcomes: dict, decisions: list, end_t: int, twists: list[str]) -> list[dict]:
    """Commander reviews the run and writes up to 5 lessons: [{role, lesson, evidence}]."""
    lost = [f"{m} ({cause})" for m, (st, cause) in outcomes.items() if st == "lost"]
    saved = [m for m, (st, _) in outcomes.items() if st == "rescued"]
    dec = "\n".join(f"t={t}s {agent}: chose {choice} out of {', '.join(opts)}" for t, agent, choice, opts in decisions)
    system = ("You are the AI incident commander of a robot firefighting team, writing an after-action review. "
              "Be concrete: name victims, rooms, timings and which choice should change. "
              'Reply with JSON only: {"lessons": [{"role": "commander" | "rescue" | "suppression", '
              '"lesson": one actionable sentence, "evidence": one sentence citing this run}]} with at most 5 lessons.')
    user = (f"Run ended at t={end_t}s. Twists: {', '.join(twists) or 'none'}.\n"
            f"Saved ({len(saved)}): {', '.join(saved) or 'nobody'}\nLost ({len(lost)}): {', '.join(lost) or 'nobody'}\n"
            f"Decisions:\n{dec}")
    try:
        r = call(system, user, max_tokens=700)
    except (urllib.error.URLError, TimeoutError, KeyError):
        return []
    out = _parse(r["text"])
    lessons = []
    for l in (out.get("lessons") or [])[:5]:
        if isinstance(l, dict) and l.get("lesson"):
            role = l.get("role") if l.get("role") in ("commander", "rescue", "suppression") else "commander"
            lessons.append({"role": role, "lesson": str(l["lesson"])[:400], "evidence": str(l.get("evidence") or "")[:400],
                            "model": r["model"], "latency_ms": r["latency_ms"]})
    return lessons
