"""ChronoVault 2.0 — domain sources.

Every function returns a "box":
    {ok, text, data, evidence, confidence, badge, meta}
No network call raises; failures become honest empty/partial boxes.
"""
from __future__ import annotations

import csv
import email.utils
import io
import json
import math
import re
import statistics
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import net
from .places import (CURRENCY_META, DEFAULT_CITY, city_slug, city_zone,
                     find_city)
from .text import clean, parse_rss, shorten

WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog", 51: "light drizzle",
    53: "moderate drizzle", 55: "dense drizzle", 56: "light freezing drizzle",
    57: "dense freezing drizzle", 61: "slight rain", 63: "moderate rain",
    65: "heavy rain", 66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snowfall", 73: "moderate snowfall", 75: "heavy snowfall",
    77: "snow grains", 80: "slight rain showers", 81: "moderate rain showers",
    82: "violent rain showers", 85: "slight snow showers",
    86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


def _rel(reg, eid, default=0.8):
    if reg:
        e = reg.get(eid)
        if e:
            return e.get("reliability", default)
    return default


def _ev(res, source, snippet, reliability=0.8):
    return {
        "source": source,
        "id": getattr(res, "endpoint_id", "") or "",
        "url": getattr(res, "url", ""),
        "ok": bool(getattr(res, "ok", False)),
        "snippet": shorten(snippet or "", 300),
        "reliability": reliability,
        "ms": getattr(res, "ms", 0),
        "cached": getattr(res, "cached", False),
        "tls_unverified": getattr(res, "tls_unverified", False),
    }


def box(text, data=None, evidence=None, confidence=0.8, badge="LIVE",
        meta=None, ok=True):
    return {
        "ok": ok, "text": text, "data": data or {}, "evidence": evidence or [],
        "confidence": round(float(confidence), 3), "badge": badge,
        "meta": meta or {},
    }


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def _fmt(x, dec=1):
    if x is None:
        return "?"
    return f"{x:,.{dec}f}"


# ============================================================== weather
def weather(city: str, lat: float, lon: float, days: int = 1, reg=None) -> dict:
    slug = city_slug(city)
    jobs = [
        {"id": f"weather_om_{slug}", "params": {"lat": lat, "lon": lon}},
        {"id": f"weather_wttr_{slug}", "params": {"city": city}},
        {"id": f"air_om_{slug}", "params": {"lat": lat, "lon": lon}},
    ]
    r_om, r_wttr, r_air = net.get_many(jobs, timeout=10, registry=reg)
    ev = []
    cur = {}
    daily = {}
    if r_om.ok and isinstance(r_om.data, dict):
        cur = r_om.data.get("current") or {}
        daily = r_om.data.get("daily") or {}
        code = cur.get("weather_code")
        ev.append(_ev(r_om, "Open-Meteo", json.dumps({
            "temp": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "precip": cur.get("precipitation"), "code": code,
        }), _rel(reg, r_om.endpoint_id, 0.92)))
    wcur = {}
    if r_wttr.ok and isinstance(r_wttr.data, dict):
        cc = r_wttr.data.get("current_condition") or []
        if cc:
            wcur = cc[0]
            ev.append(_ev(r_wttr, "wttr.in", json.dumps({
                "temp": wcur.get("temp_C"), "feels": wcur.get("FeelsLikeC"),
                "humidity": wcur.get("humidity"),
                "desc": (wcur.get("weatherDesc") or [{}])[0].get("value"),
            }), _rel(reg, r_wttr.endpoint_id, 0.8)))
    aqi = None
    if r_air.ok and isinstance(r_air.data, dict):
        ac = r_air.data.get("current") or {}
        aqi = _num(ac.get("us_aqi"))
        if aqi is not None:
            ev.append(_ev(r_air, "Open-Meteo Air", f"US AQI {aqi}, PM2.5 {ac.get('pm2_5')}",
                          _rel(reg, r_air.endpoint_id, 0.9)))
    if not cur and not wcur:
        return box("Mausam ka data abhi nahi mila (providers offline ya city name "
                   "samajh nahi aaya).", evidence=ev, confidence=0.3,
                   badge="NO-DATA", ok=False)

    temps = [v for v in [_num(cur.get("temperature_2m")),
                         _num(wcur.get("temp_C"))] if v is not None]
    temp = statistics.median(temps) if temps else None
    feels = _num(cur.get("apparent_temperature")) or _num(wcur.get("FeelsLikeC"))
    hum = _num(cur.get("relative_humidity_2m")) or _num(wcur.get("humidity"))
    wind = _num(cur.get("wind_speed_10m")) or _num(wcur.get("windspeedKmph"))
    desc = WMO.get(cur.get("weather_code")) or \
        ((wcur.get("weatherDesc") or [{}])[0].get("value") or "").lower()
    tmax = tmin = rain = None
    if daily:
        tmaxs = daily.get("temperature_2m_max") or []
        tmins = daily.get("temperature_2m_min") or []
        rains = daily.get("precipitation_probability_max") or []
        if tmaxs:
            tmax = _num(tmaxs[0])
        if tmins:
            tmin = _num(tmins[0])
        if rains:
            rain = _num(rains[0])
    spread = max(temps) - min(temps) if len(temps) > 1 else 0
    conf = 0.9 if len(temps) > 1 and spread <= 3 else (0.82 if temps else 0.7)
    if len(temps) > 1 and spread > 3:
        conf = 0.72

    parts = [f"{city} me abhi {_fmt(temp)}°C"]
    if feels is not None and temp is not None and abs(feels - temp) >= 1:
        parts[0] += f" (feels like {_fmt(feels)}°C)"
    if desc:
        parts.append(desc)
    if hum is not None:
        parts.append(f"humidity {_fmt(hum, 0)}%")
    if wind is not None:
        parts.append(f"wind {_fmt(wind, 0)} km/h")
    line = ", ".join(parts) + "."
    if tmax is not None and tmin is not None:
        line += f" Aaj max {_fmt(tmax)}°C / min {_fmt(tmin)}°C"
        if rain is not None:
            line += f", barish ka chance {_fmt(rain, 0)}%"
        line += "."
    if aqi is not None:
        cat = ("Good" if aqi <= 50 else "Moderate" if aqi <= 100 else
               "Unhealthy (sensitive)" if aqi <= 150 else "Unhealthy")
        line += f" Air quality: US AQI {_fmt(aqi, 0)} ({cat})."
    if len(temps) > 1:
        line += f" Cross-check: Open-Meteo {_fmt(temps[0])}°C vs wttr.in {_fmt(temps[1])}°C."
    return box(line, {
        "city": city, "temp_c": temp, "feels_c": feels, "humidity": hum,
        "wind_kmh": wind, "description": desc, "aqi": aqi,
        "daily": daily, "days": days,
        "sources": [e["source"] for e in ev if e["ok"]],
    }, ev, conf, "LIVE-CONSENSUS" if len(temps) > 1 else "LIVE")


