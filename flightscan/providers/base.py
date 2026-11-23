from __future__ import annotations

import datetime as dt


class ProviderError(Exception):
    pass


class Provider:
    """A flight source. One `search` call == one paid API search.

    search() returns nonstop one-way legs from any of `origins` to `dest` on
    `day` (local date at the departure airport).
    """
    name = "base"
    # True when every price the provider returns is the airline's own price.
    airline_direct = False

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.search_budget = int(cfg.get("daily_search_budget", 0))
        self.verify_budget = int(cfg.get("daily_verify_budget", 0))
        self.searches_used = 0
        self.verifies_used = 0

    # one-way nonstop search
    def search(self, origins: list[str], dest: str, day: dt.date) -> list[dict]:
        raise NotImplementedError

    # optional: confirm the seller/price/bags of a leg (SerpApi booking options)
    def can_verify(self) -> bool:
        return False

    def verify(self, leg: dict) -> dict | None:
        return None

    # how many separate API searches a (origins -> dest) query costs
    def cost(self, origins: list[str]) -> int:
        return 1
