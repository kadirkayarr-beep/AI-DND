"""The Turkish journey report: counts, known breaks by kind and item, the three-run ratio, latency, spend."""

from __future__ import annotations

import unittest

from api.model_chain import ChainAttempt
from api.tests.journeys.report import _kind as report_kind
from api.tests.journeys.report import build_report, latency_row, real_run_flags, scrub
from api.tests.journeys.runner import SCENARIO_DIR, StepResult, summary_line
from api.tests.journeys.schema import Scenario, Step

DATE = "2026-11-04"


def step(say="merhaba", *, known_broken=(), real_chain=False):
    return Step(say=say, command=None, economic_action=None, combat_action=None, script=None, expect={},
                known_broken=tuple(known_broken), real_chain=real_chain, independent=False)


def scenario(scenario_id, steps=None, *, title=None, items=(), zero_tolerance=False, core=False):
    return Scenario(id=scenario_id, title=title or f"Başlık {scenario_id}", source_items=tuple(items),
                    zero_tolerance=zero_tolerance, real_chain_core=core, setup={},
                    steps=tuple(steps if steps is not None else [step()]))


def result(index, status="pass", *, failures=(), items=(), narration="", seconds=0.5, reading=""):
    return StepResult(index, status, tuple(failures), tuple(items), narration, seconds, reading)


def three_scenarios():
    """02 passes, 03 is known broken for 37 and 38, 06 has a new break."""
    scenarios = {
        "02_beer_tip": scenario("02_beer_tip", [step()], items=[35]),
        "03_room_sleep": scenario("03_room_sleep", [step(), step(known_broken=[37]), step(known_broken=[38])],
                                  items=[37, 38]),
        "06_combat_actions": scenario("06_combat_actions", [step()], items=[40]),
    }
    results = {
        "02_beer_tip": [result(1)],
        "03_room_sleep": [
            result(1),
            result(2, "known_broken", failures=["kese: beklenen 5, görülen 6"], items=[37]),
            result(3, "known_broken", failures=["oda: beklenen var"], items=[38]),
        ],
        "06_combat_actions": [result(1, "new_break", failures=["savaş: beklenen true"])],
    }
    return results, scenarios


