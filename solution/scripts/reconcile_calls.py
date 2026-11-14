import json

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.entities import CallAttempt, Lead, Campaign
from app.services.provider import provider, ProviderUnavailable
from app.services.webhooks import process_webhook


def main():
    with SessionLocal() as db:
        rows = db.execute(
            select(CallAttempt, Lead, Campaign)
            .join(
                Lead,
                (Lead.campaign_id == CallAttempt.campaign_id)
                & (Lead.lead_id == CallAttempt.lead_id),
            )
            .join(
                Campaign,
                Campaign.campaign_id == CallAttempt.campaign_id,
            )
            .where(CallAttempt.state == "active")
        ).all()

        active = [
            {
                "request_id": a.request_id,
                "call_sid": a.call_sid,
                "campaign_id": a.campaign_id,
                "lead_id": a.lead_id,
                "phone": l.phone,
                "tenant_id": c.tenant_id,
            }
            for a, l, c in rows
        ]

    print("Active calls to reconcile:", len(active))

    for item in active:
        try:
            record = provider.get_call(item["call_sid"])

            if not record:
                print("NOT FOUND:", item["lead_id"])
                continue

            state = record.get("state")
            print(f"{item['lead_id']}: provider state={state}")

            if state not in ("completed", "finished", "ended"):
                continue

            outcome = record.get("result") or record
            status = outcome.get("status")
            if not status:
                print("Missing outcome fields:", record)
                continue

            payload = {
                "event": "call.completed",
                "call_sid": item["call_sid"],
                "request_id": item["request_id"],
                "tenant_id": item["tenant_id"],
                "campaign_id": item["campaign_id"],
                "lead_id": item["lead_id"],
                "phone": item["phone"],
                "status": status,
                "disposition": outcome.get("disposition"),
                "callback_at": outcome.get("callback_at"),
                "started_at": outcome.get("started_at"),
                "ended_at": outcome.get("ended_at"),
                "duration_sec": outcome.get("duration_sec", 0),
            }

            raw_body = json.dumps(
                payload, separators=(",", ":")
            ).encode("utf-8")

            result = process_webhook(payload, raw_body)
            print("RECONCILED:", item["lead_id"], result)

        except ProviderUnavailable as exc:
            print("PROVIDER UNAVAILABLE:", exc)
        except Exception as exc:
            print("RECONCILIATION ERROR:", item["lead_id"], repr(exc))


if __name__ == "__main__":
    main()
