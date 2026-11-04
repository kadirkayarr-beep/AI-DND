"""The journey runner: it drives the real app over HTTP with a scripted model and sorts every step.

A step marked known broken must really break (a fixed one says "remove the marker"); an unmarked failure
is a new break; the steps after a known break are not run unless they say they stand on their own.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import front_proposal
from api.tests.journeys.runner import (
    JourneyCase,
    NarratorInput,
    ScriptedClient,
    ScriptedModel,
    StepResult,
    apply_setup,
    describe_problems,
    read_observed,
    summary_line,
)
from api.tests.journeys.schema import ScenarioError, load_scenario

BUY_BEER = "/item shop_buy barman bira 1 0 4"
BUY_SECOND_BEER = "/item shop_buy barman bira 1 1 4"  # the counter sequence moved on after one trade


def beer_scenario(*steps, **changes):
    """The one built-in journey: a purse of 100 cp, a barman, one beer bought at the counter for 4 cp."""
    data = {
        "id": "00_runner_beer",
        "title": "Tezgâhtan bir bira (çalıştırıcı sınaması)",
        "source_items": [35],
        "setup": {
            "npcs": [{"id": "barman", "name": "Marek", "role": "Barmen", "current_hp": 10}],
            "currency": {"player": 100, "barman": 0},
            "inventory": [],
            "seed": 7,
        },
        "steps": list(steps) or [{"command": BUY_BEER, "expect": {"kese": 96, "envanter": {"Bira": 1}}}],
    }
    data.update(changes)
    folder = Path(tempfile.mkdtemp())
    path = folder / "scenario.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        return load_scenario(path)
    finally:
        path.unlink()
        folder.rmdir()


class RecordingModel(ScriptedModel):
    """The default driver, keeping each step's client so a test can see what it answered."""

    def __init__(self):
        self.clients = []

    @contextmanager
    def bind(self, case, step):
        with super().bind(case, step) as client:
            self.clients.append(client)
            yield client


