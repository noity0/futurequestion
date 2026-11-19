"""ChronoVault 2.2 — conversational agent with slot-filling and AI council.

The agent turns a vague question into a complete one:

    user: "mere bache ka naam kya hoga?"
    agent: "Bachay ka gender? (boy / girl / surprise)"
    user: "boy"
    agent: "Family surname?"
    ...
    agent: ranked cultural shortlist + honest SPECULATIVE badge

The same flow works for weather (which city?), FX (which pair?), EMI
(amount/rate/years?), forecasts (asset/horizon?) and dates.

No fake slot values: if a detail is missing, the agent asks for it.
The optional "AI council" cross-checks the answer with 9 specialists by
default. Prefix a message with "/deep" to run the full 50-agent council.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import babynames, formulas
from .ask import DEFAULT_DEPTH, Chrono, clamp_depth
from .memory import Memory
from .places import (CRYPTO_SYMBOL, city_slug, find_city, find_crypto,
                     find_currencies)
from .router import Intent, forecast_query, route

CITY_REPLIES = ["Lahore", "Karachi", "Islamabad", "London", "Dubai"]
CURRENCY_REPLIES = ["USD", "PKR", "EUR", "GBP", "AED", "INR", "SAR"]

# "/deep <sawal>", "/council <sawal>", "full council: <sawal>" → depth 50
_DEEP_RE = re.compile(
    r"^\s*(?:/deep|/council|deep council|full council)\s*[:\-]?\s*", re.I)

SPECS: dict[str, list[tuple[str, str, list[str]]]] = {
    "baby_name": [
        ("gender", "Bachay ka gender kya hai? (boy / girl / surprise)",
         ["Boy", "Girl", "Surprise"]),
        ("surname", "Family surname kya hai? (e.g. Khan, Ahmed, Sheikh)", []),
        ("culture", "Naam kis culture/zubaan se chahiye? (Urdu, Arabic, English, "
                    "Turkish, Persian, Hindi, Sindhi, Punjabi, mix)",
         ["Urdu", "Arabic", "English", "Turkish", "Persian", "Hindi"]),
        ("style", "Style kaisa chahiye? (classic, modern, unique, religious, "
                  "koi bhi)",
         ["Classic", "Modern", "Unique", "Religious", "Koi bhi"]),
    ],
    "weather": [
        ("city", "Kis shehar ka mausam chahiye? (e.g. Lahore, Karachi, London)",
         CITY_REPLIES),
    ],
    "time": [
        ("city", "Kis shehar ka waqt chahiye? (e.g. Lahore, Karachi, London)",
         CITY_REPLIES),
    ],
    "fx": [
        ("from", "Kaunsi currency se convert karna hai? (e.g. USD)",
         ["USD", "PKR", "EUR", "GBP"]),
        ("to", "Kaunsi currency me convert karna hai? (e.g. PKR)",
         ["PKR", "USD", "AED", "SAR"]),
    ],
    "forecast_fx": [
        ("from", "Kaunse pair ka future? Pehli currency? (e.g. USD)",
         ["USD", "PKR", "EUR"]),
        ("to", "Doosri currency? (e.g. PKR)", ["PKR", "USD", "AED"]),
        ("horizon_days", "Kitne din aage ka forecast? (e.g. 30 din, 6 mahine, "
                         "1 saal)", ["30 din", "90 din", "1 saal"]),
    ],
    "crypto": [],
    "forecast_crypto": [
        ("horizon_days", "Kitne din aage ka forecast? (e.g. 30 din, 90 din, "
                         "1 saal)", ["30 din", "90 din", "1 saal"]),
    ],
    "forecast": [
        ("asset", "Kis cheez ka future dekhna hai? (USD/PKR, Bitcoin, gold, "
                  "ya koi topic)", ["USD/PKR", "Bitcoin", "Gold"]),
        ("horizon_days", "Kitne din aage? (e.g. 30 din, 6 mahine, 1 saal)",
         ["30 din", "90 din", "1 saal"]),
    ],
    "interest": [
        ("principal", "Principal amount kitna hai? (e.g. 100000 ya 5 lakh)", []),
        ("rate", "Annual rate kitna percent hai? (e.g. 18%)", []),
        ("years", "Kitne saal/mahine ke liye? (e.g. 5 saal)", []),
    ],
    "emi": [
        ("principal", "Loan amount kitna hai? (e.g. 50 lakh)", []),
        ("rate", "Annual interest rate? (e.g. 12%)", []),
        ("years", "Loan duration? (e.g. 5 saal)", []),
    ],
    "date": [
        ("date", "Kaunsi tareekh? (e.g. 1 Jan 2050 ya 2050-01-01)", []),
    ],
    "countdown": [
        ("date", "Kis tareekh tak ka countdown? (e.g. 2050-01-01)", []),
    ],
    "capsule": [
        ("message", "Future ke liye kya message seal karna hai?", []),
    ],
}

OPTIONAL_DEFAULTS = {
    "baby_name": {"style": "any"},
    "fx": {"amount": 1.0},
    "forecast_fx": {"amount": 1.0},
    "forecast_crypto": {"amount": 1.0},
    "interest": {"per_year": 12},
    "emi": {},
    "weather": {"days": 1},
    "capsule": {"days": 365},
}


@dataclass
class ChatReply:
    session_id: str
    reply: str
    state: str
    intent: str
    slots: dict = field(default_factory=dict)
    pending: str = ""
    quick_replies: list = field(default_factory=list)
    answer: dict | None = None
    trace: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id, "reply": self.reply,
            "state": self.state, "intent": self.intent, "slots": self.slots,
            "pending": self.pending, "quick_replies": self.quick_replies,
            "answer": self.answer, "trace": self.trace,
        }


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value not in (0, 0.0)
    return True


def _num(text: str) -> float | None:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(lakh|lac|crore|k|m|million|"
                  r"billion)?", text, re.I)
    if not m:
        return None
    n = formulas.parse_amount(m.group(0))
    if n is None:
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return n


def _city_slots(text: str) -> dict | None:
    city = find_city(text)
    if not city:
        return None
    name, country, lat, lon = city
    return {"city": name, "country": country, "lat": lat, "lon": lon,
            "slug": city_slug(name)}


def parse_slot(slot: str, text: str) -> dict | None:
    """Parse one answer into one or more slot values. None = re-ask."""
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return None

    if slot in ("city", "place"):
        got = _city_slots(t)
        if got:
            return got
        # accept a bare city-looking word if it is known
        for word in re.findall(r"[A-Za-z][A-Za-z .'-]{1,30}", t):
            got = _city_slots(word.strip())
            if got:
                return got
        return None

    if slot == "gender":
        if re.search(r"\b(boy|ladka|beta|male|mard)\b", low):
            return {"gender": "boy"}
        if re.search(r"\b(girl|ladki|beti|female|aurat)\b", low):
            return {"gender": "girl"}
        if re.search(r"\b(any|surprise|dono|koi bhi|pata nahi|unknown)\b", low):
            return {"gender": "any"}
        return None

    if slot == "surname":
        cleaned = re.sub(r"(?i)\b(surname|family\s+name|last\s+name|khandan|"
                         r"naam|name|mera|meri|my|apna|apni|hai|is|ka|ki|the)\b",
                         " ", t)
        words = re.findall(r"[A-Za-z][A-Za-z'-]{1,30}", cleaned)
        if not words:
            return None
        return {"surname": " ".join(w.capitalize() for w in words[-2:])[:40]}

    if slot == "culture":
        culture = babynames.normalize_culture(low)
        if culture == "urdu" and not re.search(
                r"\b(urdu|muslim|islam|islami|pakistan|pakistani|roman)\b", low):
            return None
        return {"culture": culture}

    if slot == "style":
        style = babynames.normalize_style(low)
        if style == "any" and not re.search(
                r"\b(any|koi bhi|sab|surprise)\b", low):
            return None
        return {"style": style}

    if slot == "from":
        codes = find_currencies(t)
        if codes:
            return {"from": codes[0].upper()}
        m = re.search(r"\b([A-Za-z]{3})\b", t)
        return {"from": m.group(1).upper()} if m else None

    if slot == "to":
        codes = find_currencies(t)
        if codes:
            return {"to": codes[-1].upper()}
        m = re.search(r"\b([A-Za-z]{3})\b", t)
        return {"to": m.group(1).upper()} if m else None

    if slot == "principal":
        n = _num(t)
        return {"principal": n} if n else None

    if slot == "rate":
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
        if m:
            return {"rate": float(m.group(1))}
        n = _num(t)
        return {"rate": n} if n else None

    if slot in ("years", "duration"):
        n = _num(t)
        if not n:
            return None
        if re.search(r"\b(mahin|month|mahina)\b", low):
            n = n / 12.0
        elif re.search(r"\b(din|day)\b", low):
            n = n / 365.0
        return {"years": round(n, 4)}

    if slot == "horizon_days":
        days = formulas.parse_duration_days(t)
        if days:
            return {"horizon_days": int(days),
                    "target": (formulas.today().isoformat())}
        d = formulas.parse_date(t)
        if d and d > formulas.today():
            return {"horizon_days": max(1, (d - formulas.today()).days),
                    "target": d.isoformat()}
        return None
    if slot == "date":
        d = formulas.parse_date(t)
        return {"date": d.isoformat()} if d else None

    if slot == "asset":
        coin = find_crypto(t)
        if coin:
            return {"asset": coin, "coin": coin, "query": coin,
                    "symbol": CRYPTO_SYMBOL.get(coin, coin.upper())}
        codes = find_currencies(t)
        if len(codes) >= 2:
            return {"asset": f"{codes[0]}/{codes[1]}", "from": codes[0],
                    "to": codes[1], "query": f"{codes[0]}/{codes[1]}"}
        if re.search(r"\b(gold|sona|silver|chandi)\b", low):
            metal = "gold" if "gold" in low or "sona" in low else "silver"
            return {"asset": metal, "query": metal}
        # A named non-financial topic is valid for a generic speculative
        # forecast. Store it as `query` too, so stale FX/crypto context cannot
        # leak into the answer. One-word replies are too ambiguous to accept.
        if len(t.split()) >= 2:
            topic = forecast_query(t)
            return {"asset": topic[:60], "query": topic[:220]}
        return None

    if slot == "message":
        return {"message": t[:8000]}

    return None


def _is_time_question(text: str) -> bool:
    low = " " + text.lower() + " "
    return any(w in low for w in ("kitne baje", "kya time", "kya waqt",
                                  "current time", "local time", "abhi time",
                                  "waqt kya", "time kya", "time in ")) and \
        "time machine" not in low and "time travel" not in low


class ChatAgent:
    def __init__(self, chrono: Chrono | None = None,
                 depth: int = DEFAULT_DEPTH):
        self.memory = Memory()
        self.chrono = chrono or Chrono(depth=depth)
        self.depth = clamp_depth(depth)

    # ------------------------------------------------------------- public
    def handle(self, message: str, session_id: str | None = None,
               ai: bool = True, depth: int | None = None) -> ChatReply:
        text = (message or "").strip()
        depth = self.depth if depth is None else clamp_depth(depth, self.depth)
        # Explicit deep-council request: "/deep <sawal>"
        m = _DEEP_RE.match(text)
        if m:
            text = text[m.end():].strip()
            depth = 50
            if not text:
                answer = ("/deep ke baad sawal likhein. Misal: \"/deep Pakistan "
                          "ka future kya hoga?\" — main 50 specialist agents ki "
                          "council chalaunga.")
                sess = self.memory.chat_create(session_id)
                self.memory.chat_add_message(sess["id"], "assistant", answer,
                                             {"kind": "clarify"})
                return ChatReply(sess["id"], answer, "new", "", {}, "",
                                 [], None, ["empty deep-council request"])
        sess = (self.memory.chat_get(session_id) if session_id else None) \
            or self.memory.chat_create(session_id)
        sid = sess["id"]
        state = sess.get("state") or "new"
        kind = sess.get("intent") or ""
        slots = dict(sess.get("slots") or {})
        pending = sess.get("pending") or ""
        last_question = sess.get("last_question") or ""
        trace: list[str] = []

        if not text:
            return self._ask(sid, kind or "help", slots,
                             "Sawal likhein — misal: \"mere bache ka naam kya "
                             "hoga?\", \"USD to PKR\", ya \"Lahore ka mausam\".",
                             state="new", trace=["empty message"])

        self.memory.chat_add_message(sid, "user", text)

        if text.lower() in ("/reset", "reset", "naya sawal", "new question"):
            self.memory.chat_reset(sid)
            reply = ("Naya sawal shuru. Kya jaanna hai? Future, live data, "
                     "math — kuch bhi poochein.")
            self.memory.chat_add_message(sid, "assistant", reply,
                                         {"kind": "reset"})
            return ChatReply(sid, reply, "new", "", {}, "",
                             ["Mere bache ka naam?", "USD to PKR",
                              "Lahore ka mausam"], None,
                             ["session reset"])

        # ------------------------------------------------- pending slot
        if state == "asking" and pending:
            filled = parse_slot(pending, text)
            if filled:
                if pending == "asset":
                    # The answer defines a new forecast target. Drop the old
                    # FX/crypto context so a previous session cannot leak in.
                    for key in ("from", "to", "coin", "symbol", "amount"):
                        slots.pop(key, None)
                slots.update(filled)
                if pending == "asset":
                    if filled.get("coin"):
                        kind = "forecast_crypto"
                        slots.pop("asset", None)
                        slots.pop("query", None)
                    elif filled.get("from") and filled.get("to"):
                        kind = "forecast_fx"
                        slots.pop("asset", None)
                        slots.pop("query", None)
                trace.append(f"filled {pending}")
                pending = ""
                state = "asking"
            else:
                trace.append(f"could not parse {pending}")
                # A real, multi-word new question should replace the old slot
                # flow instead of being forced into it. This is what prevents
                # "pakistan military power" from inheriting an old USD/PKR slot.
                new_intent = route(text)
                is_meta = bool(re.match(
                    r"^(pata nahi|mujhe nahi pata|koi bhi|any|don't know|"
                    r"not sure|kuch bhi)\b", low))
                changed = (new_intent.kind != kind and not is_meta and
                           (len(text.split()) >= 2 or
                            new_intent.kind not in ("knowledge",)))
                if changed:
                    kind = new_intent.kind
                    slots = self._sanitize(new_intent, text)
                    pending = ""
                    state = "asking"
                    last_question = text
                    trace.append(f"topic changed to {kind}")
                else:
                    return self._reask(sid, kind, slots, pending, trace)

        # A short refinement after an answer (baby name flow).
        if state == "answered" and kind in ("baby_name",) and \
                len(text.split()) <= 4:
            for slot in ("gender", "culture", "style"):
                got = parse_slot(slot, text)
                if got:
                    slots.update(got)
                    state = "asking"
                    trace.append(f"refined {slot}")
                    break

        # Natural follow-ups: "Karachi" after a weather/time answer,
        # "EUR" after an FX answer — keep the topic unless it is clearly new.
        if state == "answered" and not pending and len(text.split()) <= 4:
            if kind in ("weather", "time"):
                got = _city_slots(text)
                if got:
                    slots.update(got)
                    state = "asking"
                    last_question = text
                    trace.append(f"continued {kind}")
            elif kind == "fx":
                codes = find_currencies(text)
                if len(codes) == 1:
                    slots["to"] = codes[0]
                    state = "asking"
                    trace.append("continued fx")

        # ------------------------------------------------- fresh message
        if not pending and (state != "asking" or not kind):
            intents = self._initial_intent(text)
            kind = intents.kind
            slots = self._sanitize(intents, text)
            state = "asking"
            last_question = text
            trace.append(f"intent {kind}")

        # --------------------------------------------------- slot enforcement
        spec = SPECS.get(kind, [])
        for slot, _question, _chips in spec:
            if not _present(slots.get(slot)):
                return self._ask(sid, kind, slots, _question, state="asking",
                                 pending=slot, trace=trace + [f"missing {slot}"])

        defaults = OPTIONAL_DEFAULTS.get(kind) or {}
        for key, value in defaults.items():
            if not _present(slots.get(key)):
                slots[key] = value

        # Derive slots for weather/time once a city is known.
        if kind in ("weather", "time") and slots.get("city"):
            got = _city_slots(slots["city"]) or _city_slots(
                str(slots.get("city")))
            if got:
                slots.update(got)

        intent = Intent(kind, 0.9, slots, "chat agent (slot-filled)")
        ans = self.chrono.ask_with_intent(last_question or text, intent,
                                          ai=ai, depth=depth)
        data = ans.to_dict()
        reply = ans.answer
        trace += [f"source: {', '.join(ans.sources) if ans.sources else 'deterministic'}",
                  f"badge: {ans.badge}", f"confidence: {round(ans.confidence * 100)}%"]
        if ans.council:
            trace.append(
                f"council: {ans.council.get('agents_replied', 0)}/"
                f"{ans.council.get('agents_requested', depth)} agents, "
                f"{len(ans.council.get('models_replied') or [])} models, "
                f"agreement {ans.council.get('agreement', 0)}")
        self.memory.chat_save(sid, state="answered", intent=kind, slots=slots,
                              pending="", last_question=last_question or text)
        self.memory.chat_add_message(sid, "assistant", reply, {
            "kind": "answer", "answer_id": ans.answer_id, "badge": ans.badge,
            "confidence": ans.confidence, "sources": ans.sources,
            "council": ans.council,
        })
        return ChatReply(sid, reply, "answered", kind,
                         _public_slots(kind, slots), "", [], data, trace)

    # ------------------------------------------------------------ helpers
    def _initial_intent(self, text: str) -> Intent:
        it = route(text)
        # weather without a city must ask, instead of silently using Lahore
        if it.kind == "weather" and not find_city(text):
            return Intent("weather", 0.9, {}, "chat: city needed")
        # a bare time question ("kitne baje hain?") asks for the city
        if _is_time_question(text) and not find_city(text) and \
                not re.search(r"\b(UTC|GMT)\b", text, re.I):
            return Intent("time", 0.9, {}, "chat: city needed")
        return it

    def _sanitize(self, intent: Intent, text: str) -> dict:
        """Drop router defaults that the user never actually supplied."""
        kind, s = intent.kind, dict(intent.slots or {})
        low = text.lower()
        if kind in ("weather", "time") and not find_city(text) and \
                not re.search(r"\b(UTC|GMT)\b", text, re.I):
            s = {}
        if kind in ("fx", "forecast_fx"):
            codes = find_currencies(text)
            if len(codes) < 2:
                s.pop("to", None)
            if not codes:
                s.pop("from", None)
            if kind == "fx" and not _present(s.get("amount")):
                s["amount"] = 1.0
            if kind == "forecast_fx" and not formulas.parse_duration_days(text) \
                    and not formulas.parse_date(text):
                s.pop("horizon_days", None)
        if kind in ("interest", "emi"):
            if not _num(text) and not re.search(r"\d", text):
                s.pop("principal", None)
            if not re.search(r"\d+(?:\.\d+)?\s*%", text):
                s.pop("rate", None)
            if not formulas.parse_duration_days(text):
                s.pop("years", None)
        if kind in ("forecast", "forecast_crypto"):
            if not formulas.parse_duration_days(text) and \
                    not formulas.parse_date(text):
                s.pop("horizon_days", None)
        if kind == "baby_name":
            g = parse_slot("gender", text)
            if g:
                s.update(g)
        return {k: v for k, v in s.items() if _present(v)}

    def _reask(self, sid: str, kind: str, slots: dict, pending: str,
               trace: list) -> ChatReply:
        prompt, chips = "Ek choti detail chahiye.", []
        for slot, question, quick in SPECS.get(kind, []):
            if slot == pending:
                prompt, chips = question, quick
                break
        reply = f"Samajh nahi aaya — {prompt}"
        self.memory.chat_save(sid, state="asking", intent=kind, slots=slots,
                              pending=pending)
        self.memory.chat_add_message(sid, "assistant", reply,
                                     {"kind": "clarify", "slot": pending,
                                      "quick_replies": chips})
        return ChatReply(sid, reply, "asking", kind, _public_slots(kind, slots),
                         pending, chips, None, trace)

    def _ask(self, sid: str, kind: str, slots: dict, prompt: str,
             state: str = "asking", pending: str = "",
             trace: list | None = None) -> ChatReply:
        chips = []
        if pending:
            for slot, question, quick in SPECS.get(kind, []):
                if slot == pending:
                    prompt, chips = question, quick
                    break
            filled = _filled_summary(kind, slots)
            if filled:
                prompt += f"\n\nAb tak: {filled}."
        self.memory.chat_save(sid, state=state, intent=kind, slots=slots,
                              pending=pending)
        self.memory.chat_add_message(sid, "assistant", prompt,
                                     {"kind": "clarify", "slot": pending,
                                      "quick_replies": chips})
        return ChatReply(sid, prompt, state, kind, _public_slots(kind, slots),
                         pending, chips, None, trace or [])

    def session(self, sid: str) -> dict | None:
        sess = self.memory.chat_get(sid)
        if not sess:
            return None
        sess["messages"] = self.memory.chat_messages(sid)
        return sess

    def reset(self, sid: str) -> None:
        self.memory.chat_reset(sid)


def _filled_summary(kind: str, slots: dict) -> str:
    """Human-readable summary of the slots already known (no internal names)."""
    bits: list[str] = []
    if slots.get("from") and slots.get("to"):
        bits.append(f"{slots['from']}/{slots['to']}")
    if slots.get("coin"):
        bits.append(str(slots["coin"]))
    if slots.get("asset") and not bits:
        bits.append(str(slots["asset"]))
    if slots.get("city"):
        bits.append(str(slots["city"]))
    hd = slots.get("horizon_days")
    if hd:
        try:
            bits.append(f"{int(hd):,} din ka horizon")
        except (TypeError, ValueError):
            pass
    if slots.get("principal"):
        bits.append(f"principal {slots['principal']}")
    if slots.get("rate"):
        bits.append(f"rate {slots['rate']}%")
    if slots.get("years"):
        bits.append(f"{slots['years']} saal")
    if slots.get("date"):
        bits.append(str(slots["date"]))
    return ", ".join(bits)


def _public_slots(kind: str, slots: dict) -> dict:
    """Do not leak lat/lon noise into the UI."""
    allowed = {s for s, _q, _c in SPECS.get(kind, [])}
    out = {k: v for k, v in slots.items() if k in allowed}
    for k in ("city", "from", "to", "gender", "surname", "culture", "style",
              "horizon_days", "principal", "rate", "years", "date", "asset"):
        if k in slots:
            out[k] = slots[k]
    return out
