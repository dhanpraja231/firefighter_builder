"""Event API for the firefighter film. See SPEC.md section 1.2.

Agents POST events here, the API stores them in raw.events, and Bruin builds
staging.* and mart.* from them. The dashboard at / reads from the same API.

Runs locally next to the ff-pg Postgres container and runs Bruin itself:
every BRUIN_EVERY_SECONDS (default 120), when a run ends, and from the dashboard.

    uv run --python 3.12 --with-requirements api/requirements.txt uvicorn app:app --app-dir api --port 8010
"""

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

HERE = Path(__file__).parent
REPO = HERE.parent
SCHEMA_SQL = REPO / "db" / "schema.sql"
BRUIN_BIN = os.environ.get("BRUIN_BIN") or shutil.which("bruin") or str(Path.home() / ".local/bin/bruin")
BRUIN_EVERY_SECONDS = int(os.environ.get("BRUIN_EVERY_SECONDS", "120"))
API_TOKEN = os.environ.get("API_TOKEN", "")

AgentRole = Literal["scout", "suppression", "rescue", "commander", "victim", "director", "human"]
EventType = Literal["move", "speak", "decide", "act", "request_approval", "approval", "world_event", "status"]


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/firefighter")


pool: AsyncConnectionPool | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global pool
    pool = AsyncConnectionPool(database_url(), min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False)
    await pool.open()
    async with pool.connection() as conn:
        await conn.execute(SCHEMA_SQL.read_text())
    schedule = asyncio.create_task(_bruin_schedule()) if BRUIN_EVERY_SECONDS > 0 else None
    yield
    if schedule:
        schedule.cancel()
    await pool.close()


