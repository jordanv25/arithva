"""Money arithmetic in integer paise.

Every rupee figure in Arithva passes through this module. Nothing here uses
floats, and the language model never calls any of it directly with its own
numbers: the agent passes user-supplied values in, and the result that comes
back is what gets spoken. That is the whole point of the "tools decide" rule.
"""

from __future__ import annotations

from dataclasses import dataclass

PAISE_PER_RUPEE = 100


def rupees_to_paise(rupees: float | int | str) -> int:
    """Convert a rupee amount to integer paise, rounding half up."""
    from decimal import Decimal, ROUND_HALF_UP

    value = Decimal(str(rupees)) * PAISE_PER_RUPEE
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees_str(paise: int) -> str:
    """Format paise as a plain rupee string, e.g. 15000000 -> '1,50,000.00'."""
    negative = paise < 0
    paise = abs(paise)
    rupees, remainder = divmod(paise, PAISE_PER_RUPEE)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        formatted = ",".join(parts) + "," + tail
    else:
        formatted = digits
    sign = "-" if negative else ""
    return f"{sign}{formatted}.{remainder:02d}"


def speak_rupees(paise: int) -> str:
    """Render an amount the way people say it aloud in India.

    15000000 paise -> 'one lakh fifty thousand rupees'. The spoken form matters:
    a user who hears '150,000' read as 'one hundred fifty thousand' has to stop
    and convert it in their head.
    """
    rupees = paise // PAISE_PER_RUPEE
    if rupees == 0:
        return "zero rupees"

    crore, rest = divmod(rupees, 10_000_000)
    lakh, rest = divmod(rest, 100_000)
    thousand, rest = divmod(rest, 1_000)
    hundred, rest = divmod(rest, 100)

    parts: list[str] = []
    if crore:
        parts.append(f"{_words(crore)} crore")
    if lakh:
        parts.append(f"{_words(lakh)} lakh")
    if thousand:
        parts.append(f"{_words(thousand)} thousand")
    if hundred:
        parts.append(f"{_words(hundred)} hundred")
    if rest:
        parts.append(_words(rest))
    return " ".join(parts) + " rupees"


_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]


def _words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")
    hundreds, rest = divmod(n, 100)
    out = f"{_ONES[hundreds]} hundred"
    return out + (f" {_words(rest)}" if rest else "")


@dataclass
class EmiSchedule:
    principal_paise: int
    annual_rate_pct: float
    tenure_months: int
    emi_paise: int
    total_payment_paise: int
    total_interest_paise: int
    first_row: dict
    last_row: dict


def compute_emi(principal_paise: int, annual_rate_pct: float, tenure_months: int,
                moratorium_months: int = 0) -> EmiSchedule:
    """Standard reducing-balance EMI, computed in paise.

    Interest during a moratorium is accrued and added to the principal before
    the EMI is worked out, which is the common convention for these schemes.
    The moratorium convention is a design decision and is stated in the output
    rather than hidden.
    """
    if principal_paise <= 0:
        raise ValueError("principal must be positive")
    if tenure_months <= 0:
        raise ValueError("tenure must be at least one month")

    monthly_rate = annual_rate_pct / 12 / 100

    balance = principal_paise
    for _ in range(moratorium_months):
        balance += round(balance * monthly_rate)

    if monthly_rate == 0:
        emi = -(-balance // tenure_months)
    else:
        factor = (1 + monthly_rate) ** tenure_months
        emi = round(balance * monthly_rate * factor / (factor - 1))

    # Walk the schedule so the totals are the real sum of real rows, not a
    # formula that drifts a few paise from what the borrower actually pays.
    rows = []
    remaining = balance
    total_paid = 0
    for month in range(1, tenure_months + 1):
        interest = round(remaining * monthly_rate)
        principal_part = emi - interest
        if month == tenure_months:
            principal_part = remaining
            payment = remaining + interest
        else:
            payment = emi
        remaining -= principal_part
        total_paid += payment
        rows.append({
            "month": month,
            "payment_paise": payment,
            "interest_paise": interest,
            "principal_paise": principal_part,
            "balance_paise": max(remaining, 0),
        })

    return EmiSchedule(
        principal_paise=principal_paise,
        annual_rate_pct=annual_rate_pct,
        tenure_months=tenure_months,
        emi_paise=emi,
        total_payment_paise=total_paid,
        total_interest_paise=total_paid - balance,
        first_row=rows[0],
        last_row=rows[-1],
    )
