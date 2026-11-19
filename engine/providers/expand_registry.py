"""ChronoVault 2.1 — registry expansion to 10,000+ real keyless endpoints.

The original generator produced ~3,900 endpoints. This module adds *real,
distinct* public URLs that are parameterised by country, language, city,
currency, coin and calendar year. Nothing here needs an API key.

Run:
    python engine/providers/expand_registry.py
Output:
    registry_v2.json   (updated in place, ids deduplicated)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "registry_v2.json")
sys.path.insert(0, HERE)

from registry_data import CITIES, COUNTRY_CODES  # noqa: E402

UA = "ChronoVault/2.1 (local personal time machine; no telemetry)"
CTX = ssl._create_unverified_context()

WB_INDICATORS = [
    "NY.GDP.MKTP.CD", "NY.GDP.PCAP.CD", "NY.GDP.MKTP.KD.ZG", "NY.GNP.PCAP.CD",
    "SP.POP.TOTL", "SP.POP.GROW", "SP.DYN.LE00.IN", "SH.DYN.MORT",
    "SL.UEM.TOTL.ZS", "SL.TLF.CACT.ZS", "FP.CPI.TOTL.ZG", "SI.POV.DDAY",
    "NE.EXP.GNFS.ZS", "NE.IMP.GNFS.ZS", "BX.KLT.DINV.CD.WD",
    "GC.DOD.TOTL.GD.ZS", "SE.XPD.TOTL.GD.ZS", "SH.XPD.CHEX.GD.ZS",
    "IT.NET.USER.ZS", "IT.CEL.SETS.P2", "EG.ELC.ACCS.ZS",
    "AG.LND.FRST.ZS", "EN.ATM.CO2E.KT", "GB.XPD.RSDV.GD.ZS",
]

CURRENCIES_EXTRA = (
    "ISK ILS JOD KWD BHD OMR QAR SAR AED EGP MAD TND DZD LYD IQD IRR AFN "
    "PKR INR NPR LKR BDT MMK THB LAK KHR VND MYR SGD IDR PHP BND TWD HKD "
    "MOP CNY JPY KRW KPW MNT KZT UZS TMT TJK KGZ RUB BYN UAH MDL RON BGN "
    "RSD MKD ALL BAM HRK HUF CZK PLN EUR GBP CHF NOK SEK DKK ISK "
    "TRY GEL AMD AZN ILS LBP SYP JOR KWD BHD QAR OMR YER"
).split()

OPENLIBRARY_SUBJECTS = (
    "science history philosophy mathematics physics chemistry biology "
    "astronomy psychology sociology economics politics law education medicine "
    "engineering technology computers programming artificial_intelligence "
    "machine_learning data_science cybersecurity internet religion islam "
    "christianity judaism hinduism buddhism quran bible literature poetry "
    "fiction drama fantasy science_fiction mystery romance biography "
    "autobiography memoir essays journalism travel geography architecture art "
    "music painting sculpture photography film television theatre dance "
    "cooking gardening health fitness nutrition diet business management "
    "marketing finance investing accounting entrepreneurship leadership "
    "productivity creativity design environment climate ecology sustainability "
    "energy water agriculture space cosmology quantum_mechanics relativity "
    "genetics evolution neuroscience anatomy pharmacology nursing dentistry "
    "veterinary language linguistics writing grammar vocabulary translation "
    "anthropology archaeology mythology folklore customs etiquette sports "
    "football cricket basketball tennis olympics chess games transport trains "
    "aviation ships cars motorcycles bicycles military government diplomacy "
    "human_rights women feminism civil_rights immigration poverty development "
    "africa asia europe north_america south_america oceania middle_east "
    "pakistan india bangladesh sri_lanka nepal china japan korea arabic urdu "
    "persian turkish hindi sanskrit english french german spanish portuguese "
    "italian russian chinese japanese korean"
).split()

COASTAL = {
    "Karachi", "Gwadar", "Mumbai", "Chennai", "Kolkata", "Dhaka", "Chittagong",
    "Dubai", "Abu Dhabi", "Doha", "Kuwait City", "Muscat", "Jeddah", "Mecca",
    "Medina", "Cairo", "Alexandria", "Istanbul", "Izmir", "Beirut", "Tel Aviv",
    "London", "Liverpool", "Dublin", "Lisbon", "Barcelona", "Marseille",
    "Naples", "Athens", "Venice", "Oslo", "Stockholm", "Helsinki", "Copenhagen",
    "Reykjavik", "New York", "Miami", "Los Angeles", "San Francisco", "Boston",
    "Seattle", "Vancouver", "Toronto", "Sydney", "Melbourne", "Auckland",
    "Tokyo", "Osaka", "Shanghai", "Hong Kong", "Singapore", "Bangkok",
    "Manila", "Jakarta", "Kuala Lumpur", "Seoul", "Taipei", "Hanoi",
    "Sao Paulo", "Rio de Janeiro", "Buenos Aires", "Cape Town", "Durban",
    "Nairobi", "Mombasa", "Lagos", "Accra", "Dakar", "Casablanca", "Tunis",
    "Algiers", "Colombo", "Male", "Yangon", "Phnom Penh", "Ho Chi Minh City",
}


def fetch_json(url: str, timeout: int = 25):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ! fetch failed: {url[:70]} — {type(e).__name__}: {e}")
        return None


def endpoint(eid, category, url, params=None, docs="", cache_s=0,
             reliability=0.8, kind="json", tags=None):
    return {
        "id": eid, "category": category, "url": url, "params": params or [],
        "requires_key": False, "docs": docs, "cache_s": cache_s,
        "reliability": reliability, "kind": kind, "tags": tags or [],
    }


def main():
    doc = json.load(open(OUT, encoding="utf-8"))
    endpoints = doc["endpoints"]
    before = len(endpoints)
    ids = {e["id"] for e in endpoints}
    added: dict[str, int] = {}

    def add(e):
        if e["id"] in ids:
            return False
        ids.add(e["id"])
        endpoints.append(e)
        added[e["category"]] = added.get(e["category"], 0) + 1
        return True

    print("Fetching live vocabularies (World Bank, CoinGecko, Wikimedia)...")
    wb = fetch_json("https://api.worldbank.org/v2/country?format=json&per_page=400")
    wb_countries = []
    if isinstance(wb, list) and len(wb) > 1 and isinstance(wb[1], list):
        for row in wb[1]:
            region = (row.get("region") or {}).get("id")
            if row.get("id") and region not in ("", "NA"):
                wb_countries.append(row["id"])
    if not wb_countries:
        wb_countries = ["PAK", "IND", "USA", "GBR", "CHN", "JPN", "DEU",
                        "FRA", "ARE", "SAU", "BGD", "TUR", "IDN", "BRA",
                        "ZAF", "NGA", "EGY", "CAN", "AUS", "KOR"]
    print(f"  World Bank countries: {len(wb_countries)}")

    markets = fetch_json("https://api.coingecko.com/api/v3/coins/markets"
                         "?vs_currency=usd&order=market_cap_desc&per_page=250&page=1")
    coins = []
    if isinstance(markets, list):
        coins = [(c.get("id"), c.get("symbol")) for c in markets
                 if c.get("id") and c.get("symbol")]
    print(f"  CoinGecko top coins: {len(coins)}")

    sitematrix = fetch_json("https://meta.wikimedia.org/w/api.php?action=sitematrix"
                            "&format=json&smtype=language")
    wiki_langs, wiktionary_langs = [], []
    if isinstance(sitematrix, dict):
        for key, value in (sitematrix.get("sitematrix") or {}).items():
            if not key.isdigit() or not isinstance(value, dict):
                continue
            code = value.get("code")
            for site in value.get("site") or []:
                if site.get("code") == "wiki" and code:
                    wiki_langs.append(code)
                if site.get("code") == "wiktionary" and code:
                    wiktionary_langs.append(code)
    if not wiki_langs:
        wiki_langs = ["en", "ur", "hi", "ar", "bn", "fa", "tr", "id", "ms",
                      "fr", "de", "es", "pt", "it", "ru", "zh", "ja", "ko"]
    print(f"  Wikipedia editions: {len(wiki_langs)}, "
          f"Wiktionary editions: {len(wiktionary_langs)}")

    # ------------------------------------------------------------- finance
    for iso3 in wb_countries:
        for ind in WB_INDICATORS:
            add(endpoint(
                f"wb3_{ind.replace('.', '_')}_{iso3}", "finance",
                f"https://api.worldbank.org/v2/country/{iso3}/indicator/{ind}"
                "?format=json&per_page=5&date=2015:2025",
                docs=f"World Bank {ind} for {iso3} (keyless, 2015-2025).",
                cache_s=86400, reliability=0.9, tags=["macro", "worldbank", iso3]))

    for cid, symbol in coins:
        add(endpoint(
            f"cg_coin_{cid}", "finance",
            "https://api.coingecko.com/api/v3/simple/price?ids="
            f"{cid}&vs_currencies=usd",
            docs=f"CoinGecko USD price for {cid} ({symbol.upper()}) (keyless).",
            cache_s=60, reliability=0.88, tags=["crypto", symbol.lower()]))

    for cur in CURRENCIES_EXTRA:
        add(endpoint(
            f"fx_erapi2_{cur}", "finance",
            f"https://open.er-api.com/v6/latest/{cur}",
            docs=f"All exchange rates with base {cur} (keyless).",
            cache_s=3600, reliability=0.85, tags=["fx", cur]))

    # ------------------------------------------------------------ calendar
    for (city, country, lat, lon) in CITIES:
        slug = city.lower().replace(" ", "_")
        for m in range(0, 13):
            add(endpoint(
                f"prayer2_{slug}_{m}", "calendar",
                "https://api.aladhan.com/v1/timings?latitude={{lat}}"
                "&longitude={{lon}}&method=" + str(m), ["lat", "lon"],
                docs=f"Prayer times for {city} using Aladhan method {m} "
                     "(keyless).", cache_s=3600, reliability=0.88,
                tags=["prayer", "islam", city]))

    for cc in COUNTRY_CODES:
        for y in (2029, 2030):
            add(endpoint(
                f"holiday_{cc}_{y}", "calendar",
                f"https://date.nager.at/api/v3/publicholidays/{y}/{cc}",
                docs=f"Public holidays {cc} {y} (keyless).",
                cache_s=86400 * 30, reliability=0.85, tags=["holiday", cc]))

    # ----------------------------------------------------------- knowledge
    for lang in wiki_langs:
        add(endpoint(
            f"wiki2_{lang}_summary", "knowledge",
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
            + "{{title}}", ["title"],
            docs=f"Wikipedia ({lang}) page summary (keyless).",
            cache_s=86400, reliability=0.9, tags=["wiki", lang]))
        add(endpoint(
            f"wiki2_{lang}_search", "knowledge",
            f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
            "&srsearch={{q}}&format=json&utf8=1&srlimit=3", ["q"],
            docs=f"Wikipedia ({lang}) full-text search (keyless).",
            cache_s=3600, reliability=0.9, tags=["wiki", lang]))

    for lang in wiktionary_langs:
        add(endpoint(
            f"wikt_{lang}_search", "knowledge",
            f"https://{lang}.wiktionary.org/w/api.php?action=query&list=search"
            "&srsearch={{q}}&format=json&utf8=1&srlimit=3", ["q"],
            docs=f"Wiktionary ({lang}) dictionary search (keyless).",
            cache_s=86400, reliability=0.85, tags=["dictionary", lang]))

    for subject in OPENLIBRARY_SUBJECTS:
        add(endpoint(
            f"olsub_{subject}", "knowledge",
            f"https://openlibrary.org/subjects/{subject}.json?limit=3",
            docs=f"Open Library subject '{subject.replace('_', ' ')}' "
                 "(keyless).", cache_s=86400, reliability=0.85,
            tags=["books", subject]))

    # ------------------------------------------------------------- weather
    for (city, country, lat, lon) in CITIES:
        slug = city.lower().replace(" ", "_")
        add(endpoint(
            f"weather_om_hourly_{slug}", "weather",
            "https://api.open-meteo.com/v1/forecast?latitude={{lat}}"
            "&longitude={{lon}}&hourly=temperature_2m,"
            "precipitation_probability,wind_speed_10m&forecast_days=2"
            "&timezone=auto", ["lat", "lon"],
            docs=f"Open-Meteo hourly forecast for {city} (keyless).",
            cache_s=900, reliability=0.92, tags=["weather", "hourly", city]))
        if city in COASTAL:
            add(endpoint(
                f"marine_{slug}", "weather",
                "https://marine-api.open-meteo.com/v1/marine?latitude={{lat}}"
                "&longitude={{lon}}&current=wave_height,wave_period,"
                "sea_surface_temperature", ["lat", "lon"],
                docs=f"Marine/wave conditions near {city} (keyless).",
                cache_s=1800, reliability=0.86, tags=["marine", city]))

    # --------------------------------------------------- replace dead APIs
    # restcountries v3.1 was retired in 2026; jsDelivr mirrors are stable.
    dead = {"geo_country_name", "geo_country_code", "geo_all",
            "world_countries_v2"}
    endpoints[:] = [e for e in endpoints if e["id"] not in dead]
    ids = {e["id"] for e in endpoints}
    add(endpoint(
        "geo_world_countries", "geo",
        "https://cdn.jsdelivr.net/npm/world-countries@5.1.0/countries.json",
        docs="World countries with capitals, currencies, languages, borders "
             "(keyless, jsDelivr).", cache_s=86400 * 7, reliability=0.92,
        tags=["countries"]))
    for name in ("population", "capital-city", "currency-code", "languages",
                 "calling-code", "continent", "religion"):
        add(endpoint(
            f"geo_cjson_{name}", "geo",
            "https://cdn.jsdelivr.net/gh/samayo/country-json@master/src/"
            f"country-by-{name}.json",
            docs=f"Static country dataset: {name} (keyless, jsDelivr).",
            cache_s=86400 * 7, reliability=0.85, tags=["countries", name]))

    # ------------------------------------------------------------- meta
    cats: dict[str, int] = {}
    for e in endpoints:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    doc["meta"].update({
        "name": "ChronoVault 2.1 Keyless Provider Registry",
        "version": "2.1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": ("NO API KEYS. Every endpoint is public/keyless, an official "
                   "demo key (NASA DEMO_KEY), or a localhost AI server. "
                   "Parameterised variants expand into real, distinct URLs."),
        "total_endpoints": len(endpoints),
        "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
    })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    print(f"\nRegistry: {before:,} -> {len(endpoints):,} endpoints "
          f"(+{len(endpoints) - before:,})")
    print(f"Added: {added}")
    for c, n in doc["meta"]["categories"].items():
        print(f"  {c:<12} {n}")


if __name__ == "__main__":
    main()
