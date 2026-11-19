"""ChronoVault 2.0 — deterministic math (exact answers, badge EXACT-MATH)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

MONTHS = {
    "jan": 1, "january": 1, "janvari": 1, "janawari": 1,
    "feb": 2, "february": 2, "farvari": 2, "farwari": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8, "agast": 8,
    "sep": 9, "sept": 9, "september": 9, "sitambar": 9,
    "oct": 10, "october": 10, "aktobar": 10, "aktubar": 10,
    "nov": 11, "november": 11, "navambar": 11,
    "dec": 12, "december": 12, "disambar": 12,
}

DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
           "Saturday", "Sunday"]
DAYS_ROMAN = ["Somwar", "Mangal", "Budh", "Jumerat", "Jumma", "Hafta", "Etwar"]
DAYS_UR = ["پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ", "اتوار"]


def today() -> date:
    return datetime.now(timezone.utc).date()


def fmt_num(x: float, decimals: int = 2) -> str:
    try:
        s = f"{x:,.{decimals}f}"
    except Exception:
        return str(x)
    if decimals > 0:
        s = s.rstrip("0").rstrip(".")
    return s


def fmt_money(x: float, code: str = "", decimals: int = 2) -> str:
    return f"{fmt_num(x, decimals)} {code}".strip()


def parse_amount(text: str) -> float | None:
    """Understand 1 lakh, 2 crore, 100k, 1.5m, 10,000."""
    t = text.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|crore|k|m|million|billion)?", t)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mult = {"lakh": 1e5, "lac": 1e5, "crore": 1e7, "k": 1e3,
            "m": 1e6, "million": 1e6, "billion": 1e9}.get(unit)
    return val * mult if mult else val


def parse_duration_days(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(din|days?|roz|saal|year|years?|sal|"
                  r"mahine|mahina|months?|month|hafta|hafte|weeks?|week)", t)
    if m:
        n = float(m.group(1))
        unit = m.group(2)
        if unit.startswith(("saal", "sal", "year")):
            return int(round(n * 365))
        if unit.startswith(("mahin", "month")):
            return int(round(n * 30))
        if unit.startswith(("hafta", "hafte", "week")):
            return int(round(n * 7))
        return int(n)

    # Relative phrases without digits: "agle saal", "next month", etc. Without
    # this, a one-year question silently fell back to the 30-day default.
    if re.search(r"\b(?:agle|agli|agla|next)\s+(?:saal|sal|year)\b", t) or \
            re.search(r"\b(?:ek|one|1)\s+(?:saal|sal|year)\b", t) or \
            re.search(r"\b(?:saal|sal|year)\s+(?:baad|later)\b", t):
        return 365
    if re.search(r"\b(?:agle|agli|agla|next)\s+(?:mahine|mahina|month)\b", t) or \
            re.search(r"\b(?:ek|one|1)\s+(?:mahina|mahine|month)\b", t):
        return 30
    if re.search(r"\b(?:agle|agli|agla|next)\s+(?:hafta|hafte|week)\b", t) or \
            re.search(r"\b(?:ek|one|1)\s+(?:hafta|hafte|week)\b", t):
        return 7

    # "do saal", "paanch din", "three months" ...
    words = {
        "ek": 1, "ik": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3,
        "char": 4, "chaar": 4, "four": 4, "panch": 5, "paanch": 5, "five": 5,
        "chhe": 6, "che": 6, "six": 6, "saat": 7, "seven": 7, "aath": 8,
        "eight": 8, "nau": 9, "nine": 9, "das": 10, "ten": 10,
    }
    m = re.search(r"\b(" + "|".join(words) + r")\s+(din|days?|roz|saal|sal|"
                  r"years?|year|mahine|mahina|months?|month|hafte|hafta|"
                  r"weeks?|week)\b", t)
    if m:
        n = float(words[m.group(1)])
        unit = m.group(2)
        if unit.startswith(("saal", "sal", "year")):
            return int(round(n * 365))
        if unit.startswith(("mahin", "month")):
            return int(round(n * 30))
        if unit.startswith(("haft", "week")):
            return int(round(n * 7))
        return int(n)
    return None


def parse_date(text: str) -> date | None:
    t = text.lower().strip()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", t)
    if m and m.group(2) in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b([a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", t)
    if m and m.group(1) in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            return None
    m = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), 1, 1)
        except ValueError:
            return None
    return None


def weekday_answer(d: date) -> dict:
    i = d.weekday()
    delta = (d - today()).days
    if delta > 0:
        rel = f"{delta} din baad"
    elif delta < 0:
        rel = f"{abs(delta)} din pehle"
    else:
        rel = "aaj"
    return {
        "ok": True,
        "date": d.isoformat(),
        "weekday_en": DAYS_EN[i],
        "weekday_roman": DAYS_ROMAN[i],
        "weekday_ur": DAYS_UR[i],
        "days_delta": delta,
        "relative": rel,
        "text": f"{d.isoformat()} ko {DAYS_ROMAN[i]} ({DAYS_EN[i]}) hai — {rel}.",
    }


def countdown(target: date, start: date | None = None) -> dict:
    start = start or today()
    days = (target - start).days
    weeks = days / 7
    months = days / 30.4375
    return {
        "target": target.isoformat(), "start": start.isoformat(),
        "days": days, "weeks": round(weeks, 1), "months": round(months, 1),
        "text": (f"{target.isoformat()} tak {days} din baqi hain "
                 f"(~{round(months, 1)} mahine)." if days >= 0 else
                 f"{target.isoformat()} guzar chuki hai — {abs(days)} din pehle."),
    }


def compound(principal: float, annual_rate_pct: float, years: float,
             per_year: int = 12) -> dict:
    r = annual_rate_pct / 100.0
    n = max(1, int(per_year))
    t = years
    amount = principal * (1 + r / n) ** (n * t)
    gain = amount - principal
    return {
        "principal": round(principal, 2), "rate_pct": annual_rate_pct,
        "years": years, "compounds_per_year": n,
        "amount": round(amount, 2), "gain": round(gain, 2),
        "text": (f"{fmt_num(principal)} @ {annual_rate_pct}% compound interest x "
                 f"{fmt_num(years)} saal (n={n}) = {fmt_num(amount)} "
                 f"(faida {fmt_num(gain)})."),
    }


def emi(principal: float, annual_rate_pct: float, years: float) -> dict:
    r = annual_rate_pct / 100.0 / 12.0
    n = max(1, int(round(years * 12)))
    if r == 0:
        pay = principal / n
    else:
        pay = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    total = pay * n
    interest = total - principal
    return {
        "principal": round(principal, 2), "rate_pct": annual_rate_pct,
        "years": years, "months": n, "emi": round(pay, 2),
        "total": round(total, 2), "interest": round(interest, 2),
        "text": (f"{fmt_num(principal)} loan @ {annual_rate_pct}%/saal, {n} mahine: "
                 f"EMI = {fmt_num(pay)}/mahina; total {fmt_num(total)} "
                 f"(interest {fmt_num(interest)})."),
    }


def simple_interest(principal: float, annual_rate_pct: float, years: float) -> dict:
    interest = principal * annual_rate_pct / 100.0 * years
    return {
        "principal": round(principal, 2), "interest": round(interest, 2),
        "total": round(principal + interest, 2),
        "text": (f"{fmt_num(principal)} @ {annual_rate_pct}% simple x {fmt_num(years)} saal: "
                 f"interest {fmt_num(interest)}, total {fmt_num(principal + interest)}."),
    }


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def parse_period(text: str) -> int:
    t = text.lower()
    if "quarter" in t or "trimonthly" in t or "3 month" in t:
        return 4
    if "month" in t or "mahin" in t or "mahina" in t:
        return 12
    if "week" in t or "hafta" in t:
        return 52
    if "day" in t or "roz" in t or "din" in t:
        return 365
    return 12
