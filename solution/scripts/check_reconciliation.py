from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.entities import CallAttempt
from app.services.provider import provider, ProviderUnavailable


def main():
    with SessionLocal() as db:
        attempts = db.scalars(
            select(CallAttempt).where(CallAttempt.state == "active")
        ).all()

        pending = [
            (a.request_id, a.lead_id, a.call_sid)
            for a in attempts
        ]

    print("Active attempts:", len(pending))

    for request_id, lead_id, call_sid in pending:
        print(f"\nLead: {lead_id}")
        print("Request ID:", request_id)

        try:
            result = provider.find_by_request_id(request_id)
            print("Provider result:", result)

            if result and result.get("call_sid"):
                call = provider.get_call(result["call_sid"])
                print("Call details:", call)
        except ProviderUnavailable as exc:
            print("Provider unavailable:", exc)
        except Exception as exc:
            print("ERROR:", repr(exc))


if __name__ == "__main__":
    main()
