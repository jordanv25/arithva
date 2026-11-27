"""Scheme Navigator: which government schemes fit this applicant.

Eligibility is decided here, by reading the curated rules file. The language
model's only job upstream is to turn speech into the fields this function
takes. If a scheme is not in the rules file, this tool does not know about it,
and says so.
"""

from __future__ import annotations

from .registry import load_data, ok, unavailable


def _matches(scheme: dict, profile: dict) -> tuple[bool, list[str]]:
    """Return (eligible, reasons). Reasons explain the decision either way."""
    rules = scheme["rules"]
    reasons: list[str] = []
    eligible = True

    age = profile.get("age")
    if "min_age" in rules:
        if age is None:
            # An unknown age is not a passing age. Saying "age 30 meets the
            # minimum" when nobody gave an age states a fact about the
            # applicant that we invented, which is the one thing this project
            # refuses to do. Ask instead.
            reasons.append(
                f"This scheme needs you to be at least {rules['min_age']}. "
                "You have not told me your age yet, so I have not checked it."
            )
        elif age < rules["min_age"]:
            eligible = False
            reasons.append(f"Minimum age for this scheme is {rules['min_age']}; you gave {age}.")
        else:
            reasons.append(f"Age {age} meets the minimum of {rules['min_age']}.")

    if rules.get("new_business_only") and profile.get("business_status") == "existing":
        eligible = False
        reasons.append("This scheme funds new units only, and you said the business already runs.")
    elif rules.get("new_business_only"):
        reasons.append("This scheme funds new units, which matches what you described.")

    if rules.get("street_vendor_only"):
        if profile.get("trade") != "street_vendor" and profile.get("business_type") != "street_vendor":
            eligible = False
            reasons.append("This scheme is only for registered street vendors.")
        else:
            reasons.append("You described street vending, which this scheme covers.")

    if rules.get("traditional_trade_required"):
        trade = (profile.get("trade") or "").strip().lower()
        allowed = [t.lower() for t in scheme.get("eligible_trades", [])]
        if not trade:
            reasons.append("This scheme needs a listed traditional trade; you have not told us your trade yet.")
            eligible = False
        elif trade not in allowed:
            eligible = False
            reasons.append(f"'{profile.get('trade')}' is not in this scheme's list of traditional trades.")
        else:
            reasons.append(f"'{profile.get('trade')}' is a listed traditional trade.")

    amount = profile.get("amount_needed_inr")
    if amount is not None:
        max_loan = rules.get("max_loan_inr")
        min_loan = rules.get("min_loan_inr")
        if max_loan is not None and amount > max_loan:
            eligible = False
            reasons.append(f"You asked for Rs {amount:,}, above this scheme's ceiling of Rs {max_loan:,}.")
        elif min_loan is not None and amount < min_loan:
            eligible = False
            reasons.append(f"You asked for Rs {amount:,}, below this scheme's floor of Rs {min_loan:,}.")
        elif max_loan is not None:
            reasons.append(f"Rs {amount:,} is within this scheme's ceiling of Rs {max_loan:,}.")

    return eligible, reasons


def find_schemes(profile: dict) -> dict:
    """Match an applicant profile against every scheme in the rules file."""
    data = load_data("schemes.json")
    schemes = data.get("schemes", [])
    if not schemes:
        return unavailable("The scheme rules file is empty.", source="data/schemes.json")

    eligible, not_eligible = [], []
    for scheme in schemes:
        is_eligible, reasons = _matches(scheme, profile)
        entry = {
            "id": scheme["id"],
            "name": scheme["name"],
            "full_name": scheme["full_name"],
            "what_it_gives": scheme["what_it_gives"],
            "reasons": reasons,
            "documents": scheme["documents"],
            "apply_at": scheme["apply_at"],
            "source": scheme["source"],
            "source_url": scheme.get("source_url"),
            "confidence": scheme.get("confidence"),
        }
        (eligible if is_eligible else not_eligible).append(entry)

    return ok(
        {
            "eligible": eligible,
            "not_eligible": not_eligible,
            "checked_count": len(schemes),
        },
        source="Curated scheme rules file, each rule carrying its own source",
        source_url="data/schemes.json",
        confidence="Eligibility here is indicative. Confirm at a Common Service Centre or bank before applying.",
        disclaimer="Arithva does not decide applications. Final eligibility rests with the implementing agency.",
    )


def scheme_documents(scheme_id: str) -> dict:
    """The document checklist for one scheme."""
    data = load_data("schemes.json")
    for scheme in data.get("schemes", []):
        if scheme["id"] == scheme_id:
            return ok(
                {
                    "scheme": scheme["name"],
                    "documents": scheme["documents"],
                    "apply_at": scheme["apply_at"],
                },
                source=scheme["source"],
                source_url=scheme.get("source_url"),
            )
    return unavailable(f"No scheme with id '{scheme_id}' is in the rules file.", source="data/schemes.json")


def nearest_centre(district: str = "kalaburagi") -> dict:
    """Where to go in person. Demo data, labelled as such."""
    data = load_data("schemes.json")
    centres = data.get("nearest_centres", {}).get(district.lower())
    if not centres:
        return unavailable(f"No centre list for district '{district}'.", source="data/schemes.json")
    return ok(
        centres,
        source="SYNTHETIC demo centre list",
        source_url="data/schemes.json",
        confidence="SYNTHETIC: replace with the official CSC locator before real use.",
    )
