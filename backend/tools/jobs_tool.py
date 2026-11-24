"""Jobs: post work, find work, apply, accept.

Two things this tool does that a plain job board does not:

  * Phone numbers stay masked until both sides have accepted.
  * Any offer below the minimum wage for that trade is flagged, from a lookup
    table rather than from the model's opinion.
"""

from __future__ import annotations

from .registry import load_data, ok, unavailable
from .. import db


def _wage_check(trade: str, offered_inr: float) -> dict:
    table = load_data("wage_table.json")
    category = table["trade_to_category"].get(trade.strip().lower())
    if category is None:
        return {
            "checked": False,
            "note": f"No minimum-wage category recorded for '{trade}'. Offer not checked.",
        }
    entry = table["trades"][category]
    minimum = entry["min_wage_inr"]
    below = offered_inr < minimum
    return {
        "checked": True,
        "category": category,
        "minimum_wage_inr": minimum,
        "offered_inr": offered_inr,
        "below_minimum": below,
        "flag": (
            f"This offer of Rs {offered_inr:,.0f} a day is below the Rs {minimum:,} "
            f"recorded for {category.replace('_', ' ')} work."
        ) if below else None,
        "status_warning": entry.get("status"),
        "source": table["source"],
        "confidence": table["confidence"],
    }


def post_job(employer_id: str, trade: str, workers_needed: int, days: int,
             wage_per_day_inr: float, area: str, starts_on: str | None = None) -> dict:
    """Create a job post. Called only after the user confirms the read-back."""
    if workers_needed < 1:
        return unavailable("A job needs at least one worker.")
    if days < 1:
        return unavailable("A job needs at least one day of work.")
    if wage_per_day_inr <= 0:
        return unavailable("The daily wage must be more than zero.")

    wage = _wage_check(trade, wage_per_day_inr)
    job_id = db.create_job(
        employer_id=employer_id,
        trade=trade.strip().lower(),
        workers_needed=workers_needed,
        days=days,
        wage_per_day_inr=wage_per_day_inr,
        area=area,
        starts_on=starts_on,
        wage_flag=wage.get("flag"),
    )

    return ok(
        {
            "job_id": job_id,
            "trade": trade,
            "workers_needed": workers_needed,
            "days": days,
            "wage_per_day_inr": wage_per_day_inr,
            "area": area,
            "starts_on": starts_on,
            "wage_check": wage,
        },
        source="Arithva Jobs; wage check from the Karnataka minimum-wage lookup",
        confidence=wage.get("confidence"),
    )


def find_jobs(trade: str | None = None, area: str | None = None, limit: int = 5) -> dict:
    """Open jobs, with a plain-language reason for each match."""
    jobs = db.list_open_jobs(trade=trade, area=area, limit=limit)
    if not jobs:
        return ok(
            {"jobs": [], "note": "No open jobs match that right now."},
            source="Arithva Jobs (SYNTHETIC demo data)",
        )

    for job in jobs:
        bits = []
        if trade and job["trade"] == trade.strip().lower():
            bits.append(f"matches your trade ({job['trade']})")
        if area and job["area"].lower() == area.strip().lower():
            bits.append(f"in {job['area']}")
        elif job.get("area"):
            bits.append(f"in {job['area']}")
        bits.append(f"{job['days']} day(s) at Rs {job['wage_per_day_inr']:,.0f} a day")
        job["why"] = ", ".join(bits)

    return ok(
        {"jobs": jobs},
        source="Arithva Jobs (SYNTHETIC demo data)",
        confidence="Seed jobs are synthetic and labelled. No real employers are listed.",
    )


def apply_to_job(job_id: int, worker_id: str, worker_name: str, trade: str) -> dict:
    """Apply for a job. Contacts stay masked until the employer accepts."""
    job = db.get_job(job_id)
    if job is None:
        return unavailable(f"No job with id {job_id}.")
    if job["status"] != "open":
        return unavailable(f"Job {job_id} is no longer open.")

    application_id = db.create_job_application(
        job_id=job_id, worker_id=worker_id, worker_name=worker_name, trade=trade,
    )
    return ok(
        {
            "application_id": application_id,
            "job_id": job_id,
            "status": "applied",
            "contact_shared": False,
            "note": "Your phone number stays hidden until the employer accepts.",
        },
        source="Arithva Jobs",
    )


def accept_application(application_id: int, employer_id: str) -> dict:
    """Employer accepts. This is the moment contacts become visible to each side."""
    application = db.get_job_application(application_id)
    if application is None:
        return unavailable(f"No application with id {application_id}.")

    job = db.get_job(application["job_id"])
    if job is None:
        return unavailable("The job for this application no longer exists.")
    if job["employer_id"] != employer_id:
        return unavailable("Only the employer who posted this job can accept it.")

    db.accept_job_application(application_id)
    return ok(
        {
            "application_id": application_id,
            "job_id": job["id"],
            "worker_name": application["worker_name"],
            "status": "accepted",
            "contact_shared": True,
            "note": "Both sides accepted, so contact details are now shared with each other.",
        },
        source="Arithva Jobs",
    )