# ================================================================= time
def time_now(zone: str, label: str | None = None, reg=None) -> dict:
    jobs = [
        {"url": f"https://timeapi.io/api/Time/current/zone?timeZone={urllib.parse.quote(zone)}",
         "ttl": 15, "kind": "json", "timeout": 8},
        {"url": f"https://worldtimeapi.org/api/timezone/{zone}",
         "ttl": 15, "kind": "json", "timeout": 8},
    ]
    r1, r2 = net.get_many(jobs, timeout=8, registry=reg)
    ev = []
    dt = None
    offset = ""
    abbr = ""
    if r1.ok and isinstance(r1.data, dict):
        raw = r1.data.get("dateTime") or r1.data.get("time") or ""
        try:
            dt = datetime.fromisoformat(raw.split(".")[0])
        except Exception:
            dt = None
        if dt:
            offset = dt.strftime("%z")
            abbr = r1.data.get("timeZone") or zone
            ev.append(_ev(r1, "timeapi.io", f"{raw} ({zone})", _rel(reg, r1.endpoint_id, 0.85)))
    if dt is None and r2.ok and isinstance(r2.data, dict):
        raw = r2.data.get("datetime") or ""
        try:
            dt = datetime.fromisoformat(raw.split(".")[0])
        except Exception:
            dt = None
        offset = r2.data.get("utc_offset") or offset
        abbr = r2.data.get("abbreviation") or abbr or zone
        if dt:
            ev.append(_ev(r2, "worldtimeapi.org", f"{raw} ({zone})",
                          _rel(reg, r2.endpoint_id, 0.72)))
    if dt is None:
        return box(f"{label or zone} ka waqt abhi nahi mila (time providers offline).",
                   evidence=ev, confidence=0.3, badge="NO-DATA", ok=False)
    off = offset
    if not off:
        try:
            off = dt.replace(tzinfo=ZoneInfo(zone)).strftime("%z")
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            off = ""
    if off and len(off) == 5 and off[0] in "+-":
        off = off[:3] + ":" + off[3:]
    suffix = f", UTC{off}" if off else ""
    txt = (f"{label or zone} me abhi {dt.strftime('%Y-%m-%d %H:%M:%S')} hai "
           f"({abbr}{suffix}).")
    if len(ev) > 1:
        txt += " Do independent time sources se cross-check hua."
    return box(txt, {
        "zone": zone, "datetime": dt.isoformat(), "offset": off,
        "abbreviation": abbr, "label": label or zone,
    }, ev, 0.96 if len(ev) > 1 else 0.9, "LIVE-CONSENSUS" if len(ev) > 1 else "LIVE")


# =================================================================== fx
def _fx_cross_from_usd(quote: str, reg=None):
    r = net.fetch("https://api.frankfurter.dev/v1/latest?base=USD&symbols=" +
                  urllib.parse.quote(quote), ttl=1800, endpoint_id="fx_usd_cross")
    if r.ok and isinstance(r.data, dict):
        v = _num((r.data.get("rates") or {}).get(quote))
        if v:
            return v, r.data.get("date")
    r2 = net.fetch("https://open.er-api.com/v6/latest/USD", ttl=1800,
                   endpoint_id="fx_erapi_USD")
    if r2.ok and isinstance(r2.data, dict):
        v = _num((r2.data.get("rates") or {}).get(quote))
        if v:
            return v, r2.data.get("time_last_update_utc")
    return None, None


def fx_rate(base: str, quote: str, amount: float = 1.0, reg=None) -> dict:
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return box(f"{base} → {quote}: rate 1.0 (same currency).",
                   {"base": base, "quote": quote, "rate": 1.0, "amount": amount,
                    "converted": amount}, confidence=1.0, badge="EXACT")
    jobs = []
    fe = f"fx_frank_{base}"
    if reg and reg.get(fe):
        jobs.append({"id": fe, "params": {"base": base, "symbols": quote}})
    else:
        jobs.append({"url": f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={quote}",
                     "ttl": 1800, "kind": "json"})
    ee = f"fx_erapi_{base}"
    if reg and reg.get(ee):
        jobs.append({"id": ee})
    else:
        jobs.append({"url": f"https://open.er-api.com/v6/latest/{base}",
                     "ttl": 1800, "kind": "json"})
    jobs.append({
        "url": ("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest"
                f"/v1/currencies/{base.lower()}.json"),
        "ttl": 1800, "kind": "json",
    })
    ra, rb, rc = net.get_many(jobs, timeout=12, registry=reg)
    values = []
    ev = []
    date_note = ""
    if ra.ok and isinstance(ra.data, dict):
        v = _num((ra.data.get("rates") or {}).get(quote))
        if v:
            values.append(("Frankfurter (ECB)", v))
            date_note = ra.data.get("date") or ""
            ev.append(_ev(ra, "Frankfurter/ECB", f"1 {base} = {v} {quote} ({date_note})",
                          _rel(reg, ra.endpoint_id, 0.95)))
    if rb.ok and isinstance(rb.data, dict):
        v = _num((rb.data.get("rates") or {}).get(quote))
        if v:
            values.append(("open.er-api", v))
            ev.append(_ev(rb, "open.er-api", f"1 {base} = {v} {quote}",
                          _rel(reg, rb.endpoint_id, 0.85)))
    if rc.ok and isinstance(rc.data, dict):
        v = _num((rc.data.get(base.lower()) or {}).get(quote.lower()))
        if v:
            values.append(("currency-api", v))
            if not date_note:
                date_note = rc.data.get("date") or ""
            ev.append(_ev(rc, "currency-api (jsDelivr)",
                          f"1 {base} = {v} {quote} ({date_note})", 0.9))
    if not values:
        # cross via USD
        usd_base, _ = _fx_cross_from_usd(base, reg)
        usd_quote, _ = _fx_cross_from_usd(quote, reg)
        if usd_base and usd_quote:
            v = usd_quote / usd_base
            values.append(("USD cross", v))
            ev.append({"source": "USD cross", "id": "", "url": "",
                       "ok": True, "snippet": f"1 {base} = {v} {quote} (USD cross)",
                       "reliability": 0.8, "ms": 0, "cached": False,
                       "tls_unverified": False})
    if not values:
        return box(f"{base} → {quote} ka rate abhi nahi mila (FX providers offline).",
                   evidence=ev, confidence=0.3, badge="NO-DATA", ok=False)

    nums = [v for _, v in values]
    rate = statistics.median(nums)
    spread = (max(nums) - min(nums)) / rate * 100 if rate else 0
    if len(nums) > 1 and spread <= 1:
        conf, badge = 0.94, "LIVE-CONSENSUS"
    elif len(nums) > 1:
        conf, badge = 0.78, "LIVE-DISAGREE"
    else:
        conf, badge = 0.82, "LIVE"
    conv = amount * rate
    bname = CURRENCY_META.get(base, (base, ""))[0]
    qname = CURRENCY_META.get(quote, (quote, ""))[0]
    txt = (f"1 {base} ({bname}) = {rate:,.4f} {quote} ({qname})"
           + (f" — reference date {date_note}" if date_note else "") + ".")
    if amount != 1:
        txt += f" {amount:,.2f} {base} = {conv:,.2f} {quote}."
    if len(values) > 1:
        txt += f" Cross-check: {', '.join(f'{n} {v:,.4f}' for n, v in values)} (spread {spread:.2f}%)."
    return box(txt, {
        "base": base, "quote": quote, "rate": rate, "amount": amount,
        "converted": conv, "inverse": 1 / rate if rate else None,
        "date": date_note, "spread_pct": round(spread, 3),
        "sources": [{"name": n, "value": v} for n, v in values],
    }, ev, conf, badge)


