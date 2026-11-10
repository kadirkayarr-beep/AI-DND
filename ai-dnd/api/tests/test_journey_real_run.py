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
import shutil
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx

import front_proposal
from api import model_chain
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence import campaign_store
from api.tests.journeys import real_run
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedClient, StepResult
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
    def test_the_defaults_are_core_scenarios_three_runs_a_hundred_calls_and_no_spending(self):
        args = real_run.parse_args([])
        self.assertEqual((args.scenarios, args.runs, args.max_calls, args.yap), ("core", 3, 100, False))

    def test_without_yap_nothing_is_called_the_estimate_is_printed_and_the_exit_code_is_2(self):
        write_scenarios(self.scenarios, probe("01_a", 2), probe("02_b", 3), probe("03_c", 4, core=False))
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--out", str(self.out), chain=chain)
        self.assertEqual(code, 2)
        # Core only (two scenarios, 2 + 3 say steps, two engine calls each), three runs: 30 engine calls.
        self.assertIn("2 senaryo, 5 adım, 3 koşu: 30", printed)
        self.assertIn("--yap", printed)
        self.assertIsNone(chain.local, "the adapter was built without --yap")
        self.assertEqual(chain.cloud_requests, [])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertNotIn("AI_DND_MODEL_CHAIN", os.environ)

    def test_the_estimate_counts_engine_calls_two_a_say_step_and_three_a_conversation_turn(self):
        """Ruling R20: the estimate is engine calls, an upper bound: a say step makes at least two (reading and
        narration), a conversation turn three (the reply as well); a command, a card or combat button, an undo or a
        reload is played by the engine alone."""
        talk = {"id": "04_d", "title": "Konuşma", "real_chain_core": True, "steps": [
            {"say": "Marek, nasılsın?", "expect": {"kip": {"active": True}}},
            {"say": "Marek'e soruyorum", "script": {"spoken": "İyiyim."}},
            {"say": "etrafa bakıyorum", "expect": {"kip": {"active": False}}},
            {"command": "/item shop_buy barman bira 1 0 4"},
            {"economic_action": {"kind": "prepare"}},
            {"combat_action": {"kind": "attack"}},
            {"undo": True},
            {"reload": True},
        ]}
        write_scenarios(self.scenarios, probe("01_a", 2), probe("02_b", 3), probe("03_c", 4, core=False), talk)
        code, printed = self.run_command("--scenarios", "all", "--runs", "2")
        self.assertEqual(code, 2)
        self.assertIn(f"4 senaryo, 17 adım, 2 koşu: {((2 + 3 + 4) * 2 + 3 + 3 + 2) * 2}", printed)
        selection = real_run.select_scenarios("01_a,03_c", self.scenarios)
        self.assertEqual(real_run.estimate_calls(selection, 5), (2 + 4) * 2 * 5)
        self.assertEqual(real_run.estimate_calls(real_run.select_scenarios("04_d", self.scenarios), 1), 8)

    def test_a_cap_below_the_estimate_refuses_to_start_with_its_own_exit_code(self):
        write_scenarios(self.scenarios, probe("01_a", 2))
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--yap", "--out", str(self.out), "--max-calls", "11", chain=chain)
        self.assertEqual(code, real_run.EXIT_OVER_CAP)
        self.assertEqual(code, 3)  # not 2, which says the run was not asked for
        self.assertIn("--max-calls 11", printed)
        self.assertIn("12", printed)
        self.assertIsNone(chain.local, "the adapter was built although the cap was below the estimate")
        self.assertEqual(chain.cloud_requests, [])
        self.assertEqual(list(self.out.iterdir()), [])
        code, printed = self.run_command("--max-calls", "11")  # without --yap the estimate is told, the exit stays 2
        self.assertEqual(code, 2)
        self.assertIn("--max-calls", printed)

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

    def test_a_real_run_needs_an_out_folder_so_no_report_lands_where_the_command_was_started(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--yap", chain=chain)
        self.assertEqual(code, 1)
        self.assertIn("--out", printed)
        self.assertIsNone(chain.local, "the adapter was built without an out folder")
        self.assertEqual(chain.cloud_requests, [])

    def test_the_call_cap_is_told_as_engine_calls_not_provider_requests(self):
        text = real_run.build_parser().format_help()
        self.assertIn("motor", text)
        self.assertIn("sağlayıcı", text)

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
        # The estimate is an upper bound; the cap still holds inside the run if the engine makes more calls.
        with redirect_stdout(engine_lines), patch.object(real_run, "estimate_calls", return_value=3):
            # the engine prints its fallback line for each refused call
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

    def test_the_run_notes_and_the_screen_are_scrubbed_as_well(self):
        """Key-like text in a scenario id reaches the run notes after the report and the printed selection."""
        scenario = probe(f"01_{KEY_IN_NARRATION}", 1)
        scenario["steps"][0]["expect"]["savas"] = True  # a known break: the notes name the scenario
        scenario["steps"][0]["known_broken"] = [99]
        scenario["steps"][0]["broken_because"] = ["savas: beklenen True"]
        write_scenarios(self.scenarios, scenario)
        code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1", chain=FakeChain(self.folder))
        self.assertEqual(code, 0, printed)
        report = self.report()
        self.assertIn("bilinen kırık işaretli adımı olan senaryolar: 01_[gizlendi]", report)
        for text in (report, printed):
            self.assertIsNone(KEY_LIKE.search(text), KEY_LIKE.search(text))

    def test_a_report_that_cannot_be_built_leaves_a_raw_backup_of_the_run(self):
        write_scenarios(self.scenarios, probe("01_a", 2))
        with patch.object(real_run, "assemble_report", side_effect=ValueError("gecikme satırında saniye")):
            code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                             chain=FakeChain(self.folder))
        self.assertEqual(code, 1, printed)
        self.assertIn("ValueError", printed)
        (backup,) = self.out.iterdir()
        self.assertEqual(backup.name, "ADIM2_HAM_20261104.txt")
        self.assertIn(str(backup), printed)
        text = backup.read_text(encoding="utf-8")
        self.assertIn("01_a, 1. koşu", text)
        self.assertIn("adım 1: pass", text)
        self.assertIn("adım 2: pass", text)
        self.assertIn("Model çağrısı:", text)

    def test_an_out_folder_that_cannot_be_made_stops_the_run_before_any_call(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        blocked = self.folder / "not-a-folder"
        blocked.write_text("dosya", encoding="utf-8")
        chain = FakeChain(self.folder)
        code, printed = self.run_command("--yap", "--out", str(blocked / "rapor"), "--runs", "1", chain=chain)
        self.assertEqual(code, 1, printed)
        self.assertIn("rapor klasörü", printed)
        self.assertIsNone(chain.local)

    def test_a_raw_backup_goes_to_the_temporary_folder_when_the_out_folder_cannot_be_written(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        blocked = self.folder / "not-a-folder"
        blocked.write_text("dosya", encoding="utf-8")
        real_free_path = real_run._free_path

        def out_folder_gone(folder, *rest):  # the out folder fails after the run (a lost drive, a full disk)
            return blocked / "yok.md" if Path(folder) == self.out else real_free_path(folder, *rest)

        with patch.object(real_run, "_free_path", out_folder_gone):
            code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                             chain=FakeChain(self.folder))
        self.assertEqual(code, 1, printed)
        self.assertEqual(list(self.out.iterdir()), [])
        backups = [Path(line.split(": ", 1)[1]) for line in printed.splitlines() if line.startswith("Ham kayıt: ")]
        self.assertEqual(len(backups), 1, printed)
        self.addCleanup(backups[0].unlink)
        self.assertTrue(backups[0].resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()), backups[0])
        self.assertIn("01_a, 1. koşu", backups[0].read_text(encoding="utf-8"))

    def test_the_play_settings_turn_the_front_reading_on_and_leave_the_route_log_alone(self):
        """Local play reads the front with the flag on, so the real run does too; the flag is set directly (a value
        already set stays), never through the local-play helper that also points the route log at the owner's file."""
        write_scenarios(self.scenarios, probe("01_a", 1))
        for given, expected in ((None, "1"), ("0", "0")):
            with self.subTest(given=given), patch.object(
                    front_proposal, "default_on_for_local_play", side_effect=AssertionError("helper called")):
                os.environ.pop(front_proposal.FLAG, None)
                os.environ.pop(front_proposal.ROUTE_LOG, None)
                if given is not None:
                    os.environ[front_proposal.FLAG] = given
                code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                                 chain=FakeChain(self.folder))
                self.assertEqual(code, 0, printed)
                self.assertEqual(os.environ.get(front_proposal.FLAG), expected)
                self.assertNotIn(front_proposal.ROUTE_LOG, os.environ)
        self.assertEqual(real_run._PLAY_DEFAULTS[front_proposal.FLAG], "1")

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

    def test_a_seeded_scenario_plays_every_run_in_its_own_store_on_the_same_campaign_id(self):
        # A seeded scenario always creates the same campaign id; two runs in one store made the second one fail
        # ("Koşu bozuldu: AssertionError") and lose the first, paid run. Each run gets a fresh store, same seed.
        data = probe("01_a", 1)
        data["setup"] = {"campaign_seed": 74}
        write_scenarios(self.scenarios, data)
        made: list[str] = []
        original = JourneyCase._journey_campaign

        async def recording(case, setup):
            campaign = await original(case, setup)
            made.append(campaign["campaign_id"])
            return campaign

        with patch.object(JourneyCase, "_journey_campaign", recording):
            code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "2",
                                             chain=FakeChain(self.folder))
        self.assertEqual(code, 0, printed)
        self.assertIn("- 01_a: 2 üzerinden 2", self.report())
        self.assertEqual(len(made), 2, made)
        self.assertEqual(made[0], made[1])
        self.assertTrue(made[0].endswith("000000000074"), made[0])

    def test_a_run_that_breaks_after_an_earlier_one_finished_still_leaves_the_raw_record_and_the_failing_frame(self):
        write_scenarios(self.scenarios, probe("01_a", 2))
        original = JourneyCase.run_scenario
        calls = []

        async def second_breaks(case, scenario, *, model=None):
            calls.append(scenario.id)
            if len(calls) == 2:
                raise RuntimeError("gizli ileti SECRET-MESSAGE")
            return await original(case, scenario, model=model)

        with patch.object(JourneyCase, "run_scenario", second_breaks):
            code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "2",
                                             chain=FakeChain(self.folder))
        self.assertEqual(code, 1, printed)
        self.assertIn("Koşu bozuldu: RuntimeError", printed)
        self.assertNotIn("SECRET-MESSAGE", printed)
        self.assertRegex(printed, r"test_journey_real_run\.py:\d+")
        (backup,) = self.out.iterdir()
        self.assertEqual(backup.name, "ADIM2_HAM_20261104.txt")
        self.assertIn(str(backup), printed)
        text = backup.read_text(encoding="utf-8")
        self.assertIn("01_a, 1. koşu", text)
        self.assertNotIn("SECRET-MESSAGE", text)

    def test_a_skipped_run_is_a_broken_run_not_an_empty_report(self):
        write_scenarios(self.scenarios, probe("01_a", 1))

        async def skipped(case):
            raise unittest.SkipTest("journey case skipped")

        with patch.object(JourneyCase, "asyncSetUp", skipped):
            code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                             chain=FakeChain(self.folder))
        self.assertEqual(code, 1, printed)
        self.assertIn("Koşu bozuldu", printed)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_a_scenario_with_a_known_break_is_said_to_count_the_engine_not_only_the_chain(self):
        scenario = probe("01_a", 1)
        scenario["steps"][0]["expect"]["savas"] = True  # really broken: looking around starts no fight
        scenario["steps"][0]["known_broken"] = [99]
        write_scenarios(self.scenarios, scenario)
        code, printed = self.run_command("--yap", "--out", str(self.out), "--runs", "1",
                                         chain=FakeChain(self.folder))
        self.assertEqual(code, 0, printed)
        report = self.report()
        self.assertIn("- 01_a: 1 üzerinden 0 (eksik: 3 koşu beklenir)", report)
        notes = report.split("## Gerçek zincir koşusu", 1)[1]
        self.assertIn("bilinen kırık işaretli adımı olan senaryolar: 01_a", notes)

    def test_no_real_chain_in_the_environment_means_no_run(self):
        write_scenarios(self.scenarios, probe("01_a", 1))
        printed = io.StringIO()
        code = real_run.main(["--yap", "--out", str(self.out)], out=printed, scenario_dir=self.scenarios,
                             today=TODAY, make_adapter=lambda: None)
        self.assertEqual(code, 1)
        self.assertIn("gerçek zincir kurulamadı", printed.getvalue())
        self.assertEqual(list(self.out.iterdir()), [])


