import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import SessionLocal
from app.models.entities import (
    CallAttempt,
    Campaign,
    Lead,
    PhoneLock,
    PhoneSuppression,
    WebhookEvent,
)

WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET", "whsec_au_assignment_local"
)


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        return False

    supplied = signature.removeprefix("sha256=").strip()
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, supplied)


def parse_datetime(value):
    if not value:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def process_webhook(payload: dict, raw_body: bytes):
    request_id = payload.get("request_id")
    if not request_id:
        raise ValueError("Missing request_id")

    fingerprint = hashlib.sha256(raw_body).hexdigest()

    with SessionLocal() as db:
        with db.begin():
            # Atomic insert makes simultaneous duplicate deliveries harmless.
            inserted_id = db.execute(
                pg_insert(WebhookEvent)
                .values(
                    fingerprint=fingerprint,
                    request_id=request_id,
                    payload=raw_body.decode("utf-8"),
                )
                .on_conflict_do_nothing(
                    index_elements=[WebhookEvent.fingerprint]
                )
                .returning(WebhookEvent.id)
            ).scalar_one_or_none()

            if inserted_id is None:
                return {"result": "duplicate"}

            attempt = db.scalar(
                select(CallAttempt)
                .where(CallAttempt.request_id == request_id)
                .with_for_update()
            )
            if attempt is None:
                raise LookupError("Unknown request_id")

            lead = db.scalar(
                select(Lead)
                .where(
                    Lead.campaign_id == attempt.campaign_id,
                    Lead.lead_id == attempt.lead_id,
                )
                .with_for_update()
            )
            if lead is None:
                raise LookupError("Lead not found")

            campaign = db.get(Campaign, attempt.campaign_id)
            if campaign is None:
                raise LookupError("Campaign not found")

            # The webhook proves that the provider accepted this attempt.
            # max() is safe if the POST response was persisted first.
            lead.attempts = max(lead.attempts, attempt.attempt_number)

            # A distinct delivery/payload for an already-finalized attempt
            # must not re-apply its business effects.
            if attempt.state == "completed":
                return {"result": "already_processed"}

            status = payload.get("status")
            disposition = payload.get("disposition")
            ended_at = parse_datetime(payload.get("ended_at"))
            started_at = parse_datetime(payload.get("started_at"))
            callback_at = parse_datetime(payload.get("callback_at"))

            attempt.call_sid = payload.get("call_sid") or attempt.call_sid
            attempt.state = "completed"
            attempt.status = status
            attempt.disposition = disposition
            attempt.started_at = started_at
            attempt.ended_at = ended_at
            attempt.callback_at = callback_at

            lead.last_status = status
            lead.last_disposition = disposition
            lead.next_attempt_at = None
            lead.callback_at = None

            # This call has ended; release its phone reservation.
            db.execute(
                PhoneLock.__table__.delete().where(
                    PhoneLock.request_id == request_id
                )
            )

            if disposition == "dnd":
                db.execute(
                    pg_insert(PhoneSuppression)
                    .values(phone=lead.phone, reason="dnd")
                    .on_conflict_do_nothing(
                        index_elements=[PhoneSuppression.phone]
                    )
                )

                # DND blocks every other unfinished lead using this phone.
                # The lead that actually received the DND disposition is
                # terminal/completed (R7 and R9 precedence).
                db.execute(
                    update(Lead)
                    .where(
                        Lead.phone == lead.phone,
                        Lead.state.in_([
                            "pending",
                            "calling",
                            "retry_wait",
                            "callback_scheduled",
                        ]),
                    )
                    .values(
                        state="dnd_blocked",
                        next_attempt_at=None,
                        callback_at=None,
                    )
                )
                lead.state = "completed"
                return {"result": "processed", "state": "completed"}

            if disposition in (
                "interested", "not_interested", "wrong_number"
            ):
                lead.state = "completed"
                return {"result": "processed", "state": "completed"}

            if disposition == "callback_requested":
                # The provider enforces the same three-call maximum before
                # considering another callback. A callback on attempt three
                # therefore ends as exhausted, not a permanently stuck job.
                if lead.attempts >= campaign.max_attempts:
                    lead.state = "exhausted"
                    return {"result": "processed", "state": "exhausted"}

                if callback_at is None:
                    callback_at = (
                        ended_at or datetime.now(timezone.utc)
                    ) + timedelta(minutes=60)
                    attempt.callback_at = callback_at

                lead.state = "callback_scheduled"
                lead.callback_at = callback_at
                return {
                    "result": "processed",
                    "state": "callback_scheduled",
                }

            if status in ("busy", "no_answer", "failed"):
                if lead.attempts >= campaign.max_attempts:
                    lead.state = "exhausted"
                else:
                    delay = 15 if status == "failed" else 60
                    base_time = ended_at or datetime.now(timezone.utc)
                    lead.state = "retry_wait"
                    lead.next_attempt_at = base_time + timedelta(
                        minutes=delay
                    )

                return {
                    "result": "processed",
                    "state": lead.state,
                    "next_attempt_at": (
                        lead.next_attempt_at.isoformat()
                        if lead.next_attempt_at else None
                    ),
                }

            # Any completed call without a disposition is terminal.
            lead.state = "completed"
            return {"result": "processed", "state": "completed"}
