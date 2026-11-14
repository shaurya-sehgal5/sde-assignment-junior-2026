# AI Usage Disclosure

I used ChatGPT as an AI-assisted development tool while working on Assignment B (Durable Campaign Dispatcher).

## How I used AI

- Discussed the assignment requirements and translated the workflow rules into implementation tasks.
- Used AI assistance to reason about the PostgreSQL-backed state machine, scheduling priorities, retry handling, callback handling, tenant concurrency, and phone-level locking.
- Used AI assistance while debugging Python imports, database configuration, SQLAlchemy operations, provider integration, webhook processing, and recovery behavior.
- Requested code suggestions and revisions for parts of the implementation, then integrated and adapted those changes in the project.
- Used AI to interpret test output, diagnose runtime issues, and plan verification steps.
- Used AI assistance to prepare technical documentation and submission instructions.

## What I did

I set up and ran the project in my local environment, configured PostgreSQL and the mock telephony provider, executed the dispatcher, inspected provider and database results, and ran the automated test suite.

The final local run processed 200 leads. The provider report showed 409 calls, zero provider violations, zero active calls, and 409 delivered webhooks. The reconciliation check reported zero active attempts. The test suite completed with 7 passing tests.

## Verification and limitations

AI-generated suggestions were not treated as proof of correctness. I ran the implementation locally and used the test suite, database state, provider report, and generated `final_state.csv` to check the result.

The successful full run used the mock provider with `--failure-scale 0`. A complete `kill -9` recovery test and evaluation with an unseen provider seed have not been independently demonstrated in this submission run. These remain important further validation steps.

I remain responsible for the submitted code, its behavior, and the accuracy of this disclosure.
