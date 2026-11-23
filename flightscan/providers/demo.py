"""Synthetic flights for trying the system without API keys (`--demo`).

The prices and schedules are made up; the output is flagged as demo data
and the web page shows a banner.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from .. import airports
from ..models import make_leg
from .base import Provider

_AIRLINES = [("W6", "Wizz Air", False), ("LY", "EL AL", True), ("6H", "Israir", True),
             ("IZ", "Arkia", True), ("A3", "Aegean", True)]


def _h(*parts) -> int:
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest(), 16)


class DemoProvider(Provider):
    name = "demo"
    airline_direct = True

    def __init__(self, cfg: dict, currency: str):
        super().__init__({"daily_search_budget": 10**6})
        self.currency = currency

    def search(self, origins, dest, day):
        self.searches_used += 1
        legs = []
        for origin in origins:
            israel_side = origin if airports.get(origin).israel else dest
            if israel_side == "ETM" and _h(dest, "etm") % 3:
                continue  # most destinations have no Ramon flights
            for i in range(_h(origin, dest, day) % 3):
                code, name, full = _AIRLINES[_h(origin, dest, i) % len(_AIRLINES)]
                hour = 5 + _h(origin, dest, day, i) % 17
                dep = dt.datetime.combine(day, dt.time(hour, 5 * (_h(day, i) % 12)))
                dur = 120 + _h(origin, dest) % 150
                dep_utc = dep.replace(tzinfo=airports.get(origin).zone)
                arr = (dep_utc + dt.timedelta(minutes=dur)).astimezone(airports.get(dest).zone)
                price = 250 + _h(origin, dest, day, i, "p") % 900
                legs.append(make_leg(
                    provider=self.name, dep_code=origin, arr_code=dest,
                    dep_local=dep, arr_local=arr.replace(tzinfo=None),
                    airline=name, airline_code=code,
                    flight_numbers=[f"{code} {100 + _h(origin, dest, i) % 800}"],
                    duration_min=dur, price=price, currency=self.currency,
                    seller=name, seller_is_airline=True, fare_name="Basic",
                    bags={"personal_item": True, "carry_on": full, "checked": False,
                          "notes": ["נתוני הדגמה"]},
                ))
        return legs
