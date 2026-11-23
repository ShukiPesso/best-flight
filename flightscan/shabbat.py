"""Shabbat / Yom Tov travel windows, from the Hebcal API (no key needed).

For each airport we build "closed" windows: from candle lighting to the
following havdalah. Hebcal emits a candle-lighting event on every erev
Shabbat / erev Yom Tov (and on the second night of a 2-day Yom Tov), and a
havdalah event only when the holy time ends, so "first candles -> next
havdalah" gives exactly one continuous window for Shabbat, Yom Tov and
Yom Tov adjacent to Shabbat.

A flight leg is allowed when:
  * at the departure airport: leaving home (departure - depart_after_havdalah)
    through landing does not overlap a closed window there, and
  * at the arrival airport: takeoff through landing + arrive_before_candles
    does not overlap a closed window there.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from . import airports

HEBCAL_URL = "https://www.hebcal.com/hebcal"
UTC = dt.timezone.utc


@dataclass(frozen=True)
class Window:
    start: dt.datetime  # candle lighting (aware)
    end: dt.datetime    # havdalah (aware)


def _parse(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).astimezone(UTC)


def windows_from_items(items: list[dict], range_start: dt.datetime) -> list[Window]:
    events = sorted(
        (_parse(i["date"]), i["category"])
        for i in items
        if i.get("category") in ("candles", "havdalah") and "T" in i.get("date", "")
    )
    out: list[Window] = []
    open_start: dt.datetime | None = None
    first = True
    for when, cat in events:
        if cat == "candles":
            if open_start is None:
                open_start = when
        else:  # havdalah
            if open_start is None and first:
                # range began in the middle of Shabbat / Yom Tov
                open_start = range_start
            if open_start is not None:
                out.append(Window(open_start, when))
                open_start = None
        first = False
    if open_start is not None:  # range ends mid-Shabbat: close conservatively
        out.append(Window(open_start, open_start + dt.timedelta(days=3)))
    return out


class ShabbatCalendar:
    def __init__(self, cfg: dict, start: dt.date, end: dt.date, cache_dir: Path | None = None):
        s = cfg.get("shabbat", {})
        self.arrive_buffer = dt.timedelta(hours=float(s.get("arrive_before_candles_hours", 3)))
        self.depart_buffer = dt.timedelta(hours=float(s.get("depart_after_havdalah_hours", 3.5)))
        self.diaspora_abroad = bool(s.get("diaspora_yomtov_abroad", True))
        self.cm_israel = int(s.get("candle_minutes_israel", 20))
        self.cm_abroad = int(s.get("candle_minutes_abroad", 18))
        # a little slack on both sides so trips at the edges are covered
        self.start = start - dt.timedelta(days=3)
        self.end = end + dt.timedelta(days=3)
        self.cache_dir = cache_dir
        self._windows: dict[str, list[Window]] = {}

    # -- fetching -----------------------------------------------------------
    def _fetch(self, code: str) -> list[dict]:
        ap = airports.get(code)
        israel = ap.israel or not self.diaspora_abroad
        params = {
            "v": 1, "cfg": "json", "maj": "on", "min": "off", "mod": "off",
            "nx": "off", "ss": "off", "mf": "off", "c": "on", "M": "on",
            "geo": "pos", "latitude": ap.lat, "longitude": ap.lon, "tzid": ap.tz,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "i": "on" if israel else "off",
            "b": self.cm_israel if ap.israel else self.cm_abroad,
        }
        cache = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache = self.cache_dir / f"hebcal_{code}_{self.start}_{self.end}_{params['i']}.json"
            if cache.exists():
                return json.loads(cache.read_text())
        for attempt in range(3):
            try:
                r = requests.get(HEBCAL_URL, params=params, timeout=30)
                r.raise_for_status()
                items = r.json().get("items", [])
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        if cache:
            cache.write_text(json.dumps(items))
        return items

    def windows(self, code: str) -> list[Window]:
        if code not in self._windows:
            start = dt.datetime.combine(self.start, dt.time(), airports.get(code).zone)
            self._windows[code] = windows_from_items(self._fetch(code), start.astimezone(UTC))
        return self._windows[code]

    # -- checks -------------------------------------------------------------
    @staticmethod
    def _overlaps(a0, a1, wins: list[Window]) -> Window | None:
        for w in wins:
            if a0 < w.end and w.start < a1:
                return w
        return None

    def leg_problem(self, dep_code: str, arr_code: str,
                    dep_utc: dt.datetime, arr_utc: dt.datetime) -> str | None:
        """Return a Hebrew reason if this leg is not allowed, else None."""
        w = self._overlaps(dep_utc - self.depart_buffer, arr_utc, self.windows(dep_code))
        if w:
            return f"נוגע בשבת/חג ב-{dep_code}"
        w = self._overlaps(dep_utc, arr_utc + self.arrive_buffer, self.windows(arr_code))
        if w:
            return f"נוחת קרוב מדי לשבת/חג ב-{arr_code}"
        return None

    def day_has_departure_room(self, dep_code: str, arr_code: str, day: dt.date,
                               min_flight=dt.timedelta(hours=2)) -> bool:
        """Cheap pre-filter: can *any* flight leave dep_code on this local date?

        Samples departure times every 30 minutes and checks with a nominal
        flight length. Used only to avoid wasting API searches on dates such
        as a full Shabbat/Yom Tov day.
        """
        zone = airports.get(dep_code).zone
        t = dt.datetime.combine(day, dt.time(0, 0), zone)
        for _ in range(48):
            d = t.astimezone(UTC)
            if self.leg_problem(dep_code, arr_code, d, d + min_flight) is None:
                return True
            t += dt.timedelta(minutes=30)
        return False
