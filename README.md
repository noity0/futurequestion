# ⏳ ChronoVault 2.2.0 — The Keyless Time Machine

> **TL;DR:** A working "time machine" in Python — past archives + live present data + statistical future forecasts, with honest confidence badges. No API keys. No telemetry. Local-first.

Real time travel is not possible. ChronoVault does the honest version: it **folds time** by combining cached/archived knowledge, live public data, and backtested forecasts — then tells you exactly how much to trust each answer.

---

## ✨ Features

- **Ask in Roman Urdu or English** — natural-language questions, rule-based routing.
- **Exact math** — dates, countdowns, compound/simple interest, EMI, arithmetic (`EXACT-MATH`).
- **Live keyless sources** — weather/AQI, FX, crypto, time, holidays, country facts, news, ISS, earthquakes, launches, solar activity, Wikipedia/DuckDuckGo/OpenAlex/Open Library.
- **Honest forecasts** — naive persistence, linear drift, mean reversion, exponential smoothing; walk-forward backtest; prediction interval; confidence based on skill vs naive.
- **Paradox Ledger** — every forecast is registered with a machine-checkable probe. When the due date arrives, the real value is harvested and the prediction is scored (Brier / hit-rate).
- **Time capsules** — seal a message for your future self.
- **Time Cockpit web UI** — streaming stages, badge, confidence bar, evidence fold, source chips, timeline, multiverse bands, oracle, network health, capsules, registry search.
- **12,380-endpoint keyless registry** across 13 categories.
- **Stdlib only** — no `pip install`, no build step, no JavaScript framework.
- **70-role specialist AI council** — 50+ agent cross-checks with honest confidence scoring; no API keys by default (OVHcloud anonymous tier + Pollinations).

---

## 🚀 Quick Start

### Requirements

- **Python 3.12+**
- Internet for live sources (the app degrades gracefully offline and uses cache)

### Windows

```bat
cd path\to\chronovault
python chrono.py selftest
python chrono.py cockpit
```

Or double-click **`start.bat`**.

### macOS / Linux

```bash
cd /path/to/chronovault
python3 chrono.py selftest
python3 chrono.py cockpit
```

Or run **`./start.sh`**.

The cockpit opens at **http://127.0.0.1:8765** (if busy, it tries 8766–8776).

---

## 💬 Example Questions

```bash
# Exact math / dates
python chrono.py ask "What is 2+2?"
python chrono.py ask "1 Jan 2050 konsa din hoga?"
python chrono.py ask "2050 tak kitne din baqi hain?"
python chrono.py ask "100000 @ 18% 5 saal compound interest"
python chrono.py ask "50 lakh ka loan 12% 5 saal EMI"

# Live data
python chrono.py ask "USD to PKR"
python chrono.py ask "Lahore ka mausam kaisa hai?"
python chrono.py ask "Lahore me abhi kitne baje hain?"
python chrono.py ask "latest AI news"
python chrono.py ask "Bitcoin price"
python chrono.py ask "recent earthquakes"
python chrono.py ask "ISS kahan hai?"
python chrono.py ask "Japan ki capital kya hai?"

# Knowledge + optional AI synthesis
python chrono.py ask "time travel kya hai?"

# Forecasts (registered in the Paradox Ledger)
python chrono.py forecast "USD/PKR" --days 30
python chrono.py forecast "BTC" --days 60

# Time capsule
python chrono.py capsule "2027 me khud ko yaad rakhna ke mushkil waqt guzar jayega" --days 365
python chrono.py capsules
```

Disable AI synthesis with `--no-ai`; show structured data with `--data`; show source evidence with `--detail`.

---

## 🖥️ Time Cockpit

Run `python chrono.py cockpit` and open http://127.0.0.1:8765.

| Tab | What it does |
|---|---|
| **Ask the Future** | Streaming stages, answer card, badge, confidence, sources, evidence |
| **Timeline** | Every stored answer, click for full provenance |
| **Multiverse** | Forecast lower / central / upper bands |
| **Oracle** | Prophecies, probes, scheduler, Brier calibration |
| **Network** | Provider health and HTTP cache |
| **Capsules** | Seal messages for your future self |
| **Registry** | Search 12,380 keyless endpoints |

The server binds to `127.0.0.1` only. There is no auth because it is a personal local tool — do not expose it to the internet.

---

## 🧠 How It Works

1. **Route** — `engine/chronovault/router.py` detects intent and slots (pure rules).
2. **Open the time fold** — `sources.py` fetches from parallel keyless sources with cache, retry, and fallbacks (`net.py`).
3. **Verify** — answers carry honest badges:
   - `EXACT-MATH` — deterministic calculation
   - `LIVE` — one live source
   - `LIVE-CONSENSUS` — 2+ independent sources agree
   - `LIVE-NEWS` — RSS headlines
   - `ARCHIVE` — static/documented source
   - `FORECAST` — backtested statistical projection
   - `NO-DATA` / `ERROR` / `NEED-INPUT` — honest non-answer
4. **Forecast** — `forecast.py` backtests models and picks the best by MAE; interval from residual spread.
5. **Synthesize (optional)** — keyless Pollinations LLM rewrites verified evidence in Roman Urdu. It is never allowed to invent numbers.
6. **Record** — `memory.py` stores the answer; `oracle.py` registers forecasts; `probes.py` harvests them later.

### Honest limits

- Forecasts are **statistical projections**, not guarantees.
- Weather/AQI are live but can disagree; the spread is reported.
- AI synthesis is grounded in evidence; without evidence the answer is labelled `NO-DATA` or `UNVERIFIED-AI`.
- A source returning `HTTP 502` is retried once, then reported honestly (and, where available, a fallback source is used).

---

## 📚 Endpoint Registry

