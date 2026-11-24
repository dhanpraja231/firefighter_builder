# infra

Everything runs locally for the hackathon. An AWS version (RDS, ECS, ALB) was built and then torn down in favor
of the local setup below.

## Run it

```sh
# 1. Postgres
docker run -d --name ff-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=firefighter -p 5433:5432 postgres:17

# 2. Bruin CLI and its local config
curl -LsSf https://getbruin.com/install/cli | sh
cp .bruin.example.yml .bruin.yml

# 3. Runware key for the agents (gitignored)
echo 'RUNWARE_API_KEY=...' > .env

# 4. Event API + dashboard. It creates the tables and runs Bruin every 2 minutes and when a run ends.
uv run --python 3.12 --with-requirements api/requirements.txt uvicorn app:app --app-dir api --port 8010
```

Dashboard: http://localhost:8010

## Send runs

```sh
export FF_API_URL=http://localhost:8010
python3 agents/orchestrator.py --seed 5 --no-sql --llm --api   # one Runware-backed run
python3 agents/server.py                                        # web Play button sends runs to the API
```

Settings: `DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5433/firefighter`), `API_TOKEN`
(off by default locally), `BRUIN_EVERY_SECONDS` (default 120, 0 turns the schedule off), `FF_LLM_MODEL`
(default `google:gemma@4-31b`).
