from datetime import datetime

from sqlalchemy import select

from app.core.config import CALLBACK_URL
from app.db.database import SessionLocal
from app.models.entities import CallAttempt, Lead
from app.services.claiming import claim_next_call
from app.services.provider import (
    provider,
    ProviderError,
    ProviderUnavailable,
)


def persist_provider_acceptance(
    request_id: str,
    provider_response: dict,
) -> None:
    call_sid = provider_response.get("call_sid")
    if not call_sid:
        raise ProviderError(
            f"Provider response has no call_sid: {provider_response}"
        )

    with SessionLocal() as db:
        with db.begin():
            attempt = db.scalar(
                select(CallAttempt)
                .where(CallAttempt.request_id == request_id)
                .with_for_update()
            )
            if attempt is None:
                raise RuntimeError(
                    f"Missing database attempt for request_id={request_id}"
                )

            lead = db.scalar(
                select(Lead)
                .where(
                    Lead.campaign_id == attempt.campaign_id,
                    Lead.lead_id == attempt.lead_id,
                )
                .with_for_update()
            )
            if lead is None:
                raise RuntimeError(
                    f"Missing lead for request_id={request_id}"
                )

            if attempt.call_sid and attempt.call_sid != call_sid:
                raise RuntimeError(
                    f"Request {request_id} mapped to conflicting call SIDs"
                )

            attempt.call_sid = call_sid

            # Idempotently count this accepted call. A webhook may arrive
            # before the POST response and may already have completed it.
            lead.attempts = max(lead.attempts, attempt.attempt_number)

            # Never reopen an attempt finalized by an early webhook.
            if attempt.state != "completed":
                attempt.state = "active"


def submit_claimed_call(claimed) -> dict:
    payload = {
        "request_id": claimed.request_id,
        "campaign_id": claimed.campaign_id,
        "lead_id": claimed.lead_id,
        "phone": claimed.phone,
        "callback_url": CALLBACK_URL,
    }

    last_error = None

    for _ in range(3):
        try:
            response = provider.create_call(payload)
            persist_provider_acceptance(claimed.request_id, response)
            return {
                "result": "accepted",
                "request_id": claimed.request_id,
                "call_sid": response["call_sid"],
                "lead_id": claimed.lead_id,
            }

        except ProviderUnavailable as exc:
            last_error = exc

            # A timeout may mean the provider accepted the call. Always
            # resolve the idempotency key before attempting another POST.
            try:
                existing = provider.find_by_request_id(claimed.request_id)
            except ProviderUnavailable:
                raise

            if existing is not None:
                persist_provider_acceptance(claimed.request_id, existing)
                return {
                    "result": "recovered",
                    "request_id": claimed.request_id,
                    "call_sid": existing["call_sid"],
                    "lead_id": claimed.lead_id,
                }

            # A 404 means no call is currently recorded. Re-POSTing with
            # the same request_id is safe because the provider is idempotent.

        except ProviderError:
            # Preserve the prepared attempt and lock for inspection/recovery.
            raise

    raise ProviderUnavailable(
        f"Could not submit request {claimed.request_id} after 3 attempts: "
        f"{last_error}"
    )


def _provider_now() -> datetime:
    return datetime.fromisoformat(provider.get_clock()["sim_now"])


def dispatch_once(now: datetime | None = None) -> dict | None:
    # Prefer a fresh provider clock; never use the machine clock.
    if now is None:
        now = _provider_now()

    claimed = claim_next_call(now)
    if claimed is None:
        return None

    return submit_claimed_call(claimed)


def dispatch_batch(
    now: datetime | None = None,
    limit: int = 10,
) -> list[dict]:
    results = []

    for _ in range(limit):
        try:
            # Critical: the provider runs at accelerated simulated time.
            # Refresh before EVERY claim rather than reusing one batch time.
            current_sim_time = _provider_now()
            result = dispatch_once(current_sim_time)
        except ProviderUnavailable as exc:
            results.append({
                "result": "pending_recovery",
                "error": str(exc),
            })
            break

        if result is None:
            break

        results.append(result)

    return results