`registry_v2.json` contains **12,380 keyless endpoints** in 13 categories:

`finance` 6,060 · `calendar` 2,803 · `knowledge` 1,508 · `time` 1,297 · `weather` 425 · `misc` 115 · `news` 63 · `world` 46 · `ai` 20 · `geo` 17 · `transport` 10 · `quantum` 8 · `net` 8.

Core live sources used by the answer engine: Open-Meteo, wttr.in, open.er-api, currency-api (jsDelivr), Frankfurter, Yahoo Finance, CoinGecko, Binance, Coinbase, Kraken, timeapi.io, Google Holiday Calendar, Nager.Date, Wikipedia, DuckDuckGo, OpenAlex, Open Library, Google/Bing/BBC/Al Jazeera RSS, USGS, EMSC, wheretheiss.at, Open Notify, SpaceX, NASA APOD, NOAA SWPC.

Regenerate the registry (optional):

```bash
python engine/providers/generate_registry_v2.py
```

---

## 🚀 Relativistic Time Calculations

ChronoVault 2.2.0 includes scientifically-grounded relativistic time calculations based on Einstein's Special Relativity theory. When making long-term forecasts, the system can account for time dilation effects at different velocities:

```python
from chronovault.forecast import relativistic_time_effects

# Calculate how time passes differently for travelers
result = relativistic_time_effects(10, 90)  # 10 years at 90% light speed
# Returns: {
#   "earth_years": 10,
#   "traveler_years": 2.3,
#   "dilation_factor": 4.36,
#   "velocity_percent_c": 90,
#   "note": "At 90% light speed, 10 Earth years = 2.3 traveler years"
# }
```

This feature helps understand how different observers experience time differently, which is crucial for accurate long-term predictions across different reference frames.

## 🧠 Understanding System

ChronoVault 2.2.0 includes an intelligent understanding system that clarifies what users are actually asking about:

- **Time Travel vs Predictions**: Distinguishes between actual time travel (impossible) and statistical predictions
- **Physics Concepts**: Explains relativistic time effects and their scientific basis
- **User Intent**: Identifies when users need clarification about how ChronoVault works
- **Educational Responses**: Provides explanations about the difference between science fiction and reality

```python
from chronovault.understanding import understand_user_query

# Understand what the user is actually asking
result = understand_user_query("Can you travel to the future and get Bitcoin prices?")
# Returns classification, explanation, and clarifying questions if needed
```

## 🗂️ Project Structure

```
chrono.py                    CLI entry point
engine/chronovault/          v2 engine
  ask.py                     orchestrator (Time Fold)
  router.py                  intent routing
  sources.py                 keyless live sources + fallbacks
  net.py                     HTTP layer, cache, retry, TLS fallback
  forecast.py                forecast models + walk-forward backtest
  formulas.py                exact math
  memory.py                  SQLite answers
  oracle.py                  Paradox Ledger bridge
  probes.py                  probe harvest + scheduler
  registry.py                endpoint catalog loader
  serve.py                   local HTTP server + JSON API
  cockpit.html               Time Cockpit UI
  understanding.py           intelligent query understanding system
  tests/                     offline unit tests
engine/providers/            registry generator
registry_v2.json             generated endpoint catalog
```

Runtime data (`cache/`, `Vault/`, `*.db`) is created locally and is git-ignored.

---

## 🔧 CLI Reference

```
python chrono.py ask "<question>" [--no-ai] [--detail] [--data] [--json] [--stages]
python chrono.py forecast "<USD/PKR|BTC>" --days 30
python chrono.py cockpit [--port 8765] [--no-browser]
python chrono.py status
python chrono.py registry [query] [--category CAT] [--limit N]
python chrono.py probes run|schedule|status
python chrono.py capsule "<message>" --days 365
python chrono.py capsules
python chrono.py history [--limit 20]
python chrono.py selftest [--online]
python chrono.py cache [--clear]
```

---

## 🩺 Troubleshooting

**`HTTP 502` / "Local ChronoVault server se connection nahi bana"**
- The cockpit server is not running. Start it again: `python chrono.py cockpit`.
- If a VPN/proxy is active, make sure `localhost` / `127.0.0.1` bypasses it.
- Make sure you are opening `http://127.0.0.1:8765`, not a stale preview URL.

**A single source shows `NO-DATA` / `HTTP 502`**
- The engine already retries once and uses fallbacks. If every source for that intent is down, the answer is honestly marked `NO-DATA`.

**Port already in use**
- The server automatically tries the next 11 ports; the actual URL is printed in the terminal.

**Windows console shows odd characters**
- Use Windows Terminal or PowerShell 7; `chrono.py` reconfigures stdout to UTF-8.

**Emoji/unicode errors on old consoles**
- Set `PYTHONIOENCODING=utf-8` (PowerShell): `$env:PYTHONIOENCODING='utf-8'`.

---

## 🔒 Privacy & Security

- No API keys, no accounts, no telemetry.
- All storage is local (`Vault/`, `cache/`, SQLite).
- The server binds to loopback only.
- Time capsules are stored unencrypted in local SQLite — **do not store passwords or secrets**.
- `config.json` is git-ignored; use `config.example.json` as a template.

---

## 🧪 Tests

```bash
python chrono.py selftest            # 22 offline unit tests
python chrono.py selftest --online   # + live source smoke tests
python comprehensive_test.py         # 22 end-to-end QA scenarios
```

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and new keyless sources are welcome.

## 📄 License

[MIT](LICENSE) © 2026 Hafiz Muhammad Huzaifa Shamim

## ⚠️ Disclaimer

This project does not perform physical time travel. Forecasts and speculative answers are for information and entertainment only, not financial, medical, or legal advice.

---

**ChronoVault** = *past archives + live present + statistical future, with provenance you can inspect.*