class ReportCountsTest(unittest.TestCase):
    def test_report_counts_known_broken_separately(self):
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, date=DATE)
        self.assertIn("1 geçti, 1 bilinen kırık, 1 yeni kırık", report)
        self.assertIn(DATE, report)

    def test_report_lists_item_numbers_per_known_break(self):
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, date=DATE)
        known = report.split("## Bilinen kırıklar", 1)[1].split("\n## ", 1)[0]
        self.assertIn("madde 37", known)
        self.assertIn("madde 38", known)
        self.assertIn("03_room_sleep", known)
        self.assertIn("kese: beklenen 5, görülen 6", known)
        # A passing or newly broken scenario is not in the known-break list.
        self.assertNotIn("02_beer_tip", known)
        self.assertNotIn("06_combat_actions", known)

    def test_a_known_break_lists_every_failure_of_its_step(self):
        failures = ['HTTP 400: {"detail":{"code":"no_ammunition"}}', "savas: beklenen True, gözlenen False",
                    "cephane: beklenen {'arrow': 19}, gözlenen {}"]
        scenarios = {"04_consume": scenario("04_consume", [step(known_broken=[56])])}
        results = {"04_consume": [result(1, "known_broken", items=[56], failures=failures)]}
        known = build_report(results, scenarios, date=DATE).split("## Bilinen kırıklar", 1)[1].split("\n## ", 1)[0]
        (line,) = [line for line in known.splitlines() if "04_consume" in line]
        for failure in failures:
            self.assertIn(failure, line)

    def test_the_scenario_table_names_each_outcome(self):
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, date=DATE)
        table = report.split("## Senaryolar", 1)[1].split("\n## ", 1)[0]
        row = {line.split("|")[1].strip(): line for line in table.splitlines() if line.startswith("| 0")}
        self.assertIn("geçti", row["02_beer_tip"])
        self.assertIn("bilinen kırık", row["03_room_sleep"])
        self.assertIn("37", row["03_room_sleep"])
        self.assertIn("YENİ KIRIK", row["06_combat_actions"])
        self.assertIn("1/3", row["03_room_sleep"])

    def test_a_new_break_in_a_zero_tolerance_scenario_is_flagged(self):
        scenarios = {"11_undo_reload": scenario("11_undo_reload", zero_tolerance=True)}
        results = {"11_undo_reload": [result(1, "new_break", failures=["kese değişti"])]}
        report = build_report(results, scenarios, date=DATE)
        self.assertIn("sıfır tolerans", report)

    def test_known_breaks_are_grouped_by_kind(self):
        scenarios = {
            "02_beer_tip": scenario("02_beer_tip", [step(known_broken=[35])]),
            "09c_escape_start_scene": scenario("09c_escape_start_scene", [step(known_broken=[21])]),
            "99_unlisted": scenario("99_unlisted", [step(known_broken=[1])]),
        }
        results = {
            "02_beer_tip": [result(1, "known_broken", items=[35], failures=["a"])],
            "09c_escape_start_scene": [result(1, "known_broken", items=[21], failures=["b"])],
            "99_unlisted": [result(1, "known_broken", items=[1], failures=["c"])],
        }
        known = build_report(results, scenarios, date=DATE).split("## Bilinen kırıklar", 1)[1]
        money = known.index("### Para ve alışveriş")
        escape = known.index("### Kaçış, ölüm ve sonuçları")
        other = known.index("### Diğer")
        self.assertLess(money, known.index("02_beer_tip"))
        self.assertLess(known.index("02_beer_tip"), escape)
        self.assertLess(escape, known.index("09c_escape_start_scene"))
        self.assertLess(known.index("09c_escape_start_scene"), other)
        self.assertLess(other, known.index("99_unlisted"))

    def test_every_numbered_scenario_file_has_a_kind_and_money_with_records_stand_apart(self):
        """The kind table is keyed by file number: a numbered scenario file left out of it would fall under "Diğer".
        The owner's money and record mistakes (a refused coin charged, a room line paying a job, a doubled quest
        item) are counted in their own group, apart from the plain purchases."""
        numbered = sorted(path.stem for path in SCENARIO_DIR.glob("*.json") if path.stem[:1].isdigit())
        self.assertTrue(numbered)
        self.assertEqual([name for name in numbered if report_kind(name) == "Diğer"], [])
        self.assertEqual({report_kind(name) for name in ("17_refused_gift_not_charged", "18_room_phrase_not_job",
                                                         "19_quest_item_no_duplicate", "19b_quest_item_name_dotted_i",
                                                         "19c_quest_log_one_source", "19d_delivery_undo",
                                                         "19e_take_quest_item_variants", "29_trail_follow_on",
                                                         "36_messenger_chain", "41_is_haberi_sokakta")},
                         {"Para ve kayıt"})
        self.assertEqual(report_kind("23_no_shop_in_combat"), "Para ve alışveriş")
        self.assertEqual(report_kind("08b_talk_mode_front"), "Konuşma kipi")
        self.assertEqual(report_kind("09d_escape_in_inn"), "Kaçış, ölüm ve sonuçları")
        self.assertEqual({report_kind(name) for name in ("20_xp_after_win", "21_spell_target_in_melee",
                                                         "22_one_counter_per_move", "22b_counter_told_in_order")},
                         {"Savaş eylemleri"})

    def test_the_street_job_news_journey_has_its_kind(self):
        self.assertEqual(report_kind("41_is_haberi_sokakta"), "Para ve kayıt")

    def test_a_stale_marker_and_an_unreached_scenario_are_not_counted_as_breaks(self):
        scenarios = {
            "04_consume": scenario("04_consume", [step(known_broken=[54])]),
            "10_death": scenario("10_death", [step(real_chain=True)]),
        }
        results = {
            "04_consume": [result(1, "marker_stale", items=[54])],
            "10_death": [result(1, "unreached", failures=["gerçek zincir adımı; sahte modelde koşulmadı"])],
        }
        report = build_report(results, scenarios, date=DATE)
        self.assertIn("0 bilinen kırık, 0 yeni kırık", report)
        self.assertIn("işaret kaldırılmalı", report)
        self.assertIn("1 koşulmadı", report)

    def test_a_scenario_with_no_result_is_listed_as_not_run(self):
        scenarios = {"02_beer_tip": scenario("02_beer_tip")}
        report = build_report({}, scenarios, date=DATE)
        self.assertIn("1 koşulmadı", report)
        self.assertIn("02_beer_tip", report)

    def test_a_result_without_its_scenario_is_refused(self):
        with self.assertRaises(ValueError):
            build_report({"x": [result(1)]}, {}, date=DATE)

    def test_the_report_never_says_accepted(self):
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, real_runs={"02_beer_tip": [1, 1, 1]}, date=DATE)
        self.assertNotIn("kabul edildi", report.lower())


