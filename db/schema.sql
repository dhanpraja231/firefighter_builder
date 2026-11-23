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
