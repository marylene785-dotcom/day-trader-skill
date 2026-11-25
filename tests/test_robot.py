"""robot/robot.py tests: SYNTHETIC five-minute bars (not market data) built on
Mon 2026-10-19, plus the real TSLA fixture of trader-entry."""

import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from _load import load, FIX

robot = load("robot", "robot")
entry = robot.entry

OPEN_TS = 1792416600       # 2026-10-19 09:30 EDT
TSLA = os.path.join(FIX, "trader-entry", "TSLA-2026-10-19-5m.json")


def chart(rows, sym="DEMO"):
    """rows: (high, low, close) per 5-minute bar from 9:30."""
    bars = [{"t": OPEN_TS + 300 * i, "o": c, "h": h, "l": lo, "c": c, "v": 1000} for i, (h, lo, c) in enumerate(rows)]
    return {"symbol": sym, "meta": {}, "bars": bars, "prev_close": 100.0, "data_time": None}


RANGE = [(101, 99, 100), (102, 99.5, 101), (101.5, 100, 101)]     # high 102, low 99: stop 100.50
BREAK = RANGE + [(102.5, 101, 102.40)]                             # the 9:45 bar closes above 102: the signal comes at 9:50


def ny(text):
    return entry.parse_now(text)


class Robot(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "state.json")
        self.cfg = dict(robot.DEFAULTS, symbols=["DEMO"], ntfy_topic="")
        self.sent = []

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_at(self, when, rows, cfg=None):
        with redirect_stdout(io.StringIO()):
            st, n = robot.run_once(cfg or self.cfg, ny(when), self.state, get_chart=lambda s: chart(rows, s),
                                   notify=lambda t, m, p, g: self.sent.append(t))
        return st

    def test_entry_signal_with_the_skill_levels(self):
        st = self.run_at("2026-10-19 09:51", BREAK)
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.sent[0].startswith("ENTRÉE DEMO à 102,40"))
        s = st["symbols"]["DEMO"]
        self.assertEqual((s["entry"], s["stop"], s["target"]), (102.40, 100.50, 106.20))

    def test_no_signal_inside_the_range_and_no_repeat(self):
        self.run_at("2026-10-19 09:46", RANGE + [(101.9, 101, 101.5)])
        self.assertEqual(self.sent, [])
        self.run_at("2026-10-19 09:51", BREAK)
        self.run_at("2026-10-19 09:56", BREAK + [(102.6, 102, 102.5)])
        self.assertEqual(len(self.sent), 1)

    def test_stop_then_nothing_more(self):
        self.run_at("2026-10-19 09:51", BREAK)
        st = self.run_at("2026-10-19 10:01", BREAK + [(102.5, 101.5, 102), (102, 100.40, 100.60)])
        self.assertEqual(self.sent[-1], "SORTIE DEMO : stop touché (100,50 $)")
        self.assertEqual(st["symbols"]["DEMO"]["phase"], "done")
        self.run_at("2026-10-19 10:06", BREAK + [(102.5, 101.5, 102), (102, 100.40, 100.60), (110, 100, 109)])
        self.assertEqual(len(self.sent), 2)

    def test_target(self):
        self.run_at("2026-10-19 09:51", BREAK + [])
        self.run_at("2026-10-19 09:56", BREAK + [(106.30, 102, 106)])
        self.assertEqual(self.sent[-1], "SORTIE DEMO : objectif touché (106,20 $)")

    def test_stop_and_target_in_one_bar_counts_the_stop(self):
        self.run_at("2026-10-19 09:51", BREAK)
        self.run_at("2026-10-19 09:56", BREAK + [(107, 100, 103)])
        self.assertIn("stop touché", self.sent[-1])

    def test_flat_by_close(self):
        rows = BREAK + [(102.6, 101.5, 102.2)] * 74      # 9:50 to 16:00, never hits stop or target
        self.run_at("2026-10-19 09:51", BREAK)
        self.run_at("2026-10-19 15:56", rows)
        self.assertEqual(self.sent[-1], "SORTIE DEMO : fin de journée")

    def test_max_signals_per_day(self):
        cfg = dict(self.cfg, symbols=["A", "B"], max_signals_per_day=1)
        st = self.run_at("2026-10-19 09:51", BREAK, cfg)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(st["symbols"]["B"]["phase"], "skipped")

    def test_new_day_resets_the_state(self):
        self.run_at("2026-10-19 09:51", BREAK)
        with open(self.state) as fh:
            doc = json.load(fh)
        doc["date"] = "2026-10-16"
        with open(self.state, "w") as fh:
            json.dump(doc, fh)
        st = self.run_at("2026-10-19 09:51", BREAK)
        self.assertEqual(st["signals"], 1)
        self.assertEqual(len(self.sent), 2)

    def test_real_tsla_day(self):
        cfg = dict(self.cfg, symbols=["TSLA"])
        with redirect_stdout(io.StringIO()):
            st, n = robot.run_once(cfg, ny("2026-10-19 10:16"), self.state, offline=TSLA,
                                   notify=lambda t, m, p, g: self.sent.append((t, m)))
        self.assertEqual(self.sent[0][0], "ENTRÉE TSLA à 364,18 $")
        self.assertIn("358,32 $", self.sent[0][1])
        self.assertIn("375,90 $", self.sent[0][1])
        self.assertIn("pas un conseil financier", self.sent[0][1])

    def test_a_late_start_skips_an_old_signal(self):
        st = self.run_at("2026-10-19 10:30", BREAK + [(102.6, 101.5, 102.2)] * 8)
        self.assertEqual(self.sent, [])
        self.assertEqual(st["symbols"]["DEMO"]["phase"], "skipped")
        self.assertIn("09:50", st["symbols"]["DEMO"]["why"])

    def test_a_signal_seen_late_after_watching_still_alerts(self):
        self.run_at("2026-10-19 09:46", RANGE + [(101.9, 101, 101.5)])
        self.run_at("2026-10-19 10:30", BREAK + [(102.6, 101.5, 102.2)] * 8)
        self.assertEqual(len(self.sent), 1)

    def test_send_retries_a_429(self):
        import urllib.error
        calls, naps = [], []

        class Resp(object):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=0):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
            return Resp()

        old = robot.sleep
        robot.sleep = naps.append
        try:
            with redirect_stdout(io.StringIO()):
                ok = robot.send(dict(self.cfg, ntfy_topic="t"), "T", "m", 3, None, opener=opener)
        finally:
            robot.sleep = old
        self.assertTrue(ok)
        self.assertEqual((len(calls), naps), (2, [10]))

    def test_market_window(self):
        self.assertEqual(robot.market_window(ny("2026-10-19 10:00"))[0], True)
        closed, nxt = robot.market_window(ny("2026-11-26 10:00"))    # Thanksgiving
        self.assertFalse(closed)
        self.assertEqual(entry.to_eastern(nxt), datetime.datetime(2026, 11, 27, 9, 30))
        self.assertEqual(entry.to_eastern(robot.market_window(ny("2026-10-17 12:00"))[1]).date(),
                         datetime.date(2026, 10, 19))

    def test_flat_by_on_an_early_close(self):
        self.assertEqual(robot.flat_by_time(datetime.date(2026, 11, 27), self.cfg), datetime.time(12, 55))
        self.assertEqual(robot.flat_by_time(datetime.date(2026, 10, 19), self.cfg), datetime.time(15, 55))

    def test_send_posts_json_to_ntfy(self):
        seen = {}

        class Resp(object):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=0):
            seen["url"], seen["body"] = req.full_url, json.loads(req.data.decode("utf-8"))
            return Resp()

        with redirect_stdout(io.StringIO()):
            ok = robot.send(dict(self.cfg, ntfy_topic="t-123"), "ENTRÉE", "é", 4, ["x"], opener=opener)
        self.assertTrue(ok)
        self.assertEqual(seen["url"], "https://ntfy.sh")
        self.assertEqual(seen["body"], {"topic": "t-123", "title": "ENTRÉE", "message": "é", "priority": 4, "tags": ["x"]})

    def test_never_places_an_order(self):
        with open(os.path.join(os.path.dirname(robot.__file__), "robot.py"), encoding="utf-8") as fh:
            src = fh.read()
        for word in ("place_stock_order", "alpaca", "ticket"):
            self.assertNotIn(word, src.lower())


if __name__ == "__main__":
    unittest.main()
