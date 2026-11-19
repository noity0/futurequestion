"""ChronoVault 2.2 — local Time Cockpit server (stdlib only).

Binds to 127.0.0.1, serves the embedded cockpit UI, and exposes a small JSON
API. No external assets, no telemetry, no auth — it is a personal local tool.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import chat as chatmod
from . import net, probes, swarm, ui
from .ask import DEFAULT_DEPTH, Chrono, clamp_depth
from .memory import Memory
from .oracle import Oracle
from .paths import (CACHE_DIR, DB_PATH, LEDGER_PATH, REGISTRY_PATH, ROOT,
                    VERSION)
from .registry import Registry

_REG = None
_REG_LOCK = threading.Lock()
_CHAT = None
_CHAT_LOCK = threading.Lock()
MAX_BODY = 1_000_000


def registry() -> Registry:
    global _REG
    with _REG_LOCK:
        if _REG is None:
            _REG = Registry()
        return _REG


def chat_agent() -> chatmod.ChatAgent:
    global _CHAT
    with _CHAT_LOCK:
        if _CHAT is None:
            _CHAT = chatmod.ChatAgent()
        return _CHAT


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _cache_bytes() -> int:
    total = 0
    try:
        for name in os.listdir(CACHE_DIR):
            p = os.path.join(CACHE_DIR, name)
            if os.path.isfile(p):
                total += os.path.getsize(p)
    except OSError:
        pass
    return total


def status_payload() -> dict:
    reg = registry()
    health = net.health_summary()
    mem = Memory().stats()
    oracle = Oracle()
    ostats = oracle.stats()
    return {
        "app": "ChronoVault",
        "version": VERSION,
        "now": _now(),
        "root": ROOT,
        "registry": {
            "total": reg.total,
            "categories": reg.stats().get("categories", {}),
            "generated_at": reg.stats().get("generated_at"),
            "path": REGISTRY_PATH,
        },
        "memory": mem,
        "oracle": ostats,
        "health": {
            "entries": health["entries"],
            "alive": health["alive"],
            "requests_ok": health["requests_ok"],
            "requests_fail": health["requests_fail"],
            "success_rate": health["success_rate"],
        },
        "cache": {"bytes": _cache_bytes(), "db": DB_PATH},
        "ledger": LEDGER_PATH,
        "council": {
            "roles": len(swarm.ROLES),
            "core_roles": len(swarm.CORE_IDS),
            "routes_known": len(swarm.all_routes()),
            "default_depth": DEFAULT_DEPTH,
            "max_depth": 50,
        },
        "tasks": probes.task_status(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ChronoVault/2.2"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- utilities
    def log_message(self, fmt, *args):
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send(self, body: bytes, ctype: str = "application/json; charset=utf-8",
              status: int = 200, extra: dict | None = None):
        # A browser tab can close or abort at any point (Windows WinError
        # 10053/10054). That is normal client behaviour, not a server error;
        # never try to answer a dead socket or print a traceback for it.
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                OSError):
            pass

    def _json(self, obj, status: int = 200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   status=status)

    def _error(self, message: str, status: int = 400):
        self._json({"ok": False, "error": message}, status=status)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        if n > MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(n)
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"invalid JSON: {e}")
        if not isinstance(doc, dict):
            raise ValueError("JSON object expected")
        return doc

    def _query(self) -> dict:
        q = parse_qs(urlparse(self.path).query)
        return {k: v[-1] for k, v in q.items()}

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        path = urlparse(self.path).path
        q = self._query()
        try:
            if path in ("/", "/cockpit", "/index.html"):
                html = ui.render().encode("utf-8")
                self._send(html, "text/html; charset=utf-8")
                return
            if path == "/favicon.ico":
                self._send(b"", "image/x-icon", 204)
                return
            if path == "/api/ping":
                self._json({"ok": True, "app": "ChronoVault",
                            "version": VERSION, "at": time.time()})
                return
            if path == "/api/status":
                self._json(status_payload())
                return
            if path in ("/api/swarm", "/api/council"):
                st = swarm.probe(force=q.get("force") == "1")
                self._json({"ok": True, "catalog": swarm.roles(), **st})
                return
            if path == "/api/history":
                limit = max(1, min(200, int(q.get("limit", 30))))
                self._json({"items": Memory().history(limit)})
                return
            if path == "/api/answer":
                aid = int(q.get("id", "0"))
                ans = Memory().get(aid)
                if not ans:
                    self._error("answer not found", 404)
                else:
                    self._json(ans)
                return
            if path == "/api/forecasts":
                limit = max(1, min(50, int(q.get("limit", 12))))
                self._json({"items": Memory().forecasts(limit)})
                return
            if path == "/api/network":
                h = net.health_summary()
                providers = [{"id": k, **v} for k, v in h["providers"].items()]
                providers.sort(key=lambda x: -(x.get("ok", 0) + x.get("fail", 0)))
                self._json({
                    "summary": {k: v for k, v in h.items() if k != "providers"},
                    "providers": providers,
                    "cache_bytes": _cache_bytes(),
                })
                return
            if path == "/api/oracle":
                o = Oracle()
                self._json({
                    "stats": o.stats(),
                    "prophecies": o.prophecies(),
                    "probes": o.ledger.probes(),
                    "capsules": o.capsules(include_sealed=True),
                    "tasks": probes.task_status(),
                })
                return
            if path == "/api/capsules":
                self._json({"items": Oracle().capsules(include_sealed=True)})
                return
            if path == "/api/registry":
                reg = registry()
                search = q.get("q", "").strip()
                category = q.get("category", "").strip()
                limit = max(1, min(200, int(q.get("limit", 30))))
                offset = max(0, int(q.get("offset", 0)))
                rows = reg.search(search, category, limit, offset)
                self._json({
                    "total": reg.total,
                    "categories": reg.stats().get("categories", {}),
                    "count": len(rows),
                    "offset": offset,
                    "items": rows,
                })
                return
            if path == "/api/tasks":
                self._json({"items": probes.task_status()})
                return
            if path == "/api/chat/sessions":
                limit = max(1, min(50, int(q.get("limit", 20))))
                self._json({"items": Memory().chat_list(limit)})
                return
            if path == "/api/chat/session":
                sid = (q.get("id") or "").strip()
                sess = chat_agent().session(sid) if sid else None
                if not sess:
                    self._error("session not found", 404)
                    return
                self._json({"ok": True, "session": sess})
                return
            self._error("not found", 404)
        except (ValueError, TypeError) as e:
            self._error(str(e), 400)
        except Exception as e:
            self._error(f"{type(e).__name__}: {e}", 500)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        path = urlparse(self.path).path
        q = self._query()
        try:
            body = self._body()
        except ValueError as e:
            self._error(str(e), 400)
            return

        try:
            if path == "/api/ask":
                self._ask(body, stream=q.get("stream") == "1")
                return
            if path in ("/api/swarm", "/api/council"):
                question = str(body.get("question") or body.get("q") or "").strip()
                if not question:
                    self._error("question required", 400)
                    return
                if len(question) > 2000:
                    self._error("question too long (max 2000 chars)", 400)
                    return
                depth = clamp_depth(body.get("depth") or DEFAULT_DEPTH)
                kind = str(body.get("kind") or "knowledge").strip().lower()
                context = str(body.get("context") or "").strip()[:4000]
                result = swarm.synthesize(question, kind, context, [],
                                          depth=depth)
                self._json({"ok": bool(result.get("ok")), "result": result})
                return
            if path == "/api/chat":
                message = str(body.get("message") or "").strip()
                if len(message) > 4000:
                    self._error("message too long (max 4000 chars)", 400)
                    return
                sid = str(body.get("session_id") or "").strip() or None
                use_ai = bool(body.get("ai", True))
                depth = clamp_depth(body.get("depth") or DEFAULT_DEPTH)
                reply = chat_agent().handle(message, session_id=sid,
                                            ai=use_ai, depth=depth)
                self._json({"ok": True, **reply.to_dict()})
                return
            if path == "/api/feedback":
                aid = int(body.get("id") or 0)
                vote = 1 if int(body.get("vote") or 0) > 0 else -1
                note = str(body.get("note") or "")[:500]
                if aid <= 0:
                    self._error("id required", 400)
                    return
                Memory().feedback(aid, vote, note)
                self._json({"ok": True, "id": aid, "vote": vote})
                return
            if path == "/api/capsule":
                msg = str(body.get("message") or "").strip()
                if not msg:
                    self._error("message required", 400)
                    return
                if len(msg) > 8000:
                    self._error("message too long (max 8000 chars)", 400)
                    return
                days = max(1, min(36500, int(body.get("days") or 365)))
                open_date = (date.today() + timedelta(days=days)).isoformat()
                cid = Oracle().seal_capsule(open_date, msg)
                Memory().event("capsule_sealed", {
                    "capsule_id": cid, "open_date": open_date, "days": days})
                self._json({"ok": True, "id": cid, "open_date": open_date,
                            "days": days, "message": msg})
                return
            if path == "/api/probes/run":
                o = Oracle()
                res = probes.harvest_due(o, limit=max(1, min(20, int(
                    body.get("limit") or 10))))
                self._json({"ok": True, "results": res, "stats": o.stats()})
                return
            if path == "/api/probes/schedule":
                r = probes.schedule_daily()
                self._json(r)
                return
            if path == "/api/cache/clear":
                net.clear_cache()
                self._json({"ok": True, "message": "HTTP cache cleared"})
                return
            self._error("not found", 404)
        except (ValueError, TypeError) as e:
            self._error(str(e), 400)
        except Exception as e:
            self._error(f"{type(e).__name__}: {e}", 500)

    # --------------------------------------------------------------- stream
    def _ask(self, body: dict, stream: bool):
        question = str(body.get("q") or body.get("question") or "").strip()
        if not question:
            self._error("question required", 400)
            return
        if len(question) > 2000:
            self._error("question too long (max 2000 chars)", 400)
            return
        use_ai = bool(body.get("ai", True))
        depth = clamp_depth(body.get("depth") or DEFAULT_DEPTH)

        if not stream:
            ans = Chrono(use_llm=use_ai, depth=depth).ask(
                question, ai=use_ai, depth=depth)
            self._json({"ok": True, "answer": ans.to_dict()})
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                OSError):
            return
        closed = {"v": False}

        def emit(obj: dict) -> None:
            if closed["v"]:
                return
            data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
            try:
                self.wfile.write(f"{len(data):X}\r\n".encode("ascii"))
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                closed["v"] = True

        def on_stage(name: str, payload: dict) -> None:
            emit({"type": "stage", "name": name, "payload": payload,
                  "at": time.time()})

        try:
            emit({"type": "start", "question": question, "ai": use_ai,
                  "at": time.time()})
            ans = Chrono(use_llm=use_ai, depth=depth).ask(
                question, ai=use_ai, on_stage=on_stage, depth=depth)
            emit({"type": "answer", "answer": ans.to_dict()})
        except Exception as e:
            emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass


class CockpitServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, verbose: bool = False):
        self.verbose = verbose
        super().__init__(addr, handler)

    def handle_error(self, request, client_address):
        # Windows browsers abort connections routinely (tab closed, refresh,
        # fetch cancelled). WinError 10053/10054 is not a server bug.
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError,
                            ConnectionAbortedError, OSError)):
            return
        super().handle_error(request, client_address)


def run(port: int = 8765, open_browser: bool = True, verbose: bool = False,
        host: str = "127.0.0.1") -> int:
    server = None
    actual = port
    last_err = None
    for p in range(port, port + 12):
        try:
            server = CockpitServer((host, p), Handler, verbose=verbose)
            actual = p
            break
        except OSError as e:
            last_err = e
    if server is None:
        print(f"Port {port}-{port + 11} par server start nahi ho saka: {last_err}")
        return 1
    url = f"http://{host}:{actual}/"
    print()
    print("  CHRONOVAULT 2.2.0 · TIME COCKPIT")
    print(f"  {url}")
    print("  Ctrl+C se band karein.")
    print()
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n  Cockpit band ho gaya.")
    finally:
        server.shutdown()
        server.server_close()
    return 0
