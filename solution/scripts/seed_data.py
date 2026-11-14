import csv
import json
from pathlib import Path
from datetime import time

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.entities import Tenant, Campaign, Lead


SOLUTION_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SOLUTION_DIR.parent
FIXTURE_DIR = REPO_DIR / "assignment-b-workflow" / "fixtures"
CAMPAIGNS_FILE = FIXTURE_DIR / "campaigns.json"


def first_value(data, *keys, default=None):
    """Return the first present, non-null key."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def parse_time(value):
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


def load_campaign_config():
    with CAMPAIGNS_FILE.open("r", encoding="utf-8") as file:
        config = json.load(file)

    tenants = config.get("tenants", [])
    campaigns = config.get("campaigns", [])

    # Also support tenants represented as a dictionary keyed by tenant ID.
    if isinstance(tenants, dict):
        tenants = [
            {"tenant_id": tenant_id, **details}
            for tenant_id, details in tenants.items()
        ]

    return tenants, campaigns


def seed():
    if not CAMPAIGNS_FILE.exists():
        raise FileNotFoundError(f"Missing fixture: {CAMPAIGNS_FILE}")

    tenants_data, campaigns_data = load_campaign_config()

    inserted_tenants = 0
    inserted_campaigns = 0
    inserted_leads = 0
    existing_leads = 0

    with SessionLocal() as db:
        try:
            # 1. Tenants
            for item in tenants_data:
                tenant_id = first_value(item, "tenant_id", "id")
                if not tenant_id:
                    raise ValueError(f"Tenant has no ID: {item}")

                tenant = db.get(Tenant, tenant_id)

                if tenant is None:
                    tenant = Tenant(
                        tenant_id=tenant_id,
                        max_concurrent_calls=int(
                            first_value(
                                item,
                                "max_concurrent_calls",
                                "max_concurrency",
                                default=1,
                            )
                        ),
                    )
                    db.add(tenant)
                    inserted_tenants += 1
                else:
                    tenant.max_concurrent_calls = int(
                        first_value(
                            item,
                            "max_concurrent_calls",
                            "max_concurrency",
                            default=tenant.max_concurrent_calls,
                        )
                    )

            db.flush()

            # 2. Campaigns and their leads
            for item in campaigns_data:
                campaign_id = first_value(item, "campaign_id", "id")
                tenant_id = first_value(item, "tenant_id")

                if not campaign_id or not tenant_id:
                    raise ValueError(f"Invalid campaign configuration: {item}")

                window = item.get("calling_window", item.get("window", {}))

                start = first_value(
                    window, "start", "start_time",
                    default=first_value(item, "window_start", default="09:00"),
                )
                end = first_value(
                    window, "end", "end_time",
                    default=first_value(item, "window_end", default="21:00"),
                )

                days = first_value(
                    window,
                    "days",
                    "weekdays",
                    default=first_value(item, "window_days", default=[]),
                )
                if isinstance(days, str):
                    days_string = days
                else:
                    days_string = ",".join(str(day) for day in days)

                timezone_name = first_value(
                    item, "timezone", "timezone_name",
                    default="Asia/Kolkata",
                )
                max_attempts = int(
                    first_value(item, "max_attempts", default=3)
                )

                campaign = db.get(Campaign, campaign_id)

                if campaign is None:
                    campaign = Campaign(
                        campaign_id=campaign_id,
                        tenant_id=tenant_id,
                        window_start=parse_time(start),
                        window_end=parse_time(end),
                        window_days=days_string,
                        max_attempts=max_attempts,
                        timezone=timezone_name,
                    )
                    db.add(campaign)
                    inserted_campaigns += 1
                else:
                    campaign.tenant_id = tenant_id
                    campaign.window_start = parse_time(start)
                    campaign.window_end = parse_time(end)
                    campaign.window_days = days_string
                    campaign.max_attempts = max_attempts
                    campaign.timezone = timezone_name

                db.flush()

                # Fixture naming convention:
                # leads_<campaign_id>.csv
                csv_file = FIXTURE_DIR / f"leads_{campaign_id}.csv"

                if not csv_file.exists():
                    raise FileNotFoundError(
                        f"Missing lead fixture for {campaign_id}: {csv_file}"
                    )

                with csv_file.open("r", encoding="utf-8-sig", newline="") as file:
                    reader = csv.DictReader(file)

                    required_columns = {"lead_id", "phone", "customer_name"}
                    if not required_columns.issubset(set(reader.fieldnames or [])):
                        raise ValueError(
                            f"{csv_file.name} must contain columns "
                            f"{sorted(required_columns)}"
                        )

                    for row in reader:
                        lead_id = row["lead_id"].strip()
                        phone = row["phone"].strip()
                        customer_name = row["customer_name"].strip()

                        if not lead_id or not phone:
                            raise ValueError(
                                f"Invalid lead row in {csv_file.name}: {row}"
                            )

                        existing = db.scalar(
                            select(Lead).where(
                                Lead.campaign_id == campaign_id,
                                Lead.lead_id == lead_id,
                            )
                        )

                        if existing:
                            # Never reset attempts/state during a rerun.
                            existing_leads += 1
                            continue

                        db.add(
                            Lead(
                                campaign_id=campaign_id,
                                lead_id=lead_id,
                                phone=phone,
                                customer_name=customer_name,
                                state="pending",
                                attempts=0,
                            )
                        )
                        inserted_leads += 1

            db.commit()

        except Exception:
            db.rollback()
            raise

    print("\n========== SEED SUMMARY ==========")
    print(f"Tenants inserted:       {inserted_tenants}")
    print(f"Campaigns inserted:     {inserted_campaigns}")
    print(f"Leads inserted:         {inserted_leads}")
    print(f"Existing leads skipped: {existing_leads}")
    print("==================================")
    print("Fixture import completed successfully.")


if __name__ == "__main__":
    seed()
