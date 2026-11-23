/* @bruin

name: staging.events
type: pg.sql
description: Typed view of raw.events with payload fields pulled out of jsonb. One row per event.

materialization:
  type: table

columns:
  - name: run_id
    type: uuid
    checks:
      - name: not_null
  - name: seq
    type: integer
    checks:
      - name: not_null
      - name: positive
  - name: agent_id
    type: varchar
    checks:
      - name: not_null
  - name: agent_role
    type: varchar
    checks:
      - name: not_null
      - name: accepted_values
        value: [scout, suppression, rescue, commander, victim, director, human]
  - name: type
    type: varchar
    checks:
      - name: not_null
      - name: accepted_values
        value: [move, speak, decide, act, request_approval, approval, world_event, status]
  - name: victim_status
    type: varchar
    checks:
      - name: accepted_values
        value: [trapped, found, moving, rescued, lost]

custom_checks:
  - name: seq is gap-free per run and starts at 1
    value: 0
    blocking: true
    query: |
      select count(*) from (
        select run_id from staging.events
        group by run_id
        having min(seq) <> 1 or max(seq) <> count(*)
      ) bad_runs
  - name: every risky act has an approved request
    value: 0
    blocking: true
    query: |
      select count(*)
      from staging.events a
      where a.type = 'act' and a.risky
        and not exists (
          select 1 from staging.events ap
          where ap.run_id = a.run_id
            and ap.type = 'approval'
            and ap.action = 'approve'
            and ap.approval_of_seq = a.approval_of_seq
        )
  - name: LLM decisions have reasoning
    value: 0
    blocking: false
    query: |
      select count(*) from staging.events
      where type in ('decide', 'act', 'request_approval')
        and model is not null
        and coalesce(trim(reasoning), '') = ''

@bruin */

select
  e.run_id,
  e.seq,
  e.t_sim,
  e.agent_id,
  e.agent_role,
  e.type,
  e.payload ->> 'action'                                  as action,
  e.payload ->> 'target'                                  as target,
  e.payload ->> 'actor'                                   as actor,
  coalesce((e.payload ->> 'risky')::boolean, false)       as risky,
  (e.payload ->> 'approval_of_seq')::int                  as approval_of_seq,
  e.payload ->> 'utterance'                               as utterance,
  e.payload ->> 'victim_status'                           as victim_status,
  (e.payload -> 'position' ->> 'floor')::int              as floor,
  (e.payload -> 'position' ->> 'x')::real                 as x,
  (e.payload -> 'position' ->> 'y')::real                 as y,
  (e.payload -> 'position' ->> 'z')::real                 as z,
  e.payload -> 'world'                                    as world,
  e.reasoning,
  e.confidence,
  e.model,
  e.latency_ms,
  e.tokens_in,
  e.tokens_out,
  e.received_at
from raw.events e
