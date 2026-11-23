/* @bruin

name: mart.victim_outcomes
type: pg.sql
description: Per run and victim, when they were found and rescued, who helped them, and how it ended.

materialization:
  type: table

depends:
  - staging.events

columns:
  - name: run_id
    type: uuid
    checks:
      - name: not_null
  - name: victim_id
    type: varchar
    checks:
      - name: not_null
  - name: final_status
    type: varchar
    checks:
      - name: not_null
      - name: accepted_values
        value: [trapped, found, moving, rescued, lost]

@bruin */

with victims as (
  select distinct run_id, agent_id as victim_id
  from staging.events
  where agent_role = 'victim'
),

status as (
  select run_id, agent_id as victim_id, seq, t_sim, victim_status, target
  from staging.events
  where type = 'status'
),

last_status as (
  select distinct on (run_id, victim_id)
    run_id, victim_id, victim_status as final_status, target as last_helper
  from status
  order by run_id, victim_id, seq desc
),

times as (
  select
    run_id,
    victim_id,
    min(t_sim) filter (where victim_status = 'found')   as found_at_s,
    min(t_sim) filter (where victim_status = 'rescued') as rescued_at_s,
    min(t_sim) filter (where victim_status = 'lost')    as lost_at_s,
    min(target) filter (where victim_status = 'found')  as found_by
  from status
  group by 1, 2
),

words as (
  select run_id, agent_id as victim_id, count(*) as utterances
  from staging.events
  where agent_role = 'victim' and type = 'speak'
  group by 1, 2
)

select
  v.run_id,
  v.victim_id,
  coalesce(l.final_status, 'trapped')                              as final_status,
  t.found_at_s,
  t.found_by,
  t.rescued_at_s,
  case when l.final_status = 'rescued' then l.last_helper end      as rescued_by,
  t.lost_at_s,
  coalesce(w.utterances, 0)                                        as utterances
from victims v
left join last_status l using (run_id, victim_id)
left join times t using (run_id, victim_id)
left join words w using (run_id, victim_id)
order by v.run_id, v.victim_id