# =============================================================== crypto
def crypto_price(coin: str, symbol: str, amount: float = 1.0, reg=None) -> dict:
    jobs = [{"id": f"crypto_cg_{coin}", "params": {"ids": coin, "vs": "usd"}}]
    if symbol == "BTC":
        jobs += [
            {"url": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", "kind": "json"},
            {"url": "https://api.coinbase.com/v2/prices/BTC-USD/spot", "kind": "json"},
            {"url": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD", "kind": "json"},
        ]
    elif symbol == "ETH":
        jobs += [
            {"url": "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT", "kind": "json"},
            {"url": "https://api.coinbase.com/v2/prices/ETH-USD/spot", "kind": "json"},
        ]
    elif symbol == "SOL":
        jobs.append({"url": "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
                     "kind": "json"})
    results = net.get_many(jobs, timeout=10, registry=reg)
    ra = results[0]
    vals = []
    ev = []
    if ra.ok and isinstance(ra.data, dict) and coin in ra.data:
        v = _num((ra.data[coin] or {}).get("usd"))
        if v:
            vals.append(("CoinGecko", v))
            ev.append(_ev(ra, "CoinGecko", f"1 {symbol} = ${v:,.2f}",
                          _rel(reg, ra.endpoint_id, 0.88)))
    for r in results[1:]:
        v = None
        src = ""
        if "binance.com" in r.url and isinstance(r.data, dict):
            v = _num(r.data.get("price")); src = "Binance"
        elif "coinbase.com" in r.url and isinstance(r.data, dict):
            v = _num(((r.data.get("data") or {}).get("amount"))); src = "Coinbase"
        elif "kraken.com" in r.url and isinstance(r.data, dict):
            res = r.data.get("result") or {}
            if res:
                first = next(iter(res.values()), {})
                c = first.get("c") or []
                v = _num(c[0]) if c else None
            src = "Kraken"
        if v:
            vals.append((src, v))
            ev.append(_ev(r, src, f"1 {symbol} = ${v:,.2f}", 0.86))
    if not vals:
        return box(f"{symbol} ka price abhi nahi mila (crypto providers offline).",
                   evidence=ev, confidence=0.3, badge="NO-DATA", ok=False)
    nums = [v for _, v in vals]
    price = statistics.median(nums)
    spread = (max(nums) - min(nums)) / price * 100 if price else 0
    conf = 0.93 if len(vals) > 1 and spread <= 1 else (0.84 if len(vals) > 1 else 0.8)
    txt = f"1 {symbol} ({coin}) ≈ ${price:,.2f} USD."
    if len(vals) > 1:
        txt += f" Cross-check: {', '.join(f'{n} ${v:,.2f}' for n, v in vals)} (spread {spread:.2f}%)."
    if amount != 1:
        txt += f" {amount:,.4g} {symbol} ≈ ${amount * price:,.2f}."
    return box(txt, {
        "coin": coin, "symbol": symbol, "usd": price, "amount": amount,
        "value_usd": amount * price, "spread_pct": round(spread, 3),
        "sources": [{"name": n, "value": v} for n, v in vals],
    }, ev, conf, "LIVE-CONSENSUS" if len(vals) > 1 and spread <= 1 else "LIVE")


# ============================================================= holidays
def _ics_holidays(cc: str, year: int, reg=None) -> tuple[list[tuple[date, str]], list]:
    """Google's public holiday calendar — works where Nager.Date has no data."""
    url = ("https://calendar.google.com/calendar/ical/"
           f"en.{cc.lower()}%23holiday%40group.v.calendar.google.com/public/basic.ics")
    r = net.fetch(url, ttl=86400 * 7, kind="text", timeout=12,
                  endpoint_id=f"holiday_ics_{cc.upper()}")
    if not r.ok or not r.text:
        return [], []
    out = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", r.text, re.S):
        m = re.search(r"DTSTART[^:]*:(\d{8})", block)
        s = re.search(r"SUMMARY:(.+)", block)
        if not m or not s:
            continue
        try:
            d = date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
        except ValueError:
            continue
        if d.year != year:
            continue
        name = s.group(1).strip().replace("\\,", ",").replace("\\n", " ")
        if name:
            out.append((d, clean(name)))
    uniq = {}
    for d, name in out:
        uniq[(d, name)] = True
    parsed = sorted(uniq)
    ev = []
    if parsed:
        ev.append(_ev(r, "Google Holiday Calendar",
                      f"{len(parsed)} events for {cc} {year}", 0.78))
    return parsed, ev


def holidays(cc: str, year: int, reg=None) -> dict:
    cc = (cc or "PK").upper()
    eid = f"holiday_{cc}_{year}"
    if reg and reg.get(eid):
        r = net.get(eid, registry=reg, timeout=10)
    else:
        r = net.fetch(f"https://date.nager.at/api/v3/publicholidays/{year}/{cc}",
                      ttl=86400 * 30, endpoint_id=eid)
    ev = []
    items = r.data if r.ok and isinstance(r.data, list) else []
    parsed = []
    if items:
        ev.append(_ev(r, "Nager.Date", f"{len(items)} public holidays for {cc} {year}",
                      _rel(reg, eid, 0.85)))
        for h in items:
            try:
                d = date.fromisoformat(h.get("date", ""))
            except Exception:
                continue
            parsed.append((d, h.get("localName") or h.get("name") or ""))
    source = "Nager.Date"
    if not parsed:
        parsed, ics_ev = _ics_holidays(cc, year, reg)
        ev.extend(ics_ev)
        source = "Google Holiday Calendar" if parsed else ""
    if not parsed:
        return box(f"{cc} {year} ki holiday list nahi mili (Nager.Date aur Google "
                   f"calendar dono se koi data nahi aaya).", evidence=ev,
                   confidence=0.3, badge="NO-DATA", ok=False)
    parsed.sort()
    today = date.today()
    upcoming = [p for p in parsed if p[0] >= today] if year == today.year else parsed
    shown = upcoming[:10] or parsed[:10]
    lines = [f"{d.strftime('%d %b %Y')} — {name}" for d, name in shown]
    label = ("holidays/observances" if source == "Google Holiday Calendar"
             else "public holidays")
    txt = f"{cc} {year}: {len(parsed)} {label} ({source}). Next/important:\n" + \
          "\n".join("• " + x for x in lines)
    if year == today.year and len(upcoming) > len(shown):
        txt += f"\n… aur {len(upcoming) - len(shown)} baqi hain."
    return box(txt, {
        "country": cc, "year": year, "count": len(parsed), "source": source,
        "holidays": [{"date": d.isoformat(), "name": n} for d, n in parsed],
    }, ev, 0.88 if source == "Google Holiday Calendar" else 0.9, "ARCHIVE")


# ============================================================== country
def _country_match(docs: list, cc: str | None, query: str):
    if cc:
        code = cc.upper()
        for x in docs:
            if code in (x.get("cca2"), x.get("cca3"), x.get("ccn3")):
                return x
    q = (query or "").strip().casefold()
    if not q:
        return None
    # exact common/official/alternate name first
    for x in docs:
        names = [(x.get("name") or {}).get("common", ""),
                 (x.get("name") or {}).get("official", "")]
        names += x.get("altSpellings") or []
        if any(q == (n or "").casefold() for n in names):
            return x
    for x in docs:
        common = ((x.get("name") or {}).get("common") or "").casefold()
        if q and (q in common or common in q):
            return x
    return None


def country_info(cc: str | None = None, query: str = "", reg=None) -> dict:
    """Country facts from the world-countries dataset (restcountries data,
    served keyless via jsDelivr). Falls back to Wikipedia if unavailable."""
    url = "https://cdn.jsdelivr.net/npm/world-countries@5.0.0/countries.json"
    r = net.fetch(url, ttl=86400 * 30, timeout=14,
                  endpoint_id="world_countries_json")
    ev = []
    docs = r.data if r.ok and isinstance(r.data, list) else []
    doc = _country_match(docs, cc, query) if docs else None
    if doc:
        ev.append(_ev(r, "world-countries (jsDelivr)",
                      f"{(doc.get('name') or {}).get('common', '')} — 250-country dataset",
                      0.88))
    if not doc:
        w = wiki_summary(query or cc or "", reg=reg)
        if w.get("ok"):
            return box(w["text"], {"fallback": "wikipedia", **w.get("data", {})},
                       w.get("evidence", []), 0.72, "ARCHIVE")
        return box(f"{query or cc} ki country info nahi mili.", evidence=ev,
                   confidence=0.3, badge="NO-DATA", ok=False)
    name = (doc.get("name") or {}).get("common") or query or cc
    official = (doc.get("name") or {}).get("official") or ""
    capital = ", ".join(doc.get("capital") or []) or "—"
    pop = None
    pop_year = None
    pop_r = net.fetch(
        "https://cdn.jsdelivr.net/npm/country-json@1.1.4/src/country-by-population.json",
        ttl=86400 * 30, timeout=8, endpoint_id="country_json_population")
    if pop_r.ok and isinstance(pop_r.data, list):
        aliases = [name, official] + (doc.get("altSpellings") or [])
        aliases = [a.casefold() for a in aliases if a]
        row = next((x for x in pop_r.data
                    if (x.get("country") or "").casefold() in aliases), None)
        if not row:
            row = next((x for x in pop_r.data
                        if any(a and (x.get("country") or "").casefold() == a
                               for a in aliases)), None)
        if row and row.get("population"):
            pop = int(row["population"])
            pop_year = 2018
            ev.append(_ev(pop_r, "country-json population",
                          f"{pop:,} (2018 dataset)", 0.7))
    region = doc.get("region") or ""
    sub = doc.get("subregion") or ""
    cur = doc.get("currencies") or {}
    cur_txt = ", ".join(f"{k} ({v.get('name', '')})" for k, v in cur.items())
    langs = ", ".join((doc.get("languages") or {}).values())
    tz = ", ".join((doc.get("timezones") or [])[:3])
    area = doc.get("area")
    cca2 = (doc.get("cca2") or "").lower()
    flag = f"https://flagcdn.com/w320/{cca2}.png" if cca2 else ""
    parts = [f"{name}: capital {capital}"]
    if pop:
        parts.append(f"population ~{pop:,}" +
                     (f" ({pop_year} dataset)" if pop_year else ""))
    if region:
        parts.append(f"region {region}" + (f" / {sub}" if sub else ""))
    if cur_txt:
        parts.append(f"currency {cur_txt}")
    if langs:
        parts.append(f"languages {langs}")
    if tz:
        parts.append(f"timezones {tz}")
    if area:
        parts.append(f"area {area:,.0f} km²")
    txt = "; ".join(parts) + "."
    return box(txt, {
        "name": name, "official": official,
        "cca2": doc.get("cca2"), "capital": capital,
        "population": pop, "population_year": pop_year,
        "region": region, "subregion": sub,
        "currencies": cur, "languages": doc.get("languages"),
        "timezones": doc.get("timezones"), "area": area,
        "flag": flag,
    }, ev, 0.86, "ARCHIVE")


# ================================================================= news
def _parse_date(s: str):
    try:
        return email.utils.parsedate_to_datetime(s)
    except Exception:
        return None


def news(query: str = "", reg=None, limit: int = 7) -> dict:
    q = query.strip()
    jobs = []
    if q:
        jobs.append({"url": "https://news.google.com/rss/search?q=" +
                     urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en",
                     "kind": "xml", "ttl": 900})
        jobs.append({"url": "https://www.bing.com/news/search?q=" +
                     urllib.parse.quote(q) + "&format=RSS",
                     "kind": "xml", "ttl": 900})
    else:
        jobs.append({"id": "rss_bbc_top", "kind": "xml"})
        jobs.append({"id": "rss_aljazeera_all", "kind": "xml"})
    jobs.append({"id": "rss_bbc_world", "kind": "xml"})
    results = net.get_many(jobs, timeout=10, registry=reg)
    feeds: list[tuple[object, list[dict]]] = []
    items = []
    seen = set()
    for r in results:
        if not r.ok or not isinstance(r.data, str):
            continue
        parsed = parse_rss(r.data, limit=10)
        if not parsed:
            continue
        feeds.append((r, parsed))
        for it in parsed:
            key = re.sub(r"\W+", "", it["title"].lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            it["_key"] = key
            it["_ts"] = _parse_date(it.get("date", ""))
            items.append(it)
    if not items:
        return box("Abhi koi news feed nahi mila (network off ya feeds block).",
                   evidence=[], confidence=0.3, badge="NO-DATA", ok=False)
    checked = len(items)
    matched = False
    if q:
        toks = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) > 1]
        need = 1 if len(toks) <= 1 else max(2, (len(toks) + 1) // 2)
        def hits(it):
            text = (it.get("title", "") + " " +
                    (it.get("summary") or "")).lower()
            n = 0
            for tok in toks:
                if len(tok) <= 3:
                    if re.search(r"(?<!\w)" + re.escape(tok) + r"(?!\w)", text):
                        n += 1
                elif tok in text:
                    n += 1
            return n
        filtered = [it for it in items if hits(it) >= need]
        if filtered:
            items = filtered
            matched = True
        else:
            # Do not label unrelated headlines as if they answered the query.
            # Showing a random BBC headline under a user's topic would be a
            # provenance lie, even if the feed itself is healthy.
            return box(
                f"Is sawal ({q}) se match karti koi recent news nahi mili. "
                f"{checked} headlines check kiye gaye, lekin koi relevant "
                f"match nahi tha — is liye unhein jawab ke tor par pesh nahi "
                f"kiya ja raha.",
                {"query": q, "matched": False, "checked": checked,
                 "items": []},
                evidence=[], confidence=0.2, badge="NO-DATA", ok=False)
    items.sort(key=lambda x: x["_ts"].timestamp() if x.get("_ts") else 0, reverse=True)
    items = items[:limit]
    matched_keys = {it.get("_key") for it in items}
    ev = []
    for r, parsed in feeds:
        n = sum(1 for it in parsed if it.get("_key") in matched_keys) if q \
            else len(parsed)
        if n:
            ev.append(_ev(r, "RSS", f"{n} matching items from {r.url[:80]}",
                          0.82))
    lines = []
    for it in items:
        d = it["_ts"].strftime("%d %b %H:%M") if it.get("_ts") else ""
        src = f" — {it['source']}" if it.get("source") else ""
        lines.append(f"• {it['title']}{src}" + (f" ({d})" if d else ""))
    if q:
        head = f'News matching "{q}" ({len(items)} stories):'
    else:
        head = f"Latest headlines ({len(items)} stories):"
    return box(head + "\n" + "\n".join(lines), {
        "query": q, "matched": matched, "checked": checked,
        "items": [{
            "title": it["title"], "link": it["link"],
            "date": it["_ts"].isoformat() if it.get("_ts") else it.get("date", ""),
            "source": it.get("source", ""), "summary": it.get("summary", ""),
        } for it in items],
    }, ev, 0.82, "LIVE-NEWS")


# ================================================================ space
def space(kind: str = "iss", reg=None) -> dict:
    ev = []
    if kind == "iss":
        # Primary: wheretheiss.at (HTTPS, reliable). Fallback: Open Notify.
        r_primary = net.fetch("https://api.wheretheiss.at/v1/satellites/25544",
                              ttl=30, endpoint_id="iss_wheretheiss", timeout=9)
        lat = lon = None
        when = ""
        if r_primary.ok and isinstance(r_primary.data, dict):
            lat = _num(r_primary.data.get("latitude"))
            lon = _num(r_primary.data.get("longitude"))
            ts = r_primary.data.get("timestamp")
            when = datetime.fromtimestamp(ts, timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC") if ts else ""
            ev.append(_ev(r_primary, "wheretheiss.at", f"lat {lat}, lon {lon}", 0.9))
        if lat is None:
            r1 = net.fetch("http://api.open-notify.org/iss-now.json", ttl=30,
                           endpoint_id="iss_open_notify", timeout=8)
            if r1.ok and isinstance(r1.data, dict):
                pos = r1.data.get("iss_position") or {}
                lat, lon = _num(pos.get("latitude")), _num(pos.get("longitude"))
                ts = r1.data.get("timestamp")
                when = datetime.fromtimestamp(ts, timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC") if ts else ""
                ev.append(_ev(r1, "Open Notify ISS", f"lat {lat}, lon {lon}", 0.8))
        r2 = net.fetch("http://api.open-notify.org/astros.json", ttl=300,
                       endpoint_id="iss_astros", timeout=8)
        people = []
        if r2.ok and isinstance(r2.data, dict):
            people = [p.get("name") for p in r2.data.get("people") or []]
            ev.append(_ev(r2, "Open Notify Astros", f"{len(people)} people in space", 0.8))
        if lat is None:
            return box("ISS ki position abhi nahi mili.", evidence=ev,
                       confidence=0.3, badge="NO-DATA", ok=False)
        txt = f"ISS abhi {lat:.2f}°, {lon:.2f}° par hai ({when})."
        if people:
            txt += f" Space me {len(people)} log hain: {', '.join(people[:6])}"
            if len(people) > 6:
                txt += "…"
            txt += "."
        return box(txt, {"lat": lat, "lon": lon, "timestamp": when,
                         "people": people}, ev, 0.86, "LIVE")

    if kind == "quake":
        # Primary: USGS
        r = net.fetch("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
                      ttl=600, endpoint_id="fact_earthquakes_usgs")
        if not r.ok or not isinstance(r.data, dict):
            # Fallback: EMSC (European-Mediterranean Seismological Centre)
            r = net.fetch("https://www.seismicportal.eu/fdsnws/event/1/query?format=geojson&limit=50&minmag=3",
                          ttl=600, endpoint_id="fact_earthquakes_emsc")
            if not r.ok or not isinstance(r.data, dict):
                return box("Earthquake feed abhi nahi mila.", evidence=ev,
                           confidence=0.3, badge="NO-DATA", ok=False)
            ev.append(_ev(r, "EMSC", "geojson feed", 0.90))
            feats = r.data.get("features") or []
            quakes = []
            for f in feats:
                p = f.get("properties") or {}
                m = _num(p.get("mag"))
                if m is None:
                    continue
                when = ""
                if p.get("time"):
                    try:
                        when = datetime.fromtimestamp(p["time"] / 1000, timezone.utc).strftime("%d %b %H:%M")
                    except Exception:
                        pass
                place = p.get("place") or p.get("location") or "unknown"
                quakes.append((m, place, when))
            quakes.sort(reverse=True)
            if not quakes:
                return box("Aaj koi notable earthquake record nahi hua.", evidence=ev,
                           confidence=0.8, badge="LIVE", ok=True)
            lines = [f"M{m:.1f} — {place} ({when})" for m, place, when in quakes[:6]]
            txt = (f"Aaj {len(quakes)} earthquakes record hue. Sab se bade:\n" +
                   "\n".join("• " + x for x in lines))
            return box(txt, {"count": len(quakes), "top": [
                {"mag": m, "place": p, "time": t} for m, p, t in quakes[:10]]},
                ev, 0.9, "LIVE")
        ev.append(_ev(r, "USGS", "all_day feed", 0.92))
        feats = r.data.get("features") or []
        quakes = []
        for f in feats:
            p = f.get("properties") or {}
            m = _num(p.get("mag"))
            if m is None:
                continue
            when = ""
            if p.get("time"):
                try:
                    when = datetime.fromtimestamp(p["time"] / 1000, timezone.utc).strftime("%d %b %H:%M")
                except Exception:
                    pass
            quakes.append((m, p.get("place") or "unknown", when))
        quakes.sort(reverse=True)
        if not quakes:
            return box("Aaj koi notable earthquake record nahi hua.", evidence=ev,
                       confidence=0.8, badge="LIVE", ok=True)
        lines = [f"M{m:.1f} — {place} ({when})" for m, place, when in quakes[:6]]
        txt = (f"Aaj {len(quakes)} earthquakes record hue. Sab se bade:\n" +
               "\n".join("• " + x for x in lines))
        return box(txt, {"count": len(quakes), "top": [
            {"mag": m, "place": p, "time": t} for m, p, t in quakes[:10]]},
            ev, 0.9, "LIVE")

    if kind == "launch":
        r1, r2 = net.get_many([
            {"url": "https://api.spacexdata.com/v4/launches/latest", "kind": "json", "ttl": 3600},
            {"url": "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=3", "kind": "json", "ttl": 3600},
        ], timeout=10, registry=reg)
        parts = []
        data = {}
        if r1.ok and isinstance(r1.data, dict):
            d = r1.data
            parts.append(f"Last SpaceX launch: {d.get('name')} ({d.get('date_utc', '')[:10]}) — "
                         f"{'success' if d.get('success') else d.get('details', 'status unknown')}.")
            data["latest"] = {"name": d.get("name"), "date": d.get("date_utc"),
                              "success": d.get("success"), "details": d.get("details")}
            ev.append(_ev(r1, "SpaceX API", d.get("name") or "", 0.9))
        if r2.ok and isinstance(r2.data, dict):
            res = r2.data.get("results") or []
            if res:
                n = res[0]
                parts.append(f"Next launch: {n.get('name')} — {n.get('net', '')[:16]} "
                             f"({(n.get('pad') or {}).get('location', {}).get('name', '')}).")
                data["upcoming"] = [{"name": x.get("name"), "net": x.get("net")} for x in res]
                ev.append(_ev(r2, "Launch Library", n.get("name") or "", 0.85))
        if not parts:
            return box("Launch data abhi nahi mila.", evidence=ev,
                       confidence=0.3, badge="NO-DATA", ok=False)
        return box(" ".join(parts), data, ev, 0.88, "LIVE")

    if kind == "apod":
        r = net.fetch("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY",
                      ttl=3600, endpoint_id="space_apod")
        if r.ok and isinstance(r.data, dict):
            d = r.data
            ev.append(_ev(r, "NASA APOD", d.get("title") or "", 0.9))
            return box(f"NASA APOD ({d.get('date')}): {d.get('title')} — {d.get('explanation', '')}",
                       {"title": d.get("title"), "date": d.get("date"),
                        "url": d.get("url"), "hdurl": d.get("hdurl"),
                        "explanation": d.get("explanation")}, ev, 0.88, "ARCHIVE")
        return box("NASA APOD abhi nahi mila.", evidence=ev, confidence=0.3,
                   badge="NO-DATA", ok=False)

    # solar
    r = net.fetch("https://services.swpc.noaa.gov/products/alerts.json",
                  ttl=1800, endpoint_id="space_noaa_alerts")
    if r.ok and isinstance(r.data, list):
        msgs = [x.get("message", "") for x in r.data[:3] if isinstance(x, dict)]
        ev.append(_ev(r, "NOAA SWPC", f"{len(r.data)} alerts", 0.85))
        txt = "NOAA space-weather alerts:\n" + "\n".join(
            "• " + clean(m)[:220] for m in msgs)
        return box(txt, {"alerts": [clean(m)[:500] for m in msgs]}, ev, 0.85, "LIVE")
    return box("Space weather data abhi nahi mila.", evidence=ev,
               confidence=0.3, badge="NO-DATA", ok=False)


# ============================================================= knowledge
def wiki_summary(query: str, lang: str = "en", reg=None) -> dict:
    r = net.fetch(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/" +
                  urllib.parse.quote(query.replace(" ", "_")),
                  ttl=86400, endpoint_id=f"wiki_{lang}_summary")
    ev = []
    if r.ok and isinstance(r.data, dict) and r.data.get("extract"):
        ev.append(_ev(r, f"Wikipedia ({lang})", r.data.get("title", ""), 0.9))
        return box(r.data.get("extract", ""), {
            "title": r.data.get("title"), "description": r.data.get("description"),
            "url": (r.data.get("content_urls") or {}).get("desktop", {}).get("page"),
            "thumbnail": (r.data.get("thumbnail") or {}).get("source"),
        }, ev, 0.9, "ARCHIVE", ok=True)
    # search then summary
    s = net.fetch(f"https://{lang}.wikipedia.org/w/api.php",
                  params={"action": "query", "list": "search", "srsearch": query,
                          "format": "json", "utf8": 1, "srlimit": 3},
                  ttl=3600, endpoint_id=f"wiki_{lang}_search")
    if s.ok and isinstance(s.data, dict):
        hits = ((s.data.get("query") or {}).get("search") or [])
        if hits:
            title = hits[0].get("title", "")
            r2 = net.fetch(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/" +
                           urllib.parse.quote(title.replace(" ", "_")),
                           ttl=86400, endpoint_id=f"wiki_{lang}_summary")
            if r2.ok and isinstance(r2.data, dict) and r2.data.get("extract"):
                ev.append(_ev(r2, f"Wikipedia ({lang})", title, 0.9))
                return box(r2.data.get("extract", ""), {
                    "title": r2.data.get("title"),
                    "description": r2.data.get("description"),
                    "url": (r2.data.get("content_urls") or {}).get("desktop", {}).get("page"),
                    "thumbnail": (r2.data.get("thumbnail") or {}).get("source"),
                }, ev, 0.86, "ARCHIVE", ok=True)
    return box("", {}, ev, 0.2, "NO-DATA", ok=False)


def knowledge(query: str, reg=None) -> dict:
    q = query.strip()
    if not q:
        return box("Sawal samajh nahi aaya — thora wazeh likhein.", confidence=0.2,
                   badge="NEED-QUESTION", ok=False)
    jobs = [
        {"id": "wiki_en_summary", "params": {"title": q.replace(" ", "_")}},
        {"id": "wiki_en_search", "params": {"q": q}},
        {"id": "ddg_instant", "params": {"q": q}},
        {"id": "openalex_search", "params": {"q": q}},
        {"id": "openlibrary_search", "params": {"q": q}},
        {"id": "wiki_ur_search", "params": {"q": q}},
    ]
    results = net.get_many(jobs, timeout=10, registry=reg)
    r_sum, r_search, r_ddg, r_oa, r_ol, r_ur = results
    ev = []
    title = ""
    definition = ""
    url = ""
    thumb = ""
    description = ""
    if r_sum.ok and isinstance(r_sum.data, dict) and r_sum.data.get("extract"):
        title = r_sum.data.get("title") or q
        definition = r_sum.data.get("extract") or ""
        description = r_sum.data.get("description") or ""
        url = (r_sum.data.get("content_urls") or {}).get("desktop", {}).get("page") or ""
        thumb = (r_sum.data.get("thumbnail") or {}).get("source") or ""
        ev.append(_ev(r_sum, "Wikipedia (en)", title, 0.9))
    if not definition and r_search.ok and isinstance(r_search.data, dict):
        hits = ((r_search.data.get("query") or {}).get("search") or [])
        if hits:
            t = hits[0].get("title", "")
            r2 = net.fetch("https://en.wikipedia.org/api/rest_v1/page/summary/" +
                           urllib.parse.quote(t.replace(" ", "_")),
                           ttl=86400, endpoint_id="wiki_en_summary")
            if r2.ok and isinstance(r2.data, dict) and r2.data.get("extract"):
                title = r2.data.get("title") or t
                definition = r2.data.get("extract") or ""
                description = r2.data.get("description") or ""
                url = (r2.data.get("content_urls") or {}).get("desktop", {}).get("page") or ""
                thumb = (r2.data.get("thumbnail") or {}).get("source") or ""
                ev.append(_ev(r2, "Wikipedia (en)", title, 0.9))
    ddg = {}
    if r_ddg.ok and isinstance(r_ddg.data, dict):
        ddg = r_ddg.data
        abstract = ddg.get("AbstractText") or ddg.get("Answer") or ddg.get("Definition") or ""
        if abstract:
            if not definition:
                definition = abstract
                title = ddg.get("Heading") or title or q
                url = ddg.get("AbstractURL") or url
            ev.append(_ev(r_ddg, "DuckDuckGo", abstract, 0.78))
    facts = []
    papers = []
    if r_oa.ok and isinstance(r_oa.data, dict):
        for w in (r_oa.data.get("results") or [])[:2]:
            t = w.get("title") or ""
            y = w.get("publication_year")
            if t:
                papers.append(f"{t} ({y})" if y else t)
        if papers:
            ev.append(_ev(r_oa, "OpenAlex", "; ".join(papers), 0.88))
            facts.append("Research: " + "; ".join(papers))
    books = []
    if r_ol.ok and isinstance(r_ol.data, dict):
        for b in (r_ol.data.get("docs") or [])[:2]:
            t = b.get("title") or ""
            a = (b.get("author_name") or [""])[0]
            y = b.get("first_publish_year")
            if t:
                books.append(f"{t}" + (f" — {a}" if a else "") + (f" ({y})" if y else ""))
        if books:
            ev.append(_ev(r_ol, "Open Library", "; ".join(books), 0.85))
            facts.append("Books: " + "; ".join(books))
    if not definition:
        if r_ur.ok and isinstance(r_ur.data, dict):
            hits = ((r_ur.data.get("query") or {}).get("search") or [])
            if hits:
                t = hits[0].get("title", "")
                w = wiki_summary(t, "ur", reg)
                if w.get("ok"):
                    definition = w["text"]
                    title = w.get("data", {}).get("title") or t
                    url = w.get("data", {}).get("url") or url
                    ev.extend(w.get("evidence", []))
        if not definition and papers:
            definition = ("Is topic par seedha encyclopedia summary nahi mila, lekin "
                          "research papers milte hain: " + "; ".join(papers))
            title = title or q
        elif not definition and books:
            definition = ("Is topic par books milti hain: " + "; ".join(books))
            title = title or q
    if not definition:
        return box("", {"query": q}, ev, 0.2, "NO-DATA", ok=False)

    definition = clean(definition)
    if description and description.lower() not in definition.lower()[:200]:
        definition = f"{description}. {definition}"
    txt = f"{title}: {definition}"
    if facts:
        txt += "\n\n" + "\n".join(facts)
    src_names = []
    for e in ev:
        if e["source"] not in src_names:
            src_names.append(e["source"])
    txt += f"\n\nSources: {', '.join(src_names)}."
    conf = 0.88 if ("Wikipedia (en)" in src_names and "DuckDuckGo" in src_names) else (
        0.84 if "Wikipedia (en)" in src_names else (0.62 if "DuckDuckGo" in src_names else 0.55))
    return box(txt, {
        "title": title, "definition": definition, "url": url,
        "thumbnail": thumb, "facts": facts, "papers": papers, "books": books,
        "sources": src_names,
    }, ev, conf, "ARCHIVE")


# =============================================================== series
def fx_series(base: str, quote: str, days: int = 180, reg=None) -> list[tuple[str, float]]:
    base, quote = base.upper(), quote.upper()
    end = date.today()
    start = end - timedelta(days=max(10, days))
    url = (f"https://api.frankfurter.dev/v1/{start.isoformat()}..{end.isoformat()}"
           f"?base={base}&symbols={quote}")
    r = net.fetch(url, ttl=3600, endpoint_id="fx_frank_series", timeout=14)
    out = []
    if r.ok and isinstance(r.data, dict):
        rates = r.data.get("rates") or {}
        for d, rec in rates.items():
            v = _num((rec or {}).get(quote))
            if v:
                out.append((d, v))
    # Yahoo Finance historical daily FX (keyless, all pairs)
    if not out:
        y = net.fetch(
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{base}{quote}=X?range=1y&interval=1d", ttl=3600, kind="json",
            timeout=14, endpoint_id="series_yahoo")
        if y.ok and isinstance(y.data, dict):
            result = ((y.data.get("chart") or {}).get("result") or [None])[0]
            closes = (((result or {}).get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            stamps = (result or {}).get("timestamp") or []
            for val, ts in zip(closes, stamps):
                if val is None or not ts:
                    continue
                try:
                    d = datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat()
                    out.append((d, float(val)))
                except Exception:
                    continue
    if out:
        out.sort()
        return out
    # Stooq fallback (USD pairs)
    pair = (base + quote).lower()
    r2 = net.fetch(f"https://stooq.com/q/d/l/?s={pair}&i=d", ttl=3600,
                   kind="text", timeout=14, endpoint_id="stooq_history")
    if r2.ok and r2.text:
        try:
            rows = list(csv.DictReader(io.StringIO(r2.text)))
            for row in rows[-max(10, days):]:
                d = row.get("Date") or ""
                c = _num(row.get("Close"))
                if d and c:
                    out.append((d, c))
        except Exception:
            pass
    out.sort()
    return out


def crypto_series(coin: str, days: int = 180, reg=None) -> list[tuple[str, float]]:
    days = max(30, min(365, int(days)))
    r = net.fetch(f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
                  f"?vs_currency=usd&days={days}", ttl=600,
                  endpoint_id="crypto_cg_chart", timeout=14)
    if not r.ok or not isinstance(r.data, dict):
        return []
    prices = r.data.get("prices") or []
    by_day = {}
    for pair in prices:
        try:
            ts, val = pair[0] / 1000, float(pair[1])
        except Exception:
            continue
        d = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
        by_day[d] = val
    return sorted(by_day.items())


# ================================================================== LLM
def llm(prompt: str, system: str = "", timeout: float = 24.0) -> dict:
    """Keyless LLM synthesis with strict grounding. Never invents silently."""
    sys_msg = system or (
        "You are ChronoVault, a careful research assistant. Answer in natural "
        "Roman Urdu (Hinglish), 2-4 short sentences. Use ONLY the evidence "
        "provided. If evidence is insufficient, say exactly what is missing. "
        "Never invent numbers, dates, or sources. End with a short parenthetical "
        "source note when sources are given."
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": prompt[:3000]},
    ]
    r = llm_chat(messages, model="openai-fast", temperature=0.35,
                 timeout=timeout)
    if r.get("ok"):
        return r
    # GET fallback (shorter prompt)
    short = prompt[:1400]
    r2 = net.fetch("https://text.pollinations.ai/" + urllib.parse.quote(short),
                   ttl=21600, kind="text", timeout=timeout,
                   endpoint_id="ai_pollinations_text")
    text = ""
    if r2.ok and r2.text:
        text = r2.text
    text = clean(text).strip().strip('"').strip()
    text = re.sub(r"\s*[\u2010-\u2015]\s*", " - ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 12 or text.lower().startswith(("error", "{\"error")):
        return {"ok": False, "text": "", "source": "", "error": "LLM unavailable"}
    return {"ok": True, "text": text,
            "source": "Pollinations (keyless LLM)", "model": "openai-fast"}


def llm_chat(messages: list[dict], model: str = "openai-fast",
             temperature: float = 0.4, timeout: float = 30.0,
             max_tokens: int = 700) -> dict:
    """OpenAI-compatible keyless chat call (Pollinations anonymous tier).

    `messages` is a standard role/content list. Returns {ok,text,source,model}.
    Never retries in a tight loop; callers decide how to degrade.
    """
    body = {
        "model": model or "openai-fast",
        "messages": messages,
        "temperature": max(0.0, min(1.2, float(temperature))),
        "private": True,
        "max_tokens": max(32, int(max_tokens)),
    }
    r = net.fetch("https://text.pollinations.ai/openai", method="POST",
                  json_body=body, ttl=21600, timeout=timeout,
                  endpoint_id="ai_pollinations_openai")
    text = ""
    if r.ok and isinstance(r.data, dict):
        try:
            text = r.data["choices"][0]["message"]["content"]
        except Exception:
            text = r.data.get("text") or r.data.get("response") or ""
    if not text and r.ok and isinstance(r.data, str):
        text = r.data
    text = clean(text).strip().strip('"').strip()
    text = re.sub(r"\s*[\u2010-\u2015]\s*", " - ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 8 or text.lower().startswith(("error", "{\"error")):
        return {"ok": False, "text": "", "source": "Pollinations",
                "model": body["model"], "error": "LLM unavailable"}
    return {"ok": True, "text": text, "source": "Pollinations (keyless LLM)",
            "model": body["model"]}
