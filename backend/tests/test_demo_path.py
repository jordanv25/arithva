"""The demo path, as a test.

If this passes, the sequence shown in the pitch video works. Run it before
recording, and again before submitting.

    pytest backend/tests/test_demo_path.py -v
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

from backend import audit, db
from backend.agent import classify, handle
from backend.tools import approvals_tool, jobs_tool, loan_tool, scheme_tool
from backend.tools.money import compute_emi, rupees_to_paise, speak_rupees


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init(seed=True)


# ------------------------------------------------------------------- money

def test_emi_is_computed_in_whole_paise():
    schedule = compute_emi(rupees_to_paise(150000), 10.5, 36)
    assert isinstance(schedule.emi_paise, int)
    assert schedule.total_payment_paise > schedule.principal_paise
    # The schedule must actually clear the loan, not approximately clear it.
    assert schedule.last_row["balance_paise"] == 0


def test_amounts_are_spoken_the_indian_way():
    assert speak_rupees(rupees_to_paise(150000)) == "one lakh fifty thousand rupees"
    assert speak_rupees(rupees_to_paise(5000)) == "five thousand rupees"


# ------------------------------------------------------------------ tools

def test_every_tool_result_carries_a_source():
    results = [
        loan_tool.calculate_emi(100000, 24),
        scheme_tool.find_schemes({"age": 30, "business_status": "new"}),
        approvals_tool.quorum_for(rupees_to_paise(100000)),
    ]
    for result in results:
        assert result["status"] == "ok"
        assert result["source"]
        assert result["as_of"]


def test_a_tool_that_cannot_answer_says_so():
    result = loan_tool.calculate_emi(-5, 12)
    assert result["status"] == "unavailable"
    assert "agent_instruction" in result
    assert "Do not supply a number" in result["agent_instruction"]


def test_wage_below_minimum_is_flagged():
    result = jobs_tool.post_job("e1", "mason", 1, 2, 300, "Super Market")
    assert result["value"]["wage_check"]["below_minimum"] is True


# ------------------------------------------------------------------ agent

@pytest.mark.parametrize("said,expected", [
    ("will it be very hot tomorrow", "weather"),
    ("which scheme can I get for a new stall", "scheme"),
    ("what is the emi for 1.5 lakh over 36 months", "loan"),
    ("I need 2 painters for 3 days at 800 rupees", "job_post"),
    ("find me work as a mason", "job_find"),
])
def test_intent_routing(said, expected):
    assert classify(said).name == expected


def test_amounts_are_parsed_from_speech():
    assert classify("emi for 1.5 lakh").slots["amount_inr"] == 150000
    assert classify("emi for 50000 rupees").slots["amount_inr"] == 50000


def test_state_changing_action_asks_before_it_acts():
    response = handle("I need 2 painters for 3 days at 800 rupees")
    assert response["needs_confirmation"] is True
    assert response["tool_result"] is None       # nothing happened yet
    assert "Say yes" in response["spoken"]


def test_confirmed_action_goes_through():
    said = "I need 2 painters for 3 days at 800 rupees"
    response = handle(said, {"confirmed": True, "user_id": "e1", "area": "Super Market"})
    assert response["needs_confirmation"] is False
    assert response["tool_result"]["status"] == "ok"


# -------------------------------------------------------------- approvals

def test_quorum_rises_with_the_amount():
    small = approvals_tool.quorum_for(rupees_to_paise(20000))
    medium = approvals_tool.quorum_for(rupees_to_paise(150000))
    large = approvals_tool.quorum_for(rupees_to_paise(800000))
    assert small["value"]["base_signatures"] == 1
    assert medium["value"]["base_signatures"] == 2
    assert large["value"]["base_signatures"] == 3


def test_risk_flag_adds_a_signer():
    plain = approvals_tool.quorum_for(rupees_to_paise(150000))
    flagged = approvals_tool.quorum_for(rupees_to_paise(150000), ["first_time_applicant"])
    assert flagged["value"]["signatures_required"] == plain["value"]["signatures_required"] + 1


def test_the_agent_cannot_approve():
    prepared = approvals_tool.prepare_application(
        "citizen_1", "Demo", "pm_mudra_kishor", "PM MUDRA - Kishor", 150000)
    application_id = prepared["value"]["application_id"]

    attempt = approvals_tool.agent_attempt_approve(application_id)
    assert attempt["status"] == "refused"
    assert db.get_application(application_id)["status"] == "prepared"

    # and the attempt is on the record
    actions = [row["action"] for row in db.audit_rows()]
    assert "approval.refused" in actions


def test_approvals_server_exposes_no_approve_tool():
    """The guardrail is structural: check the MCP surface really lacks it."""
    from backend.mcp_servers import approvals_server
    source = open(approvals_server.__file__, encoding="utf-8").read()
    # No tool-decorated function may be named approve.
    assert "def approve" not in source
    assert "def submit_signature" not in source


def _sign(payload: str):
    """Produce a signature in the same raw r||s shape Web Crypto emits."""
    key = ec.generate_private_key(ec.SECP256R1())
    der = key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
    r, s = asym_utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    numbers = key.public_key().public_numbers()
    jwk = {
        "kty": "EC", "crv": "P-256",
        "x": base64.urlsafe_b64encode(numbers.x.to_bytes(32, "big")).decode().rstrip("="),
        "y": base64.urlsafe_b64encode(numbers.y.to_bytes(32, "big")).decode().rstrip("="),
    }
    return jwk, base64.b64encode(raw).decode()


def test_quorum_must_be_met_before_approval():
    prepared = approvals_tool.prepare_application(
        "citizen_2", "Demo", "pm_mudra_kishor", "PM MUDRA - Kishor", 150000)
    application_id = prepared["value"]["application_id"]
    required = prepared["value"]["quorum"]["signatures_required"]
    payload = approvals_tool.signing_payload_for(application_id)["value"]["payload"]

    for index in range(required):
        jwk, signature = _sign(payload)
        result = approvals_tool.submit_signature(
            application_id, f"officer_{index + 1}", None, jwk, signature)
        assert result["status"] == "ok"
        expected = index + 1 >= required
        assert result["value"]["quorum_met"] is expected

    assert db.get_application(application_id)["status"] == "approved"


def test_a_forged_signature_is_rejected():
    prepared = approvals_tool.prepare_application(
        "citizen_3", "Demo", "pm_mudra_kishor", "PM MUDRA - Kishor", 150000)
    application_id = prepared["value"]["application_id"]

    jwk, _ = _sign("something else entirely")
    _, signature = _sign("and a signature over different text")

    result = approvals_tool.submit_signature(application_id, "officer_1", None, jwk, signature)
    assert result["status"] == "unavailable"
    assert db.get_application(application_id)["status"] == "prepared"


def test_a_signature_cannot_be_replayed_onto_another_application():
    first = approvals_tool.prepare_application(
        "citizen_4", "Demo", "pm_mudra_kishor", "PM MUDRA - Kishor", 150000)
    second = approvals_tool.prepare_application(
        "citizen_5", "Demo", "pm_mudra_kishor", "PM MUDRA - Kishor", 150000)

    payload = approvals_tool.signing_payload_for(first["value"]["application_id"])["value"]["payload"]
    jwk, signature = _sign(payload)

    result = approvals_tool.submit_signature(
        second["value"]["application_id"], "officer_1", None, jwk, signature)
    assert result["status"] == "unavailable"


# ------------------------------------------------------------- audit log

def test_the_audit_chain_catches_an_edited_row():
    db.log("user:test", "test.one", {"n": 1})
    db.log("user:test", "test.two", {"n": 2})
    db.log("user:test", "test.three", {"n": 3})

    assert audit.verify_chain(db.audit_rows())["intact"] is True

    rows = db.audit_rows()
    db.tamper_with_audit_row(rows[1]["id"], {"n": "changed"})

    verdict = audit.verify_chain(db.audit_rows())
    assert verdict["intact"] is False
    assert verdict["broken_at_row"] == 2
