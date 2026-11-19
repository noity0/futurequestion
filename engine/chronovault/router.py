"""ChronoVault 2.0 — question router (intent + slots).

One question in, one structured plan out.  Pure rules, no network: fast,
predictable, and easy to debug.
"""
from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import formulas
from .places import (CRYPTO_SYMBOL, DEFAULT_CITY, find_country, find_crypto,
                     find_city, find_currencies, city_zone, city_slug)

FUTURE_WORDS = r"(future|predict|prediction|forecast|agle|agli|aglay|next|" \
               r"hoga|hogi|honge|hone|kitna\s+hoga|kitne\s+ka|" \
               r"price\s+in|rate\s+in|will\s+be|in\s+20\d\d|20\d\d\s+me|" \
               r"20\d\d\s+mein|tak|baad|later|expected)"


@dataclass
class Intent:
    kind: str
    confidence: float
    slots: dict = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "confidence": self.confidence,
                "slots": self.slots, "reason": self.reason}


def _has(text: str, *words: str) -> bool:
    for w in words:
        if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text):
            return True
    return False


def _future(text: str) -> bool:
    return bool(re.search(FUTURE_WORDS, text))


_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}


def _eval_math(node):
    """Evaluate a tiny arithmetic AST — no names, calls, or attributes."""
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _MATH_OPS:
        return _MATH_OPS[type(node.op)](_eval_math(node.left), _eval_math(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_math(node.operand)
    raise ValueError("unsupported arithmetic")


def _pure_math(text: str):
    """Return (expression, result) only for a standalone arithmetic question.

    Deliberately strict: dates ("2050-01-01"), phone numbers, currency pairs and
    sentences are *never* treated as maths.
    """
    s = text.strip().rstrip("=?").strip()
    s = re.sub(r"(?i)^(what\s+is|what's|whats|calculate|compute|solve|how\s+much\s+is|"
               r"kitna\s+hai|kitne\s+hain|hasil\s+karo)\s+", "", s).strip()
    if not s or not re.search(r"\d", s):
        return None
    if re.search(r"\d{4}\s*-\s*\d{1,2}\s*-\s*\d{1,2}", s):
        return None  # ISO date, not maths
    if re.search(r"\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{2,4}", s):
        return None  # dd-mm-yyyy date, not maths
    if re.search(r"[a-wyz]", s):  # any letter other than x (times) is not pure maths
        return None
    s = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", "*", s)
    if not re.fullmatch(r"[\d\s\.\+\-\*\/\(\)%]+", s):
        return None
    if not re.search(r"[\+\-\*\/]", s):
        return None
    expr = s.replace("÷", "/").replace("%", "/100*")
    try:
        value = _eval_math(ast.parse(expr, mode="eval"))
    except Exception:
        return None
    return expr, value


def _horizon(text: str) -> tuple[int, str | None]:
    """Return (days, target_iso or None)."""
    d = formulas.parse_duration_days(text)
    tgt = formulas.parse_date(text)
    if tgt and (tgt.year > formulas.today().year or
                (tgt.year == formulas.today().year and tgt > formulas.today())):
        return max(1, (tgt - formulas.today()).days), tgt.isoformat()
    if d:
        return max(1, d), (formulas.today() + timedelta(days=d)).isoformat()
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        y = int(m.group(1))
        t = date(y, 1, 1)
        if t > formulas.today():
            return max(1, (t - formulas.today()).days), t.isoformat()
    return 30, (formulas.today() + timedelta(days=30)).isoformat()


def _amount_near_currency(text: str, codes: list[str]) -> float:
    for code in codes:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|crore|k|m)??\s*" +
                      re.escape(code), text, re.I)
        if m:
            n = formulas.parse_amount(m.group(0))
            if n:
                return n
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|crore|k|m)?\s*"
                  r"(?:dollars?|euros?|pounds?|rupees?|rupay|riyals?|dirhams?|"
                  r"taka|lira|yen|yuan)", text, re.I)
    if m:
        return formulas.parse_amount(m.group(0)) or 1.0
    return 1.0


