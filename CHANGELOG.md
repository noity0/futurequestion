# Changelog

All notable changes to ChronoVault 2.2.0 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-11-19

### Added
- Expanded registry to 12,380 endpoints across 13 categories (finance 6,060, calendar 2,803, knowledge 1,508, time 1,297, weather 425, misc 115, news 63, world 46, ai 20, geo 17, transport 10, quantum 8, net 8)
- 70-role specialist AI council with 50+ agent cross-checks and honest confidence scoring
- Relativistic time calculations based on Einstein's Special Relativity theory
- `forecast_query()` function to strip horizon noise from generic forecast queries
- Enhanced news relevance filtering with explicit match/no-match handling
- Honest provenance display for CLI chat with badges, confidence, sources, and council info
- Council cross-check badges updated to "COUNCIL CHECK n/m" for clarity
- Improved forecast confidence caps and horizon decay calculations
- Enhanced generic forecast handling with evidence gating

### Changed
- Updated version to 2.2.0 across all modules and documentation
- Fixed stale-context / wrong-answer bug in chat agent
- Improved source/badge display to be truthful end-to-end
- Enhanced council scoring to never raise confidence above deterministic evidence
- Updated forecast engine to cap at 10 years (3,650 days) with honest disclosure
- Improved chat slot parsing for asset queries with `forecast_query()`
- Enhanced news filtering to show "no relevant match" instead of unrelated headlines
- Updated swarm prompts to avoid presenting guesses as facts for forecasts
- Improved CLI chat provenance display with metadata

### Fixed
- Fixed news relevance filter to properly check `ok` flag before displaying results
- Fixed generic forecast to use evidence gating instead of showing failure text as background
- Fixed council badge wording from "+ COUNCIL n/m" to "+ COUNCIL CHECK n/m"
- Fixed forecast horizon cap to preserve requested days in metadata
- Fixed confidence decay with horizon length for different forecast types
- Fixed chat agent to properly escape stale FX/crypto context with new topics
- Fixed source attribution for news matches vs non-matches
- Fixed comprehensive test suite to include new relativistic time functions

### Removed
- Removed scratch files: `test_council.py`, `test_knowledge.py`, `cache_ask.json`, `cache_btc.json`, `cache_cockpit_check.js`
- Removed misleading "100x accuracy" claims; replaced with honest "70 specialist roles / 50+ agent council"

## [Unreleased]

### Added
-

### Changed
-

### Fixed
-

### Removed
-

## [2.0.1] - 2026-11-18

### Added
- Standalone arithmetic intent: `2+2`, `10 / 4`, `12*3` → `EXACT-MATH`
- `start.bat` and `start.sh` one-click launchers
- `config.example.json` template (real `config.json` stays git-ignored)
- `/api/ping` health endpoint for the cockpit UI
- `comprehensive_test.py` — 22 end-to-end QA scenarios

### Changed
- HTTP layer retries transient 5xx/timeout failures once before reporting
- ISS source now uses `wheretheiss.at` (HTTPS) as primary, Open Notify as fallback
- Cockpit shows a friendly "local server not reachable" message instead of raw `HTTP 502`
- Compound-interest text explicitly says "compound interest"
- README rewritten with accurate install/run/troubleshooting steps

### Fixed
- Date questions no longer misrouted as arithmetic (`2050-01-01` stays a countdown)
- Empty question returns `NEED-INPUT` with zero confidence instead of a knowledge search
- Earthquake source has an EMSC fallback when USGS returns 502
- Registry/HTML files were wrongly ignored by `.gitignore`
- Forecast QA now reads the nested `data.forecast` object correctly

## [2.0.0] - 2026-11-18

### Added
- **Complete ChronoVault 2.0 system** - Working time machine with past archives + live present + future forecasts
- **3,909 keyless endpoint registry** - Generated registry with 13 categories (time, finance, knowledge, weather, etc.)
- **CLI interface** (`chrono.py`) - Ask, forecast, cockpit, status, registry, probes, capsules, history, selftest
- **Web UI (Time Cockpit)** - Single-page HTML/JS interface with 7 tabs:
  - Ask the Future - Streaming stages with confidence bars
  - Timeline - Answer history
  - Multiverse - Forecast branches
  - Oracle - Prophecies and probes
  - Network - Provider health
  - Capsules - Messages to future self
  - Registry - Endpoint search
- **Statistical forecasting** - Naive, drift, mean-reversion, exponential smoothing models
- **Paradox Ledger** - Automatic prediction verification with probes
- **Time capsules** - Seal messages for future retrieval
- **Honest confidence badges** - EXACT-MATH, LIVE-CONSENSUS, ARCHIVE, FORECAST, NO-DATA
- **22 offline unit tests** - All passing (selftest command)
- **Comprehensive documentation** - README, LICENSE, CONTRIBUTING, technical guides

### Changed
- **Earthquake source** - Added EMSC fallback for USGS 502 errors
- **FX sources** - Added currency-api (jsDelivr) for better coverage
- **FX history** - Added Yahoo Finance fallback for historical data
- **Holidays** - Added Google Holiday Calendar ICS fallback
- **Country info** - Switched to world-countries + country-json population
- **Time handling** - Fixed UTC offset calculation via ZoneInfo
- **Text cleaning** - Improved AI synthesis text processing
- **News relevance** - Added filtering for relevant stories

### Fixed
- **HTTP 502 errors** - Added fallback sources for earthquake data
- **Unicode encoding** - Fixed console output issues on Windows
- **Terminal size errors** - Added try/catch for pty terminal size detection
- **Source reliability** - Improved error handling and fallback mechanisms

### Technical Details
- **Language**: Python 3.12 (stdlib only - no pip install required)
- **Storage**: SQLite (cache, memory, paradox ledger)
- **API**: HTTP server with chunked streaming support
- **Privacy**: Offline-first, no telemetry, no API keys
- **OS**: Windows/Linux/macOS compatible

## [1.0.0] - 2026-11-17

### Added
- Initial concept and research documentation
- Basic architecture planning
- Source inventory and provider analysis

---

## Versioning

- **Major (X.0.0)**: Incompatible changes or complete rewrites
- **Minor (X.Y.0)**: New features, backward compatible
- **Patch (X.Y.Z)**: Bug fixes, backward compatible

## Supported Versions

| Version | Status | Python Version | Support Until |
|---------|--------|----------------|--------------|
| 2.0.0   | ✅ Current | 3.12+ | 2027-11-18 |
| 1.0.0   | ❌ Deprecated | 3.12+ | 2026-12-31 |