"""Arithva API.

Serves the three screens and the endpoints behind them. Every state-changing
call lands in the hash-chained audit log.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, audit, db
from .tools import (
    approvals_tool, jobs_tool, loan_tool, scheme_tool, speech_tool, weather_tool,
)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# Optional keys. A missing .env is fine, and variables already set in the
# environment take precedence over the file.
load_dotenv(ROOT / ".env")

app = FastAPI(
    title="Arithva API",
    description=(
        "Voice-first assistant for rural micro-entrepreneurs. The model handles "
        "language; tools produce every number; officers sign anything involving money."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init(seed=True)


# ------------------------------------------------------------------ models

class AskRequest(BaseModel):
    text: str = Field(..., description="What the user said, already transcribed")
    context: dict = Field(default_factory=dict)


class JobPostRequest(BaseModel):
    employer_id: str = "demo_employer"
    trade: str
    workers_needed: int = 1
    days: int = 1
    wage_per_day_inr: float
    area: str = "Kalaburagi"


class JobApplyRequest(BaseModel):
    job_id: int
    worker_id: str = "demo_worker"
    worker_name: str = "Demo worker"
    trade: str | None = None


class AcceptRequest(BaseModel):
    application_id: int
    employer_id: str


class PrepareRequest(BaseModel):
    applicant_id: str = "demo_citizen"
    applicant_name: str | None = "Demo applicant"
    scheme_id: str = "pm_mudra_kishor"
    scheme_name: str = "PM MUDRA - Kishor"
    amount_inr: float
    purpose: str | None = None


class SignRequest(BaseModel):
    application_id: int
    officer_id: str
    officer_name: str | None = None
    public_key_jwk: dict
    signature_b64: str
    decision: str = "approve"


class SpeakRequest(BaseModel):
    text: str
    language: str = "en-IN"


class TamperRequest(BaseModel):
    entry_id: int
    new_detail: dict = Field(default_factory=lambda: {"note": "row edited by hand"})


# -------------------------------------------------------------------- agent

@app.post("/api/ask")
def ask(request: AskRequest) -> dict:
    """One turn of conversation."""
    response = agent.handle(request.text, request.context)
    db.log(
        actor=f"user:{request.context.get('user_id', 'demo')}",
        action="agent.turn",
        detail={
            "said": request.text,
            "intent": response["intent"],
            "needed_confirmation": response["needs_confirmation"],
            "tool_status": (response["tool_result"] or {}).get("status"),
        },
    )
    return response


# -------------------------------------------------------------------- tools

@app.get("/api/weather")
def weather(days_ahead: int = 1) -> dict:
    return weather_tool.forecast(days_ahead=days_ahead)


@app.post("/api/schemes/match")
def match_schemes(profile: dict) -> dict:
    return scheme_tool.find_schemes(profile)


@app.get("/api/schemes/{scheme_id}/documents")
def scheme_documents(scheme_id: str) -> dict:
    return scheme_tool.scheme_documents(scheme_id)


@app.get("/api/centres")
def centres(district: str = "kalaburagi") -> dict:
    return scheme_tool.nearest_centre(district)


@app.get("/api/loan/emi")
def emi(amount_inr: float, tenure_months: int = 36,
        annual_rate_pct: float | None = None, moratorium_months: int = 0) -> dict:
    return loan_tool.calculate_emi(amount_inr, tenure_months, annual_rate_pct, moratorium_months)


@app.get("/api/loan/subsidy")
def subsidy(scheme_id: str, project_cost_inr: float,
            area: str = "rural", category: str = "general") -> dict:
    return loan_tool.subsidy_estimate(scheme_id, project_cost_inr, area, category)


# ------------------------------------------------------------------ speech

@app.get("/api/speech/status")
def speech_status() -> dict:
    """Which voice provider is active. Shown on the citizen screen."""
    return speech_tool.status()


@app.post("/api/speak")
def speak(request: SpeakRequest):
    """Speak some text.

    Returns MP3 audio when ElevenLabs answers. Returns 503 with a reason when
    it does not, which is the frontend's signal to use the browser voice. A 503
    here is a normal, expected outcome, not a server fault.
    """
    result = speech_tool.synthesize(request.text, request.language)

    if result["status"] != "ok":
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "reason": result["reason"],
                     "fallback": "browser"},
        )

    return Response(
        content=result["value"]["audio"],
        media_type=result["value"]["content_type"],
        headers={
            "X-Arithva-Voice-Provider": result["value"]["provider"],
            "X-Arithva-Voice-Model": str(result["value"]["model_id"]),
        },
    )


# --------------------------------------------------------------------- jobs

@app.get("/api/jobs")
def list_jobs(trade: str | None = None, area: str | None = None, limit: int = 10) -> dict:
    return jobs_tool.find_jobs(trade=trade, area=area, limit=limit)


@app.post("/api/jobs")
def post_job(request: JobPostRequest) -> dict:
    result = jobs_tool.post_job(**request.model_dump())
    if result["status"] == "ok":
        db.log(
            actor=f"employer:{request.employer_id}",
            action="job.posted",
            detail={"job_id": result["value"]["job_id"], "trade": request.trade,
                    "wage_flag": result["value"]["wage_check"].get("flag")},
        )
    return result


@app.post("/api/jobs/apply")
def apply_job(request: JobApplyRequest) -> dict:
    result = jobs_tool.apply_to_job(
        job_id=request.job_id,
        worker_id=request.worker_id,
        worker_name=request.worker_name,
        trade=request.trade or "",
    )
    if result["status"] == "ok":
        db.log(
            actor=f"worker:{request.worker_id}",
            action="job.applied",
            detail={"job_id": request.job_id,
                    "application_id": result["value"]["application_id"]},
        )
    return result


@app.post("/api/jobs/accept")
def accept_job(request: AcceptRequest) -> dict:
    result = jobs_tool.accept_application(request.application_id, request.employer_id)
    if result["status"] == "ok":
        db.log(
            actor=f"employer:{request.employer_id}",
            action="job.accepted",
            detail={"application_id": request.application_id,
                    "note": "Contacts shared after both sides accepted."},
        )
    return result


@app.get("/api/jobs/{job_id}/applications")
def job_applications(job_id: int) -> dict:
    return {"status": "ok", "value": db.list_job_applications(job_id)}


# ---------------------------------------------------------------- approvals

@app.get("/api/quorum")
def quorum(amount_inr: float) -> dict:
    from .tools.money import rupees_to_paise
    return approvals_tool.quorum_for(rupees_to_paise(amount_inr))


@app.post("/api/applications/prepare")
def prepare(request: PrepareRequest) -> dict:
    return approvals_tool.prepare_application(**request.model_dump())


@app.get("/api/applications")
def applications(status: str | None = None) -> dict:
    rows = db.list_applications(status)
    from .tools.money import paise_to_rupees_str
    for row in rows:
        row["amount_inr"] = paise_to_rupees_str(row["amount_paise"])
        row["signatures_collected"] = len([
            s for s in db.list_signatures(row["id"]) if s["decision"] == "approve"
        ])
    return {"status": "ok", "value": rows}


@app.get("/api/applications/{application_id}")
def application(application_id: int) -> dict:
    return approvals_tool.application_detail(application_id)


@app.get("/api/applications/{application_id}/payload")
def payload(application_id: int) -> dict:
    """The exact string the officer's browser signs."""
    return approvals_tool.signing_payload_for(application_id)


