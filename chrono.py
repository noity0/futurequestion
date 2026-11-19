#!/usr/bin/env python3
"""ChronoVault 2.2.0 — command line time machine.

Examples:
    python chrono.py ask "USD/PKR 30 din baad kitna hoga?"
    python chrono.py ask "Lahore ka mausam" --detail
    python chrono.py cockpit
    python chrono.py status
    python chrono.py registry bitcoin
    python chrono.py probes run
    python chrono.py capsule "2027 me khud ko yaad rakhna" --days 365
    python chrono.py selftest --online
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "engine"))

from chronovault import VERSION, net, swarm  # noqa: E402
from chronovault.ask import Chrono  # noqa: E402
from chronovault.chat import ChatAgent  # noqa: E402
from chronovault.memory import Memory  # noqa: E402
from chronovault.oracle import Oracle  # noqa: E402
from chronovault.paths import DB_PATH, LEDGER_PATH, REGISTRY_PATH  # noqa: E402
from chronovault.registry import Registry  # noqa: E402
from chronovault import probes as probe_mod  # noqa: E402

_TTY = sys.stdout.isatty()
C = {
    "reset": "\033[0m" if _TTY else "",
    "dim": "\033[2m" if _TTY else "",
    "bold": "\033[1m" if _TTY else "",
    "cyan": "\033[96m" if _TTY else "",
    "green": "\033[92m" if _TTY else "",
    "yellow": "\033[93m" if _TTY else "",
    "red": "\033[91m" if _TTY else "",
    "violet": "\033[95m" if _TTY else "",
    "blue": "\033[94m" if _TTY else "",
}


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def paint(text: str, color: str) -> str:
    return f"{C.get(color, '')}{text}{C['reset']}"


def rule(char: str = "-", width: int = 76) -> str:
    return paint(char * width, "dim")


def print_badge(badge: str) -> str:
    b = (badge or "").upper()
    color = "green" if "EXACT" in b else \
        "cyan" if "CONSENSUS" in b else \
        "blue" if "LIVE" in b else \
        "yellow" if "FORECAST" in b else \
        "violet" if "SPEC" in b else \
        "red" if ("NO-DATA" in b or "ERROR" in b) else "dim"
    return paint(f"[{badge or 'UNKNOWN'}]", color)


def print_answer(ans, detail: bool = False, show_data: bool = False) -> None:
    print()
    print(paint("┌─ CHRONOVAULT 2.2 ", "cyan") + rule("─", 56)[1:])
    print(f"  {paint('Sawal:', 'dim')} {ans.question}")
    print(f"  {print_badge(ans.badge)}  "
          f"confidence {paint(f'{ans.confidence * 100:.0f}%', 'bold')}  "
          f"{paint(f'{ans.ms} ms', 'dim')}"
          f"{'  ' + paint('AI-SYNTHESIS', 'violet') if ans.ai_used else ''}")
    print(rule())
    try:
        cols = os.get_terminal_size().columns
    except OSError:
        cols = 92
    width = min(96, max(60, cols - 4))
    for para in (ans.answer or "").split("\n"):
        if para.strip():
            print(textwrap.fill(para, width=width))
        else:
            print()
    if ans.sources:
        print()
        print(f"  {paint('Sources:', 'dim')} " + ", ".join(ans.sources))
    if ans.council:
        c = ans.council
        print(f"  {paint('Council:', 'dim')} "
              f"{c.get('agents_replied', 0)}/{c.get('agents_requested', 0)} agents, "
              f"{len(c.get('models_replied') or [])} models, "
              f"agreement {float(c.get('agreement') or 0):.2f}")
    if ans.prophecy_id:
        print(f"  {paint('Paradox Ledger:', 'dim')} prophecy #{ans.prophecy_id}"
              + (f", probe #{ans.probe_id}" if ans.probe_id else ""))
    if ans.answer_id:
        print(f"  {paint('Memory:', 'dim')} answer #{ans.answer_id}")
    if ans.notes:
        print()
        for note in ans.notes:
            print("  " + paint("•", "dim") + " " + paint(note, "dim"))
    if detail and ans.evidence:
        print()
        print(paint("  Evidence", "bold"))
        for e in ans.evidence:
            mark = paint("OK ", "green") if e.get("ok") else paint("ERR", "red")
            flags = []
            if e.get("cached"):
                flags.append("cached")
            if e.get("tls_unverified"):
                flags.append("tls-unverified")
            extra = (" · " + ", ".join(flags)) if flags else ""
            print(f"  {mark} {e.get('source', '?'):<24} {e.get('ms', 0):>5}ms{extra}")
            if e.get("snippet"):
                print("      " + paint(textwrap.shorten(str(e["snippet"]), 300), "dim"))
    if show_data and ans.data:
        print()
        print(paint("  Structured data", "bold"))
        print(json.dumps(ans.data, ensure_ascii=False, indent=2)[:4000])


def _stage_printer(enabled: bool):
    def cb(name: str, payload: dict) -> None:
        if not enabled:
            return
        labels = {
            "plan": "Routing the question",
            "source": f"Opening live source: {payload.get('name', '')}",
            "council": (f"Convening {payload.get('agents', '?')}-agent AI council"),
            "probe": (f"Checking {payload.get('routes', '?')} live model route(s)"),
            "panel": (f"Council panel: {payload.get('agents', '?')} agents, "
                      f"{payload.get('models', '?')} models"),
            "agent": (f"  · {payload.get('role', 'agent')} "
                      f"[{payload.get('model', 'model')}] "
                      f"{'ok' if payload.get('ok') else 'skipped'}"),
            "judge": f"Judge synthesis [{payload.get('model', 'model')}]",
            "synthesize": "Folding evidence into Roman Urdu",
            "done": "Closing the time fold",
        }
        label = labels.get(name, name)
        print(paint(f"  ◌ {label}", "dim"), file=sys.stderr, flush=True)
    return cb


# ------------------------------------------------------------------ commands
def cmd_ask(args) -> int:
    question = " ".join(args.question).strip()
    if not question:
        print("Sawal likhein. Misal: python chrono.py ask \"USD to PKR\"", file=sys.stderr)
        return 2
    chrono = Chrono(use_llm=not args.no_ai, depth=args.depth)
    ans = chrono.ask(question, ai=not args.no_ai, depth=args.depth,
                     on_stage=_stage_printer(args.stages and not args.json))
    if args.json:
        print(json.dumps(ans.to_dict(), ensure_ascii=False, indent=2))
    else:
        print_answer(ans, detail=args.detail, show_data=args.data)
    return 0 if ans.confidence > 0 else 1


def cmd_cockpit(args) -> int:
    from chronovault.serve import run
    return run(port=args.port, open_browser=not args.no_browser,
               verbose=args.verbose)


def _chat_meta(answer: dict | None) -> str:
    """One honest provenance line for the conversational CLI."""
    if not answer:
        return ""
    badge = str(answer.get("badge") or "")
    bits = [badge] if badge else []
    conf = answer.get("confidence")
    if conf is not None and not any(t in badge for t in
                                    ("INFO", "SYSTEM", "NEED-INPUT")):
        bits.append(f"{round(float(conf) * 100)}% confidence")
    council = answer.get("council") or {}
    if council.get("agents_replied") is not None:
        bits.append(
            f"council check {council.get('agents_replied')}/"
            f"{council.get('agents_requested') or '?'}")
    srcs = [str(s) for s in (answer.get("sources") or []) if s]
    if srcs:
        shown = ", ".join(srcs[:4]) + (" +…" if len(srcs) > 4 else "")
        bits.append("sources: " + shown)
    return " · ".join(bits)


def cmd_chat(args) -> int:
    """Conversational agent: asks for missing details, then answers."""
    agent = ChatAgent(depth=args.depth)
    sid = args.session or None
    if args.message:
        reply = agent.handle(" ".join(args.message).strip(), session_id=sid,
                             ai=not args.no_ai, depth=args.depth)
        if args.json:
            print(json.dumps(reply.to_dict(), ensure_ascii=False, indent=2))
        else:
            print()
            print(reply.reply)
            if reply.state == "asking" and reply.quick_replies:
                print(paint("  " + " · ".join(reply.quick_replies), "dim"))
            meta = _chat_meta(reply.answer)
            if meta:
                print(paint("  " + meta, "dim"))
            print(paint(f"  session {reply.session_id} · {reply.state}"
                        + (f" · waiting for {reply.pending}"
                           if reply.pending else ""), "dim"))
        return 0

    print()
    print(paint("  CHRONOVAULT 2.2 · FUTURE AGENT", "cyan"))
    print(rule())
    print(paint("  Kuch bhi poochein. Missing details main step-by-step poochh "
                "lunga.", "dim"))
    print(paint("  /deep <sawal> = 50-agent council · /reset · /exit", "dim"))
    print(rule())
    while True:
        try:
            text = input(paint("  you  › ", "green")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("/exit", "exit", "quit", "band"):
            break
        if text.lower() in ("/reset", "reset", "naya sawal"):
            if sid:
                agent.reset(sid)
            print(paint("  agent › Naya sawal shuru. Kya jaanna hai?", "cyan"))
            continue
        try:
            reply = agent.handle(text, session_id=sid, ai=not args.no_ai,
                                 depth=args.depth)
        except Exception as e:
            print(paint(f"  error: {type(e).__name__}: {e}", "red"))
            continue
        sid = reply.session_id
        print()
        print(paint("  agent › ", "cyan") + reply.reply.replace("\n", "\n  "))
        if reply.state == "asking" and reply.quick_replies:
            print(paint("  " + " · ".join(reply.quick_replies), "dim"))
        meta = _chat_meta(reply.answer)
        if meta:
            print(paint("  " + meta, "dim"))
        print()
    return 0


def cmd_swarm(args) -> int:
    """Show the keyless AI council: roles, live routes, dormant providers."""
    if args.json:
        st = swarm.probe(force=args.force)
        print(json.dumps({"ok": True, "catalog": swarm.roles(), **st},
                         ensure_ascii=False, indent=2))
        return 0
    print()
    print(paint("  CHRONOVAULT 2.2 · KEYLESS AI COUNCIL", "cyan"))
    print(rule())
    print(swarm.status_text())
    print(rule())
    print(paint("  Roles:", "dim") + " " +
          ", ".join(r["name"] for r in swarm.roles()[:12]) + ", ...")
    print(paint("  Full council:", "dim") +
          " python chrono.py ask \"...\" --depth 50  (or /deep in chat)")
    print(paint("  No API key is required. Keyed providers stay off unless",
                "dim"))
    print(paint("  CHRONOVAULT_ALLOW_KEYS=1 is set explicitly; deterministic",
                "dim"))
    print(paint("  facts always outrank AI synthesis.", "dim"))
    return 0


def cmd_status(args) -> int:
    reg = Registry()
    mem = Memory().stats()
    oracle = Oracle()
    health = net.health_summary()
    tasks = probe_mod.task_status()
    st = oracle.stats()
    print()
    print(paint("  CHRONOVAULT 2.2 · SYSTEM STATUS", "cyan"))
    print(rule())
    print(f"  Registry      {reg.total:,} keyless endpoints, "
          f"{len(reg.stats()['categories'])} categories")
    print(f"  AI council    {len(swarm.ROLES)} specialist roles, "
          f"{len(swarm.STATIC_ROUTES)} known model routes "
          f"(default depth {swarm.DEFAULT_DEPTH}, max 50)")
    print(f"  Registry file {REGISTRY_PATH}")
    print(f"  Memory        {mem['answers']} answers ({mem['today']} today), "
          f"avg confidence {mem['avg_confidence']}")
    print(f"  Oracle        {st.get('prophecies', 0)} prophecies, "
          f"{st.get('pending', 0)} pending, "
          f"{st.get('probes', {}).get('scheduled', 0)} probes scheduled")
    print(f"  Providers     {health['alive']} alive · "
          f"{health['requests_ok']} OK / {health['requests_fail']} fail · "
          f"success {health['success_rate']}")
    print(f"  Cache DB      {DB_PATH}")
    print(f"  Ledger        {LEDGER_PATH}")
    for t in tasks:
        print(f"  Task          {t.get('TaskName')}: {t.get('State')}")
    print(rule())
    print(paint("  No API keys. No telemetry. Local-first.", "dim"))
    return 0


def cmd_registry(args) -> int:
    reg = Registry()
    rows = reg.search(args.query or "", args.category or "", args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print()
    print(f"  {reg.total:,} endpoints · showing {len(rows)}"
          + (f" for '{args.query}'" if args.query else "")
          + (f" in {args.category}" if args.category else ""))
    print(rule())
    for e in rows:
        print(f"  {paint(e['id'], 'cyan'):<40} {e['category']:<11} "
              f"rel {e.get('reliability', 0):.2f}")
        print("    " + paint(textwrap.shorten(e["url"], 110), "dim"))
    return 0


def cmd_probes(args) -> int:
    action = args.action or "run"
    if action == "schedule":
        r = probe_mod.schedule_daily()
        print(("OK: " if r.get("ok") else "FAIL: ")
              + str(r.get("output") or r.get("error")))
        return 0 if r.get("ok") else 1
    if action == "status":
        for t in probe_mod.task_status():
            print(f"{t.get('TaskName')}: {t.get('State')}")
        for p in Oracle().ledger.probes():
            print(f"probe #{p['id']} prophecy #{p['prophecy_id']} "
                  f"{p.get('when_iso')} {p.get('status')}")
        return 0
    oracle = Oracle()
    res = probe_mod.harvest_due(oracle)
    if not res:
        print("Koi due probe nahi hai. Future predictions abhi pending hain.")
    for r in res:
        state = paint("FULFILLED", "green") if r["ok"] else paint("VIOLATED", "red")
        print(f"{state} probe #{r['probe_id']} → {r['truth']}")
    st = oracle.stats()
    print(f"\nProphecies: {st.get('prophecies')} | pending: {st.get('pending')}")
    return 0


def cmd_forecast(args) -> int:
    target = args.target.strip()
    days = int(args.days)
    if not target:
        print("Target likhein, misal: USD/PKR ya BTC", file=sys.stderr)
        return 2
    if "/" in target:
        q = f"{target} {days} din baad kitna hoga?"
    else:
        q = f"{target} {days} din baad kitna hoga?"
    chrono = Chrono(use_llm=False)
    ans = chrono.ask(q, ai=False, on_stage=_stage_printer(True))
    print_answer(ans, detail=args.detail, show_data=args.data)
    return 0


def cmd_capsule(args) -> int:
    from datetime import date, timedelta
    msg = " ".join(args.message).strip()
    if not msg:
        print("Capsule ke liye message likhein.", file=sys.stderr)
        return 2
    days = max(1, int(args.days))
    open_date = (date.today() + timedelta(days=days)).isoformat()
    cid = Oracle().seal_capsule(open_date, msg)
    print(f"Capsule #{cid} seal ho gaya.")
    print(f"Khulega: {open_date} ({days} din baad).")
    print("Note: yeh local database me sealed hai — encrypted nahi.")
    return 0


def cmd_capsules(args) -> int:
    from datetime import date
    rows = Oracle().capsules(include_sealed=True)
    if not rows:
        print("Abhi koi capsule nahi hai. Banao: python chrono.py capsule \"message\" --days 365")
        return 0
    today = date.today().isoformat()
    for c in rows:
        state = "OPEN" if c.get("open_date", "") <= today else "SEALED"
        print(f"#{c['id']} [{state}] opens {c['open_date']} — {c['message'][:90]}")
    return 0


def cmd_history(args) -> int:
    rows = Memory().history(args.limit)
    if not rows:
        print("Abhi koi answer history nahi hai.")
        return 0
    for r in rows:
        print(f"#{r['id']:<4} {r['ts'][:19]}  {print_badge(r['badge'])} "
              f"{r['confidence'] * 100:3.0f}%  {r['question'][:70]}")
    return 0


def cmd_selftest(args) -> int:
    import unittest
    test_dir = os.path.join(os.path.dirname(__file__), "engine", "chronovault", "tests")
    suite = unittest.defaultTestLoader.discover(test_dir, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    ok = result.wasSuccessful()
    if args.online:
        print("\n" + rule())
        print("  ONLINE SMOKE TESTS")
        print(rule())
        from chronovault import sources
        checks = [
            ("time", lambda: sources.time_now("Asia/Karachi", "Lahore")),
            ("fx", lambda: sources.fx_rate("USD", "PKR")),
            ("weather", lambda: sources.weather("Lahore", 31.5497, 74.3436)),
            ("crypto", lambda: sources.crypto_price("bitcoin", "BTC")),
            ("knowledge", lambda: sources.knowledge("time travel")),
            ("space", lambda: sources.space("iss")),
            ("llm", lambda: sources.llm("Say as-salamu alaykum in Roman Urdu, 1 short sentence.")),
        ]
        for name, fn in checks:
            t0 = time.time()
            try:
                b = fn()
                good = bool(b.get("ok"))
                print(f"  {'PASS' if good else 'FAIL'}  {name:<10} "
                      f"{int((time.time() - t0) * 1000):>6}ms  {b.get('badge', '')}")
                if not good:
                    ok = False
            except Exception as e:
                ok = False
                print(f"  FAIL  {name:<10} {type(e).__name__}: {e}")
    print("\n" + ("SELFTEST PASSED" if ok else "SELFTEST FAILED"))
    return 0 if ok else 1


def cmd_cache(args) -> int:
    if args.action == "clear":
        net.clear_cache()
        print("HTTP cache clear ho gaya.")
        return 0
    print("Use: python chrono.py cache clear")
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chrono",
        description="ChronoVault 2.2 - keyless local time machine "
                    "(past archives + live present + statistical future + AI council).")
    p.add_argument("--version", action="version", version=f"ChronoVault {VERSION}")

    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("ask", help="ask any question (Roman Urdu/English)")
    a.add_argument("question", nargs="+")
    a.add_argument("--no-ai", action="store_true", help="deterministic answer only")
    a.add_argument("--depth", type=int, default=swarm.DEFAULT_DEPTH,
                   help="council size: 5-50 specialist agents (default 9)")
    a.add_argument("--json", action="store_true", help="raw JSON output")
    a.add_argument("--detail", action="store_true", help="show evidence table")
    a.add_argument("--data", action="store_true", help="show structured data")
    a.add_argument("--stages", action="store_true", help="show pipeline stages")
    a.set_defaults(func=cmd_ask)

    c = sub.add_parser("cockpit", help="launch the local web cockpit")
    c.add_argument("--port", type=int, default=8765)
    c.add_argument("--no-browser", action="store_true")
    c.add_argument("--verbose", action="store_true")
    c.set_defaults(func=cmd_cockpit)

    ch = sub.add_parser("chat", help="conversational future agent (asks for details)")
    ch.add_argument("message", nargs="*")
    ch.add_argument("--session", default="", help="resume an existing session id")
    ch.add_argument("--no-ai", action="store_true", help="deterministic answer only")
    ch.add_argument("--depth", type=int, default=swarm.DEFAULT_DEPTH,
                    help="council size: 5-50 specialist agents (default 9)")
    ch.add_argument("--json", action="store_true")
    ch.set_defaults(func=cmd_chat)

    sw = sub.add_parser("swarm", help="show the keyless AI council and live routes")
    sw.add_argument("--json", action="store_true")
    sw.add_argument("--force", action="store_true", help="re-probe all providers")
    sw.set_defaults(func=cmd_swarm)

    s = sub.add_parser("status", help="system and provider status")
    s.set_defaults(func=cmd_status)

    r = sub.add_parser("registry", help="search the keyless endpoint registry")
    r.add_argument("query", nargs="?", default="")
    r.add_argument("--category", default="")
    r.add_argument("--limit", type=int, default=25)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_registry)

    pr = sub.add_parser("probes", help="harvest/verify due future predictions")
    pr.add_argument("action", nargs="?", default="run",
                    choices=["run", "status", "schedule"])
    pr.set_defaults(func=cmd_probes)

    f = sub.add_parser("forecast", help="numeric forecast, e.g. USD/PKR or BTC")
    f.add_argument("target")
    f.add_argument("--days", type=int, default=30)
    f.add_argument("--detail", action="store_true")
    f.add_argument("--data", action="store_true")
    f.set_defaults(func=cmd_forecast)

    cap = sub.add_parser("capsule", help="seal a message for your future self")
    cap.add_argument("message", nargs="+")
    cap.add_argument("--days", type=int, default=365)
    cap.set_defaults(func=cmd_capsule)

    caps = sub.add_parser("capsules", help="list time capsules")
    caps.set_defaults(func=cmd_capsules)

    h = sub.add_parser("history", help="recent answers")
    h.add_argument("--limit", type=int, default=20)
    h.set_defaults(func=cmd_history)

    st = sub.add_parser("selftest", help="offline unit tests (+ optional live smoke)")
    st.add_argument("--online", action="store_true")
    st.set_defaults(func=cmd_selftest)

    ca = sub.add_parser("cache", help="cache maintenance")
    ca.add_argument("action", nargs="?", default="clear", choices=["clear"])
    ca.set_defaults(func=cmd_cache)
    return p


def main(argv=None) -> int:
    _utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        if os.environ.get("CHRONO_DEBUG"):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
