import time

from app.db.database import SessionLocal
from app.models.entities import Lead
from app.services.dispatcher import dispatch_batch
from app.services.reconciliation import (
    recover_prepared_attempts,
    reconcile_active_calls,
)


FINAL_STATES = {"completed", "exhausted", "dnd_blocked"}


def main():
    print("Starting durable campaign dispatcher...")

    while True:
        try:
            # Recover crashes/ambiguous provider responses before new work.
            recover_prepared_attempts()
            reconcile_active_calls()

            results = dispatch_batch(limit=10)
            for result in results:
                print("DISPATCH:", result)

            with SessionLocal() as db:
                counts = {}
                for lead in db.query(Lead).all():
                    counts[lead.state] = counts.get(lead.state, 0) + 1

            print("LEADS:", counts)
            terminal = sum(counts.get(state, 0) for state in FINAL_STATES)

            if terminal == 200:
                print("ALL 200 LEADS TERMINAL")
                from scripts.export_final_state import export_final_state
                try:
                    export_final_state()
                except Exception as exc:
                    print("FINAL VERIFICATION FAILED:", repr(exc))
                break

        except KeyboardInterrupt:
            print("Dispatcher stopped.")
            break
        except Exception as exc:
            print("DISPATCH ERROR:", repr(exc))

        time.sleep(0.5)


if __name__ == "__main__":
    main()