class RealRunTest(unittest.TestCase):
    def test_report_shows_three_run_ratio(self):
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, real_runs={"02_beer_tip": [1, 0, 1]}, date=DATE)
        section = report.split("## Gerçek zincir", 1)[1].split("\n## ", 1)[0]
        self.assertIn("02_beer_tip", section)
        self.assertIn("3 üzerinden 2", section)

    def test_fewer_than_three_runs_are_said_to_be_short(self):
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, real_runs={"02_beer_tip": [1], "03_room_sleep": [1, 0, 1]},
                              date=DATE)
        section = report.split("## Gerçek zincir", 1)[1].split("\n## ", 1)[0]
        self.assertIn("- 02_beer_tip: 1 üzerinden 1 (eksik: 3 koşu beklenir)", section.splitlines())
        self.assertIn("- 03_room_sleep: 3 üzerinden 2", section.splitlines())

    def test_core_scenarios_without_runs_are_named(self):
        scenarios = {"16_past_tense": scenario("16_past_tense", core=True)}
        report = build_report({"16_past_tense": [result(1)]}, scenarios, date=DATE)
        section = report.split("## Gerçek zincir", 1)[1].split("\n## ", 1)[0]
        self.assertIn("16_past_tense", section)
        self.assertIn("koşulmadı", section)

    def test_no_real_runs_at_all_is_said_plainly(self):
        results, scenarios = three_scenarios()
        section = build_report(results, scenarios, date=DATE).split("## Gerçek zincir", 1)[1].split("\n## ", 1)[0]
        self.assertIn("koşulmadı", section)

    def test_a_run_outcome_must_be_zero_or_one(self):
        results, scenarios = three_scenarios()
        with self.assertRaises(ValueError):
            build_report(results, scenarios, real_runs={"02_beer_tip": [1, 2]}, date=DATE)


class ProducerContractTest(unittest.TestCase):
    """What the real-chain command feeds the builder: pinned here so both sides use one shape."""

    def test_headline_counts_agree_with_the_runner_summary_line(self):
        results, scenarios = three_scenarios()
        headline = build_report(results, scenarios, date=DATE).splitlines()[2].strip("*")
        self.assertEqual(headline, summary_line(results))

    def test_a_chain_attempt_becomes_one_latency_row_skipped_attempts_included(self):
        skipped = ChainAttempt("gemini", "skipped", "http_500", 20.25, 0, 0, 0)
        answered = ChainAttempt("haiku", "answered", None, 3.5, 100, 20, 0)
        rows = [latency_row("bira/1", skipped), latency_row("bira/1", answered)]
        self.assertEqual(rows, [{"step": "bira/1", "provider": "gemini", "seconds": 20.25},
                                {"step": "bira/1", "provider": "haiku", "seconds": 3.5}])
        results, scenarios = three_scenarios()
        section = build_report(results, scenarios, latency=rows, date=DATE).split("## Gecikme", 1)[1] \
            .split("\n## ", 1)[0]
        self.assertIn("20,25", section)
        self.assertIn("3,5", section)

    def test_real_run_flags_encode_a_passed_run_as_one(self):
        flags = real_run_flags([True, False, True])
        self.assertEqual(flags, [1, 0, 1])
        results, scenarios = three_scenarios()
        report = build_report(results, scenarios, real_runs={"02_beer_tip": flags}, date=DATE)
        self.assertIn("3 üzerinden 2", report)

    def test_real_run_flags_refuse_anything_but_a_bool(self):
        for bad in ([1, 0], ["geçti"], [None]):
            with self.assertRaises(ValueError):
                real_run_flags(bad)