def _step(index, *failures):
    return StepResult(index=index, status="new_break" if failures else "pass", failures=tuple(failures),
                      items=(), narration="", seconds=0.0)


def write_ambient_scenario() -> Path:
    folder = Path(tempfile.mkdtemp())
    unittest.addModuleCleanup(shutil.rmtree, folder, ignore_errors=True)
    data = {"id": "01_ambient", "title": "Ortam", "steps": [{"ambient": {"action": "interact"}}]}
    path = folder / "01_ambient.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TheCallEstimate(unittest.TestCase):
    def test_an_ambient_step_costs_no_model_call(self):
        step = load_scenario(write_ambient_scenario()).steps[0]
        self.assertEqual(step.ambient, {"action": "interact"})
        self.assertEqual(real_run._step_calls(step), 0)


class TheZeroToleranceList(Offline):
    """J-014 #10 (tasarım karar 63): one zero-tolerance break in any run is listed and exits with 4."""

    def played(self, *, broken: bool) -> real_run.Played:
        played = real_run.Played()
        if broken:
            played.complete["rc6_quest_delivery_real"] = [
                [_step(1), _step(4)],                                                   # run 1: clean
                [_step(1), _step(4, "kese: 112 bekleniyordu, 100 var")],                # run 2: a functional miss only
                [_step(1), _step(4, "sıfır tolerans: izinli durumların hiçbiri tutmadı (x | y)")],   # run 3: a break
            ]
        played.complete["rc7_absent_vendor_real"] = [[_step(3)], [_step(3)], [_step(3)]]
        return played

    def selection(self):
        write_scenarios(self.scenarios, probe("rc6_quest_delivery_real", 4), probe("rc7_absent_vendor_real", 3))
        return real_run.select_scenarios("all", self.scenarios)

    def report_for(self, played):
        driver = real_run.RealChain(100)
        return real_run.assemble_report(self.selection(), played, driver, real_run.parse_args([]), TODAY)

    def main_exit_code(self, played):
        self.selection()
        with patch.object(real_run, "play", return_value=played):
            code, _ = self.run_command("--yap", "--scenarios", "all", "--out", str(self.out), "--max-calls", "500",
                                       chain=FakeChain(self.folder))
        return code

    def test_a_zero_tolerance_break_in_any_run_is_listed_and_exits_4(self):
        played = self.played(broken=True)
        self.assertEqual(real_run.zero_tolerance_breaks(played),
                         ["rc6_quest_delivery_real koşu 3 adım 4: sıfır tolerans: izinli durumların hiçbiri tutmadı (x | y)"])
        clean = self.played(broken=False)
        self.assertEqual(real_run.zero_tolerance_breaks(clean), [])
        report = self.report_for(played)
        self.assertIn("## Sıfır tolerans ihlalleri\n- rc6_quest_delivery_real koşu 3 adım 4: sıfır tolerans:", report)
        self.assertIn("## Sıfır tolerans ihlalleri\nyok", self.report_for(clean))
        self.assertEqual(self.main_exit_code(played), 4)
        for path in self.out.iterdir():
            path.unlink()
        self.assertEqual(self.main_exit_code(clean), 0)


