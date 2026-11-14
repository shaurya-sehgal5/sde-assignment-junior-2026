import csv
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.config import PROVIDER_URL
from app.db.database import SessionLocal
from app.models.entities import Lead


SOLUTION_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = SOLUTION_DIR / "final_state.csv"
FINAL_STATES = {"completed", "exhausted", "dnd_blocked"}


def export_final_state() -> Path:
    with SessionLocal() as db:
        leads = db.scalars(
            select(Lead).order_by(Lead.campaign_id, Lead.lead_id)
        ).all()
        local_rows = {
            (lead.campaign_id, lead.lead_id): {
                "campaign_id": lead.campaign_id,
                "lead_id": lead.lead_id,
                "final_state": lead.state,
                "attempts": lead.attempts,
                "last_status": lead.last_status or "",
                "last_disposition": lead.last_disposition or "",
            }
            for lead in leads
        }

    if len(local_rows) != 200:
        raise RuntimeError(
            f"Expected 200 local leads, found {len(local_rows)}"
        )

    unfinished = [
        key for key, row in local_rows.items()
        if row["final_state"] not in FINAL_STATES
    ]
    if unfinished:
        raise RuntimeError(
            f"Cannot export: {len(unfinished)} leads are not final: "
            f"{unfinished[:10]}"
        )

    report_response = httpx.get(
        f"{PROVIDER_URL.rstrip('/')}/admin/report",
        timeout=15.0,
    )
    report_response.raise_for_status()
    report = report_response.json()
    if report.get("violation_count") != 0:
        raise RuntimeError(
            f"Provider reports {report.get('violation_count')} violations; "
            "fix them before submission."
        )
    if report.get("calls_active") != 0:
        raise RuntimeError(
            f"Provider still has {report.get('calls_active')} active calls."
        )

    response = httpx.get(
        f"{PROVIDER_URL.rstrip('/')}/admin/leads",
        timeout=15.0,
    )
    response.raise_for_status()
    provider_rows = response.json()
    provider_by_key = {
        (row["campaign_id"], row["lead_id"]): row
        for row in provider_rows
    }

    mismatches = []
    for key, local in local_rows.items():
        expected = provider_by_key.get(key)
        if expected is None:
            mismatches.append((key, "missing from provider"))
            continue

        expected_state = expected["expected_state"]
        if expected_state not in FINAL_STATES:
            mismatches.append((key, f"provider state is {expected_state}"))
            continue

        actual = (
            local["final_state"],
            local["attempts"],
            local["last_status"],
            local["last_disposition"],
        )
        wanted = (
            expected_state,
            expected["attempts"],
            expected.get("last_status") or "",
            expected.get("last_disposition") or "",
        )
        if actual != wanted:
            mismatches.append((key, f"local={actual}, provider={wanted}"))

    if len(provider_by_key) != 200:
        mismatches.append(
            (("provider", "count"), f"expected 200, got {len(provider_by_key)}")
        )

    if mismatches:
        preview = "\\n".join(str(item) for item in mismatches[:20])
        raise RuntimeError(
            f"Final state does not match provider ({len(mismatches)} "
            f"mismatches):\\n{preview}"
        )

    fieldnames = [
        "campaign_id",
        "lead_id",
        "final_state",
        "attempts",
        "last_status",
        "last_disposition",
    ]
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            local_rows[key] for key in sorted(local_rows)
        )

    print(f"Verified {len(local_rows)} leads against provider.")
    print(f"CSV written: {OUTPUT_FILE}")
    return OUTPUT_FILE


if __name__ == "__main__":
    export_final_state()
