-- Raw tables written only by the API. Bruin reads these and owns staging.* and mart.*.
-- Safe to run more than once.

create schema if not exists raw;
create schema if not exists staging;
create schema if not exists mart;

create table if not exists raw.runs (
  run_id      uuid primary key,
  seed        int not null,
  scenario_id text not null,
  notes       text,
  started_at  timestamptz not null default now(),
  ended_at    timestamptz
);

create table if not exists raw.events (
  run_id      uuid not null references raw.runs (run_id),
  seq         int not null,
  t_sim       real not null,
  agent_id    text not null,
  agent_role  text not null,
  type        text not null,
  payload     jsonb not null default '{}',
  reasoning   text,
  confidence  real,
  model       text,
  latency_ms  int,
  tokens_in   int,
  tokens_out  int,
  received_at timestamptz not null default now(),
  primary key (run_id, seq)
);

create index if not exists events_run_type on raw.events (run_id, type);

-- Bruin run history, written by the API each time it runs the pipeline. Shown on the dashboard.
create schema if not exists ops;

create table if not exists ops.bruin_runs (
  id          serial primary key,
  trigger     text not null,               -- schedule, run_end, manual
  started_at  timestamptz not null,
  finished_at timestamptz,
  exit_code   int,
  output      text
);

create table if not exists ops.bruin_tasks (
  run_id      int not null references ops.bruin_runs (id) on delete cascade,
  name        text not null,               -- staging.events, or staging.events:seq:not_null
  kind        text not null,               -- asset or check
  status      text not null,               -- passed, failed, skipped
  duration_ms int,
  primary key (run_id, name)
);

-- Lessons the agents write after each run, and the human's verdict on that run's outcome.
create schema if not exists learn;

create table if not exists learn.lessons (
  id          serial primary key,
  run_id      uuid not null references raw.runs (run_id),
  role        text not null,               -- commander, rescue, suppression
  lesson      text not null,
  evidence    text,
  model       text,
  latency_ms  int,
  created_at  timestamptz not null default now()
);

create table if not exists learn.verdicts (
  run_id      uuid primary key references raw.runs (run_id),
  verdict     text not null,               -- approve or decline
  note        text,
  decided_at  timestamptz not null default now()
);
