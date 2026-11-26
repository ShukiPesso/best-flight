import datetime as dt

from flightscan.providers import serpapi as sp

SEARCH = {"best_flights": [{
    "flights": [{"departure_airport": {"id": "TLV", "time": "2027-01-10 08:00"},
                 "arrival_airport": {"id": "ATH", "time": "2027-01-10 10:10"},
                 "duration": 130, "airline": "Wizz Air", "flight_number": "W6 2329"}],
    "layovers": [], "price": 310, "extensions": ["Checked baggage for a fee"],
    "booking_token": "tok"}],
    "other_flights": [{
        "flights": [{"departure_airport": {"id": "TLV", "time": "2027-01-10 06:00"},
                     "arrival_airport": {"id": "SOF", "time": "2027-01-10 08:00"}},
                    {"departure_airport": {"id": "SOF", "time": "2027-01-10 09:00"},
                     "arrival_airport": {"id": "ATH", "time": "2027-01-10 10:00"}}],
        "layovers": [{"id": "SOF"}], "price": 100}]}

BOOK = {"baggage_prices": {"together": ["1 free carry-on"]},
        "booking_options": [
            {"together": {"book_with": "Kiwi.com", "price": 280}},
            {"together": {"book_with": "Wizz Air", "airline": True, "price": 340,
                          "option_title": "Basic", "baggage_prices": ["1st checked bag: 150 ILS"]}},
            {"together": {"book_with": "Wizz Air", "airline": True, "price": 420,
                          "option_title": "Smart"}}]}


class R:
    def __init__(self, j):
        self.status_code, self._j, self.text = 200, j, ""

    def json(self):
        return self._j

    def raise_for_status(self):
        pass


def test_search_and_verify(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "x")
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        return R(BOOK if "booking_token" in params else SEARCH)

    monkeypatch.setattr(sp.requests, "get", fake_get)
    p = sp.SerpApiProvider({"daily_search_budget": 5, "daily_verify_budget": 5}, "ILS")
    legs = p.search(["TLV", "ETM"], "ATH", dt.date(2027, 1, 10))
    assert len(legs) == 1  # connecting itinerary dropped
    leg = legs[0]
    assert calls[0]["departure_id"] == "TLV,ETM" and calls[0]["stops"] == 1
    assert leg["airline_code"] == "W6" and leg["bags"]["checked"] is False
    assert leg["seller_is_airline"] is None
    res = p.verify(leg)
    assert res["price"] == 340 and res["seller"] == "Wizz Air"  # agency price ignored
    assert res["fare_name"] == "Basic" and len(res["fares"]) == 2
    assert res["bags"]["carry_on"] is True and res["bags"]["checked"] is False


def test_auto_budget_spreads_quota(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "x")
    monkeypatch.setattr(sp.requests, "get", lambda url, params, timeout: R(
        {"plan_renewal_date": "2026-12-23", "total_searches_left": 115}))
    p = sp.SerpApiProvider({"auto_budget": True, "reserve": 3, "daily_verify_budget": 1}, "ILS")
    p.auto_budget(dt.date(2026, 11, 26))
    # (115 - 3) // 28 runs = 4 -> 3 searches + 1 verify
    assert (p.search_budget, p.verify_budget) == (3, 1)


def test_auto_budget_off_keeps_config(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "x")
    p = sp.SerpApiProvider({"daily_search_budget": 6, "daily_verify_budget": 2}, "ILS")
    p.auto_budget(dt.date(2026, 11, 26))
    assert (p.search_budget, p.verify_budget) == (6, 2)
