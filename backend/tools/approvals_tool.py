"""Approvals: adaptive quorum, and the line the agent cannot cross.

The control that matters is structural, not a prompt instruction. There is no
approve function exposed to the agent anywhere in this module. The agent can
call prepare_application. Approval happens only when enough valid ECDSA
signatures arrive from officer keys, verified server-side.

agent_attempt_approve exists so the demo can show the refusal being logged.
It always refuses. That is its entire behaviour.
"""

from __future__ import annotations

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

from .money import paise_to_rupees_str, rupees_to_paise, speak_rupees
from .registry import load_data, ok, refused, unavailable
from .. import db


def _band_for(amount_paise: int) -> dict | None:
    for band in load_data("quorum_rules.json")["bands"]:
        low = band["min_paise"]
        high = band["max_paise"]
        if amount_paise >= low and (high is None or amount_paise <= high):
            return band
    return None


def quorum_for(amount_paise: int, risk_flags: list[str] | None = None) -> dict:
    """How many signatures this amount needs, and why.

    Base requirement comes from the amount band; each risk flag adds a signer.
    Both parts are read from the rules file, so a district or bank can change
    the policy without touching code.
    """
    rules = load_data("quorum_rules.json")
    band = _band_for(amount_paise)
    if band is None:
        return unavailable("No quorum band covers that amount.", source="data/quorum_rules.json")

    risk_flags = risk_flags or []
    known = {flag["id"]: flag for flag in rules["risk_flags"]}
    extra = 0
    applied = []
    for flag_id in risk_flags:
        flag = known.get(flag_id)
        if flag:
            extra += flag["extra_signatures"]
            applied.append({"id": flag_id, "label": flag["label"],
                            "extra_signatures": flag["extra_signatures"]})

    required = band["signatures_required"] + extra
    pool = max(band["signer_pool_size"], required)

    return ok(
        {
            "amount_inr": paise_to_rupees_str(amount_paise),
            "amount_spoken": speak_rupees(amount_paise),
            "band": band["label"],
            "base_signatures": band["signatures_required"],
            "risk_flags_applied": applied,
            "extra_signatures": extra,
            "signatures_required": required,
            "signer_pool_size": pool,
            "description": f"{required} of {pool}",
        },
        source="Arithva quorum rules file",
        source_url="data/quorum_rules.json",
        confidence=(
            "These bands are our own design values for the prototype, not legal or "
            "banking thresholds. A real deployment loads the lender's own policy."
        ),
    )


def prepare_application(applicant_id: str, applicant_name: str | None, scheme_id: str,
                        scheme_name: str, amount_inr: float,
                        purpose: str | None = None) -> dict:
    """Draft an application and send it to the officer queue.

    This is the most the agent can do with money. The record is created with
    status 'prepared' and stays there until signatures arrive.
    """
    if amount_inr <= 0:
        return unavailable("The amount must be more than zero.")

    amount_paise = rupees_to_paise(amount_inr)

    risk_flags: list[str] = []
    if db.count_applications_by(applicant_id) == 0:
        risk_flags.append("first_time_applicant")

    schemes = load_data("schemes.json")["schemes"]
    scheme = next((s for s in schemes if s["id"] == scheme_id), None)
    if scheme:
        ceiling = scheme["rules"].get("max_loan_inr")
        if ceiling is not None and amount_inr > ceiling:
            risk_flags.append("amount_above_scheme_ceiling")

    quorum = quorum_for(amount_paise, risk_flags)
    if quorum["status"] != "ok":
        return quorum

    application_id = db.create_application(
        applicant_id=applicant_id,
        applicant_name=applicant_name,
        scheme_id=scheme_id,
        scheme_name=scheme_name,
        amount_paise=amount_paise,
        purpose=purpose,
        risk_flags=risk_flags,
        signatures_required=quorum["value"]["signatures_required"],
        band_label=quorum["value"]["band"],
    )

    db.log(
        actor=f"agent:on_behalf_of:{applicant_id}",
        action="application.prepared",
        detail={
            "application_id": application_id,
            "scheme": scheme_name,
            "amount_inr": paise_to_rupees_str(amount_paise),
            "signatures_required": quorum["value"]["signatures_required"],
            "risk_flags": risk_flags,
            "note": "Prepared by the agent. The agent cannot approve this.",
        },
    )

    return ok(
        {
            "application_id": application_id,
            "status": "prepared",
            "scheme": scheme_name,
            "amount_inr": paise_to_rupees_str(amount_paise),
            "amount_spoken": speak_rupees(amount_paise),
            "quorum": quorum["value"],
            "next_step": "This is now in the officer queue. Officers must sign before anything moves.",
        },
        source="Arithva Approvals",
    )


def agent_attempt_approve(application_id: int, actor: str = "agent") -> dict:
    """Always refuses, and records the attempt.

    Kept deliberately: a guardrail nobody can see being enforced is only a
    claim. In the demo this is a button, and the refusal lands in the audit log
    beside every other action.
    """
    db.log(
        actor=actor,
        action="approval.refused",
        detail={
            "application_id": application_id,
            "reason": "The agent has no approval capability. Money actions need officer signatures.",
        },
    )
    return refused(
        "The agent cannot approve an application. Approval requires ECDSA signatures from "
        "officer keys, verified on the server. This attempt has been written to the audit log.",
        application_id=application_id,
    )