class TheRunnerSortsEveryStep(JourneyCase):
    async def test_a_passing_scenario_reports_all_pass(self):
        results = await self.run_scenario(beer_scenario())
        self.assertEqual([result.status for result in results], ["pass"], results)
        (result,) = results
        self.assertIsInstance(result, StepResult)
        self.assertEqual((result.index, result.failures, result.items), (1, (), ()))
        self.assertIn("4 bakır", result.narration)
        self.assertGreaterEqual(result.seconds, 0.0)
        self.assertEqual(self.last_observations[-1]["kese"], 96)
        self.assertEqual(self.last_observations[-1]["envanter"], {"Bira": 1})

    async def test_known_broken_step_that_fails_is_counted_not_failed(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 95}, "known_broken": [35]}))
        (result,) = results
        self.assertEqual(result.status, "known_broken")
        self.assertEqual(result.items, (35,))
        self.assertEqual(result.failures, ("kese: beklenen 95, gözlenen 96",))

    async def test_known_broken_step_that_passes_is_marker_stale(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96}, "known_broken": [35]}))
        (result,) = results
        self.assertEqual(result.status, "marker_stale")
        self.assertEqual((result.items, result.failures), ((35,), ()))

    async def test_unmarked_failure_is_new_break(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 100, "envanter": {"Bira": 1}}}))
        (result,) = results
        self.assertEqual(result.status, "new_break")
        self.assertEqual(result.failures, ("kese: beklenen 100, gözlenen 96",))
        self.assertEqual(result.items, ())

    async def test_steps_after_a_known_break_are_unreached_unless_independent(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 95}, "known_broken": [35]},
            {"command": BUY_BEER, "expect": {"kese": 1}},
            {"command": BUY_SECOND_BEER, "expect": {"kese": 92, "envanter": {"Bira": 2}}, "independent": True},
            {"command": BUY_BEER, "expect": {"kese": 1}},
        ))
        self.assertEqual([result.status for result in results],
                         ["known_broken", "unreached", "pass", "unreached"], results)
        self.assertEqual([result.index for result in results], [1, 2, 3, 4])
        # The unreached steps never ran: only two beers were bought.
        self.assertEqual(read_observed(self, self.last_session_id)["kese"], 92)
        self.assertIn("adım 1", results[1].failures[0])

    async def test_same_scenario_twice_gives_identical_observations(self):
        scenario = beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96}},
            {"say": "Tezgâha yaslanıp salonu dinliyorum.",
             "script": {"intent": "narrative", "narration": "Salon uğulduyor; Marek bardak siliyor."},
             "expect": {"kese": 96, "savas": False}},
            {"command": BUY_SECOND_BEER, "expect": {"kese": 92, "envanter": {"Bira": 2}}},
        )
        first = await self.run_scenario(scenario)
        seen_first = self.last_observations
        second = await self.run_scenario(scenario)
        seen_second = self.last_observations
        self.assertEqual([result.status for result in first], ["pass", "pass", "pass"], first)
        self.assertEqual([result.status for result in second], ["pass", "pass", "pass"], second)
        self.assertEqual(len(seen_first), 3)
        self.assertEqual(seen_first, seen_second)
        self.assertEqual([result.narration for result in first], [result.narration for result in second])

    async def test_a_scripted_say_step_gets_the_scripted_narration_end_to_end(self):
        first_line = "Mum alevi titriyor; Marek kulağını tezgâha dayamış dinliyor."
        second_line = "Kapının önünde bir köpek havlıyor, sonra susuyor."
        model = RecordingModel()
        results = await self.run_scenario(beer_scenario(
            {"say": "Tezgâha yaslanıp salonu dinliyorum.",
             "script": {"intent": "narrative", "narration": first_line},
             "expect": {"gerekli_metin": first_line, "yasak_metin": second_line}},
            {"say": "Gözlerimi kapatıp salonun sesini dinliyorum.",
             "script": {"intent": "narrative", "narration": second_line},
             "expect": {"gerekli_metin": second_line, "yasak_metin": first_line}},
        ), model=model)
        self.assertEqual([result.status for result in results], ["pass", "pass"], results)
        self.assertIn(first_line, results[0].narration)
        self.assertIn(second_line, results[1].narration)
        self.assertNotIn(first_line, results[1].narration)
        # Each step's own ScriptedClient answered the narrator call, and nothing unscripted was asked.
        self.assertEqual(len(model.clients), 2)
        for client in model.clients:
            self.assertIn("narration", client.kinds)
            self.assertEqual(client.unexpected, [])
        self.assertEqual(self.last_narration, results[1].narration)

    async def test_what_the_narrator_was_sent_is_observed_per_step(self):
        """``anlaticiya_giden`` is read from the turn's own model calls (the engine's ``ollama.chat``, so it holds
        for the scripted model and the real chain alike): every narrator call's messages, nothing from another
        call kind and nothing from an earlier step. A turn without a narrator call observes None."""
        listening = "Tezgâha yaslanıp salonu dinliyorum."
        model = RecordingModel()
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96}},
            {"say": listening, "script": {"intent": "narrative", "narration": "Salon uğulduyor."},
             "expect": {"anlaticiya_giden": listening}},
            {"say": "Gözlerimi kapatıp salonun sesini dinliyorum.",
             "script": {"intent": "narrative", "narration": "Bir köpek havlıyor."},
             "expect": {"anlaticiya_giden": "bu cümle anlatıcıya hiç gitmedi"}},
        ), model=model)
        self.assertEqual([result.status for result in results], ["pass", "pass", "new_break"], results)
        self.assertEqual(results[2].failures,
                         ("anlaticiya_giden: anlatıcıya giden metinde bulunamadı: bu cümle anlatıcıya hiç gitmedi",))
        self.assertNotIn("narration", model.clients[0].kinds)
        self.assertIsNone(self.last_observations[0]["anlaticiya_giden"])
        self.assertIn("narration", model.clients[1].kinds)
        self.assertIn("intent", model.clients[1].kinds)
        told = self.last_observations[1]["anlaticiya_giden"]
        self.assertIn(listening, told)
        self.assertIn("Gözlerimi kapatıp", self.last_observations[2]["anlaticiya_giden"])

    async def test_front_proposal_setup_turns_the_front_reading_on_for_the_steps_only(self):
        step = {"say": "Tezgâha yaslanıp salonu dinliyorum.",
                "script": {"intent": "narrative", "narration": "Salon uğulduyor."}, "expect": {"kese": 100}}
        before = os.environ.get(front_proposal.FLAG)
        kinds = {}
        for setting in (True, False):
            model = RecordingModel()
            scenario = beer_scenario(step, setup={**beer_scenario().setup, "front_proposal": setting})
            results = await self.run_scenario(scenario, model=model)
            self.assertEqual([result.status for result in results], ["pass"], results)
            kinds[setting] = model.clients[0].kinds
            self.assertEqual(os.environ.get(front_proposal.FLAG), before)
        self.assertIn("front", kinds[True])
        self.assertNotIn("front", kinds[False])
        campaign = await self.create_campaign()
        with self.assertRaises(ScenarioError) as raised:
            apply_setup(self, campaign, {"front_proposal": "1"})
        self.assertIn("front_proposal", str(raised.exception))

    async def test_the_counter_offer_and_other_purses_are_observed(self):
        campaign = await self.create_campaign()
        apply_setup(self, campaign, beer_scenario().setup)
        fresh = read_observed(self, campaign["session_id"])
        self.assertIsNone(fresh["tezgah"])
        self.assertEqual(fresh["kisi_kese"], {"barman": 0})
        # A spoken order opens the counter's offer (not the economic card); the counter trade closes it and
        # pays the barman.
        results = await self.run_scenario(beer_scenario(
            {"say": "bir bira alayım",
             "expect": {"tezgah": {"npc_id": "barman", "key": "bira", "unit_cp": 4}, "kart": None,
                        "kese": 100, "kisi_kese": {"barman": 0}}},
            {"command": BUY_BEER,
             "expect": {"tezgah": None, "kese": 96, "envanter": {"Bira": 1}, "kisi_kese": {"barman": 4}}},
        ))
        self.assertEqual([result.status for result in results], ["pass", "pass"], results)

    async def test_campaign_start_and_place_stand_the_player_in_a_new_place_of_the_town(self):
        start = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                 "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}
        inn = {"kind": "smithy", "name": "Göl Sofrası Hanı", "scene_kind": "tavern", "place_kind": "tavern"}
        setup = {**beer_scenario().setup, "campaign_start": start, "place": inn}
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        here = world["location"]
        self.assertNotEqual(here, "fr:city:neverwinter")
        place = world["locations"][here]
        self.assertEqual((place["name"], place["parent_location_id"], place["exit_location_id"]),
                         ("Göl Sofrası Hanı", "fr:city:neverwinter", "fr:city:neverwinter"))
        self.assertEqual((place["scene_kind"], place["place_kind"]), ("tavern", "tavern"))
        self.assertEqual(world["npcs"][0]["location"], here)  # the people stand in the place, not in the street
        saved = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertEqual(saved["location"], here)
        for wrong, word in (({"campaign_start": "neverwinter"}, "campaign_start"),
                            ({"place": {**inn, "kapı": "açık"}}, "kapı"),
                            ({"place": {**inn, "kind": "han"}}, "han"),
                            ({"place": {"kind": "smithy"}}, "name")):
            with self.subTest(wrong=wrong), self.assertRaises(ScenarioError) as raised:
                fresh = await self.create_campaign()
                apply_setup(self, fresh, wrong)
            self.assertIn(word, str(raised.exception))

    async def test_setup_seeds_the_dice_and_rejects_an_unknown_key(self):
        scenario = beer_scenario()
        campaign = await self.create_campaign()
        apply_setup(self, campaign, scenario.setup)
        session = self.manager.get(campaign["session_id"]).game_session
        self.assertEqual(session.rng.getstate(), random.Random(7).getstate())
        self.assertEqual(session.world_state["currency"], {"player": 100, "barman": 0})
        self.assertEqual(session.world_state["npcs"][0]["location"], session.world_state["location"])
        saved = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertEqual(saved["currency"], {"player": 100, "barman": 0})
        with self.assertRaises(ScenarioError) as raised:
            apply_setup(self, campaign, {"seed": 7, "kese": 100})
        self.assertIn("kese", str(raised.exception))


