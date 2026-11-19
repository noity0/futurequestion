"""Offline unit tests for ChronoVault 2.0 (no network required)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(TESTS_DIR))
sys.path.insert(0, ENGINE_DIR)

from chronovault import formulas, net, text  # noqa: E402
from chronovault import babynames  # noqa: E402
from chronovault import swarm  # noqa: E402
from chronovault.ask import Chrono, clamp_depth  # noqa: E402
from chronovault.chat import ChatAgent, parse_slot  # noqa: E402
from chronovault.forecast import MAX_HORIZON_DAYS, forecast, prepare, to_text  # noqa: E402
from chronovault.memory import Memory  # noqa: E402
from chronovault.places import find_city, find_country, find_currencies, find_crypto  # noqa: E402
from chronovault.registry import Registry  # noqa: E402
from chronovault.router import forecast_query, route  # noqa: E402


class TestFormulas(unittest.TestCase):
    def test_weekday_known(self):
        d = date(2026, 11, 18)
        r = formulas.weekday_answer(d)
        self.assertTrue(r["ok"])
        self.assertIn("Wednesday", r["text"])

    def test_parse_date(self):
        self.assertEqual(formulas.parse_date("1 Jan 2050"), date(2050, 1, 1))
        self.assertEqual(formulas.parse_date("18 Nov 2026"), date(2026, 11, 18))
        self.assertIsNone(formulas.parse_date("kuch nahi"))

    def test_parse_duration_words(self):
        self.assertEqual(formulas.parse_duration_days("agle saal"), 365)
        self.assertEqual(formulas.parse_duration_days("next year"), 365)
        self.assertEqual(formulas.parse_duration_days("do saal"), 730)
        self.assertEqual(formulas.parse_duration_days("agle mahine"), 30)
        self.assertEqual(formulas.parse_duration_days("next week"), 7)
        self.assertEqual(formulas.parse_duration_days("5 saal"), 1825)
        self.assertIsNone(formulas.parse_duration_days("kuch nahi"))

    def test_countdown_future_past(self):
        fut = date.today() + timedelta(days=10)
        r = formulas.countdown(fut)
        self.assertIn("10", r["text"])
        past = date.today() - timedelta(days=3)
        r2 = formulas.countdown(past)
        self.assertIn("guzar chuki hai", r2["text"])

    def test_compound_matches_formula(self):
        p, r, y = 100000.0, 18.0, 5
        got = formulas.compound(p, r, y)
        expected = p * (1 + r / 100 / 12) ** (12 * y)
        self.assertAlmostEqual(got["amount"], expected, delta=1.0)

    def test_simple_interest(self):
        got = formulas.simple_interest(10000, 10, 2)
        self.assertAlmostEqual(got["interest"], 2000.0, places=2)

    def test_emi_matches_standard_formula(self):
        p, annual, years = 5000000.0, 12.0, 5
        m = int(years * 12)
        r = annual / 100 / 12
        expected = p * r * (1 + r) ** m / ((1 + r) ** m - 1)
        got = formulas.emi(p, annual, years)
        self.assertAlmostEqual(got["emi"], expected, delta=1.0)


class TestRouter(unittest.TestCase):
    CASES = [
        ("1 Jan 2050 konsa din hoga?", "date"),
        ("2050 tak kitne din baqi hain?", "countdown"),
        ("100000 @ 18% 5 saal compound interest", "interest"),
        ("50 lakh ka loan 12% 5 saal EMI", "emi"),
        ("100 dollar to PKR", "fx"),
        ("USD/PKR 30 din baad kitna hoga?", "forecast_fx"),
        ("bitcoin 2027 me kitna hoga?", "forecast_crypto"),
        ("Lahore ka mausam kaisa hai?", "weather"),
        ("Lahore me abhi kitne baje hain?", "time"),
        ("Pakistan me 2026 ki holidays batao", "holiday"),
        ("Japan ki capital kya hai?", "country"),
        ("latest AI news", "news"),
        ("ISS kahan hai abhi", "space"),
        ("aaj ke earthquakes", "space"),
        ("time travel kya hai?", "knowledge"),
        ("Pakistan ka future kya hoga?", "forecast"),
        ("salam", "smalltalk"),
        ("tum kon ho?", "identity"),
        ("time capsule banao: 1 saal baad kholna, bharosa rakho", "capsule"),
        ("mere bache ka naam kya hoga?", "baby_name"),
        ("mujhe beti ka naam suggest karo", "baby_name"),
    ]

    def test_intents(self):
        for q, kind in self.CASES:
            with self.subTest(q=q):
                it = route(q)
                self.assertEqual(it.kind, kind, f"{q} -> {it.to_dict()}")

    def test_slots(self):
        it = route("100 dollar to PKR")
        self.assertEqual(it.slots.get("from"), "USD")
        self.assertEqual(it.slots.get("to"), "PKR")
        self.assertAlmostEqual(it.slots.get("amount"), 100.0)
        w = route("Lahore ka mausam")
        self.assertEqual(w.slots.get("city"), "Lahore")

    def test_forecast_query_drops_horizon_words(self):
        self.assertEqual(
            forecast_query("20 saal baad pakistan military power kya hoga?"),
            "pakistan military power")
        self.assertEqual(
            forecast_query("Pakistan ka future kya hoga?"), "Pakistan")
        it = route("20 saal baad pakistan military power kya hoga?")
        self.assertEqual(it.kind, "forecast")
        self.assertEqual(it.slots.get("query"), "pakistan military power")
        self.assertGreaterEqual(it.slots.get("horizon_days"), 7300)


class TestForecast(unittest.TestCase):
    def test_linear_series_predicts_trend(self):
        base = date(2026, 1, 1)
        series = [((base + timedelta(days=i)).isoformat(),
                   100.0 + i * 0.4 + (i % 7) * 0.2) for i in range(120)]
        f = forecast(series, 10)
        self.assertIsNotNone(f)
        self.assertGreater(f["predicted"], series[-1][1] - 5)
        self.assertLess(f["predicted"], 100 + 120 * 0.4 + 5)
        self.assertEqual(f["target_date"], (base + timedelta(days=129)).isoformat())
        self.assertLessEqual(f["confidence"], 0.84)
        self.assertGreaterEqual(f["confidence"], 0.24)

    def test_short_series_returns_none(self):
        self.assertIsNone(forecast([("2026-01-01", 1.0)] * 3, 10))

    def _series(self):
        base = date(2026, 1, 1)
        return [((base + timedelta(days=i)).isoformat(),
                 100.0 + i * 0.4 + (i % 7) * 0.2) for i in range(120)]

    def test_horizon_cap_keeps_requested_days(self):
        f = forecast(self._series(), 36500)
        self.assertEqual(f["horizon_days"], MAX_HORIZON_DAYS)
        self.assertEqual(f["requested_horizon_days"], 36500)
        self.assertTrue(f["horizon_capped"])
        text = to_text("USD/PKR", f)
        self.assertIn("36,500", text)
        self.assertIn("nahi", text)
        # Callers may supply the raw request separately while passing the
        # already-capped horizon.
        f2 = forecast(self._series(), MAX_HORIZON_DAYS,
                      requested_horizon_days=36500)
        self.assertTrue(f2["horizon_capped"])
        self.assertEqual(f2["requested_horizon_days"], 36500)

    def test_confidence_decays_with_horizon(self):
        short = forecast(self._series(), 30)
        long = forecast(self._series(), 3650)
        self.assertGreater(short["confidence"], long["confidence"])
        self.assertGreaterEqual(long["confidence"], 0.18)
        self.assertLessEqual(short["confidence"], 0.84)

    def test_prepare_dedupes(self):
        xs, ys = prepare([("2026-01-01", 1.0), ("2026-01-01", 2.0),
                          ("2026-01-02", 3.0)])
        self.assertEqual(xs, [0, 1])
        self.assertEqual(ys, [2.0, 3.0])


class TestRegistryAndPlaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = Registry()

    def test_registry_size_and_uniqueness(self):
        self.assertGreaterEqual(self.reg.total, 10000)
        ids = [e["id"] for e in self.reg.endpoints]
        self.assertEqual(len(ids), len(set(ids)))

    def test_search(self):
        rows = self.reg.search("bitcoin", limit=5)
        self.assertTrue(rows)
        self.assertIn("bitcoin", rows[0]["id"].lower())

    def test_categories(self):
        cats = self.reg.stats()["categories"]
        self.assertIn("finance", cats)
        self.assertGreater(cats.get("calendar", 0), 2500)
        self.assertGreater(cats.get("knowledge", 0), 1400)
        self.assertGreater(cats.get("weather", 0), 400)

    def test_places(self):
        city = find_city("Lahore ka mausam")
        self.assertIsNotNone(city)
        self.assertEqual(city[0], "Lahore")
        self.assertEqual(find_country("Saudi Arabia"), "SA")
        self.assertIn("USD", find_currencies("100 dollars"))
        self.assertEqual(find_crypto("btc price"), "bitcoin")


class TestText(unittest.TestCase):
    def test_clean_html(self):
        self.assertEqual(text.clean("<b>Salam</b> &amp; salam"), "Salam & salam")

    def test_shorten(self):
        self.assertLessEqual(len(text.shorten("a" * 1000, 80)), 81)

    def test_parse_rss(self):
        xml = """<rss><channel>
          <item><title>One</title><link>http://x/1</link><pubDate>Wed, 18 Nov 2026 10:00:00 GMT</pubDate></item>
          <item><title>Two</title><link>http://x/2</link></item>
        </channel></rss>"""
        items = text.parse_rss(xml)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "One")
        self.assertTrue(items[0]["link"].startswith("http"))


class TestMemoryIsolated(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.join(tempfile.gettempdir(), "chrono_test_memory.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.tmp + suffix)
            except OSError:
                pass
        import chronovault.memory as memory
        self._old = memory.DB_PATH
        memory.DB_PATH = self.tmp

    def tearDown(self):
        import chronovault.memory as memory
        memory.DB_PATH = self._old

    def test_record_get_history_stats(self):
        mem = Memory()
        aid = mem.record("test question", {
            "kind": "date", "answer": "Wednesday", "confidence": 0.99,
            "badge": "EXACT-MATH", "evidence": [{"source": "math"}],
            "data": {"weekday": "Wednesday"}, "sources": ["math"],
        }, 42)
        row = mem.get(aid)
        self.assertEqual(row["question"], "test question")
        self.assertEqual(row["kind"], "date")
        self.assertEqual(row["data"]["weekday"], "Wednesday")
        hist = mem.history(10)
        self.assertTrue(any(h["id"] == aid for h in hist))
        st = mem.stats()
        self.assertGreaterEqual(st["answers"], 1)
        mem.feedback(aid, 1, "useful")
        mem.event("test", {"ok": True})


class TestAskExactOffline(unittest.TestCase):
    """The orchestrator itself, but only deterministic math (no network/AI)."""

    def setUp(self):
        self.tmp = os.path.join(tempfile.gettempdir(), "chrono_test_ask.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.tmp + suffix)
            except OSError:
                pass
        import chronovault.memory as memory
        self._old = memory.DB_PATH
        memory.DB_PATH = self.tmp

    def tearDown(self):
        import chronovault.memory as memory
        memory.DB_PATH = self._old

    def test_exact_date_pipeline(self):
        ans = Chrono(use_llm=False).ask("1 Jan 2050 konsa din hoga?", ai=False)
        self.assertEqual(ans.badge, "EXACT-MATH")
        self.assertGreaterEqual(ans.confidence, 0.99)
        self.assertIn("Saturday", ans.answer)  # 2050-01-01 is a Saturday
        self.assertGreater(ans.answer_id, 0)

    def test_help_identity(self):
        ans = Chrono(use_llm=False).ask("tum kon ho?", ai=False)
        self.assertEqual(ans.kind, "identity")
        self.assertEqual(ans.badge, "INFO")


class TestChatAgent(unittest.TestCase):
    """Slot-filling agent, offline only (baby names + parsing)."""

    def setUp(self):
        self.tmp = os.path.join(tempfile.gettempdir(), "chrono_test_chat.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.tmp + suffix)
            except OSError:
                pass
        import chronovault.memory as memory
        self._old = memory.DB_PATH
        memory.DB_PATH = self.tmp
        self.agent = ChatAgent()

    def tearDown(self):
        import chronovault.memory as memory
        memory.DB_PATH = self._old

    def test_slot_parsers(self):
        got = parse_slot("city", "Karachi")
        self.assertEqual(got["city"], "Karachi")
        self.assertEqual(parse_slot("gender", "ladki")["gender"], "girl")
        self.assertEqual(parse_slot("surname", "my surname is Khan")["surname"], "Khan")
        self.assertEqual(parse_slot("culture", "urdu")["culture"], "urdu")
        self.assertEqual(parse_slot("style", "modern")["style"], "modern")
        self.assertEqual(parse_slot("rate", "18%")["rate"], 18.0)

    def test_baby_name_full_flow(self):
        r = self.agent.handle("mere bache ka naam kya hoga?")
        self.assertEqual(r.state, "asking")
        self.assertEqual(r.pending, "gender")
        sid = r.session_id
        r = self.agent.handle("boy", sid)
        self.assertEqual(r.pending, "surname")
        r = self.agent.handle("Khan", sid)
        self.assertEqual(r.pending, "culture")
        r = self.agent.handle("urdu", sid)
        self.assertEqual(r.pending, "style")
        r = self.agent.handle("modern", sid)
        self.assertEqual(r.state, "answered")
        self.assertEqual(r.intent, "baby_name")
        self.assertEqual(r.answer["badge"], "SPECULATIVE")
        self.assertIn("Khan", r.reply)
        self.assertGreaterEqual(len(r.answer["data"]["names"]), 1)
        msgs = self.agent.session(sid)["messages"]
        self.assertGreaterEqual(len(msgs), 10)

    def test_baby_name_gender_in_first_message(self):
        r = self.agent.handle("meri beti ka naam kya hoga?")
        self.assertEqual(r.state, "asking")
        self.assertEqual(r.pending, "surname")

    def test_weather_asks_city(self):
        r = self.agent.handle("mausam kaisa hai?")
        self.assertEqual(r.state, "asking")
        self.assertEqual(r.intent, "weather")
        self.assertEqual(r.pending, "city")

    def test_babynames_deterministic(self):
        a = babynames.suggest("boy", "Khan", "urdu", "modern")
        b = babynames.suggest("boy", "Khan", "urdu", "modern")
        self.assertEqual([n["name"] for n in a["names"]],
                         [n["name"] for n in b["names"]])
        self.assertEqual(len(a["names"]), 5)


class TestSwarm(unittest.TestCase):
    """Offline checks for the keyless AI council."""

    def test_roles_catalogue(self):
        self.assertGreaterEqual(len(swarm.ROLES), 50)
        ids = [r.id for r in swarm.ROLES]
        self.assertEqual(len(ids), len(set(ids)))
        for cid in swarm.CORE_IDS:
            self.assertIn(cid, ids)
        for r in swarm.ROLES:
            self.assertTrue(r.name)
            self.assertTrue(r.system)

    def test_select_roles_depth_and_core(self):
        picked = swarm.select_roles("bitcoin agle saal kitna hoga?", "forecast", 12)
        self.assertEqual(len(picked), 12)
        self.assertEqual(len({r.id for r in picked}), 12)
        present = {r.id for r in picked}
        for cid in swarm.CORE_IDS:
            self.assertIn(cid, present)
        full = swarm.select_roles("mere bache ka naam kya hoga", "baby_name", 50)
        self.assertEqual(len(full), 50)
        self.assertIn("baby_name_curator", {r.id for r in full})

    def test_clamp_depth(self):
        self.assertEqual(clamp_depth(None), 9)
        self.assertEqual(clamp_depth("abc"), 9)
        self.assertEqual(clamp_depth(1), 5)
        self.assertEqual(clamp_depth(999), 50)
        self.assertEqual(clamp_depth(17), 17)

    def test_routes_are_well_formed(self):
        self.assertGreaterEqual(len(swarm.STATIC_ROUTES), 40)
        ids = [r.id for r in swarm.STATIC_ROUTES]
        self.assertEqual(len(ids), len(set(ids)))
        for r in swarm.STATIC_ROUTES:
            self.assertTrue(r.url.startswith("http"), r.id)
            self.assertTrue(r.model, r.id)
            if r.key_env:
                self.assertTrue(r.key_env.endswith("_KEY") or
                                r.key_env in ("GITHUB_TOKEN", "HF_TOKEN"))

    def test_score_candidates_prefers_grounded(self):
        base = "Verified: USD/PKR is 279.50 on 2026-11-18."
        cands = [
            {"role_id": "a", "role_name": "A", "text":
             "USD/PKR is 1.5, guaranteed (confidence: 99%)",
             "route_weight": 1.0, "role_weight": 1.0},
            {"role_id": "b", "role_name": "B", "text":
             "Verified USD/PKR 279.50 on 2026-11-18 (confidence: 70%)",
             "route_weight": 1.0, "role_weight": 1.0},
        ]
        scored = swarm.score_candidates(cands, base, "")
        self.assertEqual(scored[0]["role_id"], "b")
        self.assertGreater(scored[0]["ground"], scored[1]["ground"])

    def test_synthesize_offline_is_honest(self):
        with patch.object(swarm, "active_routes", return_value=[]):
            out = swarm.synthesize("offline-unique-question-xyz", "knowledge",
                                   "Verified fact.", [], depth=5)
        self.assertFalse(out["ok"])
        self.assertEqual(out["confidence"], 0.0)
        self.assertTrue(any("offline" in n.lower() for n in out["notes"]))

    def test_synthesize_with_fake_routes(self):
        routes = [
            swarm.Route("test:a", "Test", "test", "A", "https://x/a", "a",
                        weight=1.0),
            swarm.Route("test:b", "Test", "test", "B", "https://x/b", "b",
                        weight=0.9),
        ]

        def fake_chat(route, messages, temperature=0.25, max_tokens=700,
                      timeout=35.0, deadline=None):
            system = (messages[0].get("content") or "").lower()
            if "final judge" in system:
                return {"ok": True, "route": route, "ms": 1,
                        "model": route.model,
                        "text": "Verified: 2+2 = 4. (confidence: 80%)"}
            return {"ok": True, "route": route, "ms": 1, "model": route.model,
                    "text": "The verified answer is 2+2 = 4. (confidence: 82%)"}

        with patch.object(swarm, "active_routes", return_value=routes), \
                patch.object(swarm, "_chat", side_effect=fake_chat):
            out = swarm.synthesize("unique-council-test-2plus2", "knowledge",
                                   "2+2 = 4", [], depth=5,
                                   base_confidence=0.9)
        self.assertTrue(out["ok"])
        self.assertIn("4", out["text"])
        self.assertGreater(out["summary"]["agents_replied"], 0)
        self.assertLessEqual(out["confidence"], 0.94)
        self.assertGreater(out["confidence"], 0.5)

    def test_unsupported_numbers_detected(self):
        bad = swarm._unsupported_numbers("The price is 999.99 tomorrow.",
                                         "Verified price is 42.", [])
        self.assertIn("999.99", bad)

    def test_forecast_horizon_constant(self):
        self.assertEqual(MAX_HORIZON_DAYS, 3650)


class TestNetHealth(unittest.TestCase):
    def test_health_shape(self):
        h = net.health_summary()
        for key in ("entries", "alive", "requests_ok", "requests_fail", "success_rate"):
            self.assertIn(key, h)


if __name__ == "__main__":
    unittest.main()