def _signing_payload(application: dict) -> str:
    """The exact bytes an officer signs.

    Includes the amount and the applicant, so a signature cannot be lifted off
    one application and replayed onto another.
    """
    return json.dumps(
        {
            "application_id": application["id"],
            "applicant_id": application["applicant_id"],
            "scheme_id": application["scheme_id"],
            "amount_paise": application["amount_paise"],
            "created_at": application["created_at"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def signing_payload_for(application_id: int) -> dict:
    """What the officer's browser should sign."""
    application = db.get_application(application_id)
    if application is None:
        return unavailable(f"No application with id {application_id}.")
    return ok(
        {"application_id": application_id, "payload": _signing_payload(application)},
        source="Arithva Approvals",
    )


def _verify_ecdsa(public_key_jwk: dict, signature_b64: str, payload: str) -> bool:
    """Verify a P-256 signature produced by the Web Crypto API.

    Web Crypto emits raw r||s; the cryptography library wants DER, so the
    halves are reassembled here.
    """
    try:
        x = int.from_bytes(base64.urlsafe_b64decode(_pad(public_key_jwk["x"])), "big")
        y = int.from_bytes(base64.urlsafe_b64decode(_pad(public_key_jwk["y"])), "big")
        public_key = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()

        raw = base64.b64decode(signature_b64)
        if len(raw) != 64:
            return False
        r = int.from_bytes(raw[:32], "big")
        s = int.from_bytes(raw[32:], "big")
        der = asym_utils.encode_dss_signature(r, s)

        public_key.verify(der, payload.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False


def _pad(value: str) -> str:
    return value + "=" * (-len(value) % 4)


def submit_signature(application_id: int, officer_id: str, officer_name: str | None,
                     public_key_jwk: dict, signature_b64: str,
                     decision: str = "approve") -> dict:
    """Record one officer's signed decision, and approve if quorum is met."""
    application = db.get_application(application_id)
    if application is None:
        return unavailable(f"No application with id {application_id}.")
    if application["status"] in {"approved", "rejected"}:
        return unavailable(f"Application {application_id} is already {application['status']}.")

    officers = {o["id"]: o for o in load_data("quorum_rules.json")["officers"]}
    if officer_id not in officers:
        return unavailable(f"'{officer_id}' is not a listed officer.")

    existing = {s["officer_id"] for s in db.list_signatures(application_id)}
    if officer_id in existing:
        return unavailable(f"{officer_id} has already signed this application.")

    payload = _signing_payload(application)
    if not _verify_ecdsa(public_key_jwk, signature_b64, payload):
        db.log(
            actor=f"officer:{officer_id}",
            action="signature.rejected",
            detail={"application_id": application_id,
                    "reason": "Signature did not verify against the application payload."},
        )
        return unavailable(
            "That signature did not verify against this application. Nothing was recorded as valid."
        )

    db.add_signature(
        application_id=application_id,
        officer_id=officer_id,
        officer_name=officer_name or officers[officer_id]["name"],
        public_key_jwk=json.dumps(public_key_jwk, sort_keys=True),
        signature_b64=signature_b64,
        signed_payload=payload,
        decision=decision,
    )

    if decision == "reject":
        db.set_application_status(application_id, "rejected")
        db.log(
            actor=f"officer:{officer_id}",
            action="application.rejected",
            detail={"application_id": application_id,
                    "officer": officers[officer_id]["name"]},
        )
        return ok(
            {"application_id": application_id, "status": "rejected",
             "note": "An officer rejected this application."},
            source="Arithva Approvals",
        )

    signatures = db.list_signatures(application_id)
    approvals = [s for s in signatures if s["decision"] == "approve"]
    required = application["signatures_required"]

    db.log(
        actor=f"officer:{officer_id}",
        action="signature.accepted",
        detail={
            "application_id": application_id,
            "officer": officers[officer_id]["name"],
            "signatures_now": len(approvals),
            "signatures_required": required,
        },
    )

    quorum_met = len(approvals) >= required
    if quorum_met:
        db.set_application_status(application_id, "approved")
        db.log(
            actor="system",
            action="application.approved",
            detail={
                "application_id": application_id,
                "signatures": [s["officer_name"] for s in approvals],
                "amount_inr": paise_to_rupees_str(application["amount_paise"]),
                "note": "Approved by officer signatures. Money movement is SIMULATED in this prototype.",
            },
        )

    return ok(
        {
            "application_id": application_id,
            "signatures_collected": len(approvals),
            "signatures_required": required,
            "quorum_met": quorum_met,
            "status": "approved" if quorum_met else "prepared",
            "signed_by": [s["officer_name"] for s in approvals],
            "money_movement": "SIMULATED" if quorum_met else None,
        },
        source="Arithva Approvals, ECDSA P-256 verified server-side",
    )


def application_detail(application_id: int) -> dict:
    application = db.get_application(application_id)
    if application is None:
        return unavailable(f"No application with id {application_id}.")
    signatures = db.list_signatures(application_id)
    return ok(
        {
            "application": {
                **application,
                "amount_inr": paise_to_rupees_str(application["amount_paise"]),
            },
            "signatures": [
                {"officer_id": s["officer_id"], "officer_name": s["officer_name"],
                 "decision": s["decision"], "at": s["created_at"]}
                for s in signatures
            ],
        },
        source="Arithva Approvals",
    )
