/* @bruin

name: mart.agent_metrics
type: pg.sql
description: Per run and agent, how much it decided, LLM latency and tokens, and how its approval requests went.

materialization:
  type: table

depends:
  - staging.events

columns:
  - name: run_id
    type: uuid
    checks:
      - name: not_null
  - name: agent_id
    type: varchar
    checks:
      - name: not_null
  - name: decisions
    type: integer
    checks:
      - name: non_negative

custom_checks:
  - name: one row per run and agent
    value: 0
    query: |
      select count(*) from (
        select run_id, agent_id from mart.agent_metrics
        group by 1, 2 having count(*) > 1
      ) dupes

@bruin */

with approvals as (
  select run_id, approval_of_seq as request_seq, action as decision
  from staging.events
  where type = 'approval'
),

requests as (
  select r.run_id, r.agent_id, a.decision
  from staging.events r
  left join approvals a on a.run_id = r.run_id and a.request_seq = r.seq
  where r.type = 'request_approval'
),

request_counts as (
  select
    run_id,
    agent_id,
    count(*)                                               as approvals_requested,
    count(*) filter (where decision = 'approve')           as approved,
    count(*) filter (where decision = 'deny')              as denied,
    count(*) filter (where decision = 'timeout_default')   as timed_out
  from requests
  group by 1, 2
),

event_counts as (
  select
    run_id,
    agent_id,
    min(agent_role)                                                          as agent_role,
    count(*)                                                                 as events,
    count(*) filter (where type in ('decide', 'act', 'request_approval'))   as decisions,
    count(*) filter (where type = 'move')                                    as moves,
    count(*) filter (where type = 'speak')                                   as utterances,
    count(*) filter (where model is not null)                                as llm_calls,
    round(avg(latency_ms))::int                                              as avg_latency_ms,
    round(percentile_cont(0.95) within group (order by latency_ms))::int     as p95_latency_ms,
    coalesce(sum(tokens_in), 0)                                              as tokens_in,
    coalesce(sum(tokens_out), 0)                                             as tokens_out,
    round(avg(confidence)::numeric, 2)                                       as avg_confidence
  from staging.events
  group by 1, 2
)

select
  e.*,
  coalesce(r.approvals_requested, 0) as approvals_requested,
  coalesce(r.approved, 0)            as approved,
  coalesce(r.denied, 0)              as denied,
  coalesce(r.timed_out, 0)           as timed_out
from event_counts e
left join request_counts r using (run_id, agent_id)
order by e.run_id, e.agent_id
