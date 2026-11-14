# Assignment B — Durable Campaign Dispatcher

This directory contains the supplied Assignment B fixtures and mock telephony provider. The dispatcher implementation is in `../solution`.

> Keep the supplied `README.md` and `mock_telephony/` files from the assignment unchanged. This supplementary guide documents how to run the implementation.

## Architecture

The implementation uses:

- PostgreSQL for durable workflow state.
- FastAPI for the telephony webhook endpoint.
- A Python dispatcher for selecting and submitting eligible leads.
- The supplied mock telephony provider for call creation and call-result webhooks.
- Database-backed call attempts, phone locks, webhook-event deduplication, and reconciliation.

## Prerequisites

- Python 3.10 or newer (the project was tested in the submitted environment with Python 3.14).
- Docker Engine and Docker Compose.
- The repository's root `requirements.txt`.

Run all commands from the repository root unless a command explicitly changes directory.

## 1. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

Set the database URL in the terminal that will run the application:

```bash
export DATABASE_URL='postgresql+psycopg://au_user:au_local_password@127.0.0.1:5433/campaign_dispatcher'
```

PowerShell equivalent:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://au_user:au_local_password@127.0.0.1:5433/campaign_dispatcher"
```

## 3. Initialize and seed the database

```bash
cd solution
export PYTHONPATH="$PWD"
python -m scripts.init_db
python -m scripts.seed_data
```

The supplied fixture set contains 2 tenants, 3 campaigns, and 200 leads.

## 4. Start the mock telephony provider

Open a separate terminal, activate the same repository `.venv`, and run:

```bash
cd assignment-b-workflow
python -m mock_telephony --speed 600 --seed 7 --failure-scale 0 --port 8099
```

Keep this process running while the API and dispatcher are running. The provider uses simulated time; business scheduling must use the provider clock, not the computer's wall clock.

The `--failure-scale 0` setting is useful for a deterministic local baseline run. It disables injected provider failures; it does not replace testing failure handling.

## 5. Start the webhook API

Open another terminal:

```bash
cd solution
source ../.venv/bin/activate
export DATABASE_URL='postgresql+psycopg://au_user:au_local_password@127.0.0.1:5433/campaign_dispatcher'
export PYTHONPATH="$PWD"
uvicorn app.main:app --host 0.0.0.0 --port 8200
```

Keep the API running so the provider can deliver call-result webhooks.

## 6. Run the dispatcher

Open another terminal:

```bash
cd solution
source ../.venv/bin/activate
export DATABASE_URL='postgresql+psycopg://au_user:au_local_password@127.0.0.1:5433/campaign_dispatcher'
export PYTHONPATH="$PWD"
python -m scripts.run_dispatcher
```

The dispatcher processes leads until they reach terminal states and runs final-state export/verification as implemented by the project.

Do not restart the mock provider in the middle of a run: its simulated clock and in-memory call records belong to that provider process.

## 7. Run tests

From `solution/`:

```bash
export PYTHONPATH="$PWD"
python -m compileall -q app scripts
python -m pytest tests/ -q
```

The submitted test run completed with 7 passing tests.

## 8. Inspect results

Provider report:

```bash
curl -s http://127.0.0.1:8099/admin/report
```

Provider lead state:

```bash
curl -s http://127.0.0.1:8099/admin/leads
```

Database reconciliation:

```bash
cd solution
export PYTHONPATH="$PWD"
python -m scripts.check_reconciliation
```

The full local baseline run recorded:

- 200 leads: 138 completed, 61 exhausted, 1 DND-blocked.
- 409 provider calls.
- 0 provider violations.
- 0 active provider calls.
- 409 delivered webhooks.
- 0 active database attempts after reconciliation.
- `final_state.csv` generated with 200 terminal leads.

The baseline run used `--failure-scale 0`. Crash/restart testing with `kill -9`, injected failures, and unseen provider seeds should be performed separately before claiming those scenarios have been fully validated.

## Configuration and safety

- Do not commit `.env` files, passwords, database dumps, local backups, or virtual environments.
- The database URL above uses the local development credentials configured in the supplied Compose file. Change them for any non-local deployment.
- Keep the supplied mock provider implementation unchanged.
