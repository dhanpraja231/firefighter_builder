/* @bruin

name: mart.decision_log
type: pg.sql
description: >
  What each agent decided and why. One row per decide, act and request_approval event,
  with the human's approval outcome attached to risky requests and the acts that followed them.

materialization:
  type: table

depends:
  - staging.events

columns:
  - name: run_id
    type: uuid
    checks:
      - name: not_null
  - name: seq
    type: integer
    checks:
      - name: not_null
  - name: agent_id
    type: varchar
    checks:
      - name: not_null
  - name: approval_decision
    type: varchar
    checks:
      - name: accepted_values
        value: [approve, deny, timeout_default, pending]

@bruin */

with approvals as (
  select
    run_id,
    approval_of_seq as request_seq,
    action          as decision,
    received_at     as decided_at
  from staging.events
  where type = 'approval'
),

decisions as (
  select *
  from staging.events
  where type in ('decide', 'act', 'request_approval')
)

select
  d.run_id,
  d.seq,
  d.t_sim,
  d.agent_id,
  d.agent_role,
  d.type,
  d.action,
  d.target,
  d.actor,
  d.reasoning,
  d.confidence,
  d.risky or d.type = 'request_approval'                                   as needs_approval,
  case
    when d.type = 'request_approval' then coalesce(a.decision, 'pending')
    when d.risky then a.decision
  end                                                                      as approval_decision,
  case
    when d.type = 'request_approval'
      then round(extract(epoch from (a.decided_at - d.received_at))::numeric, 1)
  end                                                                      as approval_wait_s,
  d.model,
  d.latency_ms
from decisions d
left join approvals a
  on a.run_id = d.run_id
 and a.request_seq = case when d.type = 'request_approval' then d.seq else d.approval_of_seq end
order by d.run_id, d.seq
