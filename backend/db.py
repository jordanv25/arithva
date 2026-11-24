"""SQLite storage.

SQLite rather than Postgres on purpose: the prototype has to start with one
command on any laptop during a demo. The schema is the same shape a Postgres
deployment would use.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from . import audit

DB_PATH = Path(__file__).resolve().parents[1] / "arithva.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id TEXT NOT NULL,
    applicant_name TEXT,
    scheme_id TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    purpose TEXT,
    status TEXT NOT NULL DEFAULT 'prepared',
    risk_flags TEXT NOT NULL DEFAULT '[]',
    signatures_required INTEGER NOT NULL,
    band_label TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    officer_id TEXT NOT NULL,
    officer_name TEXT,
    public_key_jwk TEXT NOT NULL,
    signature_b64 TEXT NOT NULL,
    signed_payload TEXT NOT NULL,
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (application_id, officer_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id TEXT NOT NULL,
    trade TEXT NOT NULL,
    workers_needed INTEGER NOT NULL,
    days INTEGER NOT NULL,
    wage_per_day_inr REAL NOT NULL,
    area TEXT,
    starts_on TEXT,
    wage_flag TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    trade TEXT,
    status TEXT NOT NULL DEFAULT 'applied',
    contact_shared INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init(seed: bool = True) -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    if seed:
        seed_jobs()


def reset() -> None:
    """Drop everything and start clean. Used before a demo run."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init()


# ---------------------------------------------------------------- audit log

def log(actor: str, action: str, detail: dict) -> dict:
    """Append one entry to the hash chain."""
    with connect() as conn:
        row = conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous = row["entry_hash"] if row else audit.GENESIS
        timestamp = audit.now_iso()
        digest = audit.entry_hash(previous, timestamp, actor, action, detail)
        cursor = conn.execute(
            "INSERT INTO audit_log (timestamp, actor, action, detail, previous_hash, entry_hash)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (timestamp, actor, action, json.dumps(detail, ensure_ascii=False),
             previous, digest),
        )
        return {
            "id": cursor.lastrowid,
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "entry_hash": digest,
        }


def audit_rows(limit: int | None = None) -> list[dict]:
    query = "SELECT * FROM audit_log ORDER BY id ASC"
    if limit:
        query += f" LIMIT {int(limit)}"
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query)]
    for row in rows:
        row["detail"] = json.loads(row["detail"])
    return rows


def tamper_with_audit_row(entry_id: int, new_detail: dict) -> bool:
    """Edit a past log row WITHOUT fixing its hash.

    This exists for one reason: the demo claims the log is tamper-evident, and
    a claim like that should be demonstrated rather than asserted. Press the
    button, change a row, run the verifier, watch it name the row.
    """
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE audit_log SET detail = ? WHERE id = ?",
            (json.dumps(new_detail, ensure_ascii=False), entry_id),
        )
        return cursor.rowcount > 0


# ------------------------------------------------------------- applications

def create_application(applicant_id: str, applicant_name: str | None, scheme_id: str,
                       scheme_name: str, amount_paise: int, purpose: str | None,
                       risk_flags: list[str], signatures_required: int,
                       band_label: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO applications (applicant_id, applicant_name, scheme_id, scheme_name,"
            " amount_paise, purpose, status, risk_flags, signatures_required, band_label, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'prepared', ?, ?, ?, ?)",
            (applicant_id, applicant_name, scheme_id, scheme_name, amount_paise, purpose,
             json.dumps(risk_flags), signatures_required, band_label, audit.now_iso()),
        )
        return cursor.lastrowid


def get_application(application_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
    if row is None:
        return None
    application = dict(row)
    application["risk_flags"] = json.loads(application["risk_flags"])
    return application


def list_applications(status: str | None = None) -> list[dict]:
    query = "SELECT * FROM applications"
    params: tuple[Any, ...] = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY id DESC"
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(query, params)]
    for row in rows:
        row["risk_flags"] = json.loads(row["risk_flags"])
    return rows


def set_application_status(application_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE applications SET status = ? WHERE id = ?", (status, application_id)
        )


def count_applications_by(applicant_id: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM applications WHERE applicant_id = ?", (applicant_id,)
        ).fetchone()
    return row["n"]


# -------------------------------------------------------------- signatures

def add_signature(application_id: int, officer_id: str, officer_name: str | None,
                  public_key_jwk: str, signature_b64: str, signed_payload: str,
                  decision: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO signatures (application_id, officer_id, officer_name,"
            " public_key_jwk, signature_b64, signed_payload, decision, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (application_id, officer_id, officer_name, public_key_jwk, signature_b64,
             signed_payload, decision, audit.now_iso()),
        )
        return cursor.lastrowid


def list_signatures(application_id: int) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM signatures WHERE application_id = ? ORDER BY id ASC",
            (application_id,),
        )]


# -------------------------------------------------------------------- jobs

def create_job(employer_id: str, trade: str, workers_needed: int, days: int,
               wage_per_day_inr: float, area: str, starts_on: str | None,
               wage_flag: str | None) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO jobs (employer_id, trade, workers_needed, days, wage_per_day_inr,"
            " area, starts_on, wage_flag, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (employer_id, trade, workers_needed, days, wage_per_day_inr, area,
             starts_on, wage_flag, audit.now_iso()),
        )
        return cursor.lastrowid


def get_job(job_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_open_jobs(trade: str | None = None, area: str | None = None,
                   limit: int = 5) -> list[dict]:
    query = "SELECT * FROM jobs WHERE status = 'open'"
    params: list[Any] = []
    if trade:
        query += " AND trade = ?"
        params.append(trade.strip().lower())
    if area:
        query += " AND LOWER(area) = ?"
        params.append(area.strip().lower())
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, params)]


def create_job_application(job_id: int, worker_id: str, worker_name: str,
                           trade: str | None) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO job_applications (job_id, worker_id, worker_name, trade, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (job_id, worker_id, worker_name, trade, audit.now_iso()),
        )
        return cursor.lastrowid


# Names the jobs tool expects
create_application_job = create_job_application


def get_job_application(application_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM job_applications WHERE id = ?", (application_id,)
        ).fetchone()
    return dict(row) if row else None


def accept_job_application(application_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE job_applications SET status = 'accepted', contact_shared = 1 WHERE id = ?",
            (application_id,),
        )


def list_job_applications(job_id: int) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM job_applications WHERE job_id = ? ORDER BY id ASC", (job_id,)
        )]


def seed_jobs() -> None:
    """Synthetic Kalaburagi jobs so the demo has something to show.

    Labelled synthetic everywhere it surfaces. No real employer is listed.
    """
    with connect() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
    if existing:
        return

    samples = [
        ("employer_demo_1", "painter", 2, 3, 800, "Super Market"),
        ("employer_demo_2", "mason", 1, 10, 700, "Aland Road"),
        ("employer_demo_3", "helper", 3, 2, 450, "Jagat Circle"),
        ("employer_demo_4", "electrician", 1, 1, 900, "Station Road"),
        ("employer_demo_5", "tailor", 2, 15, 600, "Super Market"),
    ]
    from .tools.jobs_tool import _wage_check

    for employer_id, trade, workers, days, wage, area in samples:
        flag = _wage_check(trade, wage).get("flag")
        create_job(employer_id, trade, workers, days, wage, area, None, flag)
