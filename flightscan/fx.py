"""Currency conversion via the free ECB-based Frankfurter API (no key)."""
from __future__ import annotations

import functools

import requests


@functools.lru_cache(maxsize=32)
def rate(src: str, dst: str) -> float:
    if src == dst:
        return 1.0
    r = requests.get("https://api.frankfurter.dev/v1/latest",
                     params={"base": src, "symbols": dst}, timeout=20)
    r.raise_for_status()
    return float(r.json()["rates"][dst])


def convert(amount: float, src: str, dst: str) -> float:
    return amount * rate(src, dst)
