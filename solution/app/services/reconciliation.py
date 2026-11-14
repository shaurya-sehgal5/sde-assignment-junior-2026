
import json
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.entities import CallAttempt, Lead, Campaign
from app.services.claiming import ClaimedCall
from app.services.dispatcher import (
    persist_provider_acceptance,
    submit_claimed_call,
)
from app.services.provider import provider, ProviderError, ProviderUnavailable
from app.services.scheduling import is_inside_calling_window
from app.services.webhooks import process_webhook


# Avoid starting a recovery submission immediately before a campaign closes.
# The provider clock is accelerated, so leave a small safety margin.
RECOVERY_CLOSE_BUFFER_MINUTES = 2


def recover_prepared_attempts() -> int:
    """
    Recover the crash window between persisting a prepared attempt and
    persisting the provider's acceptance response.

    Existing provider calls are recovered regardless of current calling
    hours. New submissions are deferred until the campaign window is open
    and has sufficient time remaining.
    """
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
            (
                ClaimedCall(
                    request_id=attempt.request_id,
                    call_number=attempt.attempt_number,
                    campaign_id=attempt.campaign_id,
                    lead_id=attempt.lead_id,
                    phone=lead.phone,
                    customer_name=lead.customer_name,
                    tenant_id=campaign.tenant_id,
                ),
                campaign,
            )
            for attempt, lead, campaign in rows
        ]

    recovered = 0

    for claimed, campaign in pending:
        try:
            # First resolve whether the provider already accepted this call.
            existing = provider.find_by_request_id(claimed.request_id)

            if existing is not None:
                persist_provider_acceptance(claimed.request_id, existing)
                recovered += 1
                print("RECOVERED ACCEPTANCE:", claimed.lead_id)
                continue

            # No existing provider call: check the live simulated clock
            # before making a new submission.
            clock = provider.get_clock()
            now = datetime.fromisoformat(clock["sim_now"])

            safe_submission_time = now + timedelta(
                minutes=RECOVERY_CLOSE_BUFFER_MINUTES
            )

            if not is_inside_calling_window(campaign, safe_submission_time):
                print(
                    "PREPARED RECOVERY DEFERRED:",
                    claimed.lead_id,
                    "campaign window closed or too close to closing time",
                    "sim_now=",
                    now.isoformat(),
                )
                continue

            # Re-submit the exact same idempotency key.
            submit_claimed_call(claimed)
            recovered += 1
            print("RESUBMITTED PREPARED:", claimed.lead_id)

        except (ProviderUnavailable, ProviderError) as exc:
            print("PREPARED RECOVERY DEFERRED:", claimed.lead_id, repr(exc))
        except Exception as exc:
            print("PREPARED RECOVERY ERROR:", claimed.lead_id, repr(exc))

    return recovered


def reconcile_active_calls() -> int:
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

        calls = [
            {
                "request_id": attempt.request_id,
                "call_sid": attempt.call_sid,
                "campaign_id": attempt.campaign_id,
                "lead_id": attempt.lead_id,
                "phone": lead.phone,
                "tenant_id": campaign.tenant_id,
            }
            for attempt, lead, campaign in rows
        ]

    reconciled = 0

    for call in calls:
        try:
            record = provider.get_call(call["call_sid"])

            if not record or record.get("state") not in (
                "ended",
                "completed",
                "finished",
            ):
                continue

            outcome = record.get("result")
            if not outcome or not outcome.get("status"):
                continue

            payload = {
                "event": "call.completed",
                "call_sid": call["call_sid"],
                "request_id": call["request_id"],
                "tenant_id": call["tenant_id"],
                "campaign_id": call["campaign_id"],
                "lead_id": call["lead_id"],
                "phone": outcome.get("phone", call["phone"]),
                "status": outcome["status"],
                "disposition": outcome.get("disposition"),
                "callback_at": outcome.get("callback_at"),
                "started_at": outcome.get("started_at"),
                "ended_at": outcome.get("ended_at"),
                "duration_sec": outcome.get("duration_sec", 0),
            }

            raw = json.dumps(
                payload,
                separators=(",", ":"),
            ).encode()

            result = process_webhook(payload, raw)

            if result.get("result") == "processed":
                reconciled += 1
                print("RECONCILED:", call["lead_id"], result)

        except Exception as exc:
            print("RECONCILIATION ERROR:", call["lead_id"], repr(exc))

    return reconciled
