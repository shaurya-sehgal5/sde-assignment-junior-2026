# Durable Campaign Dispatcher

## Setup

From the repository root in WSL:

```bash
cd /mnt/d/sde-assignment-junior-2026/solution
source ../.venv/bin/activate
pip install -r requirements.txt
```

Create your local environment file if you do not already have one:

```bash
cp .env.example .env
```

Edit `DATABASE_URL` if your PostgreSQL port or credentials differ. Do not commit `.env` or local credentials.

## One-time clean run

Stop any old dispatcher, API, and mock-provider processes. Restarting the mock provider resets its in-memory call history. Reset the application database at the same time:

```bash
cd /mnt/d/sde-assignment-junior-2026/solution
source ../.venv/bin/activate
export PYTHONPATH="$PWD"
python -m scripts.reset_db
python -m scripts.init_db
python -m scripts.seed_data
```

## Start three terminals

**Terminal 1 — mock provider** (run from repository root):

```bash
cd /mnt/d/sde-assignment-junior-2026/assignment-b-workflow
source ../.venv/bin/activate
python -m mock_telephony --speed 600 --seed 7
```

**Terminal 2 — webhook API:**

```bash
cd /mnt/d/sde-assignment-junior-2026/solution
source ../.venv/bin/activate
export PYTHONPATH="$PWD"
uvicorn app.main:app --host 0.0.0.0 --port 8200
```

**Terminal 3 — dispatcher:**

```bash
cd /mnt/d/sde-assignment-junior-2026/solution
source ../.venv/bin/activate
export PYTHONPATH="$PWD"
python -m scripts.run_dispatcher
```

Keep the provider and API running until the dispatcher prints `ALL 200 LEADS TERMINAL` and `final_state.csv` has been written.

## Verify

```bash
cd /mnt/d/sde-assignment-junior-2026/solution
source ../.venv/bin/activate
export PYTHONPATH="$PWD"
python -m pytest -q
curl -s http://127.0.0.1:8099/admin/report
python -m scripts.export_final_state
```

The final report must show `violation_count: 0`. The export script checks all 200 local rows against `/admin/leads` before writing the CSV.

## Restart recovery

If the dispatcher process is killed, leave the provider and API running and restart only the dispatcher using Terminal 3's command. Prepared requests and active calls are recovered using their durable request IDs and provider lookup endpoints.
