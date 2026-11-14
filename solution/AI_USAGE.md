# AI Usage

AI assistance was used during development to:

- Review the dispatcher state machine and compare its behavior with the assignment's R1–R9 requirements.
- Diagnose stale simulated-clock reuse in batched dispatching.
- Review accepted-attempt accounting, callback exhaustion, DND final-state precedence, webhook idempotency, and crash recovery.
- Draft scheduling tests, the final-state export/verification script, and this design documentation.

All generated changes should be reviewed and run locally against the supplied mock provider. The provider's `/admin/report` and `/admin/leads` endpoints, plus the verified `final_state.csv`, are the acceptance checks; AI-generated code is not treated as proof of correctness.
