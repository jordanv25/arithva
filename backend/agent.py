"""The agent: turn speech into a tool call, then read the result back.

Deliberately rule-based. An LLM is optional and only ever used for the one
job it is good at here, which is working out what the user meant. It never
produces a number, a rule or an amount: those come from tools.

Running without any API key is the default, so a live demo cannot fail because
a model endpoint is slow or a key expired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .tools import approvals_tool, jobs_tool, loan_tool, scheme_tool, weather_tool
from .tools.money import speak_rupees, rupees_to_paise


@dataclass
class Intent:
    name: str
    slots: dict[str, Any] = field(default_factory=dict)
    confidence: str = "high"


# Keywords in the three languages the prototype handles. Transliterated Kannada
# and Hindi are included because that is how people actually type and how
# speech-to-text often returns mixed speech.
KEYWORDS = {
    "weather": [
        "weather", "hot", "heat", "rain", "temperature", "tomorrow", "today",
        "bisilu", "male", "garmi", "barish", "mausam", "naale", "havamana",
    ],
    "scheme": [
        "scheme", "subsidy", "yojana", "government help", "loan scheme", "eligible",
        "yojane", "sarkari", "madad", "sahaya", "which loan", "what help",
    ],
    "loan": [
        "emi", "instalment", "installment", "interest", "repay", "monthly payment",
        "kistu", "kist", "bank loan", "how much per month", "sala",
    ],
    "job_post": [
        "i need", "need workers", "need helpers", "hire", "looking for workers",
        "beku", "chahiye", "kelasagara", "mazdoor",
    ],
    "job_find": [
        "find work", "find me work", "find job", "find me a job", "need work",
        "looking for work", "any job", "work as a", "work as an", "job near",
        "kelasa", "kaam", "naukri",
    ],
    "apply": ["apply", "application", "submit", "arji", "avedan"],
}

TRADES = [
    "painter", "mason", "plumber", "electrician", "carpenter", "welder",
    "tailor", "driver", "helper", "cook", "cleaner", "labourer", "fitter", "loader",
]


def _contains(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def _extract_amount_inr(text: str) -> float | None:
    """Pull a rupee amount out of speech, handling lakh and crore.

    '1.5 lakh', 'one lakh fifty thousand', '150000' and 'Rs 50,000' all occur in
    real speech. Only the numeric forms are handled here; a worded amount falls
    through so the agent asks rather than guesses.
    """
    lowered = text.lower().replace(",", "")

    match = re.search(r"(\d+(?:\.\d+)?)\s*(crore|cr)\b", lowered)
    if match:
        return float(match.group(1)) * 10_000_000

    match = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|lakhs)\b", lowered)
    if match:
        return float(match.group(1)) * 100_000

    match = re.search(r"(\d+(?:\.\d+)?)\s*(thousand|k)\b", lowered)
    if match:
        return float(match.group(1)) * 1_000

    # "Rs 800" and "800 rupees" are both common; so is "at 800 a day".
    match = re.search(r"(?:rs\.?|rupees|inr|₹)\s*(\d+(?:\.\d+)?)", lowered)
    if match:
        return float(match.group(1))

    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:rs\.?|rupees|inr)\b", lowered)
    if match:
        return float(match.group(1))

    match = re.search(r"\bat\s+(\d{3,})\b", lowered)
    if match:
        return float(match.group(1))

    numbers = re.findall(r"\b(\d{4,})\b", lowered)
    if numbers:
        return float(numbers[0])
    return None


def _extract_int(text: str, words: list[str]) -> int | None:
    lowered = text.lower()
    for word in words:
        match = re.search(rf"(\d+)\s*{word}", lowered)
        if match:
            return int(match.group(1))
    return None


def _extract_trade(text: str) -> str | None:
    lowered = text.lower()
    for trade in TRADES:
        if trade in lowered:
            return trade
    return None


def classify(text: str) -> Intent:
    """Work out what the user wants. Keyword rules, checked most specific first."""
    lowered = text.lower()

    if _contains(lowered, KEYWORDS["job_post"]) and _extract_trade(lowered):
        return Intent("job_post", {
            "trade": _extract_trade(lowered),
            "workers_needed": _extract_int(lowered, TRADES + ["workers", "helpers", "people"]) or 1,
            "days": _extract_int(lowered, ["day", "days"]) or 1,
            "wage_per_day_inr": _extract_amount_inr(lowered),
        })

    if _contains(lowered, KEYWORDS["job_find"]):
        return Intent("job_find", {"trade": _extract_trade(lowered)})

    if _contains(lowered, KEYWORDS["apply"]):
        return Intent("apply", {"amount_inr": _extract_amount_inr(lowered)})

    if _contains(lowered, KEYWORDS["loan"]) or ("loan" in lowered and _extract_amount_inr(lowered)):
        return Intent("loan", {
            "amount_inr": _extract_amount_inr(lowered),
            "tenure_months": _extract_int(lowered, ["month", "months"])
            or (_extract_int(lowered, ["year", "years"]) or 0) * 12 or None,
        })

    if _contains(lowered, KEYWORDS["scheme"]):
        return Intent("scheme", {"amount_needed_inr": _extract_amount_inr(lowered)})

    if _contains(lowered, KEYWORDS["weather"]):
        days = 1 if any(w in lowered for w in ["tomorrow", "naale", "kal"]) else 0
        return Intent("weather", {"days_ahead": days})

    return Intent("unknown", {}, confidence="low")


# --------------------------------------------------------------- read-backs

def read_back(intent: Intent, result: dict) -> str:
    """What the assistant says out loud.

    Every number in these sentences comes from the tool result. Nothing is
    computed or embellished here.
    """
    if result["status"] == "unavailable":
        return result["reason"]
    if result["status"] == "refused":
        return result["reason"]

    value = result["value"]

    if intent.name == "weather":
        lines = [
            f"In {value['place']} on {value['date']}, the high is {value['temp_max_c']} degrees "
            f"and the low {value['temp_min_c']}, with a {value['rain_probability_pct']} percent "
            "chance of rain."
        ]
        lines.extend(value["advice"])
        for event in value["local_events"]:
            lines.append(f"{event['name']}: {event['business_effect']}")
        return " ".join(lines)

    if intent.name == "scheme":
        eligible = value["eligible"]
        if not eligible:
            return (
                f"I checked {value['checked_count']} schemes and none of them fit what you told me. "
                "Tell me more about your trade and how much you need, and I will check again."
            )
        names = ", ".join(s["name"] for s in eligible)
        first = eligible[0]
        return (
            f"You may be eligible for {len(eligible)} of the {value['checked_count']} schemes I checked: {names}. "
            f"Take {first['name']}: {first['reasons'][0]} "
            f"You would need {len(first['documents'])} documents. "
            "This is indicative. Confirm at your Common Service Centre before applying."
        )

    if intent.name == "loan":
        return (
            f"For {speak_rupees(rupees_to_paise(float(value['principal_inr'].replace(',', ''))))} "
            f"over {value['tenure_months']} months at {value['annual_rate_pct']} percent a year, "
            f"the monthly instalment is {value['emi_spoken']}. "
            f"Total interest over the whole loan is {value['total_interest_spoken']}. "
            + ("That rate is an assumed figure, not a quote from any lender."
               if value["rate_is_assumed"] else "")
        )

    if intent.name == "job_post":
        wage = value["wage_check"]
        count = value["workers_needed"]
        line = (
            f"Posted: {count} {value['trade']}{'s' if count != 1 else ''} "
            f"for {value['days']} day{'s' if value['days'] != 1 else ''} "
            f"at {value['wage_per_day_inr']:,.0f} rupees a day in {value['area']}."
        )
        if wage.get("below_minimum"):
            line += " " + wage["flag"] + " You can still post it, but I want you to know."
        return line

    if intent.name == "job_find":
        jobs = value.get("jobs", [])
        if not jobs:
            return value.get("note", "There are no open jobs matching that right now.")
        first = jobs[0]
        return (
            f"I found {len(jobs)} job{'s' if len(jobs) > 1 else ''}. "
            f"The closest match: {first['workers_needed']} {first['trade']} needed in {first['area']}, "
            f"{first['days']} day{'s' if first['days'] > 1 else ''} at {first['wage_per_day_inr']:,.0f} rupees a day. "
            "Your phone number stays hidden until the employer accepts."
        )

    if intent.name == "apply":
        quorum = value["quorum"]
        return (
            f"I have prepared an application for {value['scheme']} for {value['amount_spoken']}. "
            f"It needs {quorum['description']} officer signatures because the amount falls in the "
            f"{quorum['band']} band"
            + (f" and {len(quorum['risk_flags_applied'])} risk flag applies."
               if quorum["risk_flags_applied"] else ".")
            + " I cannot approve this myself. It is now with the officers."
        )

    return "Done."


def confirmation_for(intent: Intent) -> str | None:
    """The sentence the user must say yes to, for anything that changes state.

    Read-only questions get no confirmation step: asking the weather should not
    require ceremony. Anything that writes a record does.
    """
    if intent.name == "job_post":
        slots = intent.slots
        if not slots.get("wage_per_day_inr"):
            return None
        count = slots.get("workers_needed", 1)
        days = slots.get("days", 1)
        trade = slots.get("trade", "worker")
        return (
            f"Shall I post {count} {trade}{'s' if count != 1 else ''} "
            f"for {days} day{'s' if days != 1 else ''} at "
            f"{slots['wage_per_day_inr']:,.0f} rupees a day? Say yes to post it."
        )
    if intent.name == "apply":
        amount = intent.slots.get("amount_inr")
        if not amount:
            return None
        return (
            f"Shall I prepare an application for {speak_rupees(rupees_to_paise(amount))}? "
            "It will go to officers for signing. Say yes to prepare it."
        )
    return None


def handle(text: str, context: dict | None = None) -> dict:
    """Route one utterance: classify, call a tool, build the spoken reply."""
    context = context or {}
    intent = classify(text)

    if intent.name == "unknown":
        return {
            "intent": "unknown",
            "needs_confirmation": False,
            "spoken": (
                "I did not catch that. You can ask about the weather for your business, "
                "which government scheme fits you, what a loan would cost each month, "
                "or posting and finding work nearby."
            ),
            "tool_result": None,
        }

    confirmation = confirmation_for(intent)
    if confirmation and not context.get("confirmed"):
        return {
            "intent": intent.name,
            "slots": intent.slots,
            "needs_confirmation": True,
            "spoken": confirmation,
            "tool_result": None,
        }

    result = _call_tool(intent, context)
    return {
        "intent": intent.name,
        "slots": intent.slots,
        "needs_confirmation": False,
        "spoken": read_back(intent, result),
        "tool_result": result,
    }


def _call_tool(intent: Intent, context: dict) -> dict:
    """Dispatch to the one tool this intent needs."""
    slots = intent.slots

    if intent.name == "weather":
        return weather_tool.forecast(days_ahead=slots.get("days_ahead", 1))

    if intent.name == "scheme":
        profile = {
            "age": context.get("age", 30),
            "trade": context.get("trade"),
            "business_status": context.get("business_status", "new"),
            "amount_needed_inr": slots.get("amount_needed_inr") or context.get("amount_needed_inr"),
        }
        return scheme_tool.find_schemes(profile)

    if intent.name == "loan":
        amount = slots.get("amount_inr") or context.get("amount_inr")
        if not amount:
            return {
                "status": "unavailable",
                "reason": "Tell me how much you want to borrow and I will work out the instalment.",
                "as_of": None,
            }
        return loan_tool.calculate_emi(
            amount_inr=amount,
            tenure_months=slots.get("tenure_months") or 36,
        )

    if intent.name == "job_post":
        if not slots.get("wage_per_day_inr"):
            return {
                "status": "unavailable",
                "reason": "Tell me the daily wage you are offering and I will post the job.",
                "as_of": None,
            }
        return jobs_tool.post_job(
            employer_id=context.get("user_id", "demo_employer"),
            trade=slots["trade"],
            workers_needed=slots.get("workers_needed", 1),
            days=slots.get("days", 1),
            wage_per_day_inr=slots["wage_per_day_inr"],
            area=context.get("area", "Kalaburagi"),
        )

    if intent.name == "job_find":
        return jobs_tool.find_jobs(trade=slots.get("trade") or context.get("trade"))

    if intent.name == "apply":
        amount = slots.get("amount_inr") or context.get("amount_inr")
        if not amount:
            return {
                "status": "unavailable",
                "reason": "Tell me how much you are applying for.",
                "as_of": None,
            }
        return approvals_tool.prepare_application(
            applicant_id=context.get("user_id", "demo_citizen"),
            applicant_name=context.get("user_name", "Demo applicant"),
            scheme_id=context.get("scheme_id", "pm_mudra_kishor"),
            scheme_name=context.get("scheme_name", "PM MUDRA - Kishor"),
            amount_inr=amount,
            purpose=context.get("purpose"),
        )

    return {"status": "unavailable", "reason": "No tool handles that yet.", "as_of": None}
