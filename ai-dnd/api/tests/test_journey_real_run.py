"""The real-chain journey command: it spends only when told to (``--yap``), stops at its call cap, keeps the
owner's save and keys out of everything, and writes the Turkish report.

No test here reaches a real model: the "real" chain is the product's own ``ModelChain`` and adapter on a mock
transport whose cloud provider always answers 500, so every call is a skipped cloud attempt followed by the
scripted local model. Outside sockets are off throughout.
"""

from __future__ import annotations

import io
import json
import os
import re
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx

from api import model_chain
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence import campaign_store
from api.tests.journeys import real_run
from api.tests.journeys.runner import SCENARIO_DIR, ScriptedClient
from api.tests.journeys.schema import ScenarioError, load_scenario
from api.usage_ledger import UsageLedger

FAKE_KEY = "AIzaFAKE-test-key-0000000000000000"
KEY_IN_NARRATION = "sk-ant-api03-FAKEFAKEFAKEFAKEFAKE"
KEY_LIKE = re.compile(r"AIza|sk-ant-|sk-[A-Za-z0-9_-]{16,}")
TODAY = date(2026, 11, 4)


def write_scenarios(folder: Path, *scenarios: dict) -> Path:
    for data in scenarios:
        (folder / f"{data['id']}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return folder


def probe(scenario_id: str, steps: int, *, core: bool = True) -> dict:
    """A small journey any campaign can play: look around and wait, no fight starts."""
    return {
        "id": scenario_id,
        "title": f"Deneme {scenario_id}",
        "real_chain_core": core,
        "steps": [{"say": "etrafa bakıyorum", "expect": {"savas": False}} for _ in range(steps)],
    }


class FakeChain:
    """The product's chain and adapter, offline: Gemini answers 500 on a mock transport, a scripted model
    answers locally. ``make_adapter`` is what the command calls in place of reading the environment."""

    def __init__(self, folder: Path, *, narration: str = "Sokak sessiz."):
        self.folder = folder
        self.narration = narration
        self.cloud_requests: list[httpx.Request] = []
        self.local = None

    def answer(self, request: httpx.Request) -> httpx.Response:
        self.cloud_requests.append(request)
        return httpx.Response(500, json={"error": "fake"})

    def make_adapter(self) -> AuthenticatedOllamaAdapter:
        ledger_path = self.folder / "usage" / "model-usage.jsonl"
        chain = model_chain.ModelChain(
            [model_chain.gemini(FAKE_KEY)],
            transport=httpx.MockTransport(self.answer),
            # Through the module, as model_chain.from_environment does it, so the command can listen in.
            observer=model_chain.ledger_observer(UsageLedger(ledger_path)),
        )
        self.local = CountingClient({"narration": self.narration})
        adapter = AuthenticatedOllamaAdapter(self.local, chain=chain)
        adapter.usage_ledger = UsageLedger(ledger_path)
        return adapter


class CountingClient(ScriptedClient):
    def __init__(self, script):
        super().__init__(script)
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        return super().chat(*args, **kwargs)


class Offline(unittest.TestCase):
    """No outside socket, no key file, no environment chain: any of these is a test failure."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.out = self.folder / "out"
        self.out.mkdir()
        self.scenarios = self.folder / "scenarios"
        self.scenarios.mkdir()
        for target, name in ((model_chain, "_read_key"), (model_chain, "from_environment"),
                             (AuthenticatedOllamaAdapter, "from_environment")):
            patcher = patch.object(target, name, side_effect=AssertionError(f"{name} must not run here"))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(socket.socket, "connect",
                               side_effect=AssertionError("External network is disabled in journey tests."))
        patcher.start()
        self.addCleanup(patcher.stop)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)

    def run_command(self, *argv: str, chain: FakeChain | None = None) -> tuple[int, str]:
        printed = io.StringIO()
        code = real_run.main(
            list(argv), out=printed, scenario_dir=self.scenarios, today=TODAY,
            make_adapter=None if chain is None else chain.make_adapter,
        )
        return code, printed.getvalue()

    def report(self) -> str:
        reports = sorted(self.out.glob("ADIM2_RAPOR_*.md"))
        self.assertEqual(len(reports), 1, [path.name for path in reports])
        self.assertEqual(reports[0].name, "ADIM2_RAPOR_20261104.md")
        return reports[0].read_text(encoding="utf-8")


class TheGate(Offline):
    def test_the_defaults_are_core_scenarios_three_runs_sixty_calls_and_no_spending(self):
        args = real_run.parse_args([])
        self.assertEqual((args.scenarios, args.runs, args.max_calls, args.yap), ("core", 3, 60, False))

    def test_without_yap_nothing_is_called_the_estimate_is_printed_and_the_exit_code_is_2(self):
        write_scenarios(self.scenarios, probe("01_a", 2), probe("02_b", 3), probe("03_c", 4, core=False))
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--out", str(self.out), chain=chain)
        self.assertEqual(code, 2)
        # Core only (two scenarios, 2 + 3 steps), three runs: 15 step turns.
        self.assertIn("2 senaryo × 5 adım × 3 koşu = 15", printed)
        self.assertIn("--yap", printed)
        self.assertIsNone(chain.local, "the adapter was built without --yap")
        self.assertEqual(chain.cloud_requests, [])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertNotIn("AI_DND_MODEL_CHAIN", os.environ)

    def test_the_estimate_is_scenarios_times_steps_times_runs(self):
        write_scenarios(self.scenarios, probe("01_a", 2), probe("02_b", 3), probe("03_c", 4, core=False))
        code, printed = self.run_command("--scenarios", "all", "--runs", "2")
        self.assertEqual(code, 2)
        self.assertIn("3 senaryo × 9 adım × 2 koşu = 18", printed)
        selection = real_run.select_scenarios("01_a,03_c", self.scenarios)
        self.assertEqual(real_run.estimate_calls(selection, 5), (2 + 4) * 5)

    def test_core_means_the_scenarios_flagged_real_chain_core(self):
        write_scenarios(self.scenarios, probe("01_a", 1), probe("02_b", 1, core=False))
        self.assertEqual(list(real_run.select_scenarios("core", self.scenarios)), ["01_a"])
        self.assertEqual(list(real_run.select_scenarios("all", self.scenarios)), ["01_a", "02_b"])
        self.assertEqual(list(real_run.select_scenarios("02_b", self.scenarios)), ["02_b"])
        with self.assertRaises(ScenarioError):
            real_run.select_scenarios("02_b,99_missing", self.scenarios)

    def test_the_repository_core_set_is_the_flagged_files(self):
        core = real_run.select_scenarios("core", SCENARIO_DIR)
        self.assertTrue(core)
        flagged = {path.stem for path in SCENARIO_DIR.glob("*.json") if load_scenario(path).real_chain_core}
        self.assertEqual(set(core), flagged)

    def test_an_unknown_scenario_id_is_refused_without_spending(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--scenarios", "99_missing", "--yap", "--out", str(self.out), chain=chain)
        self.assertEqual(code, 1)
        self.assertIn("99_missing", printed)
        self.assertIsNone(chain.local)
        self.assertEqual(list(self.out.iterdir()), [])


class TheRealRun(Offline):
    def test_a_full_run_writes_the_report_with_three_runs_latency_and_skip_reasons(self):
        write_scenarios(self.scenarios, probe("01_a", 2))
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--yap", "--out", str(self.out), "--max-calls", "500", chain=chain)
        self.assertEqual(code, 0, printed)
        report = self.report()
        self.assertTrue(report.startswith("# Adım 2 raporu (2026-11-04)"), report[:80])
        self.assertIn("- 01_a: 3 üzerinden 3", report)
        latency = report.split("## Gecikme", 1)[1].split("\n## ", 1)[0]
        # The chain observer gives the cloud attempt; the adapter's timing gives the local answer and the whole call.
        for provider in ("gemini", "yerel", "toplam"):
            self.assertIn(f"| {provider} |", latency)
        self.assertIn("01_a adım 1 (", latency)
        self.assertIn("| gemini | http_500 |", report)
        self.assertIn("## Harcama", report)
        self.assertGreater(chain.local.calls, 0)
        self.assertEqual(len(chain.cloud_requests), chain.local.calls)
        self.assertIn(str(self.out / "ADIM2_RAPOR_20261104.md"), printed)

    def test_the_call_cap_stops_the_run_early_and_the_report_is_still_written(self):
        write_scenarios(self.scenarios, probe("01_a", 3), probe("02_b", 3))
        chain = FakeChain(self.folder)
        engine_lines = io.StringIO()
        with redirect_stdout(engine_lines):  # the engine prints its fallback line for each refused call
            code, printed = self.run_command("--yap", "--scenarios", "all", "--out", str(self.out),
                                             "--max-calls", "3", chain=chain)
        self.assertEqual(code, 0, printed)
        self.assertIn("_CallCapReached", engine_lines.getvalue())
        self.assertLessEqual(chain.local.calls, 3)
        self.assertLessEqual(len(chain.cloud_requests), 3)
        report = self.report()
        self.assertIn("--max-calls sınırına (3) ulaşıldı", report)
        self.assertIn("--max-calls", printed)
        # The cut run is not a run of three: no "3 üzerinden" for a scenario the cap cut.
        self.assertNotIn("3 üzerinden", report)
        self.assertIn("--max-calls sınırı", report.split("## Ham adım kaydı", 1)[1])

    def test_no_key_like_text_reaches_the_report_or_the_screen(self):
        # Key-like text in a title, in a failure (the missing required text) and in the model's narration.
        scenario = probe("01_a", 1)
        scenario["title"] = f"Anahtar başlıkta: {KEY_IN_NARRATION}"
        scenario["steps"][0]["expect"]["gerekli_metin"] = FAKE_KEY
        write_scenarios(self.scenarios, scenario)
        chain = FakeChain(self.folder, narration=f"Anahtar burada: {KEY_IN_NARRATION} ve {FAKE_KEY}")
        code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1", chain=chain)
        self.assertEqual(code, 0, printed)
        report = self.report()
        self.assertIn("Anahtar başlıkta: [gizlendi]", report)
        self.assertIn("gerekli metin bulunamadı: [gizlendi]", report)
        for text in (report, printed):
            self.assertNotIn(FAKE_KEY, text)
            self.assertNotIn(KEY_IN_NARRATION, text)
            self.assertIsNone(KEY_LIKE.search(text), KEY_LIKE.search(text))

    def test_the_campaign_lives_in_a_temporary_store_never_the_owners_save(self):
        owner_save = self.folder / "AI-DND" / "local-play.sqlite3"
        os.environ["AI_DND_CAMPAIGN_DB"] = str(owner_save)
        opened: list[Path] = []
        real_init = campaign_store.CampaignStore.__init__

        def recording_init(store, path, *args, **kwargs):
            opened.append(Path(path))
            real_init(store, path, *args, **kwargs)

        write_scenarios(self.scenarios, probe("01_a", 1))
        with patch.object(campaign_store.CampaignStore, "__init__", recording_init):
            code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                             chain=FakeChain(self.folder))
        self.assertEqual(code, 0, printed)
        self.assertTrue(opened)
        self.assertFalse(owner_save.exists())
        self.assertFalse(owner_save.parent.exists())
        temporary_root = Path(tempfile.gettempdir()).resolve()
        for path in opened:
            self.assertNotEqual(path.name, "local-play.sqlite3")
            self.assertTrue(path.resolve().is_relative_to(temporary_root), path)
        self.assertNotIn("AI_DND_CAMPAIGN_DB", os.environ)

    def test_a_second_report_on_the_same_day_does_not_overwrite_the_first(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        (self.out / "ADIM2_RAPOR_20261104.md").write_text("önceki", encoding="utf-8")
        code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                         chain=FakeChain(self.folder))
        self.assertEqual(code, 0, printed)
        self.assertEqual((self.out / "ADIM2_RAPOR_20261104.md").read_text(encoding="utf-8"), "önceki")
        self.assertTrue((self.out / "ADIM2_RAPOR_20261104_2.md").exists())

    def test_no_real_chain_in_the_environment_means_no_run(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        printed = io.StringIO()
        code = real_run.main(["--yap", "--out", str(self.out)], out=printed, scenario_dir=self.scenarios,
                             today=TODAY, make_adapter=lambda: None)
        self.assertEqual(code, 1)
        self.assertIn("gerçek zincir kurulamadı", printed.getvalue())
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
