"""ChronoVault 2.2.0 — the orchestrator.

Question → route → parallel evidence → answer → optional AI council synthesis →
optional Paradox Ledger prophecy + future probe.

Honesty rules:
  * exact math is labelled EXACT-MATH
  * live data carries sources + agreement
  * forecasts carry backtest skill, an interval, and a registered probe
  * speculation is labelled SPECULATIVE and never sold as fact
  * a council can lower confidence, never raise it above the deterministic
    evidence it was given
  * understanding system clarifies time travel vs statistical predictions
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import babynames, formulas, net, sources, swarm
from .forecast import MAX_HORIZON_DAYS, forecast, to_text
from .memory import Memory
from .oracle import Oracle
from .places import DEFAULT_CITY
from .registry import Registry
from .router import Intent, route
from .text import shorten
from .understanding import understand_user_query

# Kinds where an AI explanation/cross-check adds value. Deterministic engines
# still own the facts; the council only explains them. Baby names stay offline
# by default; opt in with depth >= 15 (the shortlist itself is deterministic).
AI_KINDS = {"knowledge", "forecast", "forecast_fx", "forecast_crypto",
            "news", "country"}
DEFAULT_DEPTH = 9


def clamp_depth(value, default: int = DEFAULT_DEPTH) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(5, min(50, n))


@dataclass
class ChronoAnswer:
    question: str
    kind: str
    answer: str
    detail: str
    confidence: float
    badge: str
    evidence: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    intent: dict = field(default_factory=dict)
    prophecy_id: int | None = None
    probe_id: int | None = None
    answer_id: int | None = None
    ms: int = 0
    ai_used: bool = False
    notes: list = field(default_factory=list)
    council: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "question": self.question, "kind": self.kind, "answer": self.answer,
            "detail": self.detail, "confidence": self.confidence,
            "badge": self.badge, "evidence": self.evidence, "data": self.data,
            "sources": self.sources, "intent": self.intent,
            "prophecy_id": self.prophecy_id, "probe_id": self.probe_id,
            "answer_id": self.answer_id, "ms": self.ms, "ai_used": self.ai_used,
            "notes": self.notes, "council": self.council,
        }


def _mk(text, data=None, evidence=None, confidence=0.8, badge="LIVE",
        prophecy=None, ok=True, force_llm=False, notes=None):
    return {
        "ok": ok, "text": text, "data": data or {}, "evidence": evidence or [],
        "confidence": confidence, "badge": badge, "prophecy": prophecy,
        "force_llm": force_llm, "notes": notes or [],
    }


class Chrono:
    def __init__(self, use_llm: bool = True, depth: int = DEFAULT_DEPTH):
        self.reg = Registry()
        self.memory = Memory()
        self.oracle = Oracle()
        self.use_llm = use_llm
        self.depth = clamp_depth(depth)

    # ------------------------------------------------------------------ ask
    def ask(self, question: str, ai: bool | None = None,
            on_stage=None, intent: Intent | None = None,
            record: bool = True, depth: int | None = None) -> ChronoAnswer:
        t0 = time.time()
        ai = self.use_llm if ai is None else ai
        depth = self.depth if depth is None else clamp_depth(depth, self.depth)
        # Check if user needs clarification about time travel vs predictions
        understanding = understand_user_query(question)
        if understanding["intent"]["primary_intent"] == "time_travel_misconception":
            self._stage(on_stage, "done", {"confidence": 0.0, "ms": 0,
                                           "badge": "NEED-CLARIFICATION"})
            return ChronoAnswer(
                question=question, kind="understanding",
                answer=understanding["explanation"],
                detail="", confidence=0.0, badge="UNDERSTANDING",
                intent={"kind": "understanding", "reason": "time_travel_misconception"},
                data={"understanding": understanding})
        
        if not (question or "").strip():
            self._stage(on_stage, "done", {"confidence": 0.0, "ms": 0,
                                           "badge": "NEED-INPUT"})
            return ChronoAnswer(
                question="", kind="empty",
                answer=("Sawal likhein — misal: \"USD to PKR\", "
                        "\"Lahore ka mausam\" ya \"1 Jan 2050 konsa din?\"."),
                detail="", confidence=0.0, badge="NEED-INPUT",
                intent={"kind": "empty", "reason": "blank question"})
        intent = intent or route(question)
        self._stage(on_stage, "plan", intent.to_dict())
        try:
            res = self._dispatch(question, intent, on_stage)
        except Exception as e:
            res = _mk(
                f"Engine error: {type(e).__name__}: {e}. Koi jhoot nahi — "
                f"is sawal ka verified jawab abhi nahi hai.",
                confidence=0.1, badge="ERROR", ok=False)
            res["notes"].append("internal exception captured")
        if res is None:
            res = _mk("Sawal route nahi ho saka.", confidence=0.1,
                      badge="NO-ROUTE", ok=False)

        evidence = res.get("evidence") or []
        sources_list = []
        for e in evidence:
            if e.get("ok") and e.get("source") not in sources_list:
                sources_list.append(e["source"])
        notes = list(res.get("notes") or [])
        unver = [e for e in evidence if e.get("tls_unverified")]
        if unver:
            notes.append(f"{len(unver)} source(s) TLS-unverified fetch (local proxy) — data used, trust noted.")
        stale = [e for e in evidence if e.get("cached")]
        if stale and len(stale) == len(evidence) and evidence:
            notes.append("Sab sources cache se aaye (offline-first).")

        # ------------------------------------------------------ AI council
        council: dict = {}
        want_ai = ai and (intent.kind in AI_KINDS or res.get("force_llm") or
                          (intent.kind == "baby_name" and depth >= 15))
        if want_ai and (res.get("ok") or res.get("force_llm")):
            self._stage(on_stage, "council",
                        {"agents": depth, "engine": "swarm",
                         "kind": intent.kind})
            constraint = ""
            fc = (res.get("data") or {}).get("forecast") or {}
            if fc:
                if fc.get("horizon_capped"):
                    constraint = (
                        f"HORIZON CAP: the user asked for "
                        f"{int(fc.get('requested_horizon_days') or 0):,} days, but "
                        f"the statistical model is only valid for "
                        f"{int(fc.get('horizon_days') or 0):,} days. The forecast "
                        f"range applies to {int(fc.get('horizon_days') or 0):,} "
                        f"days, NOT to the requested horizon. State this cap "
                        f"clearly and never present the capped range as the "
                        f"answer for the requested horizon.")
                else:
                    constraint = (
                        f"STATISTICAL HORIZON: {int(fc.get('horizon_days') or 0):,} "
                        f"days, target {fc.get('target_date')}. Do not describe "
                        f"the forecast as covering a different horizon.")
            elif intent.kind == "forecast":
                data = res.get("data") or {}
                hd = int(data.get("horizon_days") or 0)
                req = int(data.get("requested_horizon_days") or hd)
                if hd:
                    if data.get("horizon_capped") or req > hd:
                        constraint = (
                            f"HORIZON CAP: the user asked for {req:,} days, but "
                            f"this analysis is only honest up to {hd:,} days. The "
                            f"outlook applies to {hd:,} days, NOT to {req:,} days. "
                            f"State this cap clearly.")
                    else:
                        constraint = (
                            f"ANALYSIS HORIZON: {hd:,} days. Do not describe the "
                            f"outlook as covering a different horizon.")
            synth = swarm.synthesize(
                question, intent.kind, res.get("text", ""), evidence,
                depth=depth,
                base_confidence=float(res.get("confidence", 0.5)),
                on_stage=on_stage, constraint=constraint)
            council = synth.get("summary") or {}
            if synth.get("ok"):
                replied = int(council.get("agents_replied") or 0)
                models = len(council.get("models_replied") or [])
                det_conf = float(res.get("confidence", 0.3))
                council_conf = float(synth.get("confidence") or 0.0)
                if intent.kind == "baby_name":
                    # The shortlist itself is the deliverable. Keep it intact
                    # and append the council's cross-check instead of replacing.
                    res["detail"] = res.get("text", "")
                    res["text"] = (res.get("text", "").rstrip() +
                                   "\n\nCouncil cross-check: " + synth["text"])
                elif intent.kind.startswith("forecast"):
                    # Numbers, ranges, horizons and backtests are the verified
                    # deliverable. The council may add a cross-check, but it
                    # must never paraphrase or replace the deterministic values.
                    res["detail"] = res.get("text", "")
                    res["text"] = (res.get("text", "").rstrip() +
                                   "\n\nCouncil cross-check: " + synth["text"])
                else:
                    res["detail"] = res.get("text", "")
                    res["text"] = synth["text"]
                res["badge"] = (res.get("badge") or "") + \
                    f" + COUNCIL CHECK {replied}/{depth}"
                res["ai_used"] = True
                if res.get("ok"):
                    # The council may reduce confidence, never raise it above
                    # the deterministic evidence layer.
                    res["confidence"] = round(min(det_conf, council_conf), 3)
                else:
                    # A council answer without verified evidence is still
                    # speculation. Keep its confidence clearly below a
                    # sourced answer; generic forecasts are the strictest.
                    cap = 0.35 if intent.kind == "forecast" else 0.45
                    res["confidence"] = round(
                        min(max(det_conf, council_conf), cap), 3)
                notes.append(
                    f"AI council: {replied}/{depth} specialist agents, "
                    f"{models} model route(s), agreement "
                    f"{float(council.get('agreement') or 0):.2f}.")
                if not sources_list:
                    sources_list = ["Keyless AI council (unverified synthesis)"]
                    notes.append("AI ne general knowledge se jawab diya — koi "
                                 "live source verify nahi hua.")
                for n in (synth.get("notes") or [])[:4]:
                    if n and n not in notes:
                        notes.append(n)
            else:
                notes.extend((synth.get("notes") or [])[:3])
                notes.append("AI council unavailable — verified/deterministic "
                             "answer shown.")
                if not res.get("ok") and not res.get("text"):
                    res["text"] = (
                        "Mujhe is sawal ka verified jawab nahi mila, aur AI "
                        "council bhi abhi offline hai. Facts invent nahi karunga. "
                        "Dobara try karein ya zyada specific sawal poochein.")
                    res["badge"] = "NO-DATA"
                    res["confidence"] = min(res.get("confidence", 0.2), 0.2)
        elif not res.get("ok") and not res.get("text"):
            res["text"] = "Is sawal ka jawab abhi nahi mila."
            res["badge"] = "NO-DATA"

        # ------------------------------------------------------ prophecy/probe
        prophecy = res.get("prophecy")
        pid = probe_id = None
        if prophecy:
            try:
                pid = self.oracle.register(
                    question=question, answer=prophecy["answer"],
                    confidence=float(res.get("confidence", 0.5)),
                    badge=res.get("badge", "FORECAST"),
                    due=prophecy["due"], meta=prophecy.get("meta") or {},
                    engine="CHRONO", time_coord="future")
                check = prophecy.get("check")
                if check:
                    when = prophecy["due"] + "T00:00:00"
                    probe_id = self.oracle.add_probe(pid, when, check)
                    notes.append(
                        f"Paradox Ledger #{pid}: prediction registered; probe due "
                        f"{prophecy['due']}. Daily harvest truth se compare karega.")
                else:
                    notes.append(f"Paradox Ledger #{pid}: prediction registered.")
            except Exception as e:
                notes.append(f"Ledger registration failed: {type(e).__name__}: {e}")

        confidence = max(0.0, min(1.0, float(res.get("confidence", 0.3))))
        ans = ChronoAnswer(
            question=question, kind=intent.kind, answer=res.get("text", ""),
            detail=res.get("detail", ""), confidence=confidence,
            badge=res.get("badge", ""), evidence=evidence,
            data=res.get("data") or {}, sources=sources_list,
            intent=intent.to_dict(), prophecy_id=pid, probe_id=probe_id,
            ms=0, ai_used=bool(res.get("ai_used")), notes=notes,
            council=council)
        ans.ms = int((time.time() - t0) * 1000)
        if record:
            try:
                ans.answer_id = self.memory.record(question, ans.to_dict(), ans.ms)
            except Exception as e:
                ans.notes.append(f"Memory write failed: {e}")
        self._stage(on_stage, "done", {"confidence": ans.confidence,
                                       "ms": ans.ms, "badge": ans.badge})
        return ans

    def ask_with_intent(self, question: str, intent: Intent,
                        ai: bool | None = None, on_stage=None,
                        depth: int | None = None) -> ChronoAnswer:
        """Agent/chat entry point: skip routing, dispatch known slots."""
        return self.ask(question, ai=ai, on_stage=on_stage, intent=intent,
                        depth=depth)

    @staticmethod
    def _stage(cb, name: str, payload: dict):
        if cb:
            try:
                cb(name, payload)
            except Exception:
                pass

    # ------------------------------------------------------------- prompts
    def _build_prompt(self, question: str, intent: Intent, res: dict,
                      evidence: list) -> str:
        lines = []
        for e in evidence[:8]:
            if not e.get("ok"):
                continue
            lines.append(f"- [{e['source']}] {e['snippet']}")
        evidence_txt = "\n".join(lines) if lines else "(no live evidence)"
        if intent.kind == "forecast":
            task = (
                "Yeh ek FUTURE/SPECULATIVE sawal hai. Neeche diye evidence aur "
                "verified facts ki roshni me Roman Urdu me 3-5 sentence ka cautious "
                "analysis do. Facts aur guess ko alag rakho. Koi number ya event "
                "invent mat karo. Agar evidence kaafi nahi, saaf likho ke prediction "
                "advisory hai, guarantee nahi. Aakhir me ek line: 'Yeh speculative "
                "analysis hai.'")
        elif intent.kind == "news":
            task = (
                "Neeche diye headlines ko Roman Urdu me 2-3 short bullets me summarize "
                "karo. Sirf headlines ka content use karo; naya news invent mat karo.")
        elif intent.kind == "country":
            task = (
                "Neeche diye country facts ko Roman Urdu me 2-3 sentences me explain "
                "karo. Numbers exactly waise hi rakho.")
        else:
            task = (
                "Neeche diya verified jawab (English ho sakta hai) Roman Urdu/Hinglish "
                "me 2-4 short sentences me samjhao. Saare numbers, dates aur names "
                "exactly waise rakho. Koi nayi information invent mat karo. Source "
                "names ka short zikr karo.")
        return (
            f"Sawal: {question}\n"
            f"Detected intent: {intent.kind}\n"
            f"Verified answer / facts:\n{shorten(res.get('text', ''), 1600)}\n\n"
            f"Evidence:\n{evidence_txt}\n\n{task}"
        )

    # ------------------------------------------------------------ dispatch
    def _dispatch(self, question: str, it: Intent, on_stage=None) -> dict:
        k = it.kind
        s = it.slots
        q = question.lower()

        if k == "help":
            txt = (
                "Main ChronoVault 2.2 hoon — ek keyless, local time machine jo "
                "past (Vault), present (live sources) aur future (forecast + probe) "
                "teenon se kaam karti hai. Kya kar sakta hoon:\n"
                "• Exact: \"1 Jan 2050 konsa din?\", \"2050 tak kitne din?\", "
                "\"100000 @18% 5 saal compound\", \"50 lakh ka 12% EMI\"\n"
                "• Live: \"Lahore ka mausam\", \"USD to PKR\", \"Bitcoin price\", "
                "\"Lahore me abhi time\"\n"
                "• Future: \"USD/PKR 30 din baad kitna hoga?\", \"Bitcoin 2027 me "
                "kitna hoga?\", \"Pakistan ka future kya hoga?\"\n"
                "• Knowledge: \"time travel kya hai?\", \"Einstein kaun tha?\"\n"
                "• News/space: \"latest AI news\", \"ISS kahan hai\", \"aaj ke "
                "earthquakes\"\n"
                "• Time capsule: \"time capsule banao: future ke liye message, "
                "1 saal baad kholna\"\n"
                "• Council: har AI jawab keyless specialist agents ki council se "
                "cross-check hota hai (default 9, full 50: \"/deep <sawal>\").\n"
                "Har future prediction Paradox Ledger me register hoti hai aur "
                "due date par probe asli truth se compare karta hai.")
            return _mk(txt, {"examples": [
                "1 Jan 2050 konsa din?", "USD to PKR", "Bitcoin 90 din baad",
                "Lahore ka mausam", "time travel kya hai?",
            ]}, confidence=1.0, badge="INFO")
        if k == "identity":
            return _mk(
                f"Main ChronoVault 2.2 hoon — aapke PC par chalne wali keyless "
                f"time machine. Main {self.reg.total:,} public endpoints se "
                f"present data leta hoon, exact math karta hoon, 70 specialist "
                f"AI roles ki council se jawab cross-check karta hoon, aur future "
                f"predictions ko Paradox Ledger me register karke baad me verify "
                f"karta hoon. Asli time travel possible nahi hai — jo main karta "
                f"hoon woh verified retrieval + statistical forecasting hai, aur "
                f"main isay saaf label karta hoon.",
                {"version": "2.2", "endpoints": self.reg.total,
                 "council_roles": len(swarm.ROLES)},
                confidence=1.0, badge="INFO")
        if k == "smalltalk":
            return _mk("Salam! Main ChronoVault 2.2 hoon. Kisi bhi waqt, file, "
                       "rate, mausam, knowledge ya future prediction ke bare me "
                       "poochein — deterministic facts aur AI council ke saath "
                       "jawab dunga.",
                       confidence=1.0, badge="INFO")
        if k == "system":
            h = net.health_summary()
            o = self.oracle.stats()
            m = self.memory.stats()
            by_cat = self.reg.stats()["categories"]
            txt = (
                f"ChronoVault 2.2 system report:\n"
                f"• Registry: {self.reg.total:,} keyless endpoints "
                f"({len(by_cat)} categories)\n"
                f"• AI council: {len(swarm.ROLES)} specialist roles, "
                f"{len(swarm.STATIC_ROUTES)} known model routes\n"
                f"• Provider health: {h['alive']} endpoints ne successfully jawab diya; "
                f"{h['requests_ok']} OK / {h['requests_fail']} fail\n"
                f"• Oracle: {o.get('prophecies', 0)} prophecies, "
                f"{o.get('pending', 0)} pending\n"
                f"• Memory: {m['answers']} answers ({m['today']} today)\n"
                f"• Policy: no API keys, no telemetry, local-first.")
            return _mk(txt, {"registry": self.reg.stats(), "health": {
                "alive": h["alive"], "ok": h["requests_ok"],
                "fail": h["requests_fail"], "success_rate": h["success_rate"]},
                "oracle": o, "memory": m}, confidence=1.0, badge="SYSTEM")

        if k == "capsule":
            msg = (s.get("message") or "").strip()
            if not msg:
                return _mk("Time capsule ke liye message bhi likhein, e.g. "
                           "\"time capsule banao: 2027 me khud ko yaad rakhna ke "
                           "mushkil waqt guzar jayega — 1 saal baad kholna\".",
                           confidence=1.0, badge="NEED-INPUT")
            days = int(s.get("days") or 365)
            open_date = (formulas.today() + timedelta(days=days)).isoformat()
            cid = self.oracle.seal_capsule(open_date, msg)
            txt = (f"Time capsule #{cid} seal ho gaya.\n"
                   f"Message: \"{shorten(msg, 180)}\"\n"
                   f"Khulega: {open_date} ({days} din baad). Tab tak yeh encrypted "
                   f"nahi, sirf sealed hai — local Oracle database me.")
            return _mk(txt, {"capsule_id": cid, "open_date": open_date,
                             "message": msg, "days": days},
                       confidence=1.0, badge="SEALED")

        if k == "math":
            return _mk(s.get("text", ""), {
                "expression": s.get("expression"),
                "result": s.get("result"),
                "text": s.get("text")
            }, confidence=0.999, badge="EXACT-MATH")

        if k == "baby_name":
            slots = {
                "gender": (s.get("gender") or "").strip().lower(),
                "surname": (s.get("surname") or "").strip(),
                "culture": (s.get("culture") or "").strip().lower(),
                "style": (s.get("style") or "").strip().lower(),
            }
            missing = []
            if not slots["gender"]:
                missing.append("gender")
            if not slots["surname"]:
                missing.append("surname")
            if not slots["culture"]:
                missing.append("culture")
            if missing:
                return _mk(
                    "Naam shortlist banane ke liye 3 details chahiye: "
                    + ", ".join(missing) + ". Chat me \"mere bache ka naam "
                    "kya hoga?\" poochein — main step by step poochh lunga.",
                    {"missing": missing, "slots": slots},
                    confidence=1.0, badge="NEED-INPUT")
            result = babynames.suggest(
                gender=slots["gender"], surname=slots["surname"],
                culture=slots["culture"] or "urdu",
                style=slots["style"] or "any")
            return _mk(
                babynames.to_text(result), result, confidence=0.62,
                badge="SPECULATIVE",
                notes=["Yeh cultural/phonetic shortlist hai, guaranteed future "
                       "prediction nahi. Asli naam aap decide karenge."])

        if k == "date":
            if not s.get("date"):
                return _mk("Kaunsi tareekh? Misal: \"1 Jan 2050 konsa din?\"",
                           confidence=1.0, badge="NEED-INPUT")
            d = date.fromisoformat(s["date"])
            w = formulas.weekday_answer(d)
            return _mk(w["text"], w, confidence=0.999, badge="EXACT-MATH")

        if k == "countdown":
            if not s.get("date"):
                return _mk("Kis tareekh tak ka countdown chahiye? Misal: "
                           "\"2050-01-01 tak kitne din?\"", confidence=1.0,
                           badge="NEED-INPUT")
            c = formulas.countdown(date.fromisoformat(s["date"]))
            return _mk(c["text"], c, confidence=0.999, badge="EXACT-MATH")

        if k == "interest":
            p, r, y = s.get("principal", 0), s.get("rate", 0), s.get("years", 0)
            if not p or not r or not y:
                return _mk("Compound/simple interest ke liye principal, rate aur "
                           "duration chahiye — misal: \"100000 @18% 5 saal compound\" "
                           f"(mujhe mila: principal={p}, rate={r}%, years={y}).",
                           confidence=1.0, badge="NEED-INPUT")
            if "simple" in q or "sada" in q:
                d = formulas.simple_interest(p, r, y)
            else:
                d = formulas.compound(p, r, y, int(s.get("per_year") or 12))
            return _mk(d["text"], d, confidence=0.999, badge="EXACT-MATH")

        if k == "emi":
            p, r, y = s.get("principal", 0), s.get("rate", 0), s.get("years", 0)
            if not p or not r or not y:
                return _mk("EMI ke liye loan amount, annual rate aur duration "
                           "chahiye — misal: \"50 lakh ka loan 12% 5 saal EMI\" "
                           f"(mujhe mila: principal={p}, rate={r}%, years={y}).",
                           confidence=1.0, badge="NEED-INPUT")
            d = formulas.emi(p, r, y)
            return _mk(d["text"], d, confidence=0.999, badge="EXACT-MATH")

        if k in ("fx", "forecast_fx"):
            base, quote = s.get("from", "USD"), s.get("to", "PKR")
            amount = float(s.get("amount") or 1)
            self._stage(on_stage, "source", {"name": f"FX {base}/{quote}"})
            cur = sources.fx_rate(base, quote, amount, self.reg)
            if k == "fx" or not cur.get("ok"):
                return cur
            requested = max(1, int(s.get("horizon_days") or 30))
            self._stage(on_stage, "source", {"name": f"{base}/{quote} history"})
            series = sources.fx_series(base, quote, max(120, min(365, requested * 3)),
                                       self.reg)
            f = forecast(series, requested)
            if not f:
                txt = cur["text"] + ("\n\nIs pair ki history nahi mili, is liye "
                                     "forecast nahi de sakta — sirf aaj ka rate "
                                     "verified hai.")
                return _mk(txt, cur["data"], cur["evidence"],
                           confidence=cur["confidence"], badge="LIVE")
            horizon = int(f["horizon_days"])
            target = None if f.get("horizon_capped") else s.get("target")
            target = target or (formulas.today() + timedelta(days=horizon)).isoformat()
            unit = quote
            ftxt = to_text(f"{base}/{quote}", f, unit)
            txt = cur["text"] + "\n\n" + ftxt
            conf = round(cur["confidence"] * 0.4 + f["confidence"] * 0.6, 3)
            tol = max(2.0, min(25.0, f.get("band_pct") or 5))
            check = {"kind": "fx_rate", "base": base, "currency": quote,
                     "expect": f["predicted"], "tol_pct": round(tol, 1)}
            prophecy = {
                "answer": (f"{base}/{quote} {horizon}d forecast: {f['predicted']} "
                           f"(range {f['lo']}–{f['hi']}, conf {f['confidence']})"),
                "due": target, "meta": {"spot": cur["data"], "forecast": f},
                "check": check,
            }
            return _mk(txt, {**cur["data"], "forecast": f,
                             "series_points": len(series)},
                       cur["evidence"], confidence=conf,
                       badge="FORECAST + LIVE", prophecy=prophecy)

        if k in ("crypto", "forecast_crypto"):
            coin, sym = s.get("coin", "bitcoin"), s.get("symbol", "BTC")
            amount = float(s.get("amount") or 1)
            self._stage(on_stage, "source", {"name": f"{sym} price"})
            cur = sources.crypto_price(coin, sym, amount, self.reg)
            if k == "crypto" or not cur.get("ok"):
                return cur
            requested = max(1, int(s.get("horizon_days") or 90))
            self._stage(on_stage, "source", {"name": f"{sym} history"})
            series = sources.crypto_series(coin, max(90, min(365, requested * 3)),
                                           self.reg)
            f = forecast(series, requested)
            if not f:
                txt = cur["text"] + ("\n\nIs coin ki history nahi mili, is liye "
                                     "forecast nahi de sakta — sirf aaj ka price "
                                     "verified hai.")
                return _mk(txt, cur["data"], cur["evidence"],
                           confidence=cur["confidence"], badge="LIVE")
            horizon = int(f["horizon_days"])
            target = None if f.get("horizon_capped") else s.get("target")
            target = target or (formulas.today() + timedelta(days=horizon)).isoformat()
            ftxt = to_text(f"{sym}/USD", f, "USD")
            txt = cur["text"] + "\n\n" + ftxt
            conf = round(cur["confidence"] * 0.4 + f["confidence"] * 0.6, 3)
            tol = max(3.0, min(30.0, f.get("band_pct") or 8))
            check = {"kind": "crypto_usd", "coin": coin, "symbol": sym,
                     "expect": f["predicted"], "tol_pct": round(tol, 1)}
            prophecy = {
                "answer": (f"{sym}/USD {horizon}d forecast: ${f['predicted']:,} "
                           f"(range ${f['lo']:,}–${f['hi']:,}, conf {f['confidence']})"),
                "due": target, "meta": {"spot": cur["data"], "forecast": f},
                "check": check,
            }
            return _mk(txt, {**cur["data"], "forecast": f,
                             "series_points": len(series)},
                       cur["evidence"], confidence=conf,
                       badge="FORECAST + LIVE", prophecy=prophecy)

        if k == "weather":
            self._stage(on_stage, "source", {"name": "weather"})
            return sources.weather(s.get("city", DEFAULT_CITY), s.get("lat", 31.55),
                                   s.get("lon", 74.34), int(s.get("days") or 1),
                                   self.reg)

        if k == "time":
            label = s.get("city") or s.get("zone", "UTC")
            self._stage(on_stage, "source", {"name": f"time {label}"})
            return sources.time_now(s.get("zone", "UTC"), label, self.reg)

        if k == "holiday":
            self._stage(on_stage, "source", {"name": "holidays"})
            return sources.holidays(s.get("country", "PK"), int(s.get("year") or formulas.today().year),
                                    self.reg)

        if k == "country":
            cc, query = s.get("country"), s.get("query") or ""
            if not cc and not query:
                return _mk("Kis mulk ke bare me? Misal: \"Japan ki capital kya hai?\"",
                           confidence=1.0, badge="NEED-INPUT")
            self._stage(on_stage, "source", {"name": "country"})
            return sources.country_info(cc, query, self.reg)

        if k == "news":
            self._stage(on_stage, "source", {"name": "news"})
            return sources.news(s.get("query") or "", self.reg)

        if k == "space":
            self._stage(on_stage, "source", {"name": s.get("space", "iss")})
            return sources.space(s.get("space", "iss"), self.reg)

        if k == "forecast":
            query = s.get("query") or question
            self._stage(on_stage, "source", {"name": "knowledge + news"})
            with cf.ThreadPoolExecutor(max_workers=2) as ex:
                fk = ex.submit(sources.knowledge, query, self.reg)
                fn = ex.submit(sources.news, query, self.reg)
                kb = fk.result()
                nb = fn.result()
            ev = []
            facts = ""
            if kb.get("ok"):
                ev.extend(kb.get("evidence") or [])
                facts = kb.get("text") or ""
            heads = ""
            if nb.get("ok"):
                ev.extend(nb.get("evidence") or [])
                heads = nb.get("text") or ""
            requested = max(1, int(s.get("horizon_days") or 30))
            horizon = min(MAX_HORIZON_DAYS, requested)
            capped = requested > horizon
            txt = (f"Yeh ek speculative future sawal hai — iska koi deterministic "
                   f"jawab nahi aur koi guaranteed number/ranking nahi. Main "
                   f"{horizon:,} din ke horizon ke liye verified facts + current "
                   f"signals de raha hoon.\n\n")
            if capped:
                txt += (f"Aap ne {requested:,} din maange the; is analysis ka "
                        f"honest horizon {horizon:,} din (~10 saal) hai. "
                        f"Neeche diya gaya outlook {horizon:,} din ka hai, "
                        f"{requested:,} din ka nahi.\n\n")
            if facts:
                txt += "Verified background:\n" + shorten(facts, 900) + "\n\n"
            if heads:
                txt += "Current signals:\n" + shorten(heads, 700) + "\n\n"
            if not heads and (nb.get("data") or {}).get("checked"):
                txt += ("News check: is topic se match karti koi recent headline "
                        "nahi mili, is liye unrelated news ko signal nahi banaya "
                        "gaya.\n\n")
            if not facts and not heads:
                txt += ("Mujhe is topic par abhi koi verified source nahi mila, "
                        "is liye main sirf guess nahi karunga. Numeric cheezon "
                        "(FX, crypto, weather, dates) ke liye main proper forecast "
                        "model de sakta hoon.\n")
            txt += "Yeh speculative analysis hai."
            conf = 0.38 if (facts or heads) else 0.18
            return _mk(txt, {"query": query, "horizon_days": horizon,
                             "requested_horizon_days": requested,
                             "horizon_capped": capped,
                             "background": kb.get("data"), "news": nb.get("data")},
                       ev, confidence=conf, badge="SPECULATIVE",
                       ok=bool(facts or heads), force_llm=True)

        # ---------------------------------------------------------- knowledge
        query = s.get("query") or question
        self._stage(on_stage, "source", {"name": "wikipedia/ddg/papers"})
        kb = sources.knowledge(query, self.reg)
        if kb.get("ok"):
            txt = "Verified sources ke mutabiq:\n" + kb["text"]
            return _mk(txt, kb.get("data"), kb.get("evidence"),
                       confidence=kb.get("confidence", 0.75),
                       badge=kb.get("badge", "ARCHIVE"))
        return _mk("Live knowledge sources se is sawal ka verified jawab nahi "
                   "mila. AI layer se general answer try kar raha hoon — woh "
                   "unverified hoga.", {"query": query}, kb.get("evidence"),
                   confidence=0.2, badge="UNVERIFIED-AI", ok=False,
                   force_llm=True)
