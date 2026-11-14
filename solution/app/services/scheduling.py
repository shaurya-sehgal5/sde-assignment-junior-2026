
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Lead,
    Campaign,
    Tenant,
    CallAttempt,
    PhoneLock,
    PhoneSuppression,
)


REGULATORY_START = time(9, 0)
REGULATORY_END = time(21, 0)

DAY_NAMES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


@dataclass(frozen=True)
class ScheduledCandidate:
    lead: Lead
    campaign: Campaign
    tenant: Tenant
    priority: int
    scheduled_at: datetime | None


def parse_allowed_days(value: str) -> set[int]:
    """
    Supports:
      Mon,Tue,Wed
      Monday,Tuesday,Wednesday
      Mon-Sat
      Mon-Fri
      0,1,2,3,4
    """
    if not value:
        return set(range(7))

    tokens = [
        token.strip().lower()
        for token in value.replace(";", ",").split(",")
        if token.strip()
    ]

    allowed = set()

    for token in tokens:
        if "-" in token:
            start_name, end_name = [
                part.strip().lower() for part in token.split("-", 1)
            ]

            if start_name not in DAY_NAMES or end_name not in DAY_NAMES:
                raise ValueError(f"Invalid campaign day range: {token}")

            start_day = DAY_NAMES[start_name]
            end_day = DAY_NAMES[end_name]

            day = start_day
            while True:
                allowed.add(day)
                if day == end_day:
                    break
                day = (day + 1) % 7

        elif token.isdigit():
            day = int(token)
            if not 0 <= day <= 6:
                raise ValueError(f"Invalid weekday number: {token}")
            allowed.add(day)

        elif token in DAY_NAMES:
            allowed.add(DAY_NAMES[token])

        else:
            raise ValueError(f"Unknown campaign weekday: {token}")

    return allowed


def normalize_now(now: datetime, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)

    if now.tzinfo is None:
        return now.replace(tzinfo=zone)

    return now.astimezone(zone)


def is_inside_calling_window(
    campaign: Campaign,
    now: datetime,
) -> bool:
    local_now = normalize_now(now, campaign.timezone)

    # Global regulatory window: 09:00 to 21:00 IST.
    regulatory_now = local_now.astimezone(ZoneInfo("Asia/Kolkata"))

    if not (
        REGULATORY_START
        <= regulatory_now.time().replace(tzinfo=None)
        < REGULATORY_END
    ):
        return False

    # Campaign-specific weekday and time window.
    allowed_days = parse_allowed_days(campaign.window_days)

    if local_now.weekday() not in allowed_days:
        return False

    local_time = local_now.time().replace(tzinfo=None)

    return campaign.window_start <= local_time < campaign.window_end


def next_eligible_time(
    campaign: Campaign,
    not_before: datetime,
) -> datetime:
    """
    Return the next instant at or after `not_before` that falls inside both
    the campaign window and the 09:00–21:00 IST regulatory window.
    """
    zone = ZoneInfo(campaign.timezone)
    local_start = normalize_now(not_before, campaign.timezone)
    allowed_days = parse_allowed_days(campaign.window_days)
    regulatory_zone = ZoneInfo("Asia/Kolkata")

    for offset in range(0, 15):
        day = (local_start.date() + timedelta(days=offset))
        if day.weekday() not in allowed_days:
            continue

        campaign_open = datetime.combine(
            day, campaign.window_start, tzinfo=zone
        )
        campaign_close = datetime.combine(
            day, campaign.window_end, tzinfo=zone
        )
        regulatory_open = datetime.combine(
            day, REGULATORY_START, tzinfo=regulatory_zone
        ).astimezone(zone)
        regulatory_close = datetime.combine(
            day, REGULATORY_END, tzinfo=regulatory_zone
        ).astimezone(zone)

        candidate = max(local_start, campaign_open, regulatory_open)
        close = min(campaign_close, regulatory_close)

        if candidate < close:
            return candidate

    raise ValueError(
        f"No eligible calling window found in the next 14 days for "
        f"{campaign.campaign_id}"
    )


def is_due(lead: Lead, now: datetime) -> tuple[bool, int, datetime | None]:
    """
    Priority:
      0 = callback
      1 = retry
      2 = fresh lead
    """
    if lead.state == "callback_scheduled":
        if lead.callback_at is None:
            return False, 0, None

        return lead.callback_at <= now, 0, lead.callback_at

    if lead.state == "retry_wait":
        if lead.next_attempt_at is None:
            return False, 1, None

        return lead.next_attempt_at <= now, 1, lead.next_attempt_at

    if lead.state == "pending":
        return True, 2, lead.created_at

    return False, 99, None


def get_active_calls_by_tenant(db: Session) -> dict[str, int]:
    """
    PhoneLock represents an active call reservation.

    Counting locks rather than historical attempts ensures completed calls
    do not consume concurrency capacity.
    """
    rows = db.execute(
        select(
            Campaign.tenant_id,
            func.count(PhoneLock.phone),
        )
        .select_from(PhoneLock)
        .join(
            CallAttempt,
            PhoneLock.request_id == CallAttempt.request_id,
        )
        .join(
            Campaign,
            CallAttempt.campaign_id == Campaign.campaign_id,
        )
        .group_by(Campaign.tenant_id)
    ).all()

    return {
        tenant_id: count
        for tenant_id, count in rows
    }


def select_next_candidate(
    db: Session,
    now: datetime,
) -> ScheduledCandidate | None:
    """
    Find the highest-priority currently eligible lead.

    This function only selects. Atomic claiming and lock acquisition
    must happen in the dispatch transaction before a provider call.
    """
    rows = db.execute(
        select(Lead, Campaign, Tenant)
        .join(
            Campaign,
            Lead.campaign_id == Campaign.campaign_id,
        )
        .join(
            Tenant,
            Campaign.tenant_id == Tenant.tenant_id,
        )
        .where(
            Lead.state.in_([
                "callback_scheduled",
                "retry_wait",
                "pending",
            ])
        )
    ).all()

    active_calls = get_active_calls_by_tenant(db)
    candidates = []

    for lead, campaign, tenant in rows:
        if lead.attempts >= campaign.max_attempts:
            continue

        due, priority, scheduled_at = is_due(lead, now)

        if not due:
            continue

        if not is_inside_calling_window(campaign, now):
            continue

        if active_calls.get(tenant.tenant_id, 0) >= tenant.max_concurrent_calls:
            continue

        phone_is_suppressed = db.scalar(
            select(PhoneSuppression.phone).where(
                PhoneSuppression.phone == lead.phone
            ).limit(1)
        )

        if phone_is_suppressed:
            continue

        phone_is_locked = db.scalar(
            select(PhoneLock.phone).where(
                PhoneLock.phone == lead.phone
            ).limit(1)
        )

        if phone_is_locked:
            continue

        candidates.append(
            ScheduledCandidate(
                lead=lead,
                campaign=campaign,
                tenant=tenant,
                priority=priority,
                scheduled_at=scheduled_at,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.priority,
            candidate.scheduled_at or datetime.min.replace(
                tzinfo=ZoneInfo(candidate.campaign.timezone)
            ),
            candidate.lead.created_at,
            candidate.lead.lead_id,
        )
    )

    return candidates[0] if candidates else None
