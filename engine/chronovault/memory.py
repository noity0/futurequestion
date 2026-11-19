"""ChronoVault 2.0 — local memory (answers, feedback, events, capsule index)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from .paths import DB_PATH, ensure_dirs

ensure_dirs()
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _con():
    con = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS answers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, question TEXT, kind TEXT, answer TEXT,
        confidence REAL, badge TEXT, evidence TEXT, ms INT, ai INT,
        data TEXT, intent TEXT, sources TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, answer_id INT, vote INT, note TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, kind TEXT, payload TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS chat_sessions(
        id TEXT PRIMARY KEY, created TEXT, updated TEXT, state TEXT,
        intent TEXT, slots TEXT, pending TEXT, last_question TEXT,
        history TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS chat_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, ts TEXT,
        role TEXT, text TEXT, meta TEXT)""")
    con.execute("""CREATE INDEX IF NOT EXISTS idx_chat_messages_session
        ON chat_messages(session_id, id)""")
    # migrate a v2 database created before the extra columns existed
    have = {r[1] for r in con.execute("PRAGMA table_info(answers)")}
    for col in ("data", "intent", "sources"):
        if col not in have:
            con.execute(f"ALTER TABLE answers ADD COLUMN {col} TEXT")
    return con


def _j(obj) -> str:
    try:
        return json.dumps(obj or {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _loads(s):
    try:
        return json.loads(s or "null")
    except Exception:
        return None


class Memory:
    def record(self, question: str, result: dict, ms: int) -> int:
        with _LOCK:
            con = _con()
            try:
                cur = con.execute(
                    "INSERT INTO answers(ts,question,kind,answer,confidence,badge,"
                    "evidence,ms,ai,data,intent,sources) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (_now(), question, result.get("kind", ""),
                     result.get("answer", ""), float(result.get("confidence", 0)),
                     result.get("badge", ""),
                     json.dumps(result.get("evidence", [])[:12], ensure_ascii=False),
                     int(ms), 1 if result.get("ai_used") else 0,
                     _j(result.get("data")), _j(result.get("intent")),
                     _j(result.get("sources"))))
                con.commit()
                return cur.lastrowid
            finally:
                con.close()

    def history(self, limit: int = 20) -> list[dict]:
        with _LOCK:
            con = _con()
            try:
                rows = con.execute(
                    "SELECT id,ts,question,kind,answer,confidence,badge,ms,ai "
                    "FROM answers ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            finally:
                con.close()
        keys = ["id", "ts", "question", "kind", "answer", "confidence",
                "badge", "ms", "ai"]
        return [dict(zip(keys, r)) for r in rows]

    def get(self, aid: int) -> dict | None:
        with _LOCK:
            con = _con()
            try:
                r = con.execute(
                    "SELECT id,ts,question,kind,answer,confidence,badge,evidence,"
                    "ms,ai,data,intent,sources FROM answers WHERE id=?",
                    (aid,)).fetchone()
            finally:
                con.close()
        if not r:
            return None
        keys = ["id", "ts", "question", "kind", "answer", "confidence",
                "badge", "evidence", "ms", "ai", "data", "intent", "sources"]
        d = dict(zip(keys, r))
        for k in ("evidence", "data", "intent", "sources"):
            d[k] = _loads(d.get(k)) or ([] if k == "evidence" else {})
        return d

    def forecasts(self, limit: int = 12) -> list[dict]:
        """Recent numeric forecasts, newest first (for Multiverse fan)."""
        with _LOCK:
            con = _con()
            try:
                rows = con.execute(
                    "SELECT id,ts,question,kind,answer,confidence,badge,data "
                    "FROM answers WHERE kind IN ('forecast_fx','forecast_crypto') "
                    "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            finally:
                con.close()
        keys = ["id", "ts", "question", "kind", "answer", "confidence",
                "badge", "data"]
        out = []
        for row in rows:
            d = dict(zip(keys, row))
            d["data"] = _loads(d.get("data")) or {}
            if isinstance(d["data"].get("forecast"), dict):
                out.append(d)
        return out

    def feedback(self, answer_id: int, vote: int, note: str = "") -> None:
        with _LOCK:
            con = _con()
            try:
                con.execute(
                    "INSERT INTO feedback(ts,answer_id,vote,note) VALUES(?,?,?,?)",
                    (_now(), answer_id, vote, note))
                con.commit()
            finally:
                con.close()

    def event(self, kind: str, payload: dict) -> None:
        with _LOCK:
            con = _con()
            try:
                con.execute(
                    "INSERT INTO events(ts,kind,payload) VALUES(?,?,?)",
                    (_now(), kind, _j(payload)))
                con.commit()
            finally:
                con.close()

    # ------------------------------------------------------------- chat
    def chat_create(self, sid: str | None = None) -> dict:
        import uuid
        sid = sid or ("cv_" + uuid.uuid4().hex[:12])
        now = _now()
        with _LOCK:
            con = _con()
            try:
                row = con.execute("SELECT id FROM chat_sessions WHERE id=?",
                                  (sid,)).fetchone()
                if not row:
                    con.execute(
                        "INSERT INTO chat_sessions(id,created,updated,state,"
                        "intent,slots,pending,last_question,history) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (sid, now, now, "new", "", "{}", "", "", "[]"))
                    con.commit()
            finally:
                con.close()
        return self.chat_get(sid) or {"id": sid, "state": "new", "slots": {},
                                       "intent": "", "pending": "",
                                       "last_question": ""}

    def chat_get(self, sid: str) -> dict | None:
        if not sid:
            return None
        with _LOCK:
            con = _con()
            try:
                row = con.execute(
                    "SELECT id,created,updated,state,intent,slots,pending,"
                    "last_question FROM chat_sessions WHERE id=?", (sid,)
                ).fetchone()
            finally:
                con.close()
        if not row:
            return None
        keys = ["id", "created", "updated", "state", "intent", "slots",
                "pending", "last_question"]
        d = dict(zip(keys, row))
        try:
            d["slots"] = json.loads(d.get("slots") or "{}")
        except Exception:
            d["slots"] = {}
        return d

    def chat_save(self, sid: str, **fields) -> None:
        allowed = {"state", "intent", "slots", "pending", "last_question"}
        sets, vals = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "slots":
                value = _j(value)
            sets.append(f"{key}=?")
            vals.append(value)
        if not sets:
            return
        sets.append("updated=?")
        vals.append(_now())
        vals.append(sid)
        with _LOCK:
            con = _con()
            try:
                con.execute(f"UPDATE chat_sessions SET {', '.join(sets)} "
                            "WHERE id=?", tuple(vals))
                con.commit()
            finally:
                con.close()

    def chat_add_message(self, sid: str, role: str, text: str,
                         meta: dict | None = None) -> int:
        with _LOCK:
            con = _con()
            try:
                cur = con.execute(
                    "INSERT INTO chat_messages(session_id,ts,role,text,meta) "
                    "VALUES(?,?,?,?,?)",
                    (sid, _now(), role, text, _j(meta)))
                con.commit()
                return cur.lastrowid
            finally:
                con.close()

    def chat_messages(self, sid: str, limit: int = 100) -> list[dict]:
        with _LOCK:
            con = _con()
            try:
                rows = con.execute(
                    "SELECT id,ts,role,text,meta FROM chat_messages "
                    "WHERE session_id=? ORDER BY id ASC LIMIT ?",
                    (sid, limit)).fetchall()
            finally:
                con.close()
        out = []
        for r in rows:
            item = {"id": r[0], "ts": r[1], "role": r[2], "text": r[3]}
            meta = _loads(r[4])
            if meta:
                item["meta"] = meta
            out.append(item)
        return out

    def chat_list(self, limit: int = 20) -> list[dict]:
        with _LOCK:
            con = _con()
            try:
                rows = con.execute(
                    "SELECT id,created,updated,state,intent,pending "
                    "FROM chat_sessions ORDER BY updated DESC LIMIT ?",
                    (limit,)).fetchall()
            finally:
                con.close()
        keys = ["id", "created", "updated", "state", "intent", "pending"]
        return [dict(zip(keys, r)) for r in rows]

    def chat_reset(self, sid: str) -> None:
        with _LOCK:
            con = _con()
            try:
                con.execute("DELETE FROM chat_messages WHERE session_id=?",
                            (sid,))
                con.execute(
                    "UPDATE chat_sessions SET state='new',intent='',slots='{}',"
                    "pending='',last_question='',updated=? WHERE id=?",
                    (_now(), sid))
                con.commit()
            finally:
                con.close()

    def stats(self) -> dict:
        with _LOCK:
            con = _con()
            try:
                answers = con.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
                today = _now()[:10]
                today_n = con.execute(
                    "SELECT COUNT(*) FROM answers WHERE substr(ts,1,10)=?",
                    (today,)).fetchone()[0]
                avg = con.execute("SELECT AVG(confidence) FROM answers").fetchone()[0]
                kinds = dict(con.execute(
                    "SELECT kind,COUNT(*) FROM answers GROUP BY kind "
                    "ORDER BY COUNT(*) DESC").fetchall())
                db_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
            finally:
                con.close()
        return {"answers": answers, "today": today_n,
                "avg_confidence": round(avg, 3) if avg else None,
                "kinds": kinds, "db_bytes": db_bytes}
