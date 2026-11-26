import datetime as dt

from flightscan.shabbat import ShabbatCalendar, windows_from_items

UTC = dt.timezone.utc

# Hebcal output for Athens, Pesach 2027 (diaspora), trimmed
PESACH = [
    {"category": "candles", "date": "2027-04-21T19:47:00+03:00"},
    {"category": "candles", "date": "2027-04-22T20:48:00+03:00"},
    {"category": "candles", "date": "2027-04-23T19:49:00+03:00"},
    {"category": "havdalah", "date": "2027-04-24T20:50:00+03:00"},
    {"category": "candles", "date": "2027-04-27T19:52:00+03:00"},
    {"category": "candles", "date": "2027-04-28T20:54:00+03:00"},
    {"category": "havdalah", "date": "2027-04-29T20:55:00+03:00"},
    {"category": "candles", "date": "2027-04-30T19:55:00+03:00"},
    {"category": "havdalah", "date": "2027-05-01T20:57:00+03:00"},
]


def t(s):
    return dt.datetime.fromisoformat(s).astimezone(UTC)


def test_windows_merge_yomtov_and_shabbat():
    w = windows_from_items(PESACH, t("2027-04-18T00:00:00+03:00"))
    assert [(x.start, x.end) for x in w] == [
        (t("2027-04-21T19:47:00+03:00"), t("2027-04-24T20:50:00+03:00")),  # YT I-II + Shabbat
        (t("2027-04-27T19:52:00+03:00"), t("2027-04-29T20:55:00+03:00")),  # YT VII-VIII
        (t("2027-04-30T19:55:00+03:00"), t("2027-05-01T20:57:00+03:00")),  # Shabbat
    ]


def test_range_starting_mid_shabbat():
    items = [{"category": "havdalah", "date": "2027-05-01T20:57:00+03:00"}]
    start = t("2027-05-01T00:00:00+03:00")
    assert windows_from_items(items, start)[0].start == start


def _cal(windows_by_code):
    cfg = {"shabbat": {"arrive_before_candles_hours": 3, "depart_after_havdalah_hours": 3.5}}
    cal = ShabbatCalendar(cfg, dt.date(2027, 4, 1), dt.date(2027, 6, 1))
    cal._windows = windows_by_code
    return cal


FRI = windows_from_items(
    [{"category": "candles", "date": "2027-04-30T19:55:00+03:00"},
     {"category": "havdalah", "date": "2027-05-01T20:57:00+03:00"}],
    t("2027-04-01T00:00:00+03:00"))


def test_friday_arrival_rules():
    cal = _cal({"TLV": FRI, "ATH": FRI})
    ok = cal.leg_problem("TLV", "ATH", t("2027-04-30T10:00:00+03:00"), t("2027-04-30T12:00:00+03:00"))
    late = cal.leg_problem("TLV", "ATH", t("2027-04-30T14:00:00+03:00"), t("2027-04-30T17:30:00+03:00"))
    assert ok is None
    assert late is not None  # lands 2h25 before candles, buffer is 3h


def test_saturday_night_departure():
    cal = _cal({"TLV": FRI, "ATH": FRI})
    early = cal.leg_problem("ATH", "TLV", t("2027-05-01T23:00:00+03:00"), t("2027-05-02T01:00:00+03:00"))
    fine = cal.leg_problem("ATH", "TLV", t("2027-05-02T00:40:00+03:00"), t("2027-05-02T02:40:00+03:00"))
    assert early is not None  # only ~2h after havdalah
    assert fine is None


def test_flight_during_shabbat_blocked():
    cal = _cal({"TLV": FRI, "ATH": FRI})
    assert cal.leg_problem("TLV", "ATH", t("2027-05-01T11:00:00+03:00"), t("2027-05-01T13:00:00+03:00"))


def test_unverifiable_airlines_learned_and_marked():
    from flightscan.scan import mark_unverifiable, unverifiable_airlines
    state = {"stats": {"noairline|IZ": {"n": 2, "hits": 0}, "noairline|LY": {"n": 1, "hits": 0}},
             "legs": {"out|CDG|2027-06-01": {"options": {
                 "a": {"airline_code": "IZ", "seller_is_airline": False},
                 "b": {"airline_code": "LY", "seller_is_airline": None}}}}}
    codes = unverifiable_airlines({"unverifiable_airlines": ["6H"]}, state)
    assert codes == {"IZ", "6H"}
    mark_unverifiable(state, codes)
    opts = state["legs"]["out|CDG|2027-06-01"]["options"]
    assert opts["a"]["check_on_site"] and opts["a"]["seller_is_airline"] is None
    assert "check_on_site" not in opts["b"]
