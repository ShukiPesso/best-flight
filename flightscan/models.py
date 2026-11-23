"""Leg records shared by all providers (plain dicts so they serialize to JSON)."""
from __future__ import annotations

import datetime as dt
import re

from . import airports

UTC = dt.timezone.utc


def local_to_utc(code: str, local: dt.datetime) -> dt.datetime:
    if local.tzinfo is None:
        local = local.replace(tzinfo=airports.get(code).zone)
    return local.astimezone(UTC)


def make_leg(*, provider: str, dep_code: str, arr_code: str,
             dep_local: dt.datetime, arr_local: dt.datetime,
             airline: str, airline_code: str | None, flight_numbers: list[str],
             price: float, currency: str, seller: str | None, seller_is_airline: bool | None,
             duration_min: int | None = None, aircraft: str | None = None,
             bags: dict | None = None, booking_token: str | None = None,
             fare_name: str | None = None) -> dict:
    dep_utc = local_to_utc(dep_code, dep_local)
    arr_utc = local_to_utc(arr_code, arr_local)
    if duration_min is None:
        duration_min = int((arr_utc - dep_utc).total_seconds() // 60)
    return {
        "id": f"{'+'.join(flight_numbers)}|{dep_local.strftime('%Y-%m-%dT%H:%M')}",
        "provider": provider,
        "dep": dep_code,
        "arr": arr_code,
        "dep_local": dep_local.replace(tzinfo=None).isoformat(timespec="minutes"),
        "arr_local": arr_local.replace(tzinfo=None).isoformat(timespec="minutes"),
        "dep_utc": dep_utc.isoformat(),
        "arr_utc": arr_utc.isoformat(),
        "duration_min": duration_min,
        "airline": airline,
        "airline_code": airline_code,
        "flight_numbers": flight_numbers,
        "aircraft": aircraft,
        "price": round(float(price), 2),
        "currency": currency,
        "seller": seller,
        "seller_is_airline": seller_is_airline,
        "fare_name": fare_name,
        "bags": bags or empty_bags(),
        "booking_token": booking_token,
    }


def empty_bags() -> dict:
    # True = included, False = not included (paid extra), None = unknown
    return {"personal_item": True, "carry_on": None, "checked": None, "notes": []}


_NOT_INCL = re.compile(r"not included|for a fee|fee|paid|extra|\$|€|₪|ILS|EUR|USD", re.I)
_FREE = re.compile(r"\bfree\b|included|\b0\b", re.I)


def parse_bag_texts(texts: list[str], bags: dict | None = None) -> dict:
    """Best-effort parse of Google Flights baggage strings (English)."""
    bags = bags or empty_bags()
    for t in texts:
        if not t:
            continue
        low = t.lower()
        if t not in bags["notes"]:
            bags["notes"].append(t)
        target = None
        if "carry-on" in low or "carry on" in low or "cabin bag" in low or "overhead" in low:
            target = "carry_on"
        elif "checked" in low or "baggage" in low or "bag" in low:
            target = "checked"
        if not target:
            continue
        if _FREE.search(low) and not re.search(r"not included", low):
            bags[target] = True
        elif _NOT_INCL.search(low):
            bags[target] = False
    return bags


def nights(out_leg: dict, ret_leg: dict) -> int:
    d0 = dt.date.fromisoformat(out_leg["dep_local"][:10])
    d1 = dt.date.fromisoformat(ret_leg["dep_local"][:10])
    return (d1 - d0).days
