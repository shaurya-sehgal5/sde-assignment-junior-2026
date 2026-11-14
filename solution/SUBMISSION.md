# Submission

## Candidate
- **Name:** Shaurya Sehgal
- **Assignment chosen:** B (Workflow)
- **Time spent:** [Enter your honest estimate]

## How to run

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start PostgreSQL
Start the PostgreSQL service using the supplied Docker Compose configuration.

Set the database connection:
```bash
export DATABASE_URL='postgresql+psycopg://au_user:au_local_password@127.0.0.1:5433/campaign_dispatcher'
```

### 3. Initialize and seed
```bash
cd solution
export PYTHONPATH="$PWD"

python -m scripts.init_db
python -m scripts.seed_data
```

### 4. Start the mock telephony provider
In a separate terminal:
```bash
cd assignment-b-workflow
python -m mock_telephony --speed 600 --seed 7 --failure-scale 0 --port 8099
```

### 5. Start the API
In another terminal:
```bash
cd solution
export PYTHONPATH="$PWD"
uvicorn app.main:app --host 0.0.0.0 --port 8200
```

### 6. Start the dispatcher
```bash
cd solution
export PYTHONPATH="$PWD"
python -m scripts.run_dispatcher
```

### 7. Run tests
```bash
cd solution
export PYTHONPATH="$PWD"
python -m compileall -q app scripts
python -m pytest tests/ -q
```

## Design

The solution uses a PostgreSQL-backed state machine with a Python dispatcher and FastAPI webhook receiver.

PostgreSQL stores tenants, campaigns, leads, call attempts, webhook events, phone locks and phone suppressions.

The dispatcher selects eligible leads according to campaign calling windows, regulatory restrictions, tenant concurrency, callback priority and retry scheduling.

Each call attempt receives a persistent request ID before contacting the provider. Provider acceptance is persisted against that request ID. This allows recovery to query the provider and safely reuse the same idempotency key after an ambiguous outcome.

Phone locks prevent simultaneous calls to the same phone number. Tenant-level active-call checks enforce concurrency across campaigns.

### Lead lifecycle

```text
                 ┌──────────────┐
                 │   PENDING    │
                 └──────┬───────┘
                        │
                 Eligible to call
                        │
                 ┌──────▼───────┐
                 │   CALLING    │
                 └──────┬───────┘
                        │
                  Call result
                        │
          ┌─────────────┼────────────────┐
          │             │                │
     Terminal       Retryable         Callback
    disposition      outcome          requested
          │             │                │
          ▼             ▼                ▼
      COMPLETED     RETRY_WAIT    CALLBACK_SCHEDULED
                        │                │
                        └───────┬────────┘
                                │
                         Eligible again
                                │
                                ▼
                             CALLING

     Maximum attempts reached without terminal disposition
                                │
                                ▼
                            EXHAUSTED

     Global DND suppression
                                │
                                ▼
                           DND_BLOCKED
```

### At-most-once dialling

- A persistent request ID is created for each attempt.
- Database transactions and unique constraints protect attempt and phone-lock creation.
- The same request ID is reused when resolving ambiguous provider outcomes.
- Provider lookup occurs before resubmitting a prepared attempt.
- Phone locks prevent simultaneous calls to the same phone number.
- Webhook fingerprints prevent duplicate event processing.

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| PostgreSQL-backed state machine | Durable state and transactional consistency | SQLite |
| Persistent provider request IDs | Resolve ambiguous 504 responses safely | Generate a new ID per retry |
| Separate webhook receiver | Process asynchronous provider results | Polling only |
| Persistent phone locks | Prevent concurrent calls to one phone | In-memory locking |
| Provider clock for scheduling | Business rules use simulated time | System clock |
| Reconciliation of active calls | Recover missing webhooks | Depend only on webhook delivery |

## Failure modes considered

- Duplicate webhook delivery: handled using event fingerprints and idempotent processing.
- Invalid webhook signatures: rejected using HMAC-SHA256 verification.
- Lost webhooks: recovered by querying provider call records.
- Ambiguous provider responses: resolved using the persistent request ID.
- Process crashes: prepared attempts and active calls can be recovered from persistent state.
- Duplicate phone calls: prevented using phone locks.
- Calling-window violations: checked before dispatch and during prepared-attempt recovery.
- DND: persisted globally by phone number.
- Provider unavailability: handled through provider error handling and later recovery.

Known limitations:
- A complete crash-and-restart acceptance test against the original provider remains to be demonstrated.
- Injected provider failures and unseen-seed evaluation remain to be independently validated.

## Testing

- Python compilation completed successfully.
- Automated tests: 7 passed.
- Full local run processed 200 leads.
- Database reconciliation reported zero active attempts.
- Provider reported zero violations and zero active calls.

## Results

Full local run:

| Metric | Result |
|---|---:|
| Total leads | 200 |
| Completed | 138 |
| Exhausted | 61 |
| DND blocked | 1 |
| Provider calls | 409 |
| Provider violations | 0 |
| Active calls | 0 |
| Webhooks delivered | 409 |
| Maximum Zen Retail concurrency | 3 |
| Maximum Acme Insurance concurrency | 3 |
| Automated tests | 7 passed |

`final_state.csv` was generated with all 200 leads in terminal states.

## If I had another day

1. Run crash-and-restart tests at multiple points during dispatch.
2. Test with injected 503 and ambiguous 504 failures.
3. Test using multiple unseen provider seeds.
4. Improve callback lateness and scheduling efficiency.
5. Add structured observability and per-campaign progress reporting.
