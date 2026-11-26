"""SerpApi Google Flights provider.

Google Flights' headline price can come from an online travel agency, so this
provider marks its prices as unverified. `verify()` calls the booking-options
endpoint and keeps only offers sold by the airline itself (`airline: true`),
which also returns the fare name and baggage rules.
"""
from __future__ import annotations

import datetime as dt
import logging
import os

import requests

from ..models import make_leg, parse_bag_texts, empty_bags
from .base import Provider, ProviderError

URL = "https://serpapi.com/search.json"
log = logging.getLogger("flightscan")


def _code(flight_number: str) -> str | None:
    parts = (flight_number or "").split()
    return parts[0] if parts else None


class SerpApiProvider(Provider):
    name = "serpapi"
    airline_direct = False

    def __init__(self, cfg: dict, currency: str):
        super().__init__(cfg)
        self.key = os.environ.get("SERPAPI_KEY", "")
        self.currency = currency

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get("SERPAPI_KEY"))

    def auto_budget(self, today: dt.date) -> None:
        """Spread the plan's remaining searches evenly until the renewal date.

        Uses SerpApi's free Account API (does not count as a search). The
        configured daily budgets become caps only when auto_budget is off.
        """
        if not self.cfg.get("auto_budget"):
            return
        try:
            r = requests.get("https://serpapi.com/account.json",
                             params={"api_key": self.key}, timeout=30)
            r.raise_for_status()
            acc = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("SerpApi account lookup failed (%s); using configured budgets", e)
            return
        left = int(acc.get("total_searches_left") or acc.get("plan_searches_left") or 0)
        renewal = acc.get("plan_renewal_date")
        if renewal:
            reset = dt.date.fromisoformat(renewal)
        else:  # fall back to the configured day of month
            day = int(self.cfg.get("quota_reset_day", 1))
            reset = today.replace(day=min(day, 28))
            if reset <= today:
                reset = (reset.replace(day=1) + dt.timedelta(days=32)).replace(day=min(day, 28))
        # runs left in this cycle, counting the renewal day itself to be safe
        runs = max(1, (reset - today).days + 1)
        usable = max(0, left - int(self.cfg.get("reserve", 3)))
        total = usable // runs
        self.verify_budget = min(int(self.cfg.get("daily_verify_budget", 1)), total // 4)
        self.search_budget = total - self.verify_budget
        log.info("SerpApi quota: %d left, renewal %s, %d runs -> %d searches + %d verifies today",
                 left, reset, runs, self.search_budget, self.verify_budget)

    def _get(self, params: dict) -> dict:
        params = {"engine": "google_flights", "api_key": self.key, "hl": "en", "gl": "il",
                  "currency": self.currency, **params}
        r = requests.get(URL, params=params, timeout=90)
        if r.status_code != 200:
            raise ProviderError(f"SerpApi HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        if data.get("error") and "hasn't returned any results" not in data["error"]:
            raise ProviderError(f"SerpApi: {data['error']}")
        return data

    def _base_params(self, origins, dest, day):
        return {"type": 2, "departure_id": ",".join(origins), "arrival_id": dest,
                "outbound_date": day.isoformat(), "stops": 1, "adults": 1}

    def search(self, origins: list[str], dest: str, day: dt.date) -> list[dict]:
        self.searches_used += 1
        data = self._get(self._base_params(origins, dest, day))
        legs = []
        for it in (data.get("best_flights") or []) + (data.get("other_flights") or []):
            segs = it.get("flights") or []
            if len(segs) != 1 or it.get("layovers"):
                continue  # nonstop only
            s = segs[0]
            dep, arr = s["departure_airport"], s["arrival_airport"]
            bags = parse_bag_texts(list(it.get("extensions") or []), empty_bags())
            legs.append(make_leg(
                provider=self.name, dep_code=dep["id"], arr_code=arr["id"],
                dep_local=dt.datetime.strptime(dep["time"], "%Y-%m-%d %H:%M"),
                arr_local=dt.datetime.strptime(arr["time"], "%Y-%m-%d %H:%M"),
                airline=s.get("airline", ""), airline_code=_code(s.get("flight_number")),
                flight_numbers=[s.get("flight_number", "?")], aircraft=s.get("airplane"),
                duration_min=s.get("duration"), price=it.get("price") or 0,
                currency=self.currency, seller=None, seller_is_airline=None,
                bags=bags, booking_token=it.get("booking_token"),
            ))
            legs[-1]["_query"] = {"origins": origins, "dest": dest, "day": day.isoformat()}
        return [l for l in legs if l["price"] > 0]

    def can_verify(self) -> bool:
        return self.verifies_used < self.verify_budget

    def verify(self, leg: dict) -> dict | None:
        """Return {"price","seller","fare_name","bags","fares":[...]} for the
        airline's own offer, or {"no_airline_offer": True}."""
        if not leg.get("booking_token") or not leg.get("_query"):
            return None
        q = leg["_query"]
        self.verifies_used += 1
        params = self._base_params(q["origins"], q["dest"], dt.date.fromisoformat(q["day"]))
        params["booking_token"] = leg["booking_token"]
        data = self._get(params)
        top_bags = (data.get("baggage_prices") or {}).get("together") or []
        fares = []
        for opt in data.get("booking_options") or []:
            t = opt.get("together") or {}
            if opt.get("separate_tickets") or not t.get("airline") or not t.get("price"):
                continue
            bags = parse_bag_texts(list(t.get("baggage_prices") or []) + list(top_bags)
                                   + list(t.get("extensions") or []), empty_bags())
            fares.append({"price": float(t["price"]), "seller": t.get("book_with"),
                          "fare_name": t.get("option_title"), "bags": bags})
        if not fares:
            return {"no_airline_offer": True}
        fares.sort(key=lambda f: f["price"])
        best = dict(fares[0])
        best["fares"] = fares
        return best
