/* @bruin

name: mart.run_summary
type: pg.sql
description: >
  One row per run: seed, twists, how many victims were saved, how the human voted, and an ending label.
  Used for the "different runs, different outcomes" end card.

materialization:
  type: table

depends:
  - staging.events
  - mart.agent_metrics
  - mart.victim_outcomes

columns:
  - name: run_id
    type: uuid
    checks:
      - name: not_null
      - name: unique
  - name: ending
    type: varchar
    checks:
      - name: not_null
      - name: accepted_values
        value: [everyone saved, some saved, no one saved, in progress]

@bruin */

with twists as (
  select
    run_id,
    string_agg(distinct coalesce(twist, world ->> 'twist'), ', ') as twists
  from staging.events
  where twist is not null or world ->> 'kind' = 'twist'
  group by 1
),

victims as (
  select
    run_id,
    count(*)                                            as victims,
    count(*) filter (where final_status = 'rescued')    as rescued,
    count(*) filter (where final_status = 'lost')       as lost
  from mart.victim_outcomes
  group by 1
),

agents as (
  select
    run_id,
    sum(approvals_requested) as approvals_requested,
    sum(approved)            as approved,
    sum(denied)              as denied,
    sum(timed_out)           as timed_out,
    sum(llm_calls)           as llm_calls,
    sum(tokens_in + tokens_out) as tokens
  from mart.agent_metrics
  group by 1
),

duration as (
  select run_id, max(t_sim) as sim_seconds, count(*) as events
  from staging.events
  group by 1
)

select
  r.run_id,
  r.seed,
  r.scenario_id,
  r.started_at,
  r.ended_at,
  d.sim_seconds,
  d.events,
  t.twists,
  coalesce(v.victims, 0)  as victims,
  coalesce(v.rescued, 0)  as rescued,
  coalesce(v.lost, 0)     as lost,
  a.approvals_requested,
  a.approved,
  a.denied,
  a.timed_out,
  a.llm_calls,
  a.tokens,
  case
    when r.ended_at is null then 'in progress'
    when coalesce(v.victims, 0) > 0 and v.rescued = v.victims then 'everyone saved'
    when v.rescued > 0 then 'some saved'
    else 'no one saved'
  end as ending,
  now() as built_at
from raw.runs r
left join duration d using (run_id)
left join twists t using (run_id)
left join victims v using (run_id)
left join agents a using (run_id)
order by r.started_at
