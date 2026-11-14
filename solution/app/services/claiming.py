
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import SessionLocal
from app.models.entities import (
    Tenant,
    Lead,
    CallAttempt,
    PhoneLock,
    PhoneSuppression,
)
from app.services.scheduling import (
    select_next_candidate,
    is_due,
    is_inside_calling_window,
    get_active_calls_by_tenant,
)


@dataclass(frozen=True)
class ClaimedCall:
    request_id: str
    call_number: int
    campaign_id: str
    lead_id: str
    phone: str
    customer_name: str
    tenant_id: str


def claim_next_call(now: datetime) -> ClaimedCall | None:
    """
    Atomically reserve one eligible lead.

    All dispatcher workers must use this function to claim calls.
    Tenant row locks serialize claims; the unique PhoneLock.phone
    constraint prevents duplicate phone reservations across tenants.
    """

    with SessionLocal() as db:
        with db.begin():

            # Serialize dispatchers by locking tenants in a consistent order.
            db.scalars(
                select(Tenant)
                .order_by(Tenant.tenant_id)
                .with_for_update()
            ).all()

            # Select the highest-priority eligible candidate.
            candidate = select_next_candidate(db, now)

            if candidate is None:
                return None

            # Lock the selected lead and re-check eligibility.
            lead = db.scalar(
                select(Lead)
                .where(
                    Lead.campaign_id == candidate.campaign.campaign_id,
                    Lead.lead_id == candidate.lead.lead_id,
                )
                .with_for_update()
            )

            if lead is None:
                return None

            if lead.state not in (
                "pending",
                "retry_wait",
                "callback_scheduled",
            ):
                return None

            if lead.attempts >= candidate.campaign.max_attempts:
                return None

            due, _, _ = is_due(lead, now)

            if not due:
                return None

            if not is_inside_calling_window(candidate.campaign, now):
                return None

            # Check global DND suppression again.
            suppressed = db.scalar(
                select(PhoneSuppression.phone)
                .where(PhoneSuppression.phone == lead.phone)
                .limit(1)
            )

            if suppressed:
                return None

            # Check tenant concurrency while tenant rows are locked.
            active_calls = get_active_calls_by_tenant(db)

            if (
                active_calls.get(candidate.tenant.tenant_id, 0)
                >= candidate.tenant.max_concurrent_calls
            ):
                return None

            # Generate a durable idempotency key.
            request_id = str(uuid4())
            attempt_number = lead.attempts + 1

            # Acquire the global phone lock.
            # The unique constraint prevents duplicate reservations.
            db.execute(
                pg_insert(PhoneLock)
                .values(
                    phone=lead.phone,
                    request_id=request_id,
                    acquired_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[PhoneLock.phone]
                )
            )

            # Verify that this worker owns the phone lock.
            lock_owner = db.scalar(
                select(PhoneLock.request_id)
                .where(PhoneLock.phone == lead.phone)
            )

            if lock_owner != request_id:
                return None

            # Persist the attempt before making the external API request.
            attempt = CallAttempt(
                campaign_id=lead.campaign_id,
                lead_id=lead.lead_id,
                attempt_number=attempt_number,
                request_id=request_id,
                state="prepared",
            )

            db.add(attempt)

            # A reservation is not yet an accepted provider attempt.
            # R4 counts only calls accepted by the provider.
            lead.state = "calling"

            db.flush()

            result = ClaimedCall(
                request_id=request_id,
                call_number=attempt_number,
                campaign_id=lead.campaign_id,
                lead_id=lead.lead_id,
                phone=lead.phone,
                customer_name=lead.customer_name,
                tenant_id=candidate.tenant.tenant_id,
            )

        # Transaction commits before returning.
        return result
