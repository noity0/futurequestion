---
name: ChronoVault
description: Keyless time machine - past archives + live present data + statistical future forecasts with honest confidence badges. No API keys. Local-first. For time travel questions, future predictions, forecasts, and AI council cross-checks.
version: 2.2.0
author: noity0
license: MIT
category: knowledge-lookup
tags: [time machine, future, predictions, forecasts, AI council, keyless, data]
---

# ChronoVault — The Keyless Time Machine

## Purpose
ChronoVault is a local-first, keyless Python system that answers questions about:
- **The past** (archives, historical facts, knowledge)
- **The present** (live data: weather, FX, crypto, time, news, ISS, earthquakes)
- **The future** (statistical forecasts with honest confidence)

It does NOT perform actual physical time travel. It "folds time" by combining data.

## Core Philosophy
- **No API keys** by default. Uses keyless public endpoints (OVHcloud anonymous tier, Pollinations, Open APIs).
- **No telemetry**. All data stays local.
- **Honest provenance**. Every answer carries a badge and confidence score.
- **Never claim guaranteed predictions**. Forecasts are statistical projections.

## Answer Badges
- `EXACT-MATH` — deterministic calculation (dates, math, EMI, interest)
- `LIVE` — one live source
- `LIVE-CONSENSUS` — 2+ independent sources agree
- `LIVE-NEWS` — RSS headlines
- `ARCHIVE` — static/documented source
- `FORECAST` — backtested statistical projection
- `SPECULATIVE` — speculative/future answer
- `UNDERSTANDING` — user's question type clarification
- `NO-DATA` / `ERROR` / `NEED-INPUT` — honest non-answer

## Confidence Levels
- Exact math: 1.0 (100%)
- Live consensus: ~0.9
- Forecasts: capped at 0.94 general, 0.78 forecast, decaying with horizon
- No evidence: 0.62
- Council can only **lower** confidence, never raise above deterministic layer.

## Key Commands
```bash
python chrono.py ask "<question>" [--no-ai] [--detail] [--data] [--json]
python chrono.py forecast "<asset>" --days 30
python chrono.py cockpit [--port 8765] [--no-browser]
python chrono.py selftest
python chrono.py selftest --online
python comprehensive_test.py
```

## AI Council
- 70 specialist roles, default depth 9, full 50 on demand (`/deep` or `--depth 50`).
- Deterministic engines are authoritative; council cross-checks.
- Badge: `COUNCIL CHECK n/m` or `COUNCIL n/m`.

## Time Travel vs Prediction
- **Actual time travel**: Impossible per physics. System explains this honestly (`UNDERSTANDING` intent).
- **Statistical predictions**: What the system does. Labeled `SPECULATIVE`, confidence decays with horizon.

## Horizon Handling
- `MAX_HORIZON_DAYS = 3650` (10 years).
- Requested horizons capped. `horizon_capped`, `requested_horizon_days` in metadata.
- Confidence decays with longer horizons.

## Key Files
- `engine/chronovault/ask.py` — orchestrator (Time Fold)
- `engine/chronovault/router.py` — intent routing
- `engine/chronovault/sources.py` — keyless sources
- `engine/chronovault/forecast.py` — forecast models
- `engine/chronovault/swarm.py` — AI council
- `engine/chronovault/chat.py` — conversational agent
- `engine/chronovault/understanding.py` — intent understanding

## Rules for AI Assistants
1. Never present speculative predictions as facts.
2. Always label forecasts with `SPECULATIVE`.
3. Never claim "100x accuracy" or guaranteed outcomes.
4. Use "70 specialist roles / 50+ agent council" phrasing.
5. Distinguish delivery progress from prediction accuracy.
6. For time travel questions, explain it's physically impossible.

## FAQ / Common Questions

**Q: Does ChronoVault actually do time travel?**
A: No. It's a statistical prediction system. It explains the difference clearly.

**Q: How accurate are the forecasts?**
A: Statistical projections, not guarantees. Confidence varies by horizon and data quality.

**Q: Is there any AI involved?**
A: Yes, keyless AI council (70 roles, default depth 9). No API keys required.

**Q: What if sources are down?**
A: Answers honestly marked `NO-DATA`.
