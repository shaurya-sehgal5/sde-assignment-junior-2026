import os
from datetime import datetime, time, timedelta

# Use a harmless SQLite URL for the module-level engine created by database.py.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:////tmp/agentic_dispatcher_pytest_import.db",
)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.entities import Campaign, Lead, Tenant
from app.services.scheduling import (
    is_due,
    is_inside_calling_window,
    next_eligible_time,
    parse_allowed_days,
    select_next_candidate,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def make_campaign(db, campaign_id="camp", days="Mon-Sun"):
    tenant = db.get(Tenant, "tenant")
    if tenant is None:
        tenant = Tenant(
            tenant_id="tenant",
            max_concurrent_calls=4,
        )
        db.add(tenant)
    campaign = Campaign(
        campaign_id=campaign_id,
        tenant_id="tenant",
        window_start=time(10, 0),
        window_end=time(19, 0),
        window_days=days,
        max_attempts=3,
        timezone="Asia/Kolkata",
    )
    db.add(campaign)
    db.flush()
    return campaign


def make_lead(db, campaign_id, lead_id, state, now):
    lead = Lead(
        campaign_id=campaign_id,
        lead_id=lead_id,
        phone=f"+910000{lead_id[-4:]}",
        customer_name=lead_id,
        state=state,
        attempts=0,
        created_at=now - timedelta(minutes=5),
    )
    db.add(lead)
    db.flush()
    return lead


def test_allowed_day_ranges():
    assert parse_allowed_days("Mon-Sat") == {0, 1, 2, 3, 4, 5}
    assert parse_allowed_days("Mon,Wed,Fri") == {0, 2, 4}
    assert parse_allowed_days("0,2,6") == {0, 2, 6}


def test_campaign_window_is_start_inclusive_end_exclusive(db):
    campaign = make_campaign(db)
    assert is_inside_calling_window(
        campaign, datetime(2026, 11, 12, 10, 0)
    )
    assert is_inside_calling_window(
        campaign, datetime(2026, 11, 12, 18, 59, 59)
    )
    assert not is_inside_calling_window(
        campaign, datetime(2026, 11, 12, 19, 0)
    )
    assert not is_inside_calling_window(
        campaign, datetime(2026, 11, 12, 8, 59)
    )


def test_campaign_weekdays_are_enforced(db):
    campaign = make_campaign(db, days="Mon-Sat")
    # 15 November 2026 is Sunday.
    assert not is_inside_calling_window(
        campaign, datetime(2026, 11, 15, 12, 0)
    )


def test_callback_and_retry_due_times(db):
    now = datetime(2026, 11, 12, 12, 0)
    callback = Lead(
        campaign_id="camp", lead_id="callback", phone="+910000000001",
        customer_name="callback", state="callback_scheduled",
        attempts=1, callback_at=now + timedelta(minutes=1),
    )
    retry = Lead(
        campaign_id="camp", lead_id="retry", phone="+910000000002",
        customer_name="retry", state="retry_wait",
        attempts=1, next_attempt_at=now - timedelta(minutes=1),
    )
    assert is_due(callback, now)[0] is False
    assert is_due(callback, now + timedelta(minutes=1))[0] is True
    assert is_due(retry, now)[0] is True


def test_scheduler_prioritizes_callback_then_retry_then_fresh(db):
    now = datetime(2026, 11, 12, 12, 0)
    campaign = make_campaign(db)
    callback = make_lead(db, campaign.campaign_id, "lead_callback",
                         "callback_scheduled", now)
    callback.callback_at = now - timedelta(minutes=1)

    retry = make_lead(db, campaign.campaign_id, "lead_retry",
                      "retry_wait", now)
    retry.next_attempt_at = now - timedelta(minutes=1)

    make_lead(db, campaign.campaign_id, "lead_fresh", "pending", now)
    db.commit()

    assert select_next_candidate(db, now).lead.lead_id == "lead_callback"

    callback.state = "completed"
    db.flush()
    assert select_next_candidate(db, now).lead.lead_id == "lead_retry"

    retry.state = "completed"
    db.flush()
    assert select_next_candidate(db, now).lead.lead_id == "lead_fresh"



def test_next_eligible_time_moves_to_next_allowed_day(db):
    campaign = make_campaign(db, days="Mon-Sat")
    # Sunday 15 Nov 2026; the campaign reopens Monday at 10:00 IST.
    result = next_eligible_time(
        campaign, datetime(2026, 11, 15, 12, 0)
    )
    assert result == datetime(
        2026, 11, 16, 10, 0,
        tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"),
    )


def test_next_eligible_time_respects_regulatory_window(db):
    campaign = make_campaign(db)
    # Before the regulatory window; the first valid instant is 09:00 IST,
    # but this campaign itself opens at 10:00.
    result = next_eligible_time(
        campaign, datetime(2026, 11, 12, 8, 0)
    )
    assert result.hour == 10
    assert result.minute == 0
