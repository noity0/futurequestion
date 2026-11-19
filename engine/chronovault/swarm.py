"""ChronoVault 2.2 — the keyless AI council.

One model can be confidently wrong. A council of specialists, each grounded in
the same verified evidence and then cross-examined by a judge, is harder to fool.

What is real here
-----------------
* Every "agent" is a distinct role with its own system prompt and scoring weight.
  The default council runs 9 agents; the full council runs up to 50 (70 roles
  are defined).
* Live model routes are auto-detected. With no API keys the council finds:
    - OVHcloud AI Endpoints anonymous tier (10 working models, 2 req/min each)
    - LLM7 keyless tier
    - Pollinations anonymous tier
    - any local Ollama / LM Studio / llama.cpp / vLLM / KoboldCpp server
* Optional keyed providers are listed but stay dormant unless the matching
  environment variable exists. Nothing here requires a key.
* Deterministic/live answers remain authoritative. The council only explains,
  cross-checks and flags uncertainty; it can never turn a forecast into a fact.

What is not real
----------------
There is no 100x accuracy switch and no crystal ball. More models reduce the
chance of a single-model hallucination; they do not make a statistical forecast
certain. The final confidence is capped and the badge stays honest.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import re
import statistics
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from . import net

# ---------------------------------------------------------------------------
# Roles: 70 distinct specialists. The first five are the accuracy core and are
# always present in every council (when depth allows).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    domain: str
    system: str
    weight: float = 1.0
    keywords: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()


def _role(rid, name, domain, system, weight=1.0, keywords=(), kinds=()):
    return Role(rid, name, domain, system, weight, tuple(keywords), tuple(kinds))


ROLES: tuple[Role, ...] = (
    _role("anchor", "Fact Anchor", "verification",
          "State only what the verified facts support. If a detail is missing, "
          "say so plainly. Never fill a gap with imagination.",
          1.8, ("fact", "true", "sach", "verify", "exact"), ("knowledge", "news", "country", "forecast")),
    _role("source_verifier", "Source Verifier", "verification",
          "Check every claim against the supplied sources. Name the source and "
          "separate verified facts from inference.",
          1.7, ("source", "reference", "kahan", "proof", "verified"), ("knowledge", "news", "country", "forecast")),
    _role("skeptic", "Professional Skeptic", "verification",
          "Look for the weakest assumption. Say what could make this answer wrong "
          "and what evidence would change it.",
          1.5, ("why", "sure", "pakka", "really", "sach", "believe"), ("knowledge", "forecast", "news")),
    _role("statistician", "Statistician", "mathematics",
          "Check numbers, units, base rates and uncertainty. Never confuse a "
          "point estimate with a guarantee.",
          1.5, ("number", "percent", "rate", "average", "probability", "kitna", "forecast"), ("forecast", "knowledge")),
    _role("devil_advocate", "Devil's Advocate", "verification",
          "Argue the opposite case. Find the strongest counter-example or missing "
          "context before the council commits to an answer.",
          1.4, ("opposite", "but", "however", "risk", "wrong"), ("forecast", "news", "country", "knowledge")),
    _role("mathematician", "Mathematician", "mathematics",
          "Solve or check the arithmetic step by step. Keep exact values exact.",
          1.3, ("calculate", "math", "plus", "minus", "interest", "emi", "percent"), ("math", "interest", "emi")),
    _role("physicist", "Physicist", "science",
          "Explain physical mechanisms and check units, scale and causality.",
          1.1, ("physics", "energy", "force", "speed", "light", "gravity", "quantum"), ("knowledge",)),
    _role("astronomer", "Astronomer", "science",
          "Handle space, planets, stars, eclipses and missions with measured facts.",
          1.0, ("space", "iss", "moon", "mars", "star", "eclipse", "planet"), ("knowledge", "space")),
    _role("chemist", "Chemist", "science",
          "Explain substances, reactions and safety without inventing lab results.",
          0.9, ("chemical", "reaction", "acid", "element", "molecule"), ("knowledge",)),
    _role("biologist", "Biologist", "science",
          "Explain living systems carefully and distinguish evidence from analogy.",
          1.0, ("biology", "cell", "gene", "dna", "evolution", "animal"), ("knowledge",)),
    _role("physician", "Physician", "health",
          "Give general health information, never a diagnosis or prescription. "
          "Flag red-flag symptoms and advise a qualified doctor.",
          1.2, ("health", "doctor", "disease", "pain", "medicine", "symptom", "bimari"), ("knowledge",)),
    _role("pharmacist", "Pharmacist", "health",
          "Check drug classes, interactions and safe-use caveats. No dosing "
          "instructions without a clinician.",
          1.0, ("drug", "dose", "medicine", "tablet", "interaction"), ("knowledge",)),
    _role("nutritionist", "Nutritionist", "health",
          "Discuss food, calories and diet in general terms; avoid medical claims.",
          0.9, ("food", "diet", "calorie", "protein", "khana"), ("knowledge",)),
    _role("psychologist", "Psychologist", "health",
          "Explain behaviour and emotions with evidence, compassion and clear "
          "limits. Crisis cases should be pointed to real help.",
          1.0, ("mind", "stress", "anxiety", "depression", "psychology", "dimagh"), ("knowledge",)),
    _role("historian", "Historian", "humanities",
          "Place events in chronology and context; distinguish record from legend.",
          1.1, ("history", "past", "war", "empire", "tareekh", "historical"), ("knowledge", "country")),
    _role("geographer", "Geographer", "world",
          "Check places, borders, distances, climate and regional context.",
          1.1, ("country", "city", "border", "map", "region", "capital", "multan", "lahore"), ("country", "knowledge")),
    _role("economist", "Economist", "finance",
          "Explain incentives, inflation, growth and trade-offs with explicit "
          "assumptions.",
          1.3, ("economy", "inflation", "gdp", "growth", "market", "mehngai"), ("forecast", "country", "knowledge")),
    _role("fx_analyst", "FX Analyst", "finance",
          "Treat exchange rates as noisy prices. Separate the live quote from any "
          "statistical projection.",
          1.4, ("usd", "pkr", "eur", "currency", "dollar", "rupee", "exchange", "rate"), ("forecast_fx", "fx")),
    _role("crypto_analyst", "Crypto Analyst", "finance",
          "Explain crypto assets with high volatility and custody risk. Never "
          "promise a price.",
          1.2, ("bitcoin", "btc", "crypto", "ethereum", "coin", "blockchain"), ("forecast_crypto", "crypto")),
    _role("equity_analyst", "Equity Analyst", "finance",
          "Discuss shares, indices and valuation assumptions, not tips.",
          1.0, ("stock", "share", "index", "psx", "nasdaq", "equity"), ("knowledge", "forecast")),
    _role("commodities_analyst", "Commodities Analyst", "finance",
          "Handle gold, oil, food and metal prices with supply/demand context.",
          1.1, ("gold", "sona", "oil", "silver", "chandi", "commodity", "wheat"), ("forecast", "knowledge")),
    _role("accountant", "Accountant", "finance",
          "Check principal, rate, compounding, tax and cash-flow arithmetic.",
          1.2, ("account", "tax", "profit", "loss", "compound", "simple", "interest", "emi"), ("interest", "emi", "knowledge")),
    _role("tax_advisor", "Tax Advisor", "finance",
          "Explain general tax concepts; local law and professional advice still matter.",
          1.0, ("tax", "filer", "return", "gst", "income"), ("knowledge",)),
    _role("lawyer", "Legal Analyst", "law",
          "Explain legal concepts generally, never as a substitute for a licensed "
          "lawyer in the user's jurisdiction.",
          1.1, ("law", "court", "legal", "contract", "rights", "qanoon"), ("knowledge",)),
    _role("policy_analyst", "Policy Analyst", "politics",
          "Compare policy options, incentives and unintended consequences.",
          1.1, ("policy", "government", "reform", "budget", "subsidy"), ("country", "news", "knowledge")),
    _role("geopolitical_analyst", "Geopolitical Analyst", "politics",
          "Explain alliances, trade and conflict risks without speculation dressed "
          "as fact.",
          1.2, ("war", "geopolitics", "sanction", "border", "treaty", "election"), ("news", "country", "forecast")),
    _role("climate_scientist", "Climate Scientist", "environment",
          "Use measured climate trends and explicit uncertainty; do not confuse "
          "weather with climate.",
          1.1, ("climate", "warming", "carbon", "emission", "monsoon"), ("knowledge", "forecast")),
    _role("meteorologist", "Meteorologist", "environment",
          "Explain weather forecasts as probabilities with time windows.",
          1.1, ("weather", "mausam", "rain", "temperature", "storm", "humidity"), ("weather", "knowledge")),
    _role("seismologist", "Seismologist", "environment",
          "Explain earthquakes and aftershocks; never predict a exact quake date.",
          0.9, ("earthquake", "seismic", "richter", "zalzala"), ("knowledge", "news")),
    _role("environmentalist", "Environmental Scientist", "environment",
          "Weigh ecological costs and benefits with evidence.",
          0.9, ("environment", "pollution", "water", "forest", "species"), ("knowledge",)),
    _role("engineer", "Engineer", "technology",
          "Check feasibility, constraints, safety factors and units.",
          1.0, ("engineer", "build", "machine", "design", "load"), ("knowledge",)),
    _role("software_engineer", "Software Engineer", "technology",
          "Explain code, systems and debugging with concrete mechanisms.",
          1.1, ("code", "python", "javascript", "software", "bug", "api", "database"), ("knowledge",)),
    _role("data_scientist", "Data Scientist", "technology",
          "Check sampling, leakage, metrics and the difference between correlation "
          "and causation.",
          1.1, ("data", "model", "dataset", "accuracy", "ml", "statistics"), ("knowledge", "forecast")),
    _role("ai_researcher", "AI Researcher", "technology",
          "Explain AI capabilities and limits precisely; challenge hype.",
          1.1, ("ai", "llm", "model", "neural", "agent", "artificial intelligence"), ("knowledge",)),
    _role("cybersecurity", "Cybersecurity Analyst", "technology",
          "Think like an attacker and defender. Never provide instructions for "
          "real harm.",
          1.0, ("security", "password", "hack", "malware", "phishing", "privacy"), ("knowledge",)),
    _role("network_engineer", "Network Engineer", "technology",
          "Explain protocols, latency, DNS, TLS and connectivity.",
          0.9, ("network", "internet", "dns", "tcp", "wifi", "server"), ("knowledge",)),
    _role("electrical_engineer", "Electrical Engineer", "technology",
          "Check voltage, current, power, batteries and electrical safety.",
          0.9, ("electric", "voltage", "battery", "power", "solar", "watt"), ("knowledge",)),
    _role("mechanical_engineer", "Mechanical Engineer", "technology",
          "Check forces, materials, motion and mechanical safety.",
          0.9, ("mechanical", "engine", "motor", "torque", "pressure"), ("knowledge",)),
    _role("civil_engineer", "Civil Engineer", "technology",
          "Check structures, foundations, materials and public safety.",
          0.9, ("civil", "bridge", "building", "concrete", "foundation"), ("knowledge",)),
    _role("architect", "Architect", "design",
          "Discuss space, function, climate and building culture.",
          0.8, ("architecture", "house", "design", "building", "layout"), ("knowledge",)),
    _role("teacher", "Teacher", "education",
          "Explain the answer so a motivated beginner can understand it, with one "
          "concrete example.",
          1.2, ("explain", "meaning", "kya hai", "samjha", "learn", "teach"), ("knowledge",)),
    _role("linguist", "Linguist", "language",
          "Check grammar, meaning, transliteration and language variation.",
          1.1, ("language", "word", "meaning", "grammar", "translate", "matlab", "naam"), ("knowledge", "baby_name")),
    _role("translator", "Translator", "language",
          "Preserve meaning, tone and names across languages; flag ambiguity.",
          1.0, ("translate", "translation", "urdu", "english", "roman"), ("knowledge",)),
    _role("writer", "Writer", "communication",
          "Make the answer clear, specific and free of filler.",
          1.1, ("write", "essay", "story", "letter", "likho"), ("knowledge",)),
    _role("editor", "Editor", "communication",
          "Cut repetition, fix contradictions and tighten claims.",
          1.1, ("edit", "summary", "short", "clear", "review"), ("knowledge", "news")),
    _role("poet", "Poet", "communication",
          "Use imagery and rhythm only when the user asks for creative writing.",
          0.7, ("poem", "shayari", "ghazal", "creative", "kahani"), ("knowledge",)),
    _role("religious_scholar", "Religious Studies Scholar", "culture",
          "Explain religious concepts respectfully and comparatively; distinguish "
          "text, tradition and personal opinion.",
          1.0, ("islam", "quran", "hadith", "religion", "dua", "namaz", "masjid"), ("knowledge", "baby_name")),
    _role("philosopher", "Philosopher", "humanities",
          "Clarify concepts and assumptions; do not pretend contested questions "
          "have one answer.",
          0.9, ("philosophy", "ethics", "meaning", "existence", "free will"), ("knowledge",)),
    _role("ethicist", "Ethicist", "humanities",
          "Surface values, stakeholders and trade-offs.",
          0.9, ("ethical", "fair", "right", "wrong", "moral"), ("knowledge",)),
    _role("sociologist", "Sociologist", "humanities",
          "Explain social behaviour, institutions and group effects.",
          0.9, ("society", "people", "community", "family", "culture"), ("knowledge", "country")),
    _role("anthropologist", "Anthropologist", "humanities",
          "Respect cultural context and avoid universal claims from one case.",
          0.8, ("culture", "tradition", "ritual", "tribe", "custom"), ("knowledge", "baby_name")),
    _role("sports_analyst", "Sports Analyst", "sports",
          "Use results, form and rules; label predictions as uncertain.",
          0.8, ("cricket", "football", "match", "team", "player", "score"), ("knowledge", "forecast")),
    _role("travel_guide", "Travel Guide", "practical",
          "Give practical travel context, costs and safety caveats.",
          0.8, ("travel", "visa", "trip", "hotel", "flight", "tour"), ("knowledge",)),
    _role("chef", "Chef", "practical",
          "Explain ingredients, technique and food safety.",
          0.8, ("recipe", "cook", "food", "bake", "masala"), ("knowledge",)),
    _role("farmer", "Agriculture Specialist", "practical",
          "Discuss crops, soil, water and seasonality with local uncertainty.",
          0.8, ("crop", "wheat", "rice", "farm", "kheti", "soil", "weather"), ("knowledge",)),
    _role("logistician", "Logistics Specialist", "practical",
          "Check time, distance, capacity and bottlenecks.",
          0.8, ("shipping", "delivery", "supply", "transport", "cargo"), ("knowledge",)),
    _role("entrepreneur", "Entrepreneur", "business",
          "Focus on customer, unit economics, risk and next experiment.",
          0.9, ("business", "startup", "customer", "profit", "sell", "karobar"), ("knowledge",)),
    _role("marketer", "Marketer", "business",
          "Explain positioning, audience and measurement without hype.",
          0.8, ("marketing", "ad", "brand", "audience", "campaign"), ("knowledge",)),
    _role("ux_designer", "UX Designer", "design",
          "Think about user goals, friction and accessibility.",
          0.8, ("ux", "ui", "user", "design", "usability"), ("knowledge",)),
    _role("forecast_auditor", "Forecast Auditor", "forecasting",
          "Audit the horizon, method, backtest, interval and base rate. Reject "
          "precision that the data cannot support.",
          1.6, ("forecast", "predict", "future", "agle", "target", "kitna hoga"), ("forecast", "forecast_fx", "forecast_crypto")),
    _role("red_team", "Red Team", "verification",
          "Try to break the answer: edge cases, missing data, adversarial inputs "
          "and overclaiming.",
          1.3, ("risk", "fail", "wrong", "edge", "attack", "security"), ("forecast", "knowledge")),
    _role("future_historian", "Future Historian", "forecasting",
          "Write from the future backwards: what would have to happen for this "
          "prediction to be true? Keep it speculative.",
          1.0, ("future", "2027", "2030", "2050", "agle saal"), ("forecast",)),
    _role("risk_manager", "Risk Manager", "finance",
          "Quantify downside, probability and position sizing. Never encourage "
          "all-in bets.",
          1.2, ("risk", "loss", "invest", "portfolio", "downside"), ("forecast", "forecast_fx", "forecast_crypto")),
    _role("baby_name_curator", "Baby Name Curator", "culture",
          "Suggest culturally respectful names, explain meanings cautiously and "
          "never claim to know the real future name.",
          1.7, ("baby", "bache", "bacha", "naam", "name", "beti", "beta"), ("baby_name",)),
    _role("parenting_advisor", "Parenting Advisor", "family",
          "Give practical, non-judgemental parenting context and flag when a "
          "professional is needed.",
          1.0, ("parent", "baby", "child", "bacha", "family"), ("baby_name", "knowledge")),
    _role("generalist", "Generalist", "general",
          "Connect the verified facts into a clear, useful answer without adding "
          "unverified claims.",
          1.4, ("what", "kya", "kaise", "why", "explain", "help"), ("knowledge", "news", "country")),
    _role("fact_checker", "Fact Checker", "verification",
          "Mark each claim VERIFIED, INFERRED or UNKNOWN. Prefer UNKNOWN over a "
          "guess.",
          1.4, ("true", "false", "fact", "check", "verify"), ("news", "knowledge", "country")),
    _role("practical_advisor", "Practical Advisor", "practical",
          "Translate the answer into a concrete next step the user can actually take.",
          1.0, ("how", "kaise", "should", "plan", "step", "advice"), ("knowledge",)),
    _role("safety_advisor", "Safety Advisor", "safety",
          "Check for health, legal, financial or physical harm. Add a clear caveat "
          "where needed.",
          1.2, ("safe", "danger", "harm", "health", "legal", "money"), ("knowledge", "forecast")),
    _role("consensus_builder", "Consensus Builder", "verification",
          "Identify where the council agrees, where it disagrees, and what that "
          "means for the user.",
          1.3, ("agree", "disagree", "consensus", "best", "final"), ("knowledge", "forecast", "news", "country")),
)

CORE_IDS = ("anchor", "source_verifier", "skeptic", "statistician", "devil_advocate")

KIND_BOOSTS = {
    "forecast": ("forecast_auditor", "risk_manager", "economist", "statistician",
                 "future_historian", "devil_advocate", "consensus_builder"),
    "forecast_fx": ("forecast_auditor", "fx_analyst", "risk_manager", "economist",
                    "statistician", "devil_advocate"),
    "forecast_crypto": ("forecast_auditor", "crypto_analyst", "risk_manager",
                        "statistician", "devil_advocate"),
    "baby_name": ("baby_name_curator", "linguist", "parenting_advisor",
                  "religious_scholar", "anthropologist", "historian"),
    "news": ("fact_checker", "source_verifier", "editor", "geopolitical_analyst",
             "policy_analyst", "historian"),
    "country": ("geographer", "historian", "economist", "policy_analyst",
                "sociologist", "fact_checker"),
    "weather": ("meteorologist", "climate_scientist", "farmer"),
}

DEFAULT_DEPTH = 9


def roles() -> list[dict]:
    """Public, UI-friendly role catalogue."""
    return [
        {"id": r.id, "name": r.name, "domain": r.domain,
         "weight": r.weight, "core": r.id in CORE_IDS}
        for r in ROLES
    ]


def select_roles(question: str, kind: str = "knowledge", depth: int = 9) -> list[Role]:
    """Pick the most relevant specialists, always keeping the accuracy core."""
    depth = max(5, min(50, int(depth or 9)))
    low = " " + (question or "").lower() + " " + (kind or "").lower() + " "
    boosts = set(KIND_BOOSTS.get(kind, ()))
    scored: list[tuple[float, Role]] = []
    for r in ROLES:
        score = float(r.weight)
        if r.id in CORE_IDS:
            score += 100.0
        if r.id in boosts:
            score += 12.0
        for kw in r.keywords:
            if kw and kw in low:
                score += 2.2
        for k in r.kinds:
            if k and k == kind:
                score += 3.0
        # Stable, question-specific tie-break so repeated calls agree.
        seed = hashlib.sha256((question + "|" + kind + "|" + r.id).encode()).hexdigest()
        score += int(seed[:4], 16) / 65535.0 * 0.01
        scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    picked = [r for _s, r in scored[:depth]]
    # Guarantee the core is present even if a caller passes a tiny depth.
    present = {r.id for r in picked}
    for cid in CORE_IDS:
        if len(picked) >= depth:
            break
        if cid not in present:
            picked.append(next(r for r in ROLES if r.id == cid))
            present.add(cid)
    return picked


# ---------------------------------------------------------------------------
# Model routes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Route:
    id: str
    provider: str
    provider_key: str
    label: str
    url: str
    model: str
    key_env: str = ""
    local: bool = False
    rpm: int = 30
    weight: float = 1.0
    strengths: tuple[str, ...] = ()
    note: str = ""
    slow: bool = False


OVH_URL = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
OVH_CATALOG = "https://catalog.endpoints.ai.ovh.net/rest/v1/models_v2"
LLM7_MODELS = "https://api.llm7.io/v1/models"
LLM7_URL = "https://api.llm7.io/v1/chat/completions"
POLL_MODELS = "https://text.pollinations.ai/models"
POLL_URL = "https://text.pollinations.ai/openai"

# These ten were live-tested on 2026-11-18.  OVH's anonymous tier is 2 req/min
# per model; the rate limiter below respects that instead of hammering it.
OVH_ROUTES: tuple[Route, ...] = (
    Route("ovh:gpt-oss-120b", "OVHcloud", "ovh", "GPT-OSS 120B", OVH_URL,
          "gpt-oss-120b", rpm=2, weight=1.40,
          strengths=("reasoning", "general", "judge"), note="anonymous tier"),
    Route("ovh:qwen3.6-35b", "OVHcloud", "ovh", "Qwen 3.6 35B-A3B", OVH_URL,
          "qwen@latest", rpm=2, weight=1.28,
          strengths=("reasoning", "multilingual", "general"), note="anonymous tier"),
    Route("ovh:llama-3.3-70b", "OVHcloud", "ovh", "Llama 3.3 70B", OVH_URL,
          "meta-llama@latest", rpm=2, weight=1.24,
          strengths=("general", "writing", "judge"), note="anonymous tier, slow",
          slow=True),
    Route("ovh:deepseek-v4.1", "OVHcloud", "ovh", "DeepSeek V4.1 Flash", OVH_URL,
          "deepseek@latest", rpm=2, weight=1.22,
          strengths=("reasoning", "math", "code"), note="anonymous tier"),
    Route("ovh:gpt-oss-20b", "OVHcloud", "ovh", "GPT-OSS 20B", OVH_URL,
          "gpt-oss-20b", rpm=2, weight=1.20,
          strengths=("fast", "general", "reasoning"), note="anonymous tier"),
    Route("ovh:gemma-4-26b", "OVHcloud", "ovh", "Gemma 4 26B", OVH_URL,
          "gemma-4-26b-a4b", rpm=2, weight=1.12,
          strengths=("fast", "general"), note="anonymous tier"),
    Route("ovh:nemotron-nano", "OVHcloud", "ovh", "Nemotron 3 Nano 30B", OVH_URL,
          "nemotron3-nano-30b", rpm=2, weight=1.10,
          strengths=("fast", "reasoning"), note="anonymous tier"),
    Route("ovh:qwen3-vl-30b", "OVHcloud", "ovh", "Qwen 3 VL 30B", OVH_URL,
          "qwen3-vl-30b-a3b", rpm=2, weight=1.08,
          strengths=("fast", "multilingual"), note="anonymous tier"),
    Route("ovh:nemotron-omni", "OVHcloud", "ovh", "Nemotron 3 Omni 30B", OVH_URL,
          "nemotron3-omni-30b", rpm=2, weight=1.06,
          strengths=("fast", "reasoning"), note="anonymous tier"),
    Route("ovh:mistral-small", "OVHcloud", "ovh", "Mistral Small 3.2", OVH_URL,
          "mistral@latest", rpm=2, weight=1.02,
          strengths=("general", "writing"), note="anonymous tier, slow",
          slow=True),
)

KEYLESS_ROUTES: tuple[Route, ...] = (
    Route("llm7:default", "LLM7", "llm7", "LLM7 default", LLM7_URL,
          "default", rpm=4, weight=0.95,
          strengths=("general", "fallback"), note="keyless tier"),
    Route("pollinations:openai-fast", "Pollinations", "pollinations",
          "GPT-OSS 20B (Pollinations)", POLL_URL, "openai-fast", rpm=2,
          weight=0.90, strengths=("general", "fallback"), note="anonymous tier"),
)

# Optional keyed routes.  They are listed so the catalogue is complete, but they
# never become active unless the matching environment variable is present.
OPTIONAL_ROUTES: tuple[Route, ...] = (
    Route("openai:gpt", "OpenAI", "openai", "OpenAI GPT", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini", "OPENAI_API_KEY", weight=1.5),
    Route("google:gemini", "Google Gemini", "google", "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.0-flash", "GEMINI_API_KEY", weight=1.5),
    Route("groq:llama", "Groq", "groq", "Groq Llama", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile", "GROQ_API_KEY", weight=1.4),
    Route("mistral:large", "Mistral", "mistral", "Mistral Large", "https://api.mistral.ai/v1/chat/completions", "mistral-large-latest", "MISTRAL_API_KEY", weight=1.4),
    Route("deepseek:chat", "DeepSeek", "deepseek", "DeepSeek Chat", "https://api.deepseek.com/chat/completions", "deepseek-chat", "DEEPSEEK_API_KEY", weight=1.4),
    Route("xai:grok", "xAI", "xai", "Grok", "https://api.x.ai/v1/chat/completions", "grok-4", "XAI_API_KEY", weight=1.4),
    Route("together:llama", "Together AI", "together", "Together Llama", "https://api.together.xyz/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY", weight=1.3),
    Route("openrouter:auto", "OpenRouter", "openrouter", "OpenRouter Auto", "https://openrouter.ai/api/v1/chat/completions", "openrouter/auto", "OPENROUTER_API_KEY", weight=1.3),
    Route("cohere:command", "Cohere", "cohere", "Command R+", "https://api.cohere.ai/compatibility/v1/chat/completions", "command-r-plus", "COHERE_API_KEY", weight=1.2),
    Route("perplexity:sonar", "Perplexity", "perplexity", "Sonar", "https://api.perplexity.ai/chat/completions", "sonar", "PERPLEXITY_API_KEY", weight=1.3),
    Route("fireworks:llama", "Fireworks", "fireworks", "Fireworks Llama", "https://api.fireworks.ai/inference/v1/chat/completions", "accounts/fireworks/models/llama-v3p3-70b-instruct", "FIREWORKS_API_KEY", weight=1.3),
    Route("cerebras:llama", "Cerebras", "cerebras", "Cerebras Llama", "https://api.cerebras.ai/v1/chat/completions", "llama3.3-70b", "CEREBRAS_API_KEY", weight=1.3),
    Route("sambanova:llama", "SambaNova", "sambanova", "SambaNova Llama", "https://api.sambanova.ai/v1/chat/completions", "Meta-Llama-3.3-70B-Instruct", "SAMBANOVA_API_KEY", weight=1.2),
    Route("nvidia:llama", "NVIDIA NIM", "nvidia", "NVIDIA Llama", "https://integrate.api.nvidia.com/v1/chat/completions", "meta/llama-3.3-70b-instruct", "NVIDIA_API_KEY", weight=1.2),
    Route("deepinfra:llama", "DeepInfra", "deepinfra", "DeepInfra Llama", "https://api.deepinfra.com/v1/openai/chat/completions", "meta-llama/Llama-3.3-70B-Instruct", "DEEPINFRA_API_KEY", weight=1.2),
    Route("novita:llama", "Novita AI", "novita", "Novita Llama", "https://api.novita.ai/v3/openai/chat/completions", "meta-llama/llama-3.3-70b-instruct", "NOVITA_API_KEY", weight=1.1),
    Route("hyperbolic:llama", "Hyperbolic", "hyperbolic", "Hyperbolic Llama", "https://api.hyperbolic.xyz/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct", "HYPERBOLIC_API_KEY", weight=1.1),
    Route("nebius:llama", "Nebius", "nebius", "Nebius Llama", "https://api.studio.nebius.ai/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct", "NEBIUS_API_KEY", weight=1.1),
    Route("github:models", "GitHub Models", "github", "GitHub Models", "https://models.inference.ai.azure.com/chat/completions", "gpt-4o-mini", "GITHUB_TOKEN", weight=1.2),
    Route("huggingface:router", "Hugging Face", "huggingface", "HF Router", "https://router.huggingface.co/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct", "HF_TOKEN", weight=1.1),
    Route("moonshot:chat", "Moonshot", "moonshot", "Kimi", "https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-8k", "MOONSHOT_API_KEY", weight=1.1),
    Route("zhipu:glm", "Zhipu", "zhipu", "GLM", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-flash", "ZHIPU_API_KEY", weight=1.1),
    Route("minimax:chat", "MiniMax", "minimax", "MiniMax", "https://api.minimax.chat/v1/chat/completions", "abab6.5s-chat", "MINIMAX_API_KEY", weight=1.0),
    Route("upstage:solar", "Upstage", "upstage", "Solar", "https://api.upstage.ai/v1/chat/completions", "solar-pro", "UPSTAGE_API_KEY", weight=1.0),
    Route("ai21:jamba", "AI21", "ai21", "Jamba", "https://api.ai21.com/studio/v1/chat/completions", "jamba-1.5-mini", "AI21_API_KEY", weight=1.0),
    Route("ollama:cloud", "Ollama Cloud", "ollama_cloud", "Ollama Cloud", "https://ollama.com/v1/chat/completions", "llama3.2", "OLLAMA_API_KEY", weight=1.1),
    Route("baseten:llama", "Baseten", "baseten", "Baseten Llama", "https://inference.baseten.co/v1/chat/completions", "llama-3.3-70b", "BASETEN_API_KEY", weight=1.0),
    Route("lambda:llama", "Lambda", "lambda", "Lambda Llama", "https://api.lambdalabs.com/v1/chat/completions", "llama3.3-70b-instruct", "LAMBDA_API_KEY", weight=1.0),
    Route("featherless:llama", "Featherless", "featherless", "Featherless Llama", "https://api.featherless.ai/v1/chat/completions", "meta-llama/Meta-Llama-3.1-8B-Instruct", "FEATHERLESS_API_KEY", weight=0.9),
    Route("chutes:llama", "Chutes", "chutes", "Chutes Llama", "https://llm.chutes.ai/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct", "CHUTES_API_KEY", weight=0.9),
    Route("kluster:llama", "Kluster", "kluster", "Kluster Llama", "https://api.kluster.ai/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct", "KLUSTER_API_KEY", weight=0.9),
)

# Local servers are probed at runtime; these stubs keep the catalogue honest
# even when no local model is installed.
LOCAL_SERVERS: tuple[dict, ...] = (
    {"id": "ollama", "label": "Ollama", "base": "http://localhost:11434", "path": "/api/tags"},
    {"id": "lmstudio", "label": "LM Studio", "base": "http://localhost:1234", "path": "/v1/models"},
    {"id": "llamacpp", "label": "llama.cpp", "base": "http://localhost:8080", "path": "/v1/models"},
    {"id": "vllm", "label": "vLLM", "base": "http://localhost:8000", "path": "/v1/models"},
    {"id": "koboldcpp", "label": "KoboldCpp", "base": "http://localhost:5001", "path": "/v1/models"},
    {"id": "jan", "label": "Jan", "base": "http://localhost:1337", "path": "/v1/models"},
    {"id": "gpt4all", "label": "GPT4All", "base": "http://localhost:4891", "path": "/v1/models"},
    {"id": "openwebui", "label": "Open WebUI", "base": "http://localhost:3000", "path": "/v1/models"},
    {"id": "textgenwebui", "label": "Text Generation WebUI", "base": "http://localhost:5000", "path": "/v1/models"},
    {"id": "localai", "label": "LocalAI", "base": "http://localhost:8081", "path": "/v1/models"},
    {"id": "sglang", "label": "SGLang", "base": "http://localhost:30000", "path": "/v1/models"},
    {"id": "msty", "label": "Msty", "base": "http://localhost:5050", "path": "/v1/models"},
)

LOCAL_STUBS: tuple[Route, ...] = tuple(
    Route(f"local:{s['id']}", s["label"], s["id"], s["label"],
          s["base"] + "/v1/chat/completions", "auto", local=True, rpm=120,
          weight=0.75, strengths=("local", "private"), note="probe at runtime")
    for s in LOCAL_SERVERS
)

STATIC_ROUTES: tuple[Route, ...] = OVH_ROUTES + KEYLESS_ROUTES + OPTIONAL_ROUTES + LOCAL_STUBS

_PROBE: dict = {}
_PROBE_TS = 0.0
_PROBE_LOCK = threading.Lock()
_LOCAL_ROUTES: list[Route] = []
_DOWN: set[str] = set()
_COOLDOWN: dict[str, float] = {}
_RATE: dict[str, list[float]] = {}
_RATE_LOCK = threading.Lock()
_LATENCY: dict[str, int] = {}
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def allow_keyed() -> bool:
    """Opt-in only: ambient API keys are never used silently.

    The user asked for a zero-key product. Even if a key happens to exist in
    the environment (another app may have set it), keyed routes stay dormant
    until CHRONOVAULT_ALLOW_KEYS=1 is set explicitly.
    """
    return os.environ.get("CHRONOVAULT_ALLOW_KEYS", "").strip().lower() in (
        "1", "true", "yes", "on")


def all_routes() -> list[Route]:
    """Every known route, including dormant optional/local entries."""
    static = [r for r in STATIC_ROUTES if not r.local]
    local = _LOCAL_ROUTES or [r for r in STATIC_ROUTES if r.local]
    return static + local


def _local_routes_from_probe() -> tuple[list[Route], dict]:
    found: list[Route] = []
    status: dict[str, dict] = {}

    def probe_one(srv: dict) -> tuple[dict, list[Route], dict]:
        url = srv["base"] + srv["path"]
        # Localhost either answers immediately or is not running. A long
        # timeout here would make every council call feel broken.
        r = net.fetch(url, ttl=30, timeout=0.7,
                      endpoint_id="swarm:" + srv["id"])
        models: list[str] = []
        if r.ok and isinstance(r.data, dict):
            if isinstance(r.data.get("models"), list):
                models = [str(m.get("name") or "") for m in r.data["models"]
                          if isinstance(m, dict)]
            elif isinstance(r.data.get("data"), list):
                models = [str(m.get("id") or "") for m in r.data["data"]
                          if isinstance(m, dict)]
        models = [m for m in models if m][:8]
        rows: list[Route] = []
        for model in models:
            rows.append(Route(
                f"local:{srv['id']}:{model}", srv["label"], srv["id"],
                f"{srv['label']} · {model}", srv["base"] + "/v1/chat/completions",
                model, local=True, rpm=120, weight=0.78,
                strengths=("local", "private"), note="local, no key"))
        return srv, rows, {
            "active": bool(models),
            "detail": (f"{len(models)} local model(s)" if models
                       else "not running"),
        }

    with cf.ThreadPoolExecutor(max_workers=len(LOCAL_SERVERS)) as ex:
        for srv, rows, st in ex.map(probe_one, LOCAL_SERVERS):
            status[srv["id"]] = st
            found.extend(rows)
    return found, status


def probe(force: bool = False) -> dict:
    """Detect live providers. Cached for 3 minutes; never raises."""
    global _PROBE, _PROBE_TS, _LOCAL_ROUTES
    now = time.time()
    with _PROBE_LOCK:
        if not force and _PROBE and now - _PROBE_TS < 180:
            return _status_payload()
        status: dict[str, dict] = {}

        remote_jobs = {
            "ovh": (OVH_CATALOG, "anonymous catalog reachable"),
            "llm7": (LLM7_MODELS, "keyless models reachable"),
            "pollinations": (POLL_MODELS, "anonymous model reachable"),
        }

        def probe_remote(item):
            key, (url, ok_detail) = item
            r = net.fetch(url, ttl=0, timeout=8.0,
                          endpoint_id="swarm:" + key)
            return key, {
                "active": bool(r.ok),
                "detail": (ok_detail if r.ok else (r.error or "unreachable")),
            }

        with cf.ThreadPoolExecutor(max_workers=len(remote_jobs)) as ex:
            for key, st in ex.map(probe_remote, remote_jobs.items()):
                status[key] = st

        for route in OPTIONAL_ROUTES:
            key = os.environ.get(route.key_env or "", "").strip()
            if key and allow_keyed():
                detail = "key present (explicitly enabled)"
                active = True
            elif key:
                detail = (f"{route.key_env} present, but keyed routes are "
                          f"off; set CHRONOVAULT_ALLOW_KEYS=1 to enable")
                active = False
            else:
                detail = f"set {route.key_env} to enable (optional)"
                active = False
            status[route.provider_key] = {"active": active, "detail": detail}

        local_routes, local_status = _local_routes_from_probe()
        _LOCAL_ROUTES = local_routes
        status.update(local_status)

        _PROBE = status
        _PROBE_TS = now
        return _status_payload()


def _status_payload() -> dict:
    active = [r for r in all_routes() if _route_active(r)]
    return {
        "roles": len(ROLES),
        "routes_total": len(all_routes()),
        "routes_active": len(active),
        "core_roles": len(CORE_IDS),
        "providers": _PROBE,
        "active": [_route_dict(r) for r in active],
        "dormant": [_route_dict(r) for r in all_routes() if not _route_active(r)],
        "checked_at": _PROBE_TS,
    }


def _route_active(route: Route) -> bool:
    if route.id in _DOWN:
        return False
    if route.local:
        return any(r.id == route.id for r in _LOCAL_ROUTES)
    info = _PROBE.get(route.provider_key) or {}
    return bool(info.get("active"))


def active_routes() -> list[Route]:
    probe()
    return [r for r in all_routes() if _route_active(r)]


def _route_dict(route: Route) -> dict:
    return {
        "id": route.id, "provider": route.provider, "label": route.label,
        "model": route.model, "local": route.local, "weight": route.weight,
        "rpm": route.rpm, "note": route.note, "slow": route.slow,
    }


# ---------------------------------------------------------------------------
# Council execution
# ---------------------------------------------------------------------------


def _stage(cb, name: str, payload: dict) -> None:
    if not cb:
        return
    try:
        cb(name, payload)
    except Exception:
        pass


def _short(text, limit: int = 1300) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit - 1] + "..."


def _evidence_text(evidence: list) -> str:
    lines = []
    for e in (evidence or [])[:7]:
        if not isinstance(e, dict) or not e.get("ok"):
            continue
        src = str(e.get("source") or "source")
        snip = _short(e.get("snippet") or e.get("text") or "", 340)
        if snip:
            lines.append(f"- [{src}] {snip}")
    return "\n".join(lines) if lines else "(koi live evidence nahi)"


def _panel_messages(role: Role, question: str, kind: str, base_text: str,
                    evidence_txt: str, constraint: str = "") -> list[dict]:
    task = {
        "forecast": ("Yeh speculative future sawal hai. Verified facts aur current "
                     "signals ko alag rakho. Koi guaranteed number, ranking ya "
                     "exact outcome mat banao; horizon aur uncertainty batao."),
        "forecast_fx": ("FX forecast speculative hai. Live quote aur statistical "
                        "projection ko alag rakho; guarantee mat do."),
        "forecast_crypto": ("Crypto forecast speculative hai. Volatility aur "
                            "downside risk batao; guarantee mat do."),
        "news": ("Sirf diye headlines ka content summarize karo; naya news "
                 "invent mat karo."),
        "country": ("Diye country facts ko explain karo; numbers exactly rakho."),
        "baby_name": ("Yeh cultural suggestion hai, prediction nahi. Naam, "
                      "meaning aur phonetic fit par focused raho."),
    }.get(kind, ("Diye verified jawab ko simple Roman Urdu me samjhao. Koi nayi "
                 "fact, number ya date add mat karo."))
    system = (
        f"You are {role.name}, a {role.domain} specialist in the ChronoVault "
        f"multi-model council. {role.system}\n"
        "Hard rules:\n"
        "1. Use ONLY the verified facts and evidence below.\n"
        "2. Never invent numbers, dates, names or sources.\n"
        "3. If evidence is insufficient, say exactly what is missing.\n"
        "4. Answer in 2-4 short sentences of natural Roman Urdu (Hinglish).\n"
        "5. End with exactly one line: (confidence: NN%).\n"
        f"6. Your specialist lens: {role.domain}. Stay in that lens."
    )
    user = (
        f"AAJ: {date.today().isoformat()}\n"
        f"SAWAL: {question}\n"
        f"INTENT: {kind}\n\n"
        f"VERIFIED FACTS (authoritative):\n{_short(base_text, 1200)}\n\n"
        f"EVIDENCE:\n{evidence_txt}\n\n"
        f"TASK: {task}"
    )
    if constraint:
        user += f"\n\nHARD CONSTRAINT (must obey):\n{constraint}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _judge_messages(question: str, kind: str, base_text: str,
                    evidence_txt: str, scored: list[dict],
                    constraint: str = "") -> list[dict]:
    candidate_blocks = []
    for i, c in enumerate(scored[:5], 1):
        candidate_blocks.append(
            f"[{i}] {c.get('role_name')} ({c.get('route_label')}) "
            f"score={c.get('score', 0):.2f}\n{_short(c.get('text'), 420)}"
        )
    system = (
        "You are the final judge of the ChronoVault council: 70 specialist "
        "agents, each grounded in the same verified evidence. Your job is to "
        "write the answer the user will actually read.\n"
        "Rules:\n"
        "- Use only claims supported by the verified facts or by at least two "
        "candidate answers.\n"
        "- Never invent numbers, dates, names or sources. Do not add new facts.\n"
        "- For INTENT forecast, never present a guess as fact or guarantee. "
        "State uncertainty and do not invent a numeric outcome or ranking.\n"
        "- If candidates disagree, state the disagreement briefly and prefer the "
        "better-grounded side.\n"
        "- 2-4 short sentences in natural Roman Urdu (Hinglish).\n"
        "- End with exactly one line: (confidence: NN%).\n"
        "- No role labels, no markdown, no chain-of-thought."
    )
    user = (
        f"AAJ: {date.today().isoformat()}\n"
        f"SAWAL: {question}\nINTENT: {kind}\n\n"
        f"VERIFIED FACTS:\n{_short(base_text, 1200)}\n\n"
        f"EVIDENCE:\n{evidence_txt}\n\n"
        f"TOP CANDIDATES:\n" + "\n\n".join(candidate_blocks) +
        "\n\nFinal answer:"
    )
    if constraint:
        user += f"\n\nHARD CONSTRAINT (must obey):\n{constraint}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _rate_wait(route: Route, deadline: float) -> bool:
    while True:
        with _RATE_LOCK:
            now = time.time()
            hist = [t for t in _RATE.get(route.id, []) if now - t < 61.0]
            _RATE[route.id] = hist
            if len(hist) < max(1, route.rpm):
                hist.append(now)
                return True
            wait = 61.0 - (now - hist[0]) + 0.15
        if time.time() + wait > deadline:
            return False
        time.sleep(min(wait, 4.0))


def _chat(route: Route, messages: list[dict], temperature: float = 0.25,
          max_tokens: int = 700, timeout: float = 35.0,
          deadline: float | None = None) -> dict:
    if route.id in _DOWN or time.time() < _COOLDOWN.get(route.id, 0):
        return {"ok": False, "error": "route cooling down", "route": route}
    if deadline and not _rate_wait(route, deadline):
        return {"ok": False, "error": "rate-limit budget exhausted", "route": route}

    headers = {}
    if route.key_env:
        if not allow_keyed():
            return {"ok": False, "route": route,
                    "error": "keyed provider disabled; set CHRONOVAULT_ALLOW_KEYS=1"}
        key = os.environ.get(route.key_env or "", "").strip()
        if not key:
            return {"ok": False, "error": f"missing {route.key_env}", "route": route}
        headers["Authorization"] = f"Bearer {key}"

    body = {
        "model": route.model or "default",
        "messages": messages,
        "temperature": max(0.0, min(1.0, float(temperature))),
        "max_tokens": max(64, int(max_tokens)),
    }
    t0 = time.time()
    r = net.fetch(route.url, method="POST", json_body=body, ttl=0,
                  timeout=timeout, headers=headers,
                  endpoint_id="swarm:" + route.id)
    ms = int((time.time() - t0) * 1000)
    _LATENCY[route.id] = int((_LATENCY.get(route.id, ms) * 3 + ms) / 4)
    if not r.ok:
        err = r.error or f"HTTP {r.status}"
        if r.status == 429:
            _COOLDOWN[route.id] = time.time() + 40
        elif r.status in (401, 403, 404):
            _DOWN.add(route.id)
        return {"ok": False, "error": err, "route": route, "ms": ms}

    data = r.data
    text = ""
    if isinstance(data, dict):
        choices = data.get("choices") or []
        if choices and isinstance(choices, list):
            msg = (choices[0] or {}).get("message") or {}
            text = msg.get("content") or msg.get("reasoning") or ""
            if not text:
                text = (choices[0] or {}).get("text") or ""
        if not text:
            text = data.get("text") or data.get("response") or ""
    elif isinstance(data, str):
        text = data
    # Some providers return content as a list of parts.
    if isinstance(text, list):
        text = " ".join(str(p.get("text") if isinstance(p, dict) else p)
                        for p in text)
    text = _clean(text)
    if len(text) < 8:
        return {"ok": False, "error": "empty completion", "route": route,
                "ms": ms, "data": data}
    return {"ok": True, "text": text, "route": route, "ms": ms,
            "model": (data.get("model") if isinstance(data, dict) else "") or route.model}


def _clean(text) -> str:
    s = str(text or "")
    s = re.sub(r"```.*?```", " ", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"^\s*#+\s*", "", s, flags=re.M)
    s = re.sub(r"\s+", " ", s).strip()
    # Models occasionally emit a duplicated copula ("... ho sakti hai, hai").
    s = re.sub(r"\b(hai|hain)\s*,\s*(hai|hain)\b", r"\1", s, flags=re.I)
    return s


_CONF_RE = re.compile(r"(?:confidence|conf|yaqeen)\s*[:=]?\s*(\d{1,3})\s*%",
                      re.I)
_CONF_PAREN = re.compile(r"\(\s*(\d{1,3})\s*%\s*\)")


def parse_confidence(text: str, default: float = 0.55) -> float:
    s = str(text or "")
    m = _CONF_RE.search(s) or _CONF_PAREN.search(s)
    if not m:
        return default
    try:
        return max(0.05, min(0.99, float(m.group(1)) / 100.0))
    except Exception:
        return default


def strip_confidence(text: str) -> str:
    s = str(text or "")
    # Remove the whole "(confidence: 68%)" group first; otherwise the inner
    # regex leaves an empty "()" behind.
    s = re.sub(r"\(\s*(?:confidence|conf|yaqeen)?\s*[:=]?\s*\d{1,3}\s*%\s*\)",
               "", s, flags=re.I)
    s = _CONF_RE.sub("", s)
    s = _CONF_PAREN.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" ;,-")
    return re.sub(r"\s+([.,;:!?])", r"\1", s)


_STOP = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this",
    "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on",
    "for", "with", "as", "at", "by", "from", "it", "its", "we", "you", "they",
    "he", "she", "i", "me", "my", "our", "your", "their", "not", "no", "yes",
    "ho", "hai", "hain", "ka", "ki", "ke", "ko", "se", "me", "mein", "aur",
    "ya", "par", "bhi", "kya", "yeh", "woh", "ek", "jo", "tha", "thi", "hoga",
    "hogi", "kar", "karo", "liye", "koi", "nahi", "sirf", "abhi", "baad",
}


def _tokens(text: str) -> set[str]:
    s = re.sub(r"[^\w\u0600-\u06FF]+", " ", str(text or "").lower())
    return {w for w in s.split() if len(w) > 1 and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUM_RE.finditer(str(text or ""))}


def score_candidates(cands: list[dict], base_text: str,
                     evidence_text: str) -> list[dict]:
    """Offline, deterministic scoring. Exposed for tests."""
    if not cands:
        return []
    base_tokens = _tokens(base_text + " " + evidence_text)
    known_nums = _numbers(base_text + " " + evidence_text) | {
        str(date.today().year)}
    token_sets = [_tokens(c.get("text", "")) for c in cands]
    texts = [str(c.get("text", "")).lower() for c in cands]
    for i, c in enumerate(cands):
        toks = token_sets[i]
        overlap = (len(toks & base_tokens) / len(toks)) if toks else 0.0
        nums = _numbers(c.get("text", ""))
        if nums:
            num_hits = len(nums & known_nums) / len(nums)
            ground = 0.50 * num_hits + 0.50 * overlap
        else:
            ground = 0.35 + 0.65 * overlap
        sims = sorted((_jaccard(toks, token_sets[j])
                       for j in range(len(cands)) if j != i), reverse=True)
        agreement = statistics.mean(sims[:5]) if sims else 0.0
        conf = float(c.get("confidence") or parse_confidence(c.get("text", "")))
        weight = float(c.get("route_weight") or 1.0) * float(
            c.get("role_weight") or 1.0)
        low = texts[i]
        penalty = 0.0
        if re.search(r"\b(guarantee|guaranteed|100\s*%|pakka|definitely|"
                     r"zaroor hoga)\b", low):
            penalty += 0.22
        if "as an ai" in low or "i cannot" in low:
            penalty += 0.10
        if re.search(r"\b(i don't know|pata nahi|no data|maloom nahi)\b", low) \
                and base_tokens:
            penalty += 0.16
        c["ground"] = round(ground, 3)
        c["agreement"] = round(agreement, 3)
        c["score"] = round(max(0.0, min(1.0,
            0.40 * ground + 0.28 * agreement + 0.14 * overlap +
            0.10 * max(0.0, min(1.0, conf)) + 0.08 * max(0.0, min(2.0, weight))
            - penalty)), 3)
    return sorted(cands, key=lambda c: (-c.get("score", 0), c.get("role_id", "")))


def assign_roles(selected: list[Role], routes: list[Route],
                 judge: Route | None = None) -> list[tuple[Role, Route]]:
    """Round-robin roles across routes, reserving the judge route when possible.

    Fast routes are preferred for normal councils. Slow-but-strong models are
    pushed to the back so a 9-agent chat does not wait a minute for Llama or
    Mistral; the full 50-agent council still uses them.
    """
    if not selected or not routes:
        return []
    ordered = sorted(routes, key=lambda r: (
        bool(r.slow), -r.weight, _LATENCY.get(r.id, 5000), r.id))
    panel = [r for r in ordered if judge is None or r.id != judge.id]
    if len(panel) < 3:
        panel = ordered
    return [(role, panel[i % len(panel)]) for i, role in enumerate(selected)]


def _pick_judge(routes: list[Route]) -> Route | None:
    if not routes:
        return None
    preference = ("ovh:gpt-oss-120b", "ovh:qwen3.6-35b",
                  "ovh:deepseek-v4.1", "ovh:gpt-oss-20b",
                  "ovh:llama-3.3-70b")
    by_id = {r.id: r for r in routes}
    for rid in preference:
        if rid in by_id:
            return by_id[rid]
    return max(routes, key=lambda r: r.weight)


def _run_panel(assignments: list[tuple[Role, Route]], question: str, kind: str,
               base_text: str, evidence_txt: str, deadline: float,
               on_stage=None, max_workers: int = 6,
               constraint: str = "") -> list[dict]:
    if not assignments:
        return []
    results: list[dict] = []
    lock = threading.Lock()

    def one(item):
        role, route = item
        if time.time() > deadline:
            return {"ok": False, "role": role, "route": route,
                    "error": "deadline"}
        temp = 0.18 + (int(hashlib.sha256(role.id.encode()).hexdigest()[:2], 16)
                       % 5) * 0.05
        msgs = _panel_messages(role, question, kind, base_text, evidence_txt,
                               constraint)
        r = _chat(route, msgs, temperature=temp, max_tokens=650,
                  timeout=min(38.0, max(12.0, deadline - time.time())),
                  deadline=deadline)
        out = {
            "ok": bool(r.get("ok")),
            "role_id": role.id, "role_name": role.name, "domain": role.domain,
            "route_id": route.id, "route_label": route.provider + " · " + route.label,
            "model": r.get("model") or route.model,
            "text": r.get("text", ""), "error": r.get("error", ""),
            "ms": r.get("ms", 0), "confidence": parse_confidence(r.get("text", "")),
            "role_weight": role.weight, "route_weight": route.weight,
        }
        with lock:
            results.append(out)
            _stage(on_stage, "agent", {
                "role": role.name, "model": route.label,
                "ok": out["ok"], "ms": out["ms"],
            })
        return out

    with cf.ThreadPoolExecutor(max_workers=min(max_workers, len(assignments))) as ex:
        futs = [ex.submit(one, a) for a in assignments]
        for f in cf.as_completed(futs):
            try:
                f.result()
            except Exception:
                pass
    return results


def _judge(route: Route | None, question: str, kind: str, base_text: str,
           evidence_txt: str, scored: list[dict], deadline: float,
           on_stage=None, constraint: str = "") -> dict:
    if route is None or not scored:
        return {"ok": False, "text": "", "error": "no judge"}
    remaining = max(10.0, deadline - time.time())
    r = _chat(route, _judge_messages(question, kind, base_text, evidence_txt,
                                     scored, constraint),
              temperature=0.15, max_tokens=750,
              timeout=min(48.0, remaining), deadline=deadline)
    _stage(on_stage, "judge", {"model": route.label, "ok": bool(r.get("ok"))})
    return r


def _unsupported_numbers(final: str, known: str, candidates: list[dict]) -> list[str]:
    known_nums = _numbers(known)
    for c in candidates:
        known_nums |= _numbers(c.get("text", ""))
    known_nums.add(str(date.today().year))
    return sorted(n for n in _numbers(final) if n not in known_nums)


def _summary(selected: list[Role], assignments: list[tuple[Role, Route]],
             results: list[dict], scored: list[dict], judge_route: Route | None,
             agreement: float, notes: list[str], ms: int) -> dict:
    ok_results = [r for r in results if r.get("ok")]
    models = sorted({r.get("route_id", "") for r in ok_results if r.get("route_id")})
    return {
        "agents_requested": len(selected),
        "agents_replied": len(ok_results),
        "agents_failed": len(results) - len(ok_results),
        "models_requested": len({r.id for _role, r in assignments}),
        "models_replied": models,
        "judge": judge_route.id if judge_route else "",
        "agreement": round(agreement, 3),
        "consensus": sum(1 for c in scored
                         if c.get("agreement", 0) >= 0.30),
        "roles": [{
            "role": r.get("role_id"), "name": r.get("role_name"),
            "model": r.get("route_id"), "ok": r.get("ok"),
            "ms": r.get("ms"), "score": r.get("score"),
            "error": r.get("error"),
        } for r in scored[:12]],
        "notes": notes,
        "elapsed_ms": ms,
    }


def synthesize(question: str, kind: str, base_text: str,
               evidence: list | None = None, depth: int = 9,
               base_confidence: float = 0.6, on_stage=None,
               timeout: float | None = None, constraint: str = "") -> dict:
    """Run the council and return a grounded final answer.

    Returns {ok, text, confidence, summary, notes, cached}.  Never raises.
    """
    t0 = time.time()
    depth = max(5, min(50, int(depth or 9)))
    evidence = evidence or []
    evidence_txt = _evidence_text(evidence)

    # Cache identical work for five minutes.
    key_src = (question + "|" + kind + "|" + str(depth) + "|" + base_text +
               "|" + evidence_txt + "|" + constraint)
    key = hashlib.sha256(key_src.encode("utf-8", "ignore")).hexdigest()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < 300:
            out = dict(hit[1])
            out["cached"] = True
            return out

    routes = active_routes()
    if not routes:
        return {
            "ok": False, "text": "", "confidence": 0.0, "cached": False,
            "summary": {"agents_requested": depth, "agents_replied": 0,
                        "models_replied": [], "notes": []},
            "notes": ["Koi keyless AI route reachable nahi hai — council offline. "
                      "Verified/deterministic jawab hi dikhaya jayega."],
        }
    _stage(on_stage, "probe", {"routes": len(routes),
                              "roles": len(ROLES), "depth": depth})

    selected = select_roles(question, kind, depth)
    judge_route = _pick_judge(routes)
    assignments = assign_roles(selected, routes, judge_route)
    if timeout is None:
        timeout = 240.0 if depth >= 30 else (140.0 if depth >= 15 else 75.0)
    deadline = t0 + max(25.0, float(timeout))

    _stage(on_stage, "panel", {
        "agents": len(selected), "models": len({r.id for _a, r in assignments}),
        "judge": judge_route.label if judge_route else "",
    })
    results = _run_panel(assignments, question, kind, base_text, evidence_txt,
                         deadline, on_stage=on_stage,
                         max_workers=min(12, max(6, depth)),
                         constraint=constraint)
    ok_results = [r for r in results if r.get("ok") and r.get("text")]
    notes: list[str] = []
    if not ok_results:
        notes.append("Council ke tamam agents fail/rate-limited hue — "
                     "verified jawab bina AI ke dikhaya ja raha hai.")
        return {"ok": False, "text": "", "confidence": 0.0, "cached": False,
                "summary": _summary(selected, assignments, results, [], judge_route,
                                    0.0, notes, int((time.time() - t0) * 1000)),
                "notes": notes}

    scored = score_candidates(ok_results, base_text, evidence_txt)
    agreement = statistics.mean([c.get("agreement", 0.0) for c in scored[:8]])
    best_conf = statistics.median([c.get("confidence", 0.55) for c in scored[:5]])

    judge_route = _pick_judge(active_routes())
    judged = _judge(judge_route, question, kind, base_text, evidence_txt, scored,
                    deadline, on_stage=on_stage, constraint=constraint)
    final = ""
    judge_used = False
    if judged.get("ok"):
        final = strip_confidence(_clean(judged.get("text", "")))
        judge_used = True
    if len(final) < 20:
        final = strip_confidence(_clean(scored[0].get("text", "")))
        judge_used = False

    # A judge may not invent numbers that neither the evidence nor any agent
    # supplied. If it does, fall back to the best grounded candidate.
    unsupported = _unsupported_numbers(final, base_text + " " + evidence_txt,
                                       scored[:5])
    if len(unsupported) >= 2:
        notes.append("Judge ne evidence me na hone wale numbers add kiye — "
                     "top grounded agent ka jawab use kiya gaya.")
        final = strip_confidence(_clean(scored[0].get("text", "")))
        judge_used = False
    elif unsupported:
        notes.append("Ek number evidence se cross-check nahi hua; confidence "
                     "kam rakhi gayi hai.")

    cap = 0.94
    if kind.startswith("forecast"):
        cap = 0.78
    elif not evidence:
        cap = 0.62
    if kind == "baby_name":
        cap = 0.66
    conf = (0.40 * max(0.0, min(1.0, float(base_confidence))) +
            0.35 * max(0.0, min(1.0, agreement)) +
            0.25 * max(0.0, min(1.0, best_conf)))
    if unsupported:
        conf -= 0.08
    conf = round(max(0.2, min(cap, conf)), 3)

    models_used = sorted({r.get("route_id", "") for r in ok_results if r.get("route_id")})
    notes.append(
        f"Council: {len(ok_results)}/{len(selected)} agents ne jawab diya; "
        f"{len(models_used)} model route(s); agreement {agreement:.2f}; "
        f"judge {'used' if judge_used else 'fallback'}.")
    if len(results) > len(ok_results):
        notes.append(f"{len(results) - len(ok_results)} agent(s) rate-limit/down "
                     f"ki wajah se skip hue.")
    if kind.startswith("forecast"):
        notes.append("Yeh speculative statistical analysis hai — guarantee nahi.")
    if unsupported:
        notes.append("Unsupported numbers: " + ", ".join(unsupported[:5]))

    out = {
        "ok": bool(final),
        "text": final,
        "confidence": conf,
        "cached": False,
        "summary": _summary(selected, assignments, results, scored, judge_route,
                            agreement, notes, int((time.time() - t0) * 1000)),
        "notes": notes,
    }
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), dict(out))
        if len(_CACHE) > 80:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest, None)
    return out


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def status_text() -> str:
    st = probe()
    active = st.get("active") or []
    providers = sorted({r["provider"] for r in active})
    lines = [
        f"Council roles      {st.get('roles', 0)} specialists "
        f"({st.get('core_roles', 0)} core)",
        f"Model routes       {st.get('routes_active', 0)} live / "
        f"{st.get('routes_total', 0)} known",
        f"Live providers     {', '.join(providers) if providers else 'none'}",
    ]
    for r in active[:14]:
        lines.append(f"  - {r['provider']} · {r['label']}  [{r['id']}]")
    if len(active) > 14:
        lines.append(f"  ... +{len(active) - 14} more route(s)")
    return "\n".join(lines)
