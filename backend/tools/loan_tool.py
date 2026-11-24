"""Loan and EMI tool.

Everything here is integer-paise arithmetic from backend/tools/money.py. The
model never performs this calculation; it calls this tool and reads back what
comes out.
"""

from __future__ import annotations

from .money import compute_emi, paise_to_rupees_str, rupees_to_paise, speak_rupees
from .registry import load_data, ok, unavailable

# Indicative rates for the prototype. A real deployment reads the lender's
# current card rate. Stated as a design value so nobody mistakes it for a quote.
DEFAULT_RATE_PCT = 10.5


def calculate_emi(amount_inr: float, tenure_months: int,
                  annual_rate_pct: float | None = None,
                  moratorium_months: int = 0) -> dict:
    """Work out the monthly instalment for a loan."""
    if amount_inr <= 0:
        return unavailable("The loan amount must be more than zero.")
    if tenure_months <= 0:
        return unavailable("The tenure must be at least one month.")
    if tenure_months > 360:
        return unavailable("This tool handles tenures up to 360 months.")

    rate = DEFAULT_RATE_PCT if annual_rate_pct is None else annual_rate_pct
    rate_is_assumed = annual_rate_pct is None

    try:
        schedule = compute_emi(
            principal_paise=rupees_to_paise(amount_inr),
            annual_rate_pct=rate,
            tenure_months=tenure_months,
            moratorium_months=moratorium_months,
        )
    except ValueError as exc:
        return unavailable(str(exc))

    return ok(
        {
            "principal_inr": paise_to_rupees_str(schedule.principal_paise),
            "annual_rate_pct": rate,
            "rate_is_assumed": rate_is_assumed,
            "tenure_months": tenure_months,
            "moratorium_months": moratorium_months,
            "emi_inr": paise_to_rupees_str(schedule.emi_paise),
            "emi_spoken": speak_rupees(schedule.emi_paise),
            "total_payment_inr": paise_to_rupees_str(schedule.total_payment_paise),
            "total_interest_inr": paise_to_rupees_str(schedule.total_interest_paise),
            "total_interest_spoken": speak_rupees(schedule.total_interest_paise),
            "first_instalment": _row(schedule.first_row),
            "last_instalment": _row(schedule.last_row),
        },
        source="Computed in integer paise by Arithva's loan tool (reducing balance)",
        confidence=(
            f"Rate of {rate}% a year is an assumed design value, not a quote from any lender."
            if rate_is_assumed else
            f"Computed at the {rate}% a year you supplied. Confirm the actual rate with the lender."
        ),
        convention=(
            "Interest during any moratorium is accrued and added to the principal "
            "before the instalment is worked out."
        ),
    )


def _row(row: dict) -> dict:
    return {
        "month": row["month"],
        "payment_inr": paise_to_rupees_str(row["payment_paise"]),
        "interest_inr": paise_to_rupees_str(row["interest_paise"]),
        "principal_inr": paise_to_rupees_str(row["principal_paise"]),
        "balance_inr": paise_to_rupees_str(row["balance_paise"]),
    }


def subsidy_estimate(scheme_id: str, project_cost_inr: float,
                     area: str = "rural", category: str = "general") -> dict:
    """Estimate the capital subsidy for a scheme that offers one."""
    data = load_data("schemes.json")
    scheme = next((s for s in data.get("schemes", []) if s["id"] == scheme_id), None)
    if scheme is None:
        return unavailable(f"No scheme with id '{scheme_id}'.", source="data/schemes.json")

    key = f"subsidy_rate_{area.lower()}_{category.lower()}_pct"
    rate = scheme["rules"].get(key)
    if rate is None:
        return unavailable(
            f"{scheme['name']} has no subsidy rate recorded for a {category} applicant in a {area} area.",
            source=scheme["source"],
        )

    cost_paise = rupees_to_paise(project_cost_inr)
    subsidy_paise = cost_paise * rate // 100
    own_key = f"own_contribution_{category.lower()}_pct"
    own_rate = scheme["rules"].get(own_key)
    own_paise = cost_paise * own_rate // 100 if own_rate is not None else None

    value = {
        "scheme": scheme["name"],
        "project_cost_inr": paise_to_rupees_str(cost_paise),
        "subsidy_rate_pct": rate,
        "subsidy_inr": paise_to_rupees_str(subsidy_paise),
        "subsidy_spoken": speak_rupees(subsidy_paise),
    }
    if own_paise is not None:
        value["own_contribution_pct"] = own_rate
        value["own_contribution_inr"] = paise_to_rupees_str(own_paise)
        value["bank_finance_inr"] = paise_to_rupees_str(cost_paise - subsidy_paise - own_paise)

    return ok(
        value,
        source=scheme["source"],
        source_url=scheme.get("source_url"),
        confidence=scheme.get("confidence"),
    )