class TheCoreSet(Offline):
    """The default real-chain set is the design's four (spec §5): price recall (36), consistency after payment
    (2), the narrator matching the engine when there is no weapon to strike with (39), a fight started by a
    headbutt with its latency (8, 19). Each says something about the chain alone."""

    CORE = {
        "rc1_price_recall": (36,),
        "rc2_paid_consistency": (2,),
        "rc3_refusal_narration": (39,),
        "rc4_headbutt_start": (8, 19),
    }
    STATE_KEYS = {"kese", "envanter", "kip", "savas", "kisi_kese", "tezgah", "oda"}

    def core(self):
        return real_run.select_scenarios("core", SCENARIO_DIR)

    def test_the_core_set_is_the_four_real_chain_journeys_of_the_design(self):
        core = self.core()
        self.assertEqual(set(core), set(self.CORE))
        for key, items in self.CORE.items():
            self.assertEqual(core[key].source_items, items, key)
        self.assertFalse(load_scenario(SCENARIO_DIR / "05_greatsword.json").real_chain_core,
                         "05 checks the engine's weapon (item 39), not the narrator against a refusal")
        printed = io.StringIO()
        self.assertEqual(real_run.main([], out=printed, scenario_dir=SCENARIO_DIR), 2)
        steps = sum(len(scenario.steps) for scenario in core.values())
        # rc1 2+3+3+3, rc2 2+3+3, rc3 2+2+2, rc4 2+2 engine calls (their commands are the engine's), three runs.
        self.assertEqual(real_run.estimate_calls(core, 3), 87)
        self.assertLessEqual(real_run.estimate_calls(core, 3), real_run.DEFAULT_MAX_CALLS)
        self.assertIn(f"4 senaryo, {steps} adım, 3 koşu: 87", printed.getvalue())

    def test_a_core_journey_carries_no_known_break_so_its_ratio_is_the_chains(self):
        for key, scenario in self.core().items():
            for number, step in enumerate(scenario.steps, start=1):
                self.assertEqual(step.known_broken, (), f"{key} adım {number}")

    def test_every_real_chain_step_checks_the_state_and_its_forbidden_text_is_short_and_plain(self):
        for key, scenario in self.core().items():
            chain_steps = [step for step in scenario.steps if step.real_chain]
            self.assertTrue(chain_steps, f"{key}: no step for the real chain alone")
            for number, step in enumerate(scenario.steps, start=1):
                where = f"{key} adım {number}"
                self.assertTrue(set(step.expect) & self.STATE_KEYS, f"{where}: no state check")
                needles = step.expect.get("yasak_metin", [])
                self.assertLessEqual(len(needles), 4, where)
                for needle in needles:
                    self.assertLessEqual(len(needle.split()), 3, f"{where}: {needle}")
            self.assertTrue(any("yasak_metin" in step.expect for step in chain_steps), key)

    def test_the_core_journeys_play_every_step_through_the_real_chain_path_offline(self):
        chain = FakeChain(self.folder)
        driver = real_run.build_driver(500, chain.make_adapter)
        self.assertIsNotNone(driver)
        played = real_run.play(self.core(), 1, driver)
        self.assertIsNone(played.error)
        self.assertIsNone(played.cut)
        self.assertEqual(set(played.complete), set(self.CORE))
        for key, (steps,) in played.complete.items():
            for step in steps:
                where = f"{key} adım {step.index}: {step.failures}"
                self.assertNotEqual(step.status, "unreached", where)
                self.assertFalse(any(failure.startswith(("HTTP ", "beklenmeyen model çağrısı"))
                                     for failure in step.failures), where)
        self.assertGreater(chain.local.calls, 0)


if __name__ == "__main__":
    unittest.main()