def _clean_query(q: str, extra: list[str] | None = None) -> str:
    stop = {
        "kya", "hai", "hain", "ka", "ki", "ke", "ko", "se", "me", "mein",
        "mujhe", "batao", "bata", "do", "please", "plz", "about", "bare",
        "baare", "bataen", "bataiye", "kaun", "kab", "kahan", "kyun", "kyu",
        "kaise", "kitna", "kitne", "konsa", "konsi", "what", "is", "the",
        "who", "when", "where", "why", "how", "tell", "me", "of", "a", "an",
        "please", "explain", "define", "information", "info", "details",
        "detail", "kro", "karo", "kar", "de", "den", "hota", "hoti", "hain",
        "tha", "thi", "the", "and", "or", "in", "on", "for", "to", "from",
    }
    if extra:
        stop.update(extra)
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", q)
    kept = [w for w in words if w.lower() not in stop]
    return " ".join(kept).strip() or q.strip()


def forecast_query(text: str) -> str:
    """Extract the topic from a speculative future question.

    The forecast engine needs a clean subject; horizon words belong in slots,
    not in a Wikipedia/news search:

        "20 saal baad pakistan military power kya hoga?"
            -> "pakistan military power"
    """
    s = text.strip()
    # "20 saal baad", "10 years later", "3 mahine mein"
    s = re.sub(r"(?i)\b\d+(?:[.,]\d+)?\s*"
               r"(?:saal|sal|years?|din|days?|mahine|months?|hafte|weeks?)\s*"
               r"(?:baad|later|from\s+now|me|mein)?\b", " ", s)
    # relative future markers
    s = re.sub(r"(?i)\b(?:agle|agli|aglay|next|aane\s+wale|aane\s+wala|"
               r"future|baad|later)\b", " ", s)
    # a year used as the horizon ("2046 me", "in 2046 tak")
    s = re.sub(r"(?i)\b(?:in\s+)?20\d{2}\s*(?:me|mein|tak)\b", " ", s)
    # future/question verbs
    s = re.sub(r"(?i)\b(?:kya|kia|hoga|hogi|honge|hone|rahega|rahegi|"
               r"rahenge|kitna|kitne|kaisa|kaisi|kaisay|expected|predict|"
               r"prediction|forecast)\b", " ", s)
    out = _clean_query(s, ["saal", "sal", "din", "days", "year", "years",
                           "baad", "later", "future", "agle", "agli", "aglay",
                           "next", "hoga", "hogi", "honge"])
    return out or _clean_query(text) or text.strip()


def _principal(text: str) -> float:
    """Find the principal amount: a number that is not a % rate or a duration."""
    t = text.replace(",", "")
    best = None
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(lakh|lac|crore|k|m|million|billion)?", t, re.I):
        after = t[m.end():m.end() + 12].lower().strip()
        if after.startswith("%"):
            continue
        unit = (m.group(2) or "").lower()
        if not unit and re.match(r"\s*(saal|sal|year|years|mahine|month|din|day|%)", after):
            continue
        val = float(m.group(1))
        mult = {"lakh": 1e5, "lac": 1e5, "crore": 1e7, "k": 1e3, "m": 1e6,
                "million": 1e6, "billion": 1e9}.get(unit)
        val = val * mult if mult else val
        if best is None or val > best:
            best = val
    return best or 0.0


