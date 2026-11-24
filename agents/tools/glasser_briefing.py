"""Building dossier for the Commander, powered by Glasser (RentCast).

Prep time (once per scenario address):
    python -m agents.tools.glasser_briefing \\
        --scenario apartment-3f \\
        --address "5500 Grand Lake Dr, San Antonio, TX 78244" \\
        --zip 78244 \\
        --label "Harbor Court Apartments (simulated)"

Run time (every run, offline):
    from agents.tools.glasser_briefing import load, summarize
    briefing = load("apartment-3f")
    text = summarize(briefing)

No live Glasser calls happen during a sim run. Fixtures are scrubbed: no
owner names, mailing addresses, or raw street addresses appear in the
committed JSON the Commander (and demo) see.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
KEEP_FIELDS = (
    "property_type",
    "year_built",
    "bedrooms",
    "bathrooms",
    "living_area_sqft",
    "lot_size_sqft",
)
DROP_SUBSTRINGS = (
    "owner",
    "mailing",
    "address",
    "latitude",
    "longitude",
    "email",
    "phone",
    "name",
)
GLASSER_PROVIDER = "rentcast"
GLASSER_ENDPOINT = "/avm/value"
DEFAULT_TASK_USE_CASE = (
    "Fetch building structural property data for a firefighter simulation "
    "commander briefing; scrub PII and save as fixture"
)


def fixture_path(scenario_id: str) -> Path:
    return FIXTURES_DIR / f"{scenario_id}_briefing.json"


def _find_glasser() -> str:
    """Resolve the glasser CLI: PATH, then project-root npx binary."""
    found = shutil.which("glasser")
    if found:
        return found
    # agents/tools -> agents -> firefighter_builder -> Multiplayer hack
    root_bin = Path(__file__).resolve().parents[3] / "node_modules" / ".bin" / "glasser"
    if root_bin.is_file():
        return str(root_bin)
    raise FileNotFoundError(
        "glasser CLI not found. From the Multiplayer hack root run: npm install && npx glasser login"
    )


def _glasser_json(args: list[str]) -> dict[str, Any]:
    glasser = _find_glasser()
    env = os.environ.copy()
    cmd = [glasser, *args, "-j"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"glasser {' '.join(args)} failed: exit {result.returncode}: {err}")
    if not result.stdout.strip():
        raise RuntimeError(f"glasser {' '.join(args)} returned empty stdout")
    return json.loads(result.stdout)


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _subject_blob(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize RentCast AVM / property payloads to a flat subject dict."""
    if not isinstance(raw, dict):
        return {}
    for key in ("subjectProperty", "subject", "property", "output"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            # Prefer nested subject when present; fall through if empty-ish.
            if any(k in nested for k in ("propertyType", "yearBuilt", "bedrooms", "squareFootage")):
                return nested
            deeper = _subject_blob(nested)
            if deeper:
                return deeper
    if any(k in raw for k in ("propertyType", "yearBuilt", "bedrooms", "squareFootage")):
        return raw
    data = raw.get("data")
    if isinstance(data, dict):
        return _subject_blob(data)
    return raw if isinstance(raw, dict) else {}


def scrub(
    raw: dict[str, Any],
    *,
    label: str,
    scenario_id: str,
    zip_code: str | None = None,
) -> dict[str, Any]:
    """Keep structural fields only; drop PII and exact address."""
    subject = _subject_blob(raw)

    def first(*keys: str) -> Any:
        return _pick(subject, *keys)

    # Drop any leftover keys that look like PII even if we only copy KEEP_FIELDS.
    for key in list(subject.keys()):
        lower = key.lower()
        if any(part in lower for part in DROP_SUBSTRINGS):
            continue

    out: dict[str, Any] = {
        "scenario_id": scenario_id,
        "label": label,
        "source": "glasser:rentcast:/avm/value",
        "scrubbed": True,
        "property_type": first("propertyType", "property_type"),
        "year_built": first("yearBuilt", "year_built"),
        "bedrooms": first("bedrooms"),
        "bathrooms": first("bathrooms"),
        "living_area_sqft": first("squareFootage", "living_area_sqft", "square_footage"),
        "lot_size_sqft": first("lotSize", "lot_size_sqft", "lotSizeSquareFeet"),
    }
    if zip_code:
        out["zip"] = zip_code
    return out


def summarize(
    briefing: dict[str, Any],
    *,
    floors: int | None = 3,
    scenario_kind: str = "multifamily walkup",
) -> str:
    """Commander briefing text.

    Scenario geometry (floors / apartment layout) is authored and wins for
    what the sim *is*. Glasser only supplies age/size risk signals from a
    scrubbed parcel lookup — we do not treat parcel property_type as the
    in-world building type (e.g. a Single Family AVM must not override a
    3-floor apartment fire scenario).
    """
    label = briefing.get("label") or briefing.get("scenario_id") or "the building"
    year = briefing.get("year_built")
    sqft = briefing.get("living_area_sqft")

    age_bits: list[str] = []
    if year is not None:
        age_bits.append(f"year_built={year}")
    if sqft is not None:
        age_bits.append(f"parcel ~{sqft} sqft")
    age_detail = ", ".join(age_bits) if age_bits else "age/size unavailable"

    floor_bit = f"{floors}-floor {scenario_kind}" if floors else scenario_kind
    risk = (
        "Older construction elevates stair-collapse and smoke-spread risk on shared stairs."
        if isinstance(year, int) and year < 1990
        else "Treat stairwells and exits as primary constraints."
    )
    return (
        f"Incident at {label}: authored as a {floor_bit}. "
        f"Glasser building-age intel ({age_detail}). {risk} "
        f"Prioritize upper-floor sweep before committing rescue."
    )


def save_fixture(scenario_id: str, briefing: dict[str, Any]) -> Path:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = fixture_path(scenario_id)
    path.write_text(json.dumps(briefing, indent=2) + "\n", encoding="utf-8")
    return path


def load(scenario_id: str) -> dict[str, Any]:
    path = fixture_path(scenario_id)
    if not path.is_file():
        raise FileNotFoundError(
            f"No briefing fixture for {scenario_id} at {path}. "
            f'Run: python -m agents.tools.glasser_briefing --scenario {scenario_id} '
            f'--address "..." --zip "..."'
        )
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_avm_value(address: str, task_id: str | None = None) -> dict[str, Any]:
    """Paid Glasser Run: RentCast /avm/value. Returns the full Run object."""
    idem = str(uuid.uuid4())
    payload = json.dumps({"address": address, "compCount": 5})
    args = [
        "run",
        "-p",
        GLASSER_PROVIDER,
        "-e",
        GLASSER_ENDPOINT,
        "-i",
        payload,
        "--idempotency-key",
        idem,
        "--wait",
    ]
    if task_id:
        args.extend(["--task", task_id])
    data = _glasser_json(args)
    if isinstance(data, dict) and "output" in data:
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {"output": data}


def load_run(run_id: str) -> dict[str, Any]:
    """Re-read an existing Glasser Run (free)."""
    data = _glasser_json(["runs", "get", "-r", run_id])
    if isinstance(data, dict) and "output" in data:
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def briefing_from_run(
    run: dict[str, Any],
    scenario_id: str,
    zip_code: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    output = run.get("output") if isinstance(run, dict) else {}
    if not isinstance(output, dict):
        output = {}
    public_label = label or f"{scenario_id} (simulated)"
    briefing = scrub(output, label=public_label, scenario_id=scenario_id, zip_code=zip_code)
    if run.get("charge_usd") is not None:
        briefing["glasser_charge_usd"] = run["charge_usd"]
    if run.get("id") is not None:
        briefing["glasser_run_id"] = run["id"]
    return briefing


def fetch_and_save(
    scenario_id: str,
    address: str,
    zip_code: str | None = None,
    label: str | None = None,
    task_id: str | None = None,
    from_run: str | None = None,
) -> dict[str, Any]:
    """Fetch once from Glasser (or reuse a Run), scrub, write fixture."""
    if from_run:
        run = load_run(from_run)
    else:
        run = fetch_avm_value(address, task_id=task_id)
    briefing = briefing_from_run(run, scenario_id=scenario_id, zip_code=zip_code, label=label)
    path = save_fixture(scenario_id, briefing)
    briefing["_fixture_path"] = str(path)
    return briefing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="scenario_id, e.g. apartment-3f")
    parser.add_argument("--address", default=None, help="US address for RentCast lookup (not saved)")
    parser.add_argument("--zip", dest="zip_code", default=None, help="ZIP code (optional, saved)")
    parser.add_argument(
        "--label",
        default=None,
        help='Public label shown in demo, e.g. "Harbor Court Apartments (simulated)"',
    )
    parser.add_argument("--task", dest="task_id", default=None, help="Glasser task id to attach Runs to")
    parser.add_argument(
        "--from-run",
        default=None,
        help="Reuse an existing Glasser Run id (free) instead of a new paid call",
    )
    parser.add_argument(
        "--from-scenario",
        action="store_true",
        help="Load address/zip/label from scenarios/<scenario>.json (address still not written to fixture)",
    )
    args = parser.parse_args(argv)

    address = args.address
    zip_code = args.zip_code
    label = args.label
    if args.from_scenario:
        scenario_path = Path(__file__).resolve().parents[2] / "scenarios" / f"{args.scenario}.json"
        data = json.loads(scenario_path.read_text(encoding="utf-8"))
        address = address or data.get("address")
        zip_code = zip_code or data.get("zip")
        label = label or data.get("label")

    if not args.from_run and not address:
        parser.error("address is required unless --from-run is set")

    if args.from_run:
        print(
            f"Re-scrubbing Glasser Run {args.from_run} for scenario={args.scenario}…",
            file=sys.stderr,
        )
    else:
        print(
            f"Glasser RentCast {GLASSER_ENDPOINT} ≈ $0.0814/call. "
            f"Fetching for scenario={args.scenario} (address will not be saved)…",
            file=sys.stderr,
        )

    briefing = fetch_and_save(
        scenario_id=args.scenario,
        address=address or "",
        zip_code=zip_code,
        label=label,
        task_id=args.task_id,
        from_run=args.from_run,
    )
    path = briefing.pop("_fixture_path", None)
    print(json.dumps(briefing, indent=2))
    print(f"\nWrote {path}", file=sys.stderr)
    print(summarize(briefing), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