@app.post("/api/applications/sign")
def sign(request: SignRequest) -> dict:
    return approvals_tool.submit_signature(**request.model_dump())


@app.post("/api/applications/{application_id}/agent-approve")
def agent_approve(application_id: int) -> dict:
    """Always refuses. Wired to a button so the guardrail can be seen working."""
    return approvals_tool.agent_attempt_approve(application_id)


# -------------------------------------------------------------------- audit

@app.get("/api/audit")
def audit_log(limit: int = 100) -> dict:
    return {"status": "ok", "value": db.audit_rows(limit=limit)}


@app.get("/api/audit/verify")
def verify_audit() -> dict:
    return {"status": "ok", "value": audit.verify_chain(db.audit_rows())}


@app.post("/api/audit/tamper")
def tamper(request: TamperRequest) -> dict:
    """Edit a past log row on purpose, so /api/audit/verify can catch it.

    Demo-only, and labelled as such in the UI.
    """
    changed = db.tamper_with_audit_row(request.entry_id, request.new_detail)
    return {
        "status": "ok" if changed else "unavailable",
        "value": {
            "entry_id": request.entry_id,
            "changed": changed,
            "note": "Row edited without recomputing its hash. Run /api/audit/verify.",
        },
    }


# ----------------------------------------------------------------- frontend

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "arithva"}


class NoCacheStaticFiles(StaticFiles):
    """Serve the frontend with caching off.

    StaticFiles sends only etag and last-modified, no cache-control. With no
    cache-control a browser is free to cache heuristically, and Chrome does:
    it kept serving a previous app.js and styles.css without asking the server
    at all, so a merged UI change looked like it had not landed. Cost an hour
    before a demo. The frontend is a few files served off localhost, so there
    is nothing to gain by caching it.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


app.mount("/", NoCacheStaticFiles(directory=FRONTEND, html=True), name="frontend")
