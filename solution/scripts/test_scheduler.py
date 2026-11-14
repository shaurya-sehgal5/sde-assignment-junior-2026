
from datetime import datetime

from app.db.database import SessionLocal
from app.services.scheduling import select_next_candidate


# Assignment's initial simulated time.
SIMULATION_START = datetime.fromisoformat(
    "2026-11-12T17:30:00+05:30"
)


with SessionLocal() as db:
    candidate = select_next_candidate(db, SIMULATION_START)

    if candidate is None:
        print("No eligible lead found.")
    else:
        print("========== SCHEDULER RESULT ==========")
        print("Lead ID:", candidate.lead.lead_id)
        print("Phone:", candidate.lead.phone)
        print("Campaign:", candidate.campaign.campaign_id)
        print("Tenant:", candidate.tenant.tenant_id)
        print("Priority:", candidate.priority)
        print("Attempts:", candidate.lead.attempts)
        print("======================================")
