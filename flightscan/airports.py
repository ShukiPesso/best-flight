"""Static airport table: Hebrew names, coordinates and time zones.

Coordinates feed Hebcal (candle-lighting / havdalah per location); time zones
convert the local times that the flight APIs return into absolute instants.
Add a row here to search a new destination.
"""
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Airport:
    code: str
    city_he: str
    country_he: str
    lat: float
    lon: float
    tz: str
    israel: bool = False

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


_ROWS = [
    # code, city, country, lat, lon, tz
    ("TLV", "תל אביב (נתב\"ג)", "ישראל", 32.011, 34.887, "Asia/Jerusalem"),
    ("ETM", "אילת (רמון)", "ישראל", 29.727, 35.011, "Asia/Jerusalem"),
    ("ATH", "אתונה", "יוון", 37.936, 23.947, "Europe/Athens"),
    ("SKG", "סלוניקי", "יוון", 40.520, 22.971, "Europe/Athens"),
    ("HER", "הרקליון, כרתים", "יוון", 35.340, 25.180, "Europe/Athens"),
    ("RHO", "רודוס", "יוון", 36.405, 28.086, "Europe/Athens"),
    ("CFU", "קורפו", "יוון", 39.602, 19.912, "Europe/Athens"),
    ("KGS", "קוס", "יוון", 36.793, 27.092, "Europe/Athens"),
    ("LCA", "לרנקה", "קפריסין", 34.875, 33.625, "Asia/Nicosia"),
    ("PFO", "פאפוס", "קפריסין", 34.718, 32.486, "Asia/Nicosia"),
    ("LHR", "לונדון הית'רו", "בריטניה", 51.470, -0.454, "Europe/London"),
    ("LTN", "לונדון לוטון", "בריטניה", 51.875, -0.368, "Europe/London"),
    ("STN", "לונדון סטנסטד", "בריטניה", 51.885, 0.235, "Europe/London"),
    ("CDG", "פריז שארל דה גול", "צרפת", 49.010, 2.548, "Europe/Paris"),
    ("ORY", "פריז אורלי", "צרפת", 48.723, 2.379, "Europe/Paris"),
    ("NCE", "ניס", "צרפת", 43.658, 7.216, "Europe/Paris"),
    ("LYS", "ליון", "צרפת", 45.726, 5.091, "Europe/Paris"),
    ("MRS", "מרסיי", "צרפת", 43.439, 5.221, "Europe/Paris"),
    ("FCO", "רומא", "איטליה", 41.800, 12.239, "Europe/Rome"),
    ("MXP", "מילאנו מלפנסה", "איטליה", 45.630, 8.723, "Europe/Rome"),
    ("BGY", "מילאנו ברגמו", "איטליה", 45.674, 9.704, "Europe/Rome"),
    ("VCE", "ונציה", "איטליה", 45.505, 12.352, "Europe/Rome"),
    ("NAP", "נאפולי", "איטליה", 40.886, 14.291, "Europe/Rome"),
    ("BLQ", "בולוניה", "איטליה", 44.535, 11.289, "Europe/Rome"),
    ("CTA", "קטניה, סיציליה", "איטליה", 37.467, 15.066, "Europe/Rome"),
    ("BRI", "בארי", "איטליה", 41.139, 16.761, "Europe/Rome"),
    ("BCN", "ברצלונה", "ספרד", 41.297, 2.078, "Europe/Madrid"),
    ("MAD", "מדריד", "ספרד", 40.472, -3.561, "Europe/Madrid"),
    ("PMI", "פלמה דה מיורקה", "ספרד", 39.552, 2.739, "Europe/Madrid"),
    ("LIS", "ליסבון", "פורטוגל", 38.774, -9.134, "Europe/Lisbon"),
    ("AMS", "אמסטרדם", "הולנד", 52.310, 4.768, "Europe/Amsterdam"),
    ("BRU", "בריסל", "בלגיה", 50.901, 4.484, "Europe/Brussels"),
    ("BER", "ברלין", "גרמניה", 52.367, 13.503, "Europe/Berlin"),
    ("FRA", "פרנקפורט", "גרמניה", 50.038, 8.562, "Europe/Berlin"),
    ("MUC", "מינכן", "גרמניה", 48.354, 11.786, "Europe/Berlin"),
    ("VIE", "וינה", "אוסטריה", 48.110, 16.570, "Europe/Vienna"),
    ("ZRH", "ציריך", "שווייץ", 47.458, 8.548, "Europe/Zurich"),
    ("GVA", "ז'נבה", "שווייץ", 46.238, 6.109, "Europe/Zurich"),
    ("PRG", "פראג", "צ'כיה", 50.101, 14.260, "Europe/Prague"),
    ("BUD", "בודפשט", "הונגריה", 47.437, 19.256, "Europe/Budapest"),
    ("WAW", "ורשה", "פולין", 52.166, 20.967, "Europe/Warsaw"),
    ("KRK", "קרקוב", "פולין", 50.078, 19.785, "Europe/Warsaw"),
    ("KTW", "קטוביצה", "פולין", 50.474, 19.080, "Europe/Warsaw"),
    ("OTP", "בוקרשט", "רומניה", 44.571, 26.085, "Europe/Bucharest"),
    ("SOF", "סופיה", "בולגריה", 42.697, 23.411, "Europe/Sofia"),
    ("VAR", "ורנה", "בולגריה", 43.232, 27.825, "Europe/Sofia"),
    ("BEG", "בלגרד", "סרביה", 44.818, 20.309, "Europe/Belgrade"),
    ("TIA", "טירנה", "אלבניה", 41.415, 19.721, "Europe/Tirane"),
    ("TIV", "טיבאט", "מונטנגרו", 42.405, 18.723, "Europe/Podgorica"),
    ("DBV", "דוברובניק", "קרואטיה", 42.561, 18.268, "Europe/Zagreb"),
    ("ZAG", "זאגרב", "קרואטיה", 45.743, 16.069, "Europe/Zagreb"),
    ("LJU", "לובליאנה", "סלובניה", 46.224, 14.458, "Europe/Ljubljana"),
    ("TBS", "טביליסי", "גאורגיה", 41.669, 44.955, "Asia/Tbilisi"),
    ("BUS", "בטומי", "גאורגיה", 41.610, 41.600, "Asia/Tbilisi"),
    ("EVN", "ירוואן", "ארמניה", 40.147, 44.396, "Asia/Yerevan"),
    ("IST", "איסטנבול", "טורקיה", 41.275, 28.752, "Europe/Istanbul"),
    ("DUB", "דבלין", "אירלנד", 53.421, -6.270, "Europe/Dublin"),
    ("CPH", "קופנהגן", "דנמרק", 55.618, 12.656, "Europe/Copenhagen"),
    ("ARN", "סטוקהולם", "שוודיה", 59.650, 17.919, "Europe/Stockholm"),
    ("RIX", "ריגה", "לטביה", 56.924, 23.971, "Europe/Riga"),
    ("VNO", "וילנה", "ליטא", 54.634, 25.286, "Europe/Vilnius"),
    ("MLA", "מלטה", "מלטה", 35.857, 14.477, "Europe/Malta"),
    ("DXB", "דובאי", "איחוד האמירויות", 25.253, 55.366, "Asia/Dubai"),
    ("AUH", "אבו דאבי", "איחוד האמירויות", 24.433, 54.651, "Asia/Dubai"),
    ("BKK", "בנגקוק", "תאילנד", 13.690, 100.750, "Asia/Bangkok"),
    ("BOM", "מומבאי", "הודו", 19.090, 72.866, "Asia/Kolkata"),
    ("JFK", "ניו יורק JFK", "ארה\"ב", 40.641, -73.778, "America/New_York"),
    ("EWR", "ניוארק", "ארה\"ב", 40.690, -74.174, "America/New_York"),
    ("BOS", "בוסטון", "ארה\"ב", 42.366, -71.010, "America/New_York"),
    ("MIA", "מיאמי", "ארה\"ב", 25.795, -80.287, "America/New_York"),
    ("LAX", "לוס אנג'לס", "ארה\"ב", 33.942, -118.408, "America/Los_Angeles"),
    ("YYZ", "טורונטו", "קנדה", 43.677, -79.625, "America/Toronto"),
]

AIRPORTS: dict[str, Airport] = {
    r[0]: Airport(*r, israel=r[0] in ("TLV", "ETM")) for r in _ROWS
}


def get(code: str) -> Airport:
    try:
        return AIRPORTS[code]
    except KeyError:
        raise KeyError(
            f"Airport {code} is not in flightscan/airports.py - add a row for it"
        ) from None
