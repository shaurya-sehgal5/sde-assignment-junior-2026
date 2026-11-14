from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.entities import CallAttempt, Lead, Campaign
from app.services.claiming import ClaimedCall
from app.services.dispatcher import submit_claimed_call
from app.services.provider import ProviderUnavailable


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
            .where(CallAttempt.state == "prepared")
        ).all()

        pending = [
            ClaimedCall(
                request_id=attempt.request_id,
                call_number=attempt.attempt_number,
                campaign_id=attempt.campaign_id,
                lead_id=attempt.lead_id,
                phone=lead.phone,
                customer_name=lead.customer_name,
                tenant_id=campaign.tenant_id,
            )
            for attempt, lead, campaign in rows
        ]

    print("Prepared attempts found:", len(pending))

    for claimed in pending:
        print("\nRecovering:", claimed.lead_id, claimed.request_id)

        try:
            result = submit_claimed_call(claimed)
            print("RESULT:", result)
        except ProviderUnavailable as exc:
            print("PENDING:", exc)
        except Exception as exc:
            print("ERROR:", repr(exc))


if __name__ == "__main__":
    main()
