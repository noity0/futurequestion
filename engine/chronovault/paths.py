"""ChronoVault 2.2.0 — shared paths and constants."""
from __future__ import annotations

import os

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(PKG_DIR)
ROOT = os.path.dirname(ENGINE_DIR)

CACHE_DIR = os.path.join(ROOT, "cache")
DB_PATH = os.path.join(CACHE_DIR, "chrono.db")
HEALTH_PATH = os.path.join(CACHE_DIR, "health.json")
REGISTRY_PATH = os.path.join(ROOT, "registry_v2.json")
VAULT_DIR = os.path.join(ROOT, "Vault")
ORACLE_DIR = os.path.join(ENGINE_DIR, "oracle")
LEDGER_PATH = os.path.join(ORACLE_DIR, "paradox_ledger.db")

APP_NAME = "ChronoVault"
VERSION = "2.2.0"
UA = ("Mozilla/5.0 (compatible; ChronoVault/2.2; local personal time machine; "
      "offline-first; no telemetry; contact: local-user)")


def ensure_dirs() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
