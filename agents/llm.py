"""LLM-backed policy via an OpenAI-compatible chat endpoint (Runware by default).

    RUNWARE_API_KEY   bearer token (unset => every decision uses the heuristic fallback)
    RUNWARE_MODEL     model id / AIR id, e.g. "google:gemini@3.1-pro" (unset => fallback)
    RUNWARE_BASE_URL  default https://api.runware.ai/v1  (POST {base}/chat/completions)

Standard library only. Any network error, timeout, non-200, malformed JSON, or an
out-of-range / invalid choice makes that single decision fall back to the
HeuristicPolicy, so a flaky model never breaks a run.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from policy import Decision, HeuristicPolicy

ROLES_DIR = Path(__file__).parent / "roles"
PERSONAS_DIR = Path(__file__).parent / "personas"
ROLE_FILE = {"commander": "commander.md", "scout": "scout.md", "suppression": "hose.md", "rescue": "rescue.md"}

FORMAT_RULES = """
You are one agent in a simulated apartment-building fire rescue. Each turn you are given an
observation and a numbered list of LEGAL options. Choose exactly one.

Reply with ONE JSON object and nothing else:
{"choice": <integer index of the option>, "utterance": "<what you say out loud, or empty>",
 "reasoning": "<one or two sentences: why you chose it>", "confidence": <number 0..1>}

Stay in character. Keep utterance under 25 words, radio-style for robots, in your own voice for people.
Never invent options that are not listed. Never narrate actions with asterisks.
"""


def _system_prompt(role: str, agent_id: str, obs: dict) -> str:
    if role == "victim":
        persona = obs.get("persona", {})
        return (f"You are {persona.get('name', agent_id)}, a resident trapped in a burning building.\n"
                f"Persona card: {json.dumps(persona)}\nRespond as this person would, honoring their compliance rule."
                + FORMAT_RULES)
    if role == "director":
        return ("You are the Director of a short film about a fire rescue. You choose whether a twist happens now, "
                "to make the story dramatic but fair. Prefer 'none' most of the time." + FORMAT_RULES)
    path = ROLES_DIR / ROLE_FILE.get(role, "commander.md")
    text = path.read_text(encoding="utf-8") if path.exists() else f"You are the {role}."
    return text + FORMAT_RULES


class LLMPolicy:
    def __init__(self, fallback=None, api_key=None, model=None, base_url=None, timeout=20.0, temperature=0.8):
        self.fallback = fallback or HeuristicPolicy()
        self.api_key = api_key if api_key is not None else os.environ.get("RUNWARE_API_KEY", "")
        self.model = model if model is not None else os.environ.get("RUNWARE_MODEL", "")
        self.base_url = (base_url or os.environ.get("RUNWARE_BASE_URL") or "https://api.runware.ai/v1").rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.calls = 0
        self.fallbacks = 0
        self.last_error: str | None = None

    @property
    def name(self) -> str:
        return self.model or self.fallback.name

    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def decide(self, agent_id: str, role: str, obs: dict, options: list[dict], rng) -> Decision:
        if not self.available() or len(options) < 2 and role not in ("commander",):
            return self.fallback.decide(agent_id, role, obs, options, rng)
        try:
            return self._call(agent_id, role, obs, options)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade, never crash the run
            self.fallbacks += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            dec = self.fallback.decide(agent_id, role, obs, options, rng)
            dec.extra["fallback_reason"] = self.last_error
            return dec

    # -- internals ---------------------------------------------------------
    free_director = True  # the Director invents twists freely on the LLM path (validated by the engine)

    def _chat(self, system: str, user: str, max_tokens: int = 300):
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        t0 = time.monotonic()
        self.calls += 1
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - fixed https endpoint (or test server)
            payload = json.loads(resp.read().decode("utf-8"))
        latency = int((time.monotonic() - t0) * 1000)
        return payload["choices"][0]["message"]["content"], latency, (payload.get("usage") or {})

    def _call(self, agent_id, role, obs, options) -> Decision:
        listing = "\n".join(f"{o['i']}: {o['label']}  [action={o['action']}, target={o['target']}, risky={o['risky']}]" for o in options)
        user = f"Observation:\n{json.dumps(obs, separators=(',', ':'))}\n\nLegal options:\n{listing}\n\nChoose one."
        text, latency, usage = self._chat(_system_prompt(role, agent_id, obs), user)
        data = _parse_json(text)
        choice = data.get("choice", data.get("index"))
        if isinstance(choice, bool) or not isinstance(choice, int) or not 0 <= choice < len(options):
            raise ValueError(f"invalid choice {choice!r}")
        reasoning = str(data.get("reasoning") or "").strip()
        if not reasoning:
            raise ValueError("empty reasoning")
        utterance = str(data.get("utterance") or "").strip()[:240] or None
        conf = data.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.6
        return Decision(
            index=choice, utterance=utterance, reasoning=reasoning[:400], confidence=max(0.0, min(1.0, conf)),
            model=self.model, latency_ms=latency,
            tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"),
        )

    def director_free(self, obs: dict, rng) -> dict | None:
        """Free-form Director: a short invented twist plus ONE structured effect from the engine's fixed vocabulary.
        Returns {"twist": str, "effect": {"kind": str, "target": ...}} or None (no twist / any error)."""
        if not self.available():
            return None
        system = (
            "You are the Director of a short film about a night-time apartment fire rescue. Every few seconds you may "
            "invent ONE twist that complicates the rescue, grounded in where the fire and the people actually are. "
            "Most of the time do nothing. "
            'Reply with ONE JSON object: {"twist": "<one vivid sentence, or empty for no twist>", '
            '"effect": {"kind": "<one of effect_vocabulary>", "target": "<room id like 3-hall, a flight number 1-4, a victim id, or null>"}, '
            '"reasoning": "<why now>"}. '
            "Effects only land where fire really is (fire_surge/backdraft/flashover need a room with fire >= 0.25; stair_collapse "
            "needs fire in the halls at that flight). Never invent kinds outside the vocabulary."
        )
        try:
            text, _, _ = self._chat(system, json.dumps(obs, separators=(",", ":")), max_tokens=250)
            data = _parse_json(text)
            if not str(data.get("twist") or "").strip():
                return None
            return {"twist": data["twist"], "effect": data.get("effect") or {}, "reasoning": data.get("reasoning", "")}
        except Exception as exc:  # noqa: BLE001
            self.fallbacks += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return None


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("reply JSON is not an object")
    return obj
