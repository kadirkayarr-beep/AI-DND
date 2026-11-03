"""The daily usage ledger: one JSON line a call, per local day, never in the way of a model call."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api import usage_ledger
from api.usage_ledger import PRICES_USD_PER_MILLION, UsageLedger

_TEMP: tempfile.TemporaryDirectory | None = None
ZONE = timezone(timedelta(hours=3))


def setUpModule():
    global _TEMP
    _TEMP = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(_TEMP.cleanup)


def ledger_file() -> Path:
    return Path(tempfile.mkdtemp(dir=_TEMP.name)) / "play" / "model-usage.jsonl"


class Clock:
    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def noon(day: int = 4) -> Clock:
    return Clock(datetime(2026, 11, day, 12, 0, tzinfo=ZONE))


class TheLedger(unittest.TestCase):
    def test_record_appends_one_line_per_call(self):
        path = ledger_file()
        ledger = UsageLedger(path, now=noon())
        ledger.record("gemini", input_tokens=100, output_tokens=20, thought_tokens=5, seconds=1.5)
        ledger.record("haiku", input_tokens=7, output_tokens=3, outcome="answered")
        ledger.record("gemini", input_tokens=0, output_tokens=0, seconds=0.2, outcome="skipped")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(
            json.loads(lines[0]),
            {"day": "2026-11-04", "provider": "gemini", "input": 100, "output": 20, "thought": 5,
             "seconds": 1.5, "outcome": "answered"},
        )
        self.assertEqual(json.loads(lines[1])["seconds"], None)
        self.assertEqual(json.loads(lines[2])["outcome"], "skipped")

    def test_today_sums_only_today(self):
        clock = noon(4)
        ledger = UsageLedger(ledger_file(), now=clock)
        ledger.record("haiku", input_tokens=10, output_tokens=2, seconds=1.0)
        clock.moment = datetime(2026, 11, 4, 23, 59, 59, tzinfo=ZONE)
        ledger.record("haiku", input_tokens=5, output_tokens=1, seconds=0.5)
        self.assertEqual(
            ledger.today(),
            {"haiku": {"calls": 2, "input": 15, "output": 3, "thought": 0, "seconds": 1.5}},
        )
        clock.moment = datetime(2026, 11, 5, 0, 0, 1, tzinfo=ZONE)
        self.assertEqual(ledger.today(), {})
        ledger.record("gemma", input_tokens=4, output_tokens=4)
        self.assertEqual(
            ledger.today(),
            {"gemma": {"calls": 1, "input": 4, "output": 4, "thought": 0, "seconds": 0}},
        )
        clock.moment = datetime(2026, 11, 4, 12, 0, tzinfo=ZONE)
        self.assertEqual(set(ledger.today()), {"haiku"})

    def test_the_day_is_the_clocks_local_date_not_utc(self):
        # 01:30 on the 5th at +03:00 is still the 4th in UTC; the ledger follows the local date.
        ledger = UsageLedger(ledger_file(), now=Clock(datetime(2026, 11, 5, 1, 30, tzinfo=ZONE)))
        ledger.record("haiku", input_tokens=1, output_tokens=1)
        line = json.loads(ledger_path_text(ledger))
        self.assertEqual(line["day"], "2026-11-05")

    def test_thought_tokens_are_counted(self):
        ledger = UsageLedger(ledger_file(), now=noon())
        ledger.record("gemini", input_tokens=100, output_tokens=20, thought_tokens=300, seconds=2.0)
        ledger.record("gemini", input_tokens=50, output_tokens=10, thought_tokens=40, seconds=1.0)
        self.assertEqual(
            ledger.today()["gemini"],
            {"calls": 2, "input": 150, "output": 30, "thought": 340, "seconds": 3.0},
        )

    def test_known_usd_ignores_unknown_price(self):
        ledger = UsageLedger(ledger_file(), now=noon())
        ledger.record("gemini", input_tokens=900_000_000, output_tokens=900_000_000, thought_tokens=5)
        ledger.record("haiku", input_tokens=2_000_000, output_tokens=1_000_000)
        ledger.record("gemma", input_tokens=50_000_000, output_tokens=50_000_000)
        ledger.record("someone-new", input_tokens=50_000_000, output_tokens=50_000_000)
        self.assertEqual(PRICES_USD_PER_MILLION["gemini"], None)
        # haiku: 2 M in at 0.10 + 1 M out at 0.50 = 0.70; gemini unknown, gemma free, unlisted provider unknown.
        self.assertAlmostEqual(ledger.known_usd_today(), 0.70)

    def test_warning_at_three_usd_with_known_prices(self):
        ledger = UsageLedger(ledger_file(), now=noon())
        ledger.record("haiku", input_tokens=29_000_000, output_tokens=0)
        self.assertIsNone(ledger.warning())
        ledger.record("haiku", input_tokens=1_000_000, output_tokens=0)
        message = ledger.warning()
        self.assertIsInstance(message, str)
        self.assertIn("3.00", message)
        self.assertNotIn("gemini", message.lower())

    def test_warning_never_counts_an_unknown_price(self):
        ledger = UsageLedger(ledger_file(), now=noon())
        ledger.record("gemini", input_tokens=10**12, output_tokens=10**12, thought_tokens=10**12)
        self.assertEqual(ledger.known_usd_today(), 0.0)
        self.assertIsNone(ledger.warning())

    def test_the_warning_threshold_and_prices_can_be_set(self):
        ledger = UsageLedger(ledger_file(), now=noon(), prices={"haiku": (1.0, 2.0)}, warn_usd=0.5)
        ledger.record("haiku", input_tokens=100_000, output_tokens=200_000)
        self.assertAlmostEqual(ledger.known_usd_today(), 0.5)
        self.assertIsNotNone(ledger.warning())

    def test_unreadable_or_unwritable_file_never_raises(self):
        base = Path(tempfile.mkdtemp(dir=_TEMP.name))
        # The file's place is a directory: it can be neither appended to nor read as a file.
        as_directory = base / "model-usage.jsonl"
        as_directory.mkdir()
        # The parent is a regular file: the parent directory cannot be made.
        blocker = base / "blocker"
        blocker.write_text("x", encoding="utf-8")
        for path in (as_directory, blocker / "play" / "model-usage.jsonl"):
            ledger = UsageLedger(path, now=noon())
            ledger.record("haiku", input_tokens=1, output_tokens=1)
            self.assertEqual(ledger.today(), {})
            self.assertEqual(ledger.known_usd_today(), 0.0)
            self.assertIsNone(ledger.warning())
        # A file that does not exist yet reads as an empty day.
        self.assertEqual(UsageLedger(base / "nothing-yet.jsonl", now=noon()).today(), {})

    def test_broken_lines_are_skipped_and_good_ones_still_count(self):
        path = ledger_file()
        path.parent.mkdir(parents=True)
        good = {"day": "2026-11-04", "provider": "haiku", "input": 10, "output": 5, "thought": 0,
                "seconds": 1.0, "outcome": "answered"}
        other_day = dict(good, day="2026-11-03", input=999)
        wrong_types = dict(good, input="many")
        bool_count = dict(good, output=True)
        no_provider = {key: value for key, value in good.items() if key != "provider"}
        raw = "\n".join([
            json.dumps(good),
            "{not json",
            "",
            "[1, 2, 3]",
            "null",
            json.dumps(other_day),
            json.dumps(wrong_types),
            json.dumps(bool_count),
            json.dumps(no_provider),
            json.dumps(good),
            '{"day": "2026-11-04", "provider": "haiku", "inp',  # a line cut short, last in the file
        ])
        path.write_bytes(raw.encode("utf-8") + b"\xff\xfe\n")
        ledger = UsageLedger(path, now=noon())
        self.assertEqual(
            ledger.today(),
            {"haiku": {"calls": 2, "input": 20, "output": 10, "thought": 0, "seconds": 2.0}},
        )
        # A file with broken lines in it still takes new records.
        ledger.record("haiku", input_tokens=1, output_tokens=1)
        self.assertEqual(ledger.today()["haiku"]["calls"], 3)

    def test_two_ledgers_on_one_file_lose_nothing(self):
        path = ledger_file()
        first = UsageLedger(path, now=noon())
        second = UsageLedger(path, now=noon())
        first.record("haiku", input_tokens=10, output_tokens=1)
        second.record("haiku", input_tokens=20, output_tokens=2)
        first.record("gemini", input_tokens=5, output_tokens=5, thought_tokens=9)
        for ledger in (first, second):
            today = ledger.today()
            self.assertEqual(today["haiku"]["calls"], 2)
            self.assertEqual(today["haiku"]["input"], 30)
            self.assertEqual(today["gemini"]["thought"], 9)

    def test_nothing_but_counts_and_names_reach_the_file(self):
        path = ledger_file()
        UsageLedger(path, now=noon()).record("haiku", input_tokens=1, output_tokens=2, seconds=0.1)
        self.assertEqual(
            set(json.loads(path.read_text(encoding="utf-8"))),
            {"day", "provider", "input", "output", "thought", "seconds", "outcome"},
        )

    def test_a_record_failure_logs_the_error_type_only(self):
        base = Path(tempfile.mkdtemp(dir=_TEMP.name))
        path = base / "secret-name-sk-123" / "model-usage.jsonl"
        path.parent.mkdir()
        path.mkdir()
        with self.assertLogs("ai_dnd.api.ollama", level="WARNING") as captured:
            UsageLedger(path, now=noon()).record("haiku", input_tokens=1, output_tokens=1)
        text = "\n".join(captured.output)
        self.assertNotIn("secret-name-sk-123", text)
        self.assertNotIn("haiku", text)
        self.assertIn("Error", text)


def ledger_path_text(ledger: UsageLedger) -> str:
    return ledger._path.read_text(encoding="utf-8")


class TheModule(unittest.TestCase):
    def test_the_default_clock_is_timezone_aware(self):
        ledger = UsageLedger(ledger_file())
        self.assertIsNotNone(ledger._now().tzinfo)

    def test_the_file_name_is_the_documented_one(self):
        self.assertEqual(usage_ledger.USAGE_FILE_NAME, "model-usage.jsonl")


if __name__ == "__main__":
    unittest.main()