class LatencyAndSpendTest(unittest.TestCase):
    def test_report_says_not_found_when_no_latency_source(self):
        results, scenarios = three_scenarios()
        for latency in (None, []):
            report = build_report(results, scenarios, latency=latency, date=DATE)
            section = report.split("## Gecikme", 1)[1].split("\n## ", 1)[0]
            self.assertIn("bulunamadı", section)

    def test_latency_table_has_median_and_worst_per_step_and_provider(self):
        results, scenarios = three_scenarios()
        latency = [
            {"step": "bira/1", "provider": "gemini", "seconds": 2.0},
            {"step": "bira/1", "provider": "gemini", "seconds": 4.0},
            {"step": "bira/1", "provider": "gemini", "seconds": 30.5},
            {"step": "bira/1", "provider": "gemma", "seconds": 8.0},
        ]
        section = build_report(results, scenarios, latency=latency, date=DATE).split("## Gecikme", 1)[1] \
            .split("\n## ", 1)[0]
        self.assertNotIn("bulunamadı", section)
        gemini = next(line for line in section.splitlines() if "gemini" in line and line.startswith("|"))
        self.assertIn("bira/1", gemini)
        self.assertIn("4,0", gemini)
        self.assertIn("30,5", gemini)
        gemma = next(line for line in section.splitlines() if "gemma" in line and line.startswith("|"))
        self.assertIn("8,0", gemma)

    def test_a_malformed_latency_row_is_refused(self):
        results, scenarios = three_scenarios()
        with self.assertRaises(ValueError):
            build_report(results, scenarios, latency=[{"step": "a", "provider": "b"}], date=DATE)
        with self.assertRaises(ValueError):
            build_report(results, scenarios, latency=[{"step": "a", "provider": "b", "seconds": "x"}], date=DATE)

    def test_spend_summary_lists_each_provider(self):
        results, scenarios = three_scenarios()
        usage = {"gemini": {"calls": 12, "input": 3400, "output": 800, "thought": 1500, "seconds": 41.2},
                 "haiku": {"calls": 3, "input": 900, "output": 120, "thought": 0, "seconds": 5.0}}
        section = build_report(results, scenarios, usage_today=usage, date=DATE).split("## Harcama", 1)[1] \
            .split("\n## ", 1)[0]
        gemini = next(line for line in section.splitlines() if "gemini" in line)
        self.assertIn("12", gemini)
        self.assertIn("3400", gemini)
        self.assertIn("1500", gemini)
        self.assertIn("haiku", section)

    def test_spend_without_a_ledger_is_said_plainly(self):
        results, scenarios = three_scenarios()
        section = build_report(results, scenarios, date=DATE).split("## Harcama", 1)[1].split("\n## ", 1)[0]
        self.assertIn("kayıt yok", section)