class TheSuiteSummary(unittest.TestCase):
    def test_new_breaks_and_stale_markers_fail_the_suite_and_scenarios_are_counted(self):
        def step(index, status, items=()):
            return StepResult(index, status, ("kese: beklenen 95, gözlenen 96",) if status != "pass" else (),
                              items, "", 0.0)

        results = {
            "a": [step(1, "pass")],
            "b": [step(1, "known_broken", (35,)), step(2, "unreached")],
            "c": [step(1, "pass"), step(2, "new_break")],
            "d": [step(1, "marker_stale", (38,))],
        }
        self.assertEqual(summary_line(results), "2 geçti, 1 bilinen kırık, 1 yeni kırık (1 adımda işaret kaldırılmalı)")
        self.assertEqual(describe_problems(results["a"] + results["b"]), [])
        (new,) = describe_problems(results["c"])
        self.assertIn("YENİ KIRIK", new)
        self.assertIn("kese: beklenen 95, gözlenen 96", new)
        (stale,) = describe_problems(results["d"])
        self.assertIn("[38]", stale)
        self.assertIn("işareti kaldır", stale)


class TheScriptedClient(unittest.TestCase):
    def test_scripted_client_rejects_an_unscripted_call_kind(self):
        client = ScriptedClient({"narration": "Sessiz bir akşam."})
        with self.assertRaises(AssertionError):
            client.chat(model="m", messages=[], format={"type": "object", "properties": {"verdict": {}}})
        with self.assertRaises(AssertionError):
            client.chat(model="m", messages=[])
        self.assertEqual(len(client.unexpected), 2)
        with self.assertRaises(ScenarioError):
            ScriptedClient({"narrasyon": "yazım hatası"})

    def test_each_known_call_kind_answers_from_the_script(self):
        client = ScriptedClient({"intent": "attack", "front": {"kind": "look"}, "spoken": "Hoş geldin.",
                                 "narration": "Kapı gıcırdar."})

        def ask(*keys):
            reply = client.chat(model="m", messages=[], format={"properties": {key: {} for key in keys}})
            return json.loads(reply["message"]["content"])

        self.assertEqual(ask("spoken_text", "stage_direction")["spoken_text"], "Hoş geldin.")
        self.assertEqual(ask("narration", "world_updates")["narration"], "Kapı gıcırdar.")
        self.assertEqual(ask("steps")["steps"], [])
        self.assertEqual(ask("intent", "action")["intent"], "attack")
        front = ask("intent", "front")
        self.assertEqual((front["intent"], front["front"]["kind"], front["front"]["person_id"]),
                         ("attack", "look", "none"))
        self.assertEqual(client.kinds, ["speech", "narration", "steps", "intent", "front"])
        self.assertEqual(client.unexpected, [])


class TheNarratorInput(unittest.TestCase):
    def test_only_narrator_calls_are_kept_and_every_call_still_goes_through(self):
        answered = []

        def chat(*args, **kwargs):
            answered.append(kwargs["format"])
            return {"message": {"content": "{}"}}

        listen = NarratorInput(chat)
        self.assertIsNone(listen.text())
        listen(model="m", messages=[{"role": "system", "content": "sınıflandır"}],
               format={"properties": {"intent": {}, "narration": {}}})
        listen(model="m", messages=[{"role": "user", "content": "konuş"}], format={"properties": {"spoken_text": {}}})
        self.assertIsNone(listen.text(), "a classifier that may narrate and a speech call are not the narrator")
        listen(model="m", messages=[{"role": "system", "content": "Anlat."}, {"role": "user", "content": "Oda tutuldu."}],
               format={"properties": {"narration": {}, "world_updates": {}}})
        listen(model="m", messages=[{"role": "user", "content": "İkinci anlatı."}], format={"properties": {"narration": {}}})
        self.assertEqual(listen.text(), "Anlat.\nOda tutuldu.\nİkinci anlatı.")
        self.assertEqual(len(answered), 4)


if __name__ == "__main__":
    unittest.main()
