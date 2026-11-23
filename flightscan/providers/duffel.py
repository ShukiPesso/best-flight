"""Duffel provider: offers come straight from the airlines (NDC / direct
connections), so the price and baggage allowance are the airline's own."""
from __future__ import annotations

import datetime as dt
import logging
import os

import requests

from ..fx import convert
from ..models import make_leg, empty_bags
from .base import Provider, ProviderError

URL = "https://api.duffel.com/air/offer_requests"


class DuffelProvider(Provider):
    name = "duffel"
    airline_direct = True

    def __init__(self, cfg: dict, currency: str):
        super().__init__(cfg)
        self.token = os.environ.get("DUFFEL_TOKEN", "")
        self.currency = currency

    @classmethod
    def available(cls) -> bool:
        token = os.environ.get("DUFFEL_TOKEN", "")
        if token.startswith("duffel_test_"):
            # test mode returns made-up airlines and prices; never mix them in
            logging.getLogger("flightscan").warning(
                "DUFFEL_TOKEN is a test token (fake data) - Duffel skipped")
            return False
        return bool(token)

    def cost(self, origins):
        return len(origins)

    def _one(self, origin: str, dest: str, day: dt.date) -> list[dict]:
        self.searches_used += 1
        body = {"data": {
            "slices": [{"origin": origin, "destination": dest, "departure_date": day.isoformat()}],
            "passengers": [{"type": "adult"}],
            "cabin_class": "economy",
            "max_connections": 0,
        }}
        r = requests.post(URL, params={"return_offers": "true", "supplier_timeout": 20000},
                          json=body, timeout=90, headers={
                              "Authorization": f"Bearer {self.token}",
                              "Duffel-Version": "v2", "Accept": "application/json",
                              "Accept-Encoding": "gzip"})
        if r.status_code >= 300:
            raise ProviderError(f"Duffel HTTP {r.status_code}: {r.text[:300]}")
        legs = []
        for off in r.json()["data"].get("offers", []):
            owner = off.get("owner") or {}
            if owner.get("iata_code") == "ZZ":  # Duffel Airways (test mode)
                continue
            sl = off["slices"][0]
            if len(sl["segments"]) != 1:
                continue
            seg = sl["segments"][0]
            bags = empty_bags()
            for b in (seg.get("passengers") or [{}])[0].get("baggages", []):
                key = "checked" if b.get("type") == "checked" else "carry_on"
                bags[key] = (b.get("quantity") or 0) > 0
                bags["notes"].append(f"{b.get('type')}: {b.get('quantity')}")
            if bags["checked"] is None:
                bags["checked"] = False
            if bags["carry_on"] is None:
                bags["carry_on"] = False
            mc = seg.get("marketing_carrier") or {}
            fn = f"{mc.get('iata_code', '')} {seg.get('marketing_carrier_flight_number', '')}".strip()
            price = convert(float(off["total_amount"]), off["total_currency"], self.currency)
            legs.append(make_leg(
                provider=self.name, dep_code=seg["origin"]["iata_code"],
                arr_code=seg["destination"]["iata_code"],
                dep_local=dt.datetime.fromisoformat(seg["departing_at"]),
                arr_local=dt.datetime.fromisoformat(seg["arriving_at"]),
                airline=owner.get("name", ""), airline_code=owner.get("iata_code"),
                flight_numbers=[fn], aircraft=(seg.get("aircraft") or {}).get("name"),
                price=price, currency=self.currency, seller=owner.get("name"),
                seller_is_airline=True, bags=bags, fare_name=sl.get("fare_brand_name"),
            ))
        return legs

    def search(self, origins: list[str], dest: str, day: dt.date) -> list[dict]:
        out = []
        for o in origins:
            out += self._one(o, dest, day)
        return out