def route(question: str) -> Intent:
    raw = question.strip()
    q = " " + re.sub(r"\s+", " ", raw.lower()) + " "

    # ------------------------------------------------------------- meta/help
    if _has(q, "help", "madad") or "kya kar sakte" in q or "what can you do" in q:
        return Intent("help", 0.95, {}, "help keywords")
    if (_has(q, "tum", "aap", "you") and _has(q, "kon", "who")) or \
            "who are you" in q or "tumhara naam" in q:
        return Intent("identity", 0.95, {}, "identity question")
    if _has(q, "endpoints", "endpoint", "registry", "sources", "providers") and \
            _has(q, "kitne", "how many", "count", "total", "list"):
        return Intent("system", 0.9, {}, "system stats")
    if _has(q, "salam", "salaam", "hello", "hi", "hey", "assalam") and len(q) < 40:
        return Intent("smalltalk", 0.9, {"text": "greeting"}, "greeting")

    # -------------------------------------------------------------- capsule
    if _has(q, "capsule", "kapsul") or "future ke liye message" in q or \
            "message to future" in q or "agli nasl" in q:
        horizon, target = _horizon(q)
        msg = raw
        msg = re.sub(r"(?i)\b(time\s*)?capsule\b", "", msg)
        msg = re.sub(r"(?i)\b(ban(a|ao|do)|banao|create|make|seal|likho|likh do)\b", "", msg)
        msg = re.sub(r"(?i)\b(\d+\s*(din|days?|saal|years?|mahine|months?)\s*(baad|later)?)\b", "", msg)
        return Intent("capsule", 0.9, {
            "message": msg.strip(" ,.-") or raw,
            "days": horizon, "open_at": target,
        }, "capsule keywords")

    # ---------------------------------------------------------- exact dates
    date_words = ("konsa din", "kaunsa din", "which day", "what day", "day of week",
                  "din hoga", "din hai", "day hai")
    count_words = ("kitne din", "how many days", "days until", "days to", "din baqi",
                   "din baki", "countdown", "kab aayega", "kab aaega", "how long until")
    parsed = formulas.parse_date(q)
    if _has(q, *count_words):
        if parsed is None:
            m = re.search(r"\b(aaj|kal|tomorrow|today)\b", q)
            if m:
                parsed = formulas.today() + (timedelta(days=1) if m.group(1) in ("kal", "tomorrow") else timedelta(0))
        if parsed:
            return Intent("countdown", 0.98, {"date": parsed.isoformat()},
                          "countdown phrase + date")
        return Intent("countdown", 0.6, {}, "countdown without parsable date")
    if _has(q, *date_words):
        if parsed is None:
            m = re.search(r"\b(aaj|today)\b", q)
            if m:
                parsed = formulas.today()
            else:
                m = re.search(r"\b(kal|tomorrow)\b", q)
                if m:
                    parsed = formulas.today() + timedelta(days=1)
        if parsed:
            return Intent("date", 0.98, {"date": parsed.isoformat()}, "weekday phrase + date")
    parsed = formulas.parse_date(q)
    if parsed and len(re.findall(r"[a-z]+", q)) <= 5 and not _future(q) and \
            not _has(q, "kya", "kaisa", "kaisi", "hoga", "hogi", "future",
                     "predict", "forecast", "news", "holiday", "holidays",
                     "chutti", "chhutti", "weather", "mausam", "rate", "price"):
        return Intent("date", 0.85, {"date": parsed.isoformat()}, "bare date")

    # ---------------------------------------------------------- finance math
    if _has(q, "emi", "installment", "installments", "qist", "qisht", "loan",
            "car loan", "house loan", "mortgage") and \
            not _has(q, "rate today", "exchange rate"):
        principal = _principal(raw) or 0
        mr = re.search(r"(\d+(?:\.\d+)?)\s*%", raw)
        rate = float(mr.group(1)) if mr else 0.0
        yr = re.search(r"(\d+(?:\.\d+)?)\s*(saal|sal|year|years|mahine|months?|"
                       r"mahina|din|days?)", q)
        years = 1.0
        if yr:
            n = float(yr.group(1))
            years = n / 12 if yr.group(2).startswith(("mahin", "month")) else (
                n / 365 if yr.group(2).startswith(("din", "day")) else n)
        return Intent("emi", 0.9, {"principal": principal, "rate": rate,
                                   "years": years}, "EMI/loan keywords")
    if _has(q, "compound", "compounding", "interest", "markup", "munafa",
            "sood") and not _has(q, "interest rate of", "rate today"):
        principal = _principal(raw) or 0
        mr = re.search(r"(\d+(?:\.\d+)?)\s*%", raw)
        rate = float(mr.group(1)) if mr else 0.0
        yr = re.search(r"(\d+(?:\.\d+)?)\s*(saal|sal|year|years|mahine|months?|"
                       r"mahina|din|days?)", q)
        years = 1.0
        if yr:
            n = float(yr.group(1))
            years = n / 12 if yr.group(2).startswith(("mahin", "month")) else (
                n / 365 if yr.group(2).startswith(("din", "day")) else n)
        per = formulas.parse_period(q)
        return Intent("interest", 0.9, {"principal": principal, "rate": rate,
                                        "years": years, "per_year": per},
                      "compound/simple interest keywords")

    # ----------------------------------------------------------------- fx
    currencies = find_currencies(raw)
    fx_words = _has(q, "rate", "exchange", "convert", "conversion", "dollar",
                    "euro", "pound", "rupee", "rupay", "riyal", "dirham",
                    "taka", "lira", "yen", "yuan", "currency")
    pair = re.search(r"\b([A-Za-z]{3})\s*(?:to|se|in|into|mein|me)\s*([A-Za-z]{3})\b", raw)
    if pair and pair.group(1).upper() in {c.upper() for c in currencies + ["USD", "PKR", "EUR", "GBP", "INR", "AED", "SAR", "BDT", "TRY", "JPY", "CNY"]}:
        a, b = pair.group(1).upper(), pair.group(2).upper()
        if len(a) == 3 and len(b) == 3:
            currencies = [a, b]
    if currencies and (fx_words or len(currencies) >= 2 or pair):
        frm = currencies[0]
        to = currencies[1] if len(currencies) > 1 else ("USD" if frm == "PKR" else "PKR")
        amount = _amount_near_currency(raw, [frm, to])
        fut = _future(q)
        horizon, target = _horizon(raw) if fut else (0, None)
        return Intent("forecast_fx" if fut else "fx", 0.9, {
            "from": frm, "to": to, "amount": amount,
            "horizon_days": horizon, "target": target,
        }, "currency pair/words")

    # -------------------------------------------------------------- crypto
    coin = find_crypto(raw)
    if coin:
        fut = _future(q)
        horizon, target = _horizon(raw) if fut else (0, None)
        return Intent("forecast_crypto" if fut else "crypto", 0.92, {
            "coin": coin, "symbol": CRYPTO_SYMBOL.get(coin, coin.upper()),
            "amount": _amount_near_currency(raw, []) if re.search(r"\d", raw) else 1.0,
            "horizon_days": horizon, "target": target,
        }, "crypto asset")

    # ------------------------------------------------------------- weather
    if _has(q, "weather", "mausam", "temperature", "temp", "barish", "rain",
            "garmi", "sardi", "humidity", "aqi", "air quality", "forecast"):
        city = find_city(raw)
        if not city and _has(q, "pakistan", "punjab", "sindh"):
            city = find_city("Karachi" if "sindh" in q else "Lahore")
        if not city:
            city = find_city(DEFAULT_CITY)
        days = 3 if _has(q, "forecast", "kal", "tomorrow", "agle", "next",
                         "3 din", "week", "hafta") else 1
        return Intent("weather", 0.92, {
            "city": city[0], "country": city[1], "lat": city[2], "lon": city[3],
            "slug": city_slug(city[0]), "days": days,
        }, "weather keywords")

    # ---------------------------------------------------------------- time
    if _has(q, "kitne baje", "kya time", "kya waqt", "current time", "time in",
            "local time", "clock", "abhi time", "waqt kya", "time kya") and \
            "time machine" not in q and "time travel" not in q:
        city = find_city(raw)
        zone = None
        mz = re.search(r"\b(UTC|GMT)\b", raw)
        if mz:
            zone = mz.group(1).upper().replace("GMT", "UTC")
        elif city:
            zone = city_zone(city[0])
        m = re.search(r"\b([A-Z][a-z]+/[A-Z][A-Za-z_]+)\b", raw)
        if m:
            zone = m.group(1)
        if zone:
            return Intent("time", 0.95, {"zone": zone,
                                         "city": city[0] if city else zone},
                          "time keywords + zone")
        return Intent("time", 0.85, {"zone": city_zone(DEFAULT_CITY),
                                     "city": DEFAULT_CITY},
                      "time keywords, default city")

    # ------------------------------------------------------------- holiday
    if _has(q, "holiday", "holidays", "chutti", "chhutti", "public holiday",
            "eid", "ramzan", "ramadan", "diwali", "christmas"):
        cc = find_country(raw)
        if not cc:
            city = find_city(raw)
            if city:
                from .places import COUNTRY_ALIASES
                cc = COUNTRY_ALIASES.get(city[1].lower())
        cc = cc or "PK"
        my = re.search(r"\b(20\d{2})\b", raw)
        year = int(my.group(1)) if my else formulas.today().year
        return Intent("holiday", 0.88, {"country": cc, "year": year},
                      "holiday keywords")

    # ------------------------------------------------------------- country
    if _has(q, "capital", "population", "country", "flag", "continent",
            "currency of", "about country", "which country"):
        cc = find_country(raw)
        q2 = _clean_query(raw, ["capital", "population", "country", "of", "flag"])
        return Intent("country", 0.85, {"country": cc, "query": q2},
                      "country keywords")

    # ---------------------------------------------------------------- news
    if _has(q, "news", "khabar", "khabrein", "headlines", "sarokar", "latest",
            "aaj ki", "breaking"):
        query = _clean_query(raw, ["news", "khabar", "khabrein", "headlines",
                                   "latest", "aaj", "ki", "breaking", "update",
                                   "updates", "today", "ajj"])
        return Intent("news", 0.88, {"query": query}, "news keywords")

    # --------------------------------------------------------------- space
    if _has(q, "iss", "space station", "earthquake", "earthquakes", "zalzala",
            "zalzale", "zealzala", "quakes", "launch", "rocket", "nasa", "mars",
            "asteroid", "solar", "sunspot", "apod", "satellite"):
        kind = "iss"
        if _has(q, "earthquake", "earthquakes", "zalzala", "zalzale", "zealzala",
                "quake", "quakes"):
            kind = "quake"
        elif _has(q, "launch", "rocket", "satellite"):
            kind = "launch"
        elif _has(q, "apod", "nasa picture"):
            kind = "apod"
        elif _has(q, "solar", "sunspot", "sun"):
            kind = "solar"
        return Intent("space", 0.88, {"space": kind}, "space keywords")

    # ----------------------------------------------------------- baby name
    baby_words = ("bacha", "bachay", "bacche", "bache", "bachcha", "bachon",
                  "bachpan", "baby", "beti", "beta", "child", "newborn",
                  "hone wala", "hone wali")
    name_words = ("naam", "name", "kya hoga", "kya hogi", "rakhna", "rakhein")
    if _has(q, *baby_words) and _has(q, *name_words):
        gender = ""
        if re.search(r"\b(boy|ladka|beta|male|mard)\b", q):
            gender = "boy"
        elif re.search(r"\b(girl|ladki|beti|female|aurat)\b", q):
            gender = "girl"
        return Intent("baby_name", 0.93, {"gender": gender},
                      "baby name question")

    # --------------------------------------------------------- exact math
    math = _pure_math(raw)
    if math:
        expr, value = math
        return Intent("math", 0.999, {
            "expression": expr, "result": value,
            "text": f"{expr.strip()} = {formulas.fmt_num(value, 6)}",
        }, "standalone arithmetic expression")

    # ----------------------------------------------------- generic forecast
    if _future(q) and not _has(q, "time machine", "time travel"):
        horizon, target = _horizon(raw)
        return Intent("forecast", 0.72, {
            "horizon_days": horizon, "target": target,
            "query": forecast_query(raw),
        }, "future words without concrete domain")

    # -------------------------------------------------------------- knowledge
    return Intent("knowledge", 0.7, {
        "query": _clean_query(raw),
    }, "default knowledge route")
