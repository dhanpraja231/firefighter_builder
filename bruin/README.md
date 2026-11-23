# bruin

Bruin pipeline that turns `raw.events` (written by the API) into the tables behind the decision log,
agent metrics, victim outcomes and the run comparison. See SPEC.md section 1.4.

| Asset | What it holds |
| --- | --- |
| `staging.events` | Typed copy of `raw.events` with payload fields as columns |
| `mart.decision_log` | One row per decision with reasoning and the human's approval outcome |
| `mart.agent_metrics` | Per agent: decisions, LLM latency, tokens, approvals |
| `mart.victim_outcomes` | Per victim: found, rescued or lost, and by whom |
| `mart.run_summary` | Per run: twists, victims saved, approvals, ending |

The blocking check on `staging.events` stops the marts from updating if a robot did a risky action
without an approved request.

## Run locally

```sh
curl -LsSf https://getbruin.com/install/cli | sh
docker run -d --name ff-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=firefighter -p 5433:5432 postgres:17
cp .bruin.example.yml .bruin.yml            # from the repo root

export PGPASSWORD=postgres DB=postgresql://postgres@localhost:5433/firefighter
psql "$DB" -f db/schema.sql
for s in 1 2 3; do python3 db/fake_run.py --seed $s | psql "$DB" -q; done

bruin validate bruin/
bruin run bruin/
psql "$DB" -c "select * from mart.run_summary"
```

## Run the container

The image is what ECS runs. Against the local database:

```sh
docker build -t firefighter-bruin bruin/
docker run --rm -e PGHOST=host.docker.internal -e PGPORT=5433 -e PGSSLMODE=disable \
  -e PGUSER=postgres -e PGPASSWORD=postgres firefighter-bruin
```
