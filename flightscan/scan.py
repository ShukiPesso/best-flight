"""Daily scan: pick which (destination, direction, date) searches to run within
the API budget, store the legs, combine them into Shabbat/Yom Tov-safe round
trips and write docs/deals.json for the web page.

Run:  python -m flightscan.scan            (uses SERPAPI_KEY / DUFFEL_TOKEN)
      python -m flightscan.scan --demo     (synthetic data, no keys)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

import yaml

from . import airports
from .models import nights
from .providers.base import ProviderError
from .providers.demo import DemoProvider
from .providers.duffel import DuffelProvider
from .providers.serpapi import SerpApiProvider
from .shabbat import ShabbatCalendar

ROOT = Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc
log = logging.getLogger("flightscan")


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------
def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"legs": {}, "stats": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


def key(direction: str, dest: str, day: dt.date) -> str:
    return f"{direction}|{dest}|{day.isoformat()}"


def prune(state: dict, today: dt.date, destinations: list[str]) -> None:
    for k in list(state["legs"]):
        _, dest, day = k.split("|")
        if dt.date.fromisoformat(day) < today or dest not in destinations:
            del state["legs"][k]


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last_day = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(y, m, min(d.day, last_day))


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------
def departure_window(cfg, today: dt.date) -> tuple[dt.date, dt.date]:
    """First and last allowed *outbound* date (returns may run later)."""
    w = cfg.get("search_window") or {}
    earliest = today + dt.timedelta(days=2)
    if w.get("from") and w.get("to"):
        first, last = dt.date.fromisoformat(str(w["from"])), dt.date.fromisoformat(str(w["to"]))
    elif w.get("start_after_months") is not None:
        first = add_months(today, int(w["start_after_months"]))
        last = add_months(today, int(w["start_after_months"]) + int(w.get("length_months", 1)))
    else:
        first = today + dt.timedelta(days=int(w.get("start_after_days", 2)))
        last = first + dt.timedelta(days=int(w.get("length_days", 90)) - 1)
    return max(first, earliest), last


def build_tasks(cfg, cal: ShabbatCalendar, today: dt.date) -> list[tuple]:
    td = cfg["trip_days"]
    first, last = departure_window(cfg, today)
    tasks = []
    for dest in cfg["destinations"]:
        airports.get(dest)
        ranges = (("out", first, last),
                  ("ret", first + dt.timedelta(days=td["flex_min"] - 1),
                   last + dt.timedelta(days=td["flex_max"] - 1)))
        for direction, a, b in ranges:
            for off in range((b - a).days + 1):
                day = a + dt.timedelta(days=off)
                dep = "TLV" if direction == "out" else dest
                arr = dest if direction == "out" else "TLV"
                if cal.day_has_departure_room(dep, arr, day):
                    tasks.append((dest, direction, day))
    return tasks


def _target_hours(days_ahead: int) -> float:
    return 24 if days_ahead <= 30 else 48 if days_ahead <= 60 else 72


def prioritize(tasks, state, provider_name: str, now: dt.datetime, dest_order) -> list:
    scored = []
    for dest, direction, day in tasks:
        entry = state["legs"].get(key(direction, dest, day), {})
        last = entry.get("checked", {}).get(provider_name)
        age_h = (now - dt.datetime.fromisoformat(last)).total_seconds() / 3600 if last else 1e6
        ahead = (day - now.date()).days
        target = _target_hours(ahead)
        # learn which weekdays / routes have no nonstop flights and probe them less
        wk = state["stats"].get(f"{provider_name}|{direction}|{dest}|{day.weekday()}", {})
        rt = state["stats"].get(f"{provider_name}|{direction}|{dest}", {})
        if rt.get("n", 0) >= 10 and rt.get("hits", 0) == 0:
            target *= 10
        elif wk.get("n", 0) >= 3 and wk.get("hits", 0) == 0:
            target *= 5
        score = age_h / target
        if score >= 1:
            scored.append((-min(score, 1e3), ahead, dest_order[dest], direction, dest, day))
    scored.sort()
    return [(s[4], s[3], s[5]) for s in scored]


def _bump(state, k, hit):
    s = state["stats"].setdefault(k, {"n": 0, "hits": 0})
    s["n"] += 1
    s["hits"] += 1 if hit else 0


def run_searches(cfg, provider, tasks, state, now) -> int:
    origins = cfg["origins"]
    dest_order = {d: i for i, d in enumerate(cfg["destinations"])}
    queue = prioritize(tasks, state, provider.name, now, dest_order)
    done = 0
    for dest, direction, day in queue:
        if provider.searches_used + provider.cost(origins) > provider.search_budget:
            break
        try:
            if direction == "out":
                legs = provider.search(origins, dest, day)
            elif provider.name == "serpapi":  # one call can target "TLV,ETM"
                legs = provider.search([dest], ",".join(origins), day)
            else:
                legs = []
                for o in origins:
                    legs += provider.search([dest], o, day)
        except ProviderError as e:
            log.warning("%s %s %s %s failed: %s", provider.name, direction, dest, day, e)
            continue
        legs = [l for l in legs if (l["arr"] if direction == "out" else l["dep"]) == dest]
        store_legs(state, key(direction, dest, day), provider.name, legs, now)
        _bump(state, f"{provider.name}|{direction}|{dest}|{day.weekday()}", bool(legs))
        _bump(state, f"{provider.name}|{direction}|{dest}", bool(legs))
        done += 1
    log.info("%s: %d searches (%d API calls)", provider.name, done, provider.searches_used)
    return done


def store_legs(state, k, provider_name, legs, now) -> None:
    entry = state["legs"].setdefault(k, {"checked": {}, "options": {}})
    old = {i: l for i, l in entry["options"].items() if l["provider"] == provider_name}
    for i in old:
        del entry["options"][i]
    for l in legs:
        prev = old.get(l["id"])
        # keep an earlier airline verification while Google's price hasn't moved
        if prev and prev.get("verified_at") and prev.get("google_price") == l["price"]:
            for f in ("price", "google_price", "seller", "seller_is_airline", "fare_name",
                      "bags", "fares", "verified_at"):
                l[f] = prev.get(f)
        l["checked_at"] = now.isoformat()
        cur = entry["options"].get(l["id"])
        if cur is None or l["price"] < cur["price"]:
            entry["options"][l["id"]] = l
    entry["checked"][provider_name] = now.isoformat()


# --------------------------------------------------------------------------
# combining into round trips
# --------------------------------------------------------------------------
def _usable(leg, cal, now, max_age_days) -> bool:
    if leg.get("seller_is_airline") is False:
        return False
    if (now - dt.datetime.fromisoformat(leg["checked_at"])).days > max_age_days:
        return False
    if leg.get("_shabbat_ok") is None:
        leg["_shabbat_ok"] = cal.leg_problem(
            leg["dep"], leg["arr"],
            dt.datetime.fromisoformat(leg["dep_utc"]),
            dt.datetime.fromisoformat(leg["arr_utc"])) is None
    return leg["_shabbat_ok"]


def _cheapest_by_airport(state, direction, dest, day, cal, now, max_age, side):
    entry = state["legs"].get(key(direction, dest, day))
    best = {}
    if not entry:
        return best
    for leg in entry["options"].values():
        if not _usable(leg, cal, now, max_age):
            continue
        ap = leg[side]
        if ap not in best or leg["price"] < best[ap]["price"]:
            best[ap] = leg
    return best


def combine(cfg, state, cal, today, now) -> dict[str, list[dict]]:
    td = cfg["trip_days"]
    max_age = cfg["max_leg_age_days"]
    mixed = cfg.get("allow_mixed_israeli_airports", False)
    result = {}
    for dest in cfg["destinations"]:
        trips = []
        first, last = departure_window(cfg, today)
        for off in range((last - first).days + 1):
            d0 = first + dt.timedelta(days=off)
            outs = _cheapest_by_airport(state, "out", dest, d0, cal, now, max_age, "dep")
            if not outs:
                continue
            for days in range(td["flex_min"], td["flex_max"] + 1):
                d1 = d0 + dt.timedelta(days=days - 1)
                rets = _cheapest_by_airport(state, "ret", dest, d1, cal, now, max_age, "arr")
                for o in outs.values():
                    for r in rets.values():
                        if not mixed and r["arr"] != o["dep"]:
                            continue
                        if r["dep_utc"] <= o["arr_utc"]:
                            continue
                        n = nights(o, r)
                        trips.append({
                            "dest": dest, "days": n + 1, "nights": n,
                            "in_range": td["min"] <= n + 1 <= td["max"],
                            "price_pp": round(o["price"] + r["price"]),
                            "verified": o.get("seller_is_airline") is True
                                        and r.get("seller_is_airline") is True,
                            "out": o, "ret": r,
                        })
        in_range = [t for t in trips if t["in_range"]]
        best_in = min((t["price_pp"] for t in in_range), default=None)
        pct = td["flex_min_saving_pct"] / 100
        keep = [t for t in trips if t["in_range"] or best_in is None
                or t["price_pp"] <= best_in * (1 - pct)]
        keep.sort(key=lambda t: (t["price_pp"], not t["verified"]))
        result[dest] = keep
    return result


def verify_candidates(cfg, providers, combined) -> bool:
    """Verify (seller == airline) the legs of the top trips. Returns True if
    anything changed so the caller can recombine."""
    v = next((p for p in providers if p.name == "serpapi"), None)
    if not v:
        return False
    changed = False
    k = cfg["verify_top_trips_per_destination"]
    for dest, trips in combined.items():
        for t in trips[:k]:
            for leg in (t["out"], t["ret"]):
                if leg["provider"] != "serpapi" or leg.get("seller_is_airline") is not None:
                    continue
                if not v.can_verify():
                    return changed
                try:
                    res = v.verify(leg)
                except ProviderError as e:
                    log.warning("verify %s failed: %s", leg["id"], e)
                    continue
                if res is None:
                    continue
                changed = True
                leg["verified_at"] = dt.datetime.now(UTC).isoformat()
                leg["google_price"] = leg["price"]
                if res.get("no_airline_offer"):
                    leg["seller_is_airline"] = False
                else:
                    leg.update(price=res["price"], seller=res["seller"], seller_is_airline=True,
                               fare_name=res.get("fare_name"), bags=res["bags"],
                               fares=res.get("fares"))
    return changed


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------
def _public_leg(l: dict) -> dict:
    return {k: v for k, v in l.items() if not k.startswith("_") and k != "booking_token"}


def _public_trip(t: dict) -> dict:
    return {**{k: v for k, v in t.items() if k not in ("out", "ret")},
            "out": _public_leg(t["out"]), "ret": _public_leg(t["ret"])}


def build_output(cfg, combined, tasks, state, now, providers, demo) -> dict:
    max_age = cfg["max_leg_age_days"]
    dests = []
    for dest in cfg["destinations"]:
        ap = airports.get(dest)
        mine = [t for t in tasks if t[0] == dest]
        fresh = 0
        for _, direction, day in mine:
            ch = state["legs"].get(key(direction, dest, day), {}).get("checked", {})
            if any((now - dt.datetime.fromisoformat(v)).days <= max_age for v in ch.values()):
                fresh += 1
        trips = combined.get(dest, [])
        alts, seen = [], set()
        for t in trips:
            sig = (t["days"], t["out"]["dep"])
            if sig in seen:
                continue
            seen.add(sig)
            alts.append(_public_trip(t))
            if len(alts) >= cfg["alternatives_per_destination"]:
                break
        dests.append({
            "code": dest, "city": ap.city_he, "country": ap.country_he,
            "best": alts[0] if alts else None, "options": alts,
            "coverage_pct": round(100 * fresh / len(mine)) if mine else 0,
        })
    dests.sort(key=lambda d: (d["best"] is None, d["best"]["price_pp"] if d["best"] else 0))
    return {
        "generated_at": now.isoformat(), "demo": demo, "currency": cfg["currency"],
        "family_size": cfg.get("family_size", 1),
        "trip_days": cfg["trip_days"],
        "window": [d.isoformat() for d in departure_window(cfg, now.date())],
        "shabbat": cfg["shabbat"],
        "providers": [{"name": p.name, "searches": p.searches_used,
                       "verifies": p.verifies_used} for p in providers],
        "destinations": dests,
    }


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=None)
    ap.add_argument("--out", default=str(ROOT / "docs" / "deals.json"))
    ap.add_argument("--demo", action="store_true", help="synthetic data, no API keys")
    ap.add_argument("--search-budget", type=int, default=None,
                    help="override today's search budget (e.g. a one-off full sweep)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = yaml.safe_load(Path(args.config).read_text())
    cur = cfg.get("currency", "ILS")
    state_path = Path(args.state) if args.state else ROOT / "data" / (
        "state_demo.json" if args.demo else "state.json")
    now = dt.datetime.now(UTC).replace(microsecond=0)
    today = now.astimezone(airports.get("TLV").zone).date()

    providers = []
    if args.demo:
        providers.append(DemoProvider({}, cur))
    else:
        pc = cfg.get("providers", {})
        if DuffelProvider.available():
            providers.append(DuffelProvider(pc.get("duffel", {}), cur))
        if SerpApiProvider.available():
            providers.append(SerpApiProvider(pc.get("serpapi", {}), cur))
        if not providers:
            log.error("No provider keys found. Set SERPAPI_KEY and/or DUFFEL_TOKEN, "
                      "or run with --demo.")
            return 2

    first, last = departure_window(cfg, today)
    if args.search_budget is not None:
        for p in providers:
            p.search_budget = args.search_budget
    else:
        for p in providers:
            if hasattr(p, "auto_budget"):
                p.auto_budget(today)
    end = last + dt.timedelta(days=cfg["trip_days"]["flex_max"])
    cal = ShabbatCalendar(cfg, first, end, cache_dir=ROOT / "data" / "cache")
    state = load_state(state_path)
    prune(state, today, cfg["destinations"])

    tasks = build_tasks(cfg, cal, today)
    log.info("%d searchable (destination, direction, date) slots", len(tasks))
    for p in providers:
        run_searches(cfg, p, tasks, state, now)

    combined = combine(cfg, state, cal, today, now)
    for _ in range(4):
        if not verify_candidates(cfg, providers, combined):
            break
        combined = combine(cfg, state, cal, today, now)

    out = build_output(cfg, combined, tasks, state, now, providers, args.demo)
    for entry in state["legs"].values():  # drop per-run caches before saving
        for l in entry["options"].values():
            l.pop("_shabbat_ok", None)
    save_state(state_path, state)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    found = sum(1 for d in out["destinations"] if d["best"])
    log.info("wrote %s (%d/%d destinations with a deal)", args.out, found, len(out["destinations"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