app = FastAPI(title="firefighter events", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def require_token(authorization: str = Header(default="")):
    if not API_TOKEN:
        return
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(401, "missing or wrong bearer token")


async def fetch(sql: str, params: tuple | dict = ()) -> list[dict]:
    async with pool.connection() as conn:
        try:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
            # mart.* does not exist until Bruin has run once.
            return []


def mart_rows(table: str, run_id: uuid.UUID | None = None, order: str = "") -> Any:
    where = "where run_id = %s" if run_id else ""
    return fetch(f"select * from {table} {where} {order}", (run_id,) if run_id else ())


# ---------- writes (agents) ----------

class RunIn(BaseModel):
    seed: int
    scenario_id: str = "apartment-3f"
    notes: str | None = None
    run_id: uuid.UUID | None = None


class EventIn(BaseModel):
    t_sim: float
    agent_id: str
    agent_role: AgentRole
    type: EventType
    payload: dict = Field(default_factory=dict)
    reasoning: str | None = None
    confidence: float | None = None
    model: str | None = None
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


@app.post("/runs", dependencies=[Depends(require_token)])
async def create_run(body: RunIn):
    run_id = body.run_id or uuid.uuid4()
    async with pool.connection() as conn:
        await conn.execute(
            "insert into raw.runs (run_id, seed, scenario_id, notes) values (%s, %s, %s, %s)",
            (run_id, body.seed, body.scenario_id, body.notes),
        )
    return {"run_id": run_id}


@app.post("/runs/{run_id}/events", dependencies=[Depends(require_token)])
async def add_events(run_id: uuid.UUID, events: list[EventIn]):
    async with pool.connection() as conn, conn.transaction():
        # Lock the run row so concurrent posts get gap-free seq numbers.
        cur = await conn.execute("select ended_at from raw.runs where run_id = %s for update", (run_id,))
        run = await cur.fetchone()
        if run is None:
            raise HTTPException(404, "unknown run_id")
        cur = await conn.execute("select coalesce(max(seq), 0) as seq from raw.events where run_id = %s", (run_id,))
        seq = (await cur.fetchone())["seq"]
        seqs = []
        for e in events:
            seq += 1
            await conn.execute(
                """insert into raw.events (run_id, seq, t_sim, agent_id, agent_role, type, payload, reasoning,
                   confidence, model, latency_ms, tokens_in, tokens_out)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, seq, e.t_sim, e.agent_id, e.agent_role, e.type, Jsonb(e.payload), e.reasoning,
                 e.confidence, e.model, e.latency_ms, e.tokens_in, e.tokens_out),
            )
            seqs.append(seq)
    return {"seq": seqs}


class ApprovalIn(BaseModel):
    decision: Literal["approve", "deny"]
    note: str | None = None


@app.post("/runs/{run_id}/approvals/{seq}", dependencies=[Depends(require_token)])
async def approve(run_id: uuid.UUID, seq: int, body: ApprovalIn):
    rows = await fetch(
        "select t_sim from raw.events where run_id = %s and seq = %s and type = 'request_approval'", (run_id, seq)
    )
    if not rows:
        raise HTTPException(404, "no approval request with that seq")
    payload = {"action": body.decision, "approval_of_seq": seq, "note": body.note}
    return await add_events(run_id, [EventIn(t_sim=rows[0]["t_sim"], agent_id="human", agent_role="human",
                                             type="approval", payload=payload)])


@app.post("/runs/{run_id}/end", dependencies=[Depends(require_token)])
async def end_run(run_id: uuid.UUID):
    async with pool.connection() as conn:
        await conn.execute("update raw.runs set ended_at = now() where run_id = %s and ended_at is null", (run_id,))
    return {"ended": True, "bruin": await start_bruin("run_end")}


# ---------- reads (scene, dashboard) ----------

@app.get("/runs")
async def list_runs():
    return await fetch(
        """select r.run_id, r.seed, r.scenario_id, r.notes, r.started_at, r.ended_at,
                  count(e.seq) as events, max(e.received_at) as last_event_at
           from raw.runs r left join raw.events e using (run_id)
           group by r.run_id order by r.started_at desc limit 50"""
    )


@app.get("/runs/compare")
async def compare():
    return await mart_rows("mart.run_summary", order="order by started_at desc")


@app.get("/runs/{run_id}/timeline")
async def timeline(run_id: uuid.UUID, since_seq: int = 0, limit: int = Query(1000, le=5000)):
    return await fetch(
        "select * from raw.events where run_id = %s and seq > %s order by seq limit %s", (run_id, since_seq, limit)
    )


@app.get("/runs/{run_id}/stream")
async def stream(run_id: uuid.UUID, since_seq: int = 0):
    async def gen():
        last = since_seq
        while True:
            rows = await timeline(run_id, last, 500)
            for row in rows:
                last = row["seq"]
                yield f"data: {json.dumps(row, default=str)}\n\n"
            if not rows:
                yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/runs/{run_id}/approvals")
async def approvals(run_id: uuid.UUID, status: Literal["pending", "all"] = "pending"):
    rows = await fetch(
        """select r.seq, r.t_sim, r.agent_id, r.payload, r.reasoning, a.payload ->> 'action' as decision
           from raw.events r
           left join raw.events a on a.run_id = r.run_id and a.type = 'approval'
                                  and (a.payload ->> 'approval_of_seq')::int = r.seq
           where r.run_id = %s and r.type = 'request_approval' order by r.seq""",
        (run_id,),
    )
    return [r for r in rows if status == "all" or r["decision"] is None]


@app.get("/runs/{run_id}/decision-log")
async def decision_log(run_id: uuid.UUID):
    return await mart_rows("mart.decision_log", run_id, "order by seq")


@app.get("/runs/{run_id}/metrics")
async def metrics(run_id: uuid.UUID):
    return {
        "agents": await mart_rows("mart.agent_metrics", run_id, "order by agent_id"),
        "victims": await mart_rows("mart.victim_outcomes", run_id, "order by victim_id"),
    }


TASK_LINE = re.compile(r"(Finished|Failed): (\S+) \(([\d.]+)(ms|s|m)\)")


def parse_bruin_output(text: str) -> list[dict]:
    """Turn Bruin's console log into one row per asset and per quality check."""
    tasks = {}
    for status, name, num, unit in TASK_LINE.findall(text):
        ms = float(num) * {"ms": 1, "s": 1000, "m": 60000}[unit]
        tasks[name] = {"name": name, "kind": "check" if ":" in name else "asset",
                       "status": "passed" if status == "Finished" else "failed", "duration_ms": round(ms)}
    return list(tasks.values())


_bruin: dict = {"running": False}


async def start_bruin(trigger: str = "manual") -> dict:
    """Run the Bruin pipeline in the background now (also runs every BRUIN_EVERY_SECONDS)."""
    if _bruin["running"]:
        return {"started": False, "reason": "Bruin is already running"}
    _bruin["running"] = True
    asyncio.create_task(_run_bruin(trigger))
    return {"started": True}


async def _run_bruin(trigger: str) -> None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "insert into ops.bruin_runs (trigger, started_at) values (%s, now()) returning id", (trigger,))
        run_id = (await cur.fetchone())["id"]
    code, text = -1, ""
    try:
        proc = await asyncio.create_subprocess_exec(
            BRUIN_BIN, "run", "--no-color", str(REPO / "bruin"), cwd=REPO,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        code, text = proc.returncode, out.decode(errors="replace")
    except Exception as exc:  # report it on the dashboard rather than crash the API
        text = f"could not run bruin: {exc}"
    finally:
        tasks = parse_bruin_output(text)
        async with pool.connection() as conn, conn.transaction():
            # Anything a recent passing run had that this run never reached was skipped (upstream failure).
            cur = await conn.execute(
                """select name, kind from ops.bruin_tasks where run_id =
                   (select id from ops.bruin_runs where exit_code = 0 order by id desc limit 1)""")
            seen = {t["name"] for t in tasks}
            tasks += [{"name": r["name"], "kind": r["kind"], "status": "skipped", "duration_ms": None}
                      for r in await cur.fetchall() if r["name"] not in seen]
            await conn.execute(
                "update ops.bruin_runs set finished_at = now(), exit_code = %s, output = %s where id = %s",
                (code, text[-20000:], run_id))
            for t in tasks:
                await conn.execute(
                    "insert into ops.bruin_tasks (run_id, name, kind, status, duration_ms) values (%s, %s, %s, %s, %s)",
                    (run_id, t["name"], t["kind"], t["status"], t["duration_ms"]))
        _bruin["running"] = False


async def _bruin_schedule() -> None:
    while True:
        await asyncio.sleep(BRUIN_EVERY_SECONDS)
        await start_bruin("schedule")


@app.post("/pipeline/run")
async def pipeline_run():
    return await start_bruin("manual")


@app.get("/pipeline/status")
async def pipeline_status():
    raw = await fetch("select count(*) as n, max(received_at) as last_event_at from raw.events")
    staged = await fetch("select count(*) as n from staging.events")
    runs = await fetch(
        """select r.id, r.trigger, r.started_at, r.finished_at, r.exit_code,
                  extract(epoch from (r.finished_at - r.started_at)) * 1000 as duration_ms,
                  count(*) filter (where t.kind = 'asset' and t.status = 'passed') as assets_passed,
                  count(*) filter (where t.kind = 'asset' and t.status <> 'passed') as assets_not_passed,
                  count(*) filter (where t.kind = 'check' and t.status = 'passed') as checks_passed,
                  count(*) filter (where t.kind = 'check' and t.status = 'failed') as checks_failed,
                  count(*) filter (where t.kind = 'check' and t.status = 'skipped') as checks_skipped
           from ops.bruin_runs r left join ops.bruin_tasks t on t.run_id = r.id
           group by r.id order by r.id desc limit 40""")
    last = next((r for r in runs if r["finished_at"]), None)
    tasks = await fetch(
        "select name, kind, status, duration_ms from ops.bruin_tasks where run_id = %s order by name",
        (last["id"],)) if last else []
    return {
        "running": _bruin["running"],
        "every_seconds": BRUIN_EVERY_SECONDS,
        "raw_events": raw[0]["n"],
        "last_event_at": raw[0]["last_event_at"],
        "staged_events": staged[0]["n"] if staged else None,
        "runs": runs,
        "last_run_tasks": tasks,
    }


@app.get("/pipeline/runs/{bruin_run_id}/output")
async def pipeline_output(bruin_run_id: int):
    rows = await fetch("select output from ops.bruin_runs where id = %s", (bruin_run_id,))
    if not rows:
        raise HTTPException(404, "no such Bruin run")
    return {"output": rows[0]["output"]}


@app.get("/runs/{run_id}/capture")
async def capture(run_id: uuid.UUID):
    """Did every agent decision make it through? Compares raw.events with what Bruin built."""
    raw = await fetch(
        """select count(*) filter (where type in ('decide', 'act', 'request_approval')) as decisions,
                  count(*) filter (where type in ('decide', 'act', 'request_approval')
                                   and coalesce(trim(reasoning), '') <> '') as with_reasoning,
                  count(*) filter (where latency_ms is not null) as llm_calls,
                  count(*) filter (where type = 'request_approval') as approval_requests,
                  count(*) filter (where type = 'approval' and payload ? 'approval_of_seq'
                                   and payload ->> 'approval_of_seq' is not null) as approvals,
                  max(payload ->> 'action') filter (where type = 'approval' and payload ->> 'approval_of_seq' is null)
                      as outcome_verdict,
                  count(*) as events
           from raw.events where run_id = %s""", (run_id,))
    logged = await fetch("select count(*) as n from mart.decision_log where run_id = %s", (run_id,))
    return {**raw[0], "in_decision_log": logged[0]["n"] if logged else None}


# ---------- learning loop ----------

class LessonIn(BaseModel):
    role: Literal["commander", "rescue", "suppression"]
    lesson: str
    evidence: str | None = None
    model: str | None = None
    latency_ms: int | None = None


@app.post("/runs/{run_id}/lessons", dependencies=[Depends(require_token)])
async def add_lessons(run_id: uuid.UUID, lessons: list[LessonIn]):
    async with pool.connection() as conn, conn.transaction():
        for l in lessons:
            await conn.execute(
                "insert into learn.lessons (run_id, role, lesson, evidence, model, latency_ms) values (%s, %s, %s, %s, %s, %s)",
                (run_id, l.role, l.lesson, l.evidence, l.model, l.latency_ms))
    return {"added": len(lessons)}


class VerdictIn(BaseModel):
    verdict: Literal["approve", "decline"]
    note: str | None = None


@app.post("/runs/{run_id}/verdict", dependencies=[Depends(require_token)])
async def verdict(run_id: uuid.UUID, body: VerdictIn):
    """The human judges the run's overall outcome. Stored for the learning loop and logged as the outcome approval event."""
    async with pool.connection() as conn:
        await conn.execute(
            """insert into learn.verdicts (run_id, verdict, note) values (%s, %s, %s)
               on conflict (run_id) do update set verdict = excluded.verdict, note = excluded.note, decided_at = now()""",
            (run_id, body.verdict, body.note))
    rows = await fetch("select coalesce(max(t_sim), 0) as t from raw.events where run_id = %s", (run_id,))
    await add_events(run_id, [EventIn(t_sim=rows[0]["t"], agent_id="human", agent_role="human", type="approval",
                                      payload={"action": "approve" if body.verdict == "approve" else "deny",
                                               "approval_of_seq": None, "note": body.note or "outcome verdict"})])
    return {"verdict": body.verdict}


@app.post("/learning/reset", dependencies=[Depends(require_token)])
async def reset_learning():
    """Erase the agents' memory: all lessons and verdicts, and start the track record over. Run history stays."""
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute("delete from learn.lessons")
        lessons = cur.rowcount
        cur = await conn.execute("delete from learn.verdicts")
        verdicts = cur.rowcount
        await conn.execute("insert into learn.resets default values")
    return {"deleted_lessons": lessons, "deleted_verdicts": verdicts}


@app.get("/learning")
async def learning(limit: int = 12):
    """What the next run should know: recent lessons (with the verdict on their run) and the track record."""
    lessons = await fetch(
        """select l.id, l.run_id, l.role, l.lesson, l.evidence, l.created_at, v.verdict, r.seed
           from learn.lessons l join raw.runs r using (run_id) left join learn.verdicts v using (run_id)
           order by l.id desc limit %s""", (limit,))
    curve = await learning_curve()
    recent = [c for c in curve if c["victims"]][-5:]
    history = ", ".join(f"{c['saved']}/{c['victims']}" + (f" ({c['verdict']}d)" if c["verdict"] else "") for c in recent)
    return {"runs": len(curve), "history": f"last runs saved {history}" if history else "", "lessons": lessons}


@app.get("/learning/curve")
async def learning_curve():
    """Victims saved per run, in run order, straight from raw events (no Bruin lag)."""
    return await fetch(
        """with last_status as (
             select distinct on (run_id, agent_id) run_id, agent_id, payload ->> 'victim_status' as st
             from raw.events where type = 'status' order by run_id, agent_id, seq desc)
           select r.run_id, r.seed, r.started_at, row_number() over (order by r.started_at) as n,
                  count(s.agent_id) as victims, count(*) filter (where s.st = 'rescued') as saved,
                  v.verdict,
                  (select count(*) from learn.lessons l where l.run_id = r.run_id) as lessons
           from raw.runs r left join last_status s using (run_id) left join learn.verdicts v using (run_id)
           where r.started_at > coalesce((select max(reset_at) from learn.resets), '-infinity')
           group by r.run_id, v.verdict order by r.started_at""")


@app.get("/runs/{run_id}/lessons")
async def run_lessons(run_id: uuid.UUID):
    rows = await fetch("select role, lesson, evidence, model, latency_ms, created_at from learn.lessons where run_id = %s order by id", (run_id,))
    v = await fetch("select verdict, note, decided_at from learn.verdicts where run_id = %s", (run_id,))
    return {"lessons": rows, "verdict": v[0] if v else None}


@app.get("/health")
async def health():
    await fetch("select 1")
    return {"ok": True}


@app.get("/")
async def dashboard():
    return FileResponse(HERE / "dashboard.html")


@app.get("/live")
async def live():
    """3D scene (Vite dev server on :5173) and the dashboard, side by side."""
    return FileResponse(HERE / "live.html")