class RawLogAndSafetyTest(unittest.TestCase):
    def test_raw_step_log_covers_three_scenarios_with_their_steps(self):
        scenarios = {key: scenario(key, [step(say=f"cümle {key}")]) for key in
                     ("01_a", "02_b", "03_c", "04_d")}
        results = {key: [result(1, narration=f"anlatı {key}\nikinci satır", seconds=1.25)] for key in scenarios}
        section = build_report(results, scenarios, date=DATE).split("## Ham adım kaydı", 1)[1]
        shown = [key for key in scenarios if f"### {key}" in section]
        self.assertEqual(len(shown), 3)
        self.assertIn("cümle", section)
        self.assertIn("anlatı", section)
        self.assertIn("1,25", section)

    def test_raw_step_log_prefers_a_break_over_passing_scenarios(self):
        results, scenarios = three_scenarios()
        section = build_report(results, scenarios, date=DATE).split("## Ham adım kaydı", 1)[1]
        self.assertIn("### 06_combat_actions", section)
        self.assertIn("### 03_room_sleep", section)
        self.assertIn("### 02_beer_tip", section)

    def test_raw_step_log_shows_every_broken_scenario_with_its_reading(self):
        # Görev 22 Step 6: rc7 broke but the three-scenario sample left it out; every scenario that breaks the gate
        # is shown, and its failed step carries the model's reading next to the narration and the expected/observed
        keys = ("01_a", "02_b", "03_c", "04_d", "05_e")
        scenarios = {key: scenario(key, [step(say=f"cümle {key}"), step(say="ikinci")]) for key in keys}
        results = {key: [result(1, narration=f"geçen {key}", reading='{"kind": "go_to"}'),
                         result(2, "new_break", failures=[f"kip: beklenen kapalı, gözlenen açık {key}"],
                                narration=f"anlatı {key}", reading=f'{{"kind": "speak_to", "who": "{key}"}}')]
                   for key in keys[:4]}
        results["05_e"] = [result(1), result(2)]
        section = build_report(results, scenarios, date=DATE).split("## Ham adım kaydı", 1)[1]
        for key in keys[:4]:
            block = section.split(f"### {key}", 1)[1].split("\n### ", 1)[0]
            self.assertIn(f"kip: beklenen kapalı, gözlenen açık {key}", block)
            self.assertIn(f"anlatı {key}", block)
            self.assertIn(f'ön okuma: {{"kind": "speak_to", "who": "{key}"}}', block)
            self.assertNotIn('ön okuma: {"kind": "go_to"}', block)       # a passing step's reading is not repeated
        self.assertIn("### 05_e", section)                                 # the sample still shows a passing one

    def test_report_never_contains_key_like_text(self):
        scenarios = {"02_beer_tip": scenario("02_beer_tip", [step(say="AIzaSyFAKEFAKEFAKEFAKE")])}
        results = {"02_beer_tip": [result(1, "new_break", narration="anahtar AIzaSyFAKEFAKEFAKEFAKE ve sk-ant-api03-ZZZZ",
                                          failures=["sk-ant-api03-ZZZZ göründü"])]}
        report = build_report(results, scenarios, latency=[{"step": "AIzaX", "provider": "sk-ant-y", "seconds": 1}],
                              date=DATE)
        self.assertNotIn("AIza", report)
        self.assertNotIn("sk-ant-", report)

    def test_scrub_hides_every_key_like_text(self):
        """``scrub`` is the report's own filter, for text a caller adds after the report (the run notes)."""
        self.assertEqual(scrub("a AIzaSyFAKE b sk-ant-api03-FAKE c sk-ABCDEFGHIJKLMNOP d sk-short e"),
                         "a [gizlendi] b [gizlendi] c [gizlendi] d sk-short e")

    def test_table_cells_survive_pipes_in_text(self):
        scenarios = {"02_beer_tip": scenario("02_beer_tip", title="a | b")}
        report = build_report({"02_beer_tip": [result(1)]}, scenarios, date=DATE)
        row = next(line for line in report.splitlines() if line.startswith("| 02_beer_tip"))
        self.assertEqual(row.replace("\\|", "").count("|"), 6)

    def test_the_arrival_scenario_is_told_under_narration_form(self):
        self.assertEqual(report_kind("38_varis_anlatimi"), "Anlatı biçimi")

    def test_the_new_journeys_have_their_kinds(self):
        self.assertEqual(report_kind("39_ingilizce_saat_para"), "Oda, uyku ve çıkış")
        self.assertEqual(report_kind("40_yuru_sor_eslik"), "Yol ve hedef")


if __name__ == "__main__":
    unittest.main()
