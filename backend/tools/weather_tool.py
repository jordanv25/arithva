"""Weather and Local Pulse.

Forecast comes from Open-Meteo. Advice comes from the deterministic bands in
data/events_kalaburagi.json. The model does not decide what weather means for
a business; it reads out what the rules say.

Open-Meteo's free tier is non-commercial. Fine for a prototype; a real product
needs a licence, self-hosting, or IMD data.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from .registry import load_data, ok, unavailable

KALABURAGI = {"lat": 17.3297, "lon": 76.8343, "name": "Kalaburagi"}
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 8.0


def _advice_for(temp_c: float | None, rain_pct: float | None) -> list[str]:
    """Look up advice bands. Deterministic: same inputs, same words, every time."""
    rules = load_data("events_kalaburagi.json")["advice_rules"]
    notes: list[str] = []

    if temp_c is not None:
        for band in rules["temperature_c"]:
            low, high = band.get("min"), band.get("max")
            if (low is None or temp_c >= low) and (high is None or temp_c < high):
                notes.append(band["text"])
                break

    if rain_pct is not None:
        for band in rules["rain_probability_pct"]:
            low, high = band.get("min"), band.get("max")
            if (low is None or rain_pct >= low) and (high is None or rain_pct < high):
                notes.append(band["text"])
                break

    return notes


def _season_events(target: date) -> list[dict]:
    """Events whose window covers the target date.

    The windows live in the data file, not here, so adding an event is a data
    change. Month granularity only.
    """
    events = load_data("events_kalaburagi.json")["events"]
    month = target.month
    hits = []
    for event in events:
        months = event.get("active_months")
        if months and month in months:
            hits.append({
                "name": event["name"],
                "business_effect": event["business_effect"],
                "date_confidence": event["date_confidence"],
                "areas_affected": event["areas_affected"],
            })
    return hits


def _events_with_unconfirmed_dates() -> list[dict]:
    """Events we know happen but cannot place on a calendar.

    The Urs and Ramzan move with the lunar calendar; the Jatra is set by a
    temple committee. Guessing a Gregorian date for any of them would be
    exactly the invented number this project refuses to produce, so they are
    listed apart, with how to confirm each one.
    """
    events = load_data("events_kalaburagi.json")["events"]
    return [
        {
            "name": event["name"],
            "typical_window": event["typical_window"],
            "business_effect": event["business_effect"],
            "confirm_by": event.get("confirm_by"),
        }
        for event in events
        if event.get("active_months") is None
    ]


def forecast(days_ahead: int = 1, lat: float | None = None, lon: float | None = None,
             place: str | None = None) -> dict:
    """Forecast plus what it means for a small business."""
    if days_ahead < 0 or days_ahead > 6:
        return unavailable("This tool forecasts up to six days ahead.")

    latitude = lat if lat is not None else KALABURAGI["lat"]
    longitude = lon if lon is not None else KALABURAGI["lon"]
    place_name = place or KALABURAGI["name"]
    target = date.today() + timedelta(days=days_ahead)

    try:
        response = httpx.get(
            OPEN_METEO,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "Asia/Kolkata",
                "forecast_days": days_ahead + 1,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        daily = response.json()["daily"]
    except Exception as exc:  # network down, rate limited, shape changed
        # The honest failure path. The agent reads this out; it does not invent
        # a temperature to keep the conversation smooth.
        return unavailable(
            f"The weather service did not answer ({type(exc).__name__}). "
            "I cannot tell you tomorrow's temperature right now.",
            source="Open-Meteo",
        )

    try:
        index = daily["time"].index(target.isoformat())
    except (KeyError, ValueError):
        index = -1

    temp_max = daily["temperature_2m_max"][index]
    temp_min = daily["temperature_2m_min"][index]
    rain_pct = daily["precipitation_probability_max"][index]

    return ok(
        {
            "place": place_name,
            "date": target.isoformat(),
            "temp_max_c": temp_max,
            "temp_min_c": temp_min,
            "rain_probability_pct": rain_pct,
            "advice": _advice_for(temp_max, rain_pct),
            "local_events": _season_events(target),
            "events_with_unconfirmed_dates": _events_with_unconfirmed_dates(),
        },
        source="Open-Meteo forecast; advice bands from Arithva's curated rules file",
        source_url="https://open-meteo.com/",
        confidence=(
            "Open-Meteo's free tier is non-commercial. Advice bands are our own design "
            "values, not official guidance. Event dates need local confirmation."
        ),
    )
