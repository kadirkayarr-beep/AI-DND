"""The journey runner: it drives the real app over HTTP with a scripted model and sorts every step.

A step marked known broken must really break (a fixed one says "remove the marker"); an unmarked failure
is a new break; the steps after a known break are not run unless they say they stand on their own.
"""

from __future__ import annotations

import copy
import json
import os
import random
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import campaign_time
import equipment_economy
import front_proposal
from api import serializers
from api.tests.journeys import runner
from api.tests.journeys.runner import (
    JourneyCase,
    NarratorInput,
    ScriptedClient,
    ScriptedModel,
    StepResult,
    apply_setup,
    call_kind,
    counter_attacks,
    describe_problems,
    read_observed,
    step_status,
    summary_line,
)
from api.tests.journeys.schema import ScenarioError, load_scenario
from api.tests.town_seed import fixed_town

BUY_BEER = "/item shop_buy barman bira 1 0 4"
BUY_SECOND_BEER = "/item shop_buy barman bira 1 1 4"  # the counter sequence moved on after one trade
ARRIVAL_SCHEMA = {"type": "object", "properties": {"narration": {"type": "string"}, "world_updates": {"type": "object"},
                                                   "lore_claims": {"type": "array"}, "arrival": {"type": "boolean"}}}
SPEECH = {"type": "object", "properties": {"spoken_text": {}, "stage_direction": {}}}  # an NPC speech call's schema
NEVERWINTER = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
               "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}


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
    path = folder / f"{data['id']}.json"
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


class UnsavedChangeModel(ScriptedModel):
    """The default driver, but just before a reload step it changes the live purse without saving it."""

    @contextmanager
    def bind(self, case, step):
        with super().bind(case, step) as client:
            if step.reload:
                case.manager.get(case.last_session_id).game_session.world_state["currency"]["player"] = 1
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
        self.assertEqual(self.last_observations[-1]["esya_sayisi"], 1)  # every item held, whatever its name

    async def test_the_item_count_counts_every_item_whatever_its_name(self):
        await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"esya_sayisi": 1}},
            setup={"npcs": [{"id": "barman", "name": "Marek", "role": "Barmen", "current_hp": 10}],
                   "currency": {"player": 100, "barman": 0}, "inventory": ["Iade takımı", "İade takımı"],
                   "seed": 7}))
        observed = self.last_observations[0]
        self.assertEqual(observed["envanter"], {"Iade takımı": 1, "İade takımı": 1, "Bira": 1})
        self.assertEqual(observed["esya_sayisi"], 3)

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

    async def test_a_marked_step_that_breaks_for_another_reason_is_a_new_break(self):
        """Ruling R19: a marker stands only for the failures its ``broken_because`` names. Every failure of the step
        must hold one of them; one that does not makes the step a new break, and all its failures are told."""
        (named,) = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 95}, "known_broken": [35],
             "broken_because": ["kese: beklenen 95"]}))
        self.assertEqual((named.status, named.failures), ("known_broken", ("kese: beklenen 95, gözlenen 96",)))
        (other,) = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 95, "envanter": {"Bira": 2}}, "known_broken": [35],
             "broken_because": ["kese: beklenen 95"]}))
        self.assertEqual(other.status, "new_break")
        self.assertEqual(other.items, (35,))
        self.assertEqual(len(other.failures), 2)
        (line,) = describe_problems([other])
        self.assertIn("YENİ KIRIK", line)
        self.assertIn("[35]", line)
        self.assertIn("kese: beklenen 95", line)
        self.assertIn("envanter: beklenen", line)

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

    async def test_an_undo_step_takes_back_the_last_turn_through_the_undo_route(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96, "envanter": {"Bira": 1}}},
            {"undo": True, "expect": {"kese": 100, "envanter": {}, "kisi_kese": {"barman": 0},
                                      "gerekli_metin": "Son tur geri alındı"}},
        ))
        self.assertEqual([result.status for result in results], ["pass", "pass"], results)
        record = self.manager.get(self.last_session_id)
        self.assertEqual(record.game_session.world_state["currency"], {"player": 100, "barman": 0})
        # The route's own trace: the undone turn stays in the history, followed by the undo marker.
        history = self.store.get_campaign(record.campaign_id).history
        self.assertEqual(history[-1]["player_message"], "↶ Son turu geri al")
        self.assertIsNone(self.last_narrator_input)

    async def test_an_undo_the_route_refuses_or_with_no_turn_before_it_fails_its_step(self):
        (alone,) = await self.run_scenario(beer_scenario({"undo": True, "expect": {"kese": 100}}))
        self.assertEqual(alone.status, "new_break")
        self.assertIn("geri alınacak tur yok", alone.failures[0])
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96}},
            {"undo": True, "expect": {"kese": 100}},
            {"undo": True, "expect": {"kese": 100}},
        ))
        self.assertEqual([result.status for result in results], ["pass", "pass", "new_break"], results)
        self.assertIn("HTTP 409", results[2].failures[0])  # one undo per turn: the route says no
        self.assertIn("undo_unavailable", results[2].failures[0])

    async def test_a_reload_step_reads_the_campaign_back_from_the_save(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96}},
            {"reload": True, "expect": {"kese": 96, "envanter": {"Bira": 1}, "kisi_kese": {"barman": 4}}},
            {"command": BUY_SECOND_BEER, "expect": {"kese": 92, "envanter": {"Bira": 2}}},
        ))
        self.assertEqual([result.status for result in results], ["pass", "pass", "pass"], results)

        def state(observed):
            return {key: value for key, value in observed.items() if key not in {"narration", "anlaticiya_giden"}}

        self.assertEqual(state(self.last_observations[1]), state(self.last_observations[0]))
        self.assertEqual(results[1].narration, "")

    async def test_a_reload_that_finds_the_save_behind_the_live_game_fails_its_step(self):
        results = await self.run_scenario(beer_scenario(
            {"command": BUY_BEER, "expect": {"kese": 96}},
            {"reload": True},
        ), model=UnsavedChangeModel())
        self.assertEqual([result.status for result in results], ["pass", "new_break"], results)
        self.assertEqual(results[1].failures, ("yenileme: kese: canlı 1, kayıttan 96",))
        self.assertEqual(self.last_observations[1]["kese"], 96)  # the step observes what came back from the save

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

    async def test_the_ammunition_counter_is_observed_apart_from_the_items(self):
        campaign = await self.create_campaign()
        apply_setup(self, campaign, beer_scenario().setup)
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        world.pop("ammunition", None)
        self.assertEqual(read_observed(self, campaign["session_id"])["cephane"], {})
        apply_setup(self, campaign, {"ammunition": {"arrow": 20}, "inventory": ["Uzun Yay & 20 Ok"]})
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual(observed["cephane"], {"arrow": 20})
        self.assertEqual(observed["envanter"], {"Uzun Yay & 20 Ok": 1})  # the pack label is an item, not arrows
        observed["cephane"]["arrow"] = 0
        self.assertEqual(world["ammunition"], {"arrow": 20})  # a copy: reading never changes the counter

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

    async def test_death_mode_setup_makes_the_campaign_in_that_mode(self):
        start = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                 "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}
        for setup, mode in (({"death_mode": "PERMADEATH"}, "PERMADEATH"),
                            ({"death_mode": "IRONMAN", "campaign_start": start}, "IRONMAN"),
                            ({}, "NORMAL")):
            with self.subTest(setup=setup):
                campaign = await self._journey_campaign(setup)
                apply_setup(self, campaign, setup)
                world = self.manager.get(campaign["session_id"]).game_session.world_state
                self.assertEqual(world["death_state"]["mode"], mode)
        for wrong in ("SONSUZ", 1, None):
            with self.subTest(wrong=wrong):
                with self.assertRaises(ScenarioError) as raised:
                    await self._journey_campaign({"death_mode": wrong})
                self.assertIn("death_mode", str(raised.exception))

    async def test_a_place_with_no_exit_has_no_way_out_of_it(self):
        start = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                 "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}
        cellar = {"kind": "smithy", "name": "Kilitli Mahzen", "no_exit": True}
        setup = {"campaign_start": start, "place": cellar}
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        place = world["locations"][world["location"]]
        self.assertEqual(place["name"], "Kilitli Mahzen")
        self.assertNotIn("parent_location_id", place)
        self.assertIsNone(place["exit_location_id"])
        saved = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertIsNone(saved["locations"][world["location"]]["exit_location_id"])
        with self.assertRaises(ScenarioError) as raised:
            apply_setup(self, await self.create_campaign(), {"place": {**cellar, "no_exit": "evet"}})
        self.assertIn("no_exit", str(raised.exception))

    async def test_the_players_combat_movement_this_turn_is_observed(self):
        campaign = await self.create_campaign()
        apply_setup(self, campaign, {"npcs": [{"id": "bandit", "name": "Haydut", "role": "Bandit", "current_hp": 30,
                                               "max_hp": 30, "hostile": True, "distance_ft": 5}]})
        session = self.manager.get(campaign["session_id"]).game_session
        self.assertIsNone(read_observed(self, campaign["session_id"])["hareket"])  # no fight, no combat movement
        session.start_combat(session.world_state["npcs"][0])
        self.assertEqual(read_observed(self, campaign["session_id"])["hareket"], 0)  # a fresh turn: nothing moved
        session.world_state["combat"]["turn_resources"]["player"]["movement_used"] = 15
        self.assertEqual(read_observed(self, campaign["session_id"])["hareket"], 15)

    async def test_varis_reads_the_sessions_arrival_diagnostic(self):
        with fixed_town(self, 4421):
            campaign = await self.create_campaign()
        sid = campaign["session_id"]
        self.assertEqual(read_observed(self, sid)["varis"], {"cagri": 0, "kaynak": None, "neden": None})
        self.manager.get(sid).game_session.last_arrival_narration = {"source": "model", "reason_code": None}
        self.assertEqual(read_observed(self, sid)["varis"]["kaynak"], "model")
        self.manager.get(sid).game_session.last_arrival_narration = {"source": "python", "reason_code": "model_error"}
        self.assertEqual(read_observed(self, sid)["varis"], {"cagri": 0, "kaynak": "python", "neden": "model_error"})

    async def test_every_step_result_carries_its_arrival_diagnostic(self):
        # Task 6b: the real-chain report lists every run's arrivals, so each step keeps what ``varis`` observed.
        with fixed_town(self, 4431):
            (result,) = await self.run_scenario(beer_scenario())
        self.assertEqual(result.varis, {"cagri": 0, "kaynak": None, "neden": None})
        self.assertEqual(result.varis, self.last_observations[-1]["varis"])

    async def test_experience_game_hours_and_open_quests_are_observed(self):
        campaign = await self._journey_campaign({"campaign_start": NEVERWINTER})  # a started campaign clock
        apply_setup(self, campaign, beer_scenario().setup)
        session = self.manager.get(campaign["session_id"]).game_session
        fresh = read_observed(self, campaign["session_id"])
        self.assertEqual((fresh["xp"], fresh["saat"], fresh["gorev"]), (0, 0, {"aktif": 0, "kayit": []}))
        self.assertIsNone(fresh["yuva"])  # the default character casts no spells (scenario 21 reads a caster's)
        casting = {"slots": {"1": 2}}
        slots = runner._spell_slots({"spellcasting_v1": casting})
        self.assertEqual(slots, {"1": 2})
        slots["1"] = 0
        self.assertEqual(casting["slots"], {"1": 2})  # a copy: reading never spends a slot
        session.character["xp"] = 10
        session.world_state["campaign_time"]["elapsed_seconds"] += 8 * 3600 + 59 * 60  # whole hours only
        session.world_state["quests"] = [{"quest_id": "q1", "title": "İade takımı", "status": "ACTIVE"},
                                         {"quest_id": "q2", "title": "Eski iş", "status": "COMPLETED"}]
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual((observed["xp"], observed["saat"]), (10, 8))
        self.assertEqual(observed["gorev"], {"aktif": 1, "kayit": ["İade takımı"]})

    async def test_the_card_names_its_lines(self):
        results = await self.run_scenario(beer_scenario(
            {"economic_action": {"kind": "prepare", "proposal": {"purpose": "tip", "recipient_id": "barman",
                                                                 "amount_cp": 4}},
             "expect": {"kart": {"max_total_cp": 4, "kalemler": ["Bahşiş"]}}}))
        self.assertEqual([result.status for result in results], ["pass"], results)
        self.assertEqual(self.last_observations[0]["kart"],
                         {"max_total_cp": 4, "counterparty_label": "Marek", "kalemler": ["Bahşiş"]})

    def test_counter_attacks_are_counted_per_enemy_from_the_turn_combat_result(self):
        swing = {"actor": "bandit", "outcome": "hit", "damage": 3}
        self.assertEqual(counter_attacks(None), 0)
        self.assertEqual(counter_attacks({"outcome": "hit"}), 0)  # the player's own swing is no counter-attack
        self.assertEqual(counter_attacks({"enemy_actions": [swing]}), 1)
        self.assertEqual(counter_attacks({"enemy_actions": [swing, {**swing, "outcome": "miss"},
                                                            {"actor": "thug", "outcome": "critical_hit"}]}), 2)
        self.assertEqual(counter_attacks({"enemy_actions": [{"actor": "bandit", "outcome": "dodge"}]}), 0)
        # The singular field is the engine's compatibility alias of the first entry; it counts only on its own.
        self.assertEqual(counter_attacks({"enemy_action": swing, "enemy_actions": [swing]}), 1)
        self.assertEqual(counter_attacks({"enemy_action": swing}), 1)

    def test_only_enemy_swings_resolved_after_the_players_swing_are_counter_attacks(self):
        """An enemy that won initiative swings before the player's blow and again after it in one response; only the
        swing after the blow answers it. The order is the resolution id's last number within the same action."""
        def roll(actor, number, action="act-1"):
            return {"actor": actor, "outcome": "miss", "action_id": action,
                    "resolution_id": f"{action}:attack_roll:{number}"}
        player = {**roll("player", 2), "enemy_action": roll("barman", 1),
                  "enemy_actions": [roll("barman", 1), roll("barman", 3)]}
        self.assertEqual(counter_attacks(player), 1)
        self.assertEqual(counter_attacks({**player, "enemy_actions": [roll("barman", 1)]}), 0)
        self.assertEqual(counter_attacks({**player, "enemy_actions": [roll("barman", 3), roll("barman", 4),
                                                                      roll("thug", 5)]}), 2)
        self.assertEqual(counter_attacks({**player, "enemy_actions": [roll("barman", 10)]}), 1)  # 10 after 2, not "1"
        # Without an order to compare (no player roll, another action, no id), every swing counts as before.
        self.assertEqual(counter_attacks({"enemy_actions": [roll("barman", 1), roll("barman", 3)]}), 2)
        self.assertEqual(counter_attacks({**player, "enemy_actions": [roll("barman", 1, "act-0")]}), 1)
        self.assertEqual(counter_attacks({**player, "enemy_actions": [{"actor": "barman", "outcome": "hit"}]}), 1)

    async def test_a_fight_step_observes_its_counter_attacks_from_the_turn_response(self):
        bandit = {"id": "bandit", "name": "Haydut", "role": "Bandit", "current_hp": 300, "max_hp": 300,
                  "armor_class": 30, "hostile": True, "distance_ft": 5}
        attack = {"intent": "attack", "action": "attack",
                  "target": {"type": "npc", "reference": "Haydut", "npc_id": "bandit", "evidence_quote": "Haydut"},
                  "completion": "complete"}
        results = await self.run_scenario(beer_scenario(
            {"say": "Haydut'a saldırıyorum", "script": {"intent": attack}, "expect": {"savas": True}},
            {"undo": True},
            setup={"npcs": [bandit], "seed": 1}))
        self.assertEqual(results[0].status, "pass", results)
        fought, undone = (observed["karsi_saldiri"] for observed in self.last_observations)
        self.assertGreaterEqual(fought, 1)  # the bandit answered the blow
        self.assertEqual(undone, 0)  # an undo step is no exchange of blows

    async def test_job_setup_gives_the_owner_a_town_job_where_the_player_stands(self):
        owner = {"id": "potter", "name": "Halil", "role": "Çömlekçi", "current_hp": 10}
        hiring = {"type": "hiring", "owner": "potter", "status": "accepted", "pay": 26, "work_days": 1,
                  "line": "Tezgâhtaki çanakları say, akşama yirmi altı bakır."}
        start = NEVERWINTER  # the default campaign has no town of its own to hold a job
        campaign = await self._journey_campaign({"campaign_start": start})
        apply_setup(self, campaign, {"npcs": [owner], "job": hiring})
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        (thread,) = world["world_threads_v1"]["threads"]
        self.assertEqual((thread["type"], thread["status"], thread["owner_npc_id"], thread["place_id"]),
                         ("hiring", "accepted", "potter", world["location"]))
        self.assertEqual((thread["terms"]["pay"], thread["terms"]["work_days"]), (26, 1))
        self.assertEqual(world["npcs"][0]["place_role_of"], world["location"])
        saved = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertEqual(saved["world_threads_v1"]["threads"][0]["status"], "accepted")

        errand = {"type": "errand", "owner": "potter", "status": "offered", "pay": 12, "noun": "iade takımı",
                  "recipient": "Tuna", "target_kind": "harbor", "line": "İade takımını iskeledeki Tuna'ya götür."}
        campaign = await self._journey_campaign({"campaign_start": start})
        apply_setup(self, campaign, {"npcs": [owner], "job": errand})
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        (thread,) = world["world_threads_v1"]["threads"]
        target = world["locations"][thread["target_place_id"]]
        self.assertEqual((thread["type"], thread["status"], thread["item_noun"], thread["recipient_name"]),
                         ("errand", "offered", "iade takımı", "Tuna"))
        self.assertEqual((target["place_kind"], target["resident_name"]), ("harbor", "Tuna"))
        for wrong, word in (({**hiring, "maas": 1}, "maas"), ({**hiring, "owner": "nobody"}, "owner"),
                            ({**hiring, "type": "kavga"}, "type"), ({**errand, "status": "accepted"}, "status"),
                            ({**hiring, "pay": "26"}, "pay")):
            with self.subTest(wrong=wrong), self.assertRaises(ScenarioError) as raised:
                apply_setup(self, await self._journey_campaign({"campaign_start": start}),
                            {"npcs": [owner], "job": wrong})
            self.assertIn(word, str(raised.exception))

    async def test_letter_setup_offers_a_sealed_letter_where_the_job_ends_and_a_trouble_where_it_goes(self):
        owner = {"id": "potter", "name": "Halil", "role": "Çömlekçi", "current_hp": 10}
        clerk = {"id": "clerk", "name": "Selin", "role": "Kâtip", "current_hp": 10}
        errand = {"type": "errand", "owner": "potter", "status": "offered", "pay": 12, "noun": "iade takımı",
                  "recipient": "Tuna", "target_kind": "harbor", "line": "İade takımını iskeledeki Tuna'ya götür."}
        letter = {"owner": "clerk", "pay": 10, "noun": "mühürlü mektup", "recipient": "Ozan", "target_kind": "graveyard",
                  "line": "Mühürlü mektubu Ozan'a götür, mührü bozma."}
        campaign = await self._journey_campaign({"campaign_start": NEVERWINTER})
        apply_setup(self, campaign, {"npcs": [owner, clerk], "job": errand, "letter": letter})
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        job, sealed, *rest = world["world_threads_v1"]["threads"]
        self.assertEqual((sealed["type"], sealed["status"], sealed["owner_npc_id"], sealed["item_noun"]),
                         ("errand", "offered", "clerk", "mühürlü mektup"))
        self.assertEqual(world["npcs"][1]["location"], job["target_place_id"])            # waits where the job ends
        self.assertNotIn(world["npcs"][1]["place_role_of"], {job["place_id"], job["target_place_id"]})
        self.assertEqual([t["type"] for t in rest if t["place_id"] == sealed["target_place_id"]], ["trouble"])
        for wrong, word in (({**letter, "seal": 1}, "seal"), ({**letter, "owner": "potter"}, "owner"),
                            ({**letter, "line": "Mektubu götür."}, "line"), ({**letter, "pay": 0}, "pay")):
            with self.subTest(wrong=wrong), self.assertRaises(ScenarioError) as raised:
                apply_setup(self, await self._journey_campaign({"campaign_start": NEVERWINTER}),
                            {"npcs": [owner, clerk], "job": errand, "letter": wrong})
            self.assertIn(word, str(raised.exception))

    async def test_a_konus_step_is_say_mode_to_that_person(self):
        campaign = await self.create_campaign()
        apply_setup(self, campaign, beer_scenario().setup)
        sid = campaign["session_id"]
        spoken, plain = beer_scenario({"say": "Akşam kalabalık olur mu?", "konus": "barman"},
                                      {"say": "Akşam kalabalık olur mu?"}).steps
        body = self._body(sid, spoken)
        self.assertEqual((body["message"], body["interaction_mode"], body["target_id"]),
                         ("Akşam kalabalık olur mu?", "say", "barman"))
        self.assertFalse({"interaction_mode", "target_id"} & set(self._body(sid, plain)))

    async def test_the_speech_call_input_is_observed_apart_from_the_narrator(self):
        """``konusmaya_giden`` is what the turn's last speech call was sent (every message of it), read like
        ``anlaticiya_giden`` from the engine's own model calls; a turn without a speech call observes None."""
        line = "Akşam kalabalık olur mu?"
        model = RecordingModel()
        results = await self.run_scenario(beer_scenario(
            {"say": line, "konus": "barman", "script": {"spoken": "Olur, hem de nasıl."},
             "expect": {"konusmaya_giden": line, "gerekli_metin": "Olur, hem de nasıl."}},
            {"command": BUY_BEER, "expect": {"kese": 96}},
        ), model=model)
        self.assertEqual([result.status for result in results], ["pass", "pass"], results)
        self.assertIn("speech", model.clients[0].kinds)
        talked, bought = self.last_observations
        self.assertIsInstance(talked["konusmaya_giden"], str)
        self.assertIn(line, talked["konusmaya_giden"])
        self.assertIsNone(talked["anlaticiya_giden"])  # the speech call is not the narrator
        self.assertIsNone(bought["konusmaya_giden"])  # nothing carried over from the step before

    async def test_setup_items_get_ids_and_item_name_becomes_the_bag_id(self):
        """The setup's inventory is made into records with ids, as the counter hands them out in play; a front
        reading's ``item_name`` is turned into the first bag record of that name (``none`` when there is none)."""
        campaign = await self.create_campaign()
        apply_setup(self, campaign, {**beer_scenario().setup, "inventory": ["Bira", "Greatsword", "Bira"]})
        self.last_session_id = campaign["session_id"]
        bag = self.manager.get(campaign["session_id"]).game_session.world_state["inventory"]
        self.assertTrue(all(isinstance(item, dict) and item.get("item_id") for item in bag), bag)
        self.assertEqual([item["name"] for item in bag], ["Bira", "Greatsword", "Bira"])
        self.assertEqual(len({item["item_id"] for item in bag}), 3)
        saved = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertEqual(saved["inventory"], bag)
        self.assertEqual(read_observed(self, campaign["session_id"])["envanter"], {"Bira": 2, "Greatsword": 1})
        drink, sword, nothing = beer_scenario(
            {"say": "biramı içiyorum", "script": {"front": {"kind": "consume", "item_name": "Bira"}}},
            {"say": "kılıcımı yiyorum", "script": {"front": {"kind": "consume", "item_name": "Greatsword"}}},
            {"say": "şarabımı içiyorum", "script": {"front": {"kind": "consume", "item_name": "Şarap"}}},
        ).steps
        for step, wanted in ((drink, bag[0]["item_id"]), (sword, bag[1]["item_id"]), (nothing, "none")):
            with self.subTest(step=step.say), ScriptedModel().bind(self, step) as client:
                front = client._front()
                self.assertEqual((front["kind"], front["item_id"]), ("consume", wanted))
                self.assertNotIn("item_name", front)
        self.assertEqual(drink.script, {"front": {"kind": "consume", "item_name": "Bira"}})  # the step is untouched

    async def test_anlatilan_and_the_counter_tip_are_observed(self):
        """``anlatilan`` is what each person keeps of the player's words (``npc_told_v1``), a state compared on
        reload; ``tezgah`` carries the counter's tip (0 without one) and the total it asks for."""
        campaign = await self.create_campaign()
        apply_setup(self, campaign, beer_scenario().setup)
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        self.assertEqual(read_observed(self, campaign["session_id"])["anlatilan"], {})
        world["npc_told_v1"] = {"gezgin": [{"text": "Babam değirmenci."}, {"text": "Yeşilova'dan geldim.", "cut": False},
                                           {"cut": True}, "satır"],
                                "yolcu": "bozuk"}
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual(observed["anlatilan"], {"gezgin": ["Babam değirmenci.", "Yeşilova'dan geldim."]})
        observed["anlatilan"]["gezgin"].clear()
        self.assertEqual(len(world["npc_told_v1"]["gezgin"]), 4)  # a copy: reading never changes the record

        results = await self.run_scenario(beer_scenario(
            {"say": "bir bira alayım",
             "expect": {"tezgah": {"npc_id": "barman", "key": "bira", "unit_cp": 4, "tip_cp": 0, "total_cp": 4}}}))
        self.assertEqual([result.status for result in results], ["pass"], results)
        live = self.manager.get(self.last_session_id).game_session.world_state
        live["flags"]["counter_offer_v1"]["tip_cp"] = 1
        self.assertEqual(read_observed(self, self.last_session_id)["tezgah"],
                         {"npc_id": "barman", "key": "bira", "unit_cp": 4, "tip_cp": 1, "total_cp": 5})

        class UntoldModel(ScriptedModel):
            """Just before a reload step it changes what a person was told, without saving it."""

            @contextmanager
            def bind(self, case, step):
                with super().bind(case, step) as client:
                    if step.reload:
                        case.manager.get(case.last_session_id).game_session.world_state["npc_told_v1"] = {
                            "barman": [{"text": "Kaydedilmedi."}]}
                    yield client

        results = await self.run_scenario(beer_scenario({"reload": True, "expect": {"kese": 100}}),
                                          model=UntoldModel())
        self.assertEqual(results[0].status, "new_break", results)
        self.assertEqual(results[0].failures,
                         ("yenileme: anlatilan: canlı {'barman': ['Kaydedilmedi.']}, kayıttan {}",))

    async def test_step_bound_observations_are_reset_by_undo_and_reload(self):
        """``konusmaya_giden`` and ``inkar`` belong to the step's own turn: an undo or a reload observes neither, and
        a reload never compares them with the save. ``inkar`` says whether one of the engine's stock denial or
        "I do not know" lines was narrated."""
        denial = runner.game._CLAIM_DENIAL_LINES[0].split("“", 1)[-1].rstrip("”")
        results = await self.run_scenario(beer_scenario(
            {"say": "Bana dün bir söz vermiştin.", "konus": "barman", "script": {"spoken": denial},
             "expect": {"inkar": True, "konusmaya_giden": "dün bir söz"}},
            {"undo": True, "expect": {"inkar": False}},
            {"say": "Akşam kalabalık olur mu?", "konus": "barman", "script": {"spoken": "Olur."},
             "expect": {"inkar": False, "konusmaya_giden": "kalabalık"}},
            {"reload": True, "expect": {"inkar": False}},
        ))
        self.assertEqual([result.status for result in results], ["pass", "pass", "pass", "pass"], results)
        self.assertEqual([observed["konusmaya_giden"] is None for observed in self.last_observations],
                         [False, True, False, True])
        self.assertTrue({"konusmaya_giden", "inkar"} <= runner._NOT_STATE)
        self.assertNotIn("anlatilan", runner._NOT_STATE)
        unknown = runner.interaction_adventure._UNKNOWN_LINES[0].format(n="Marek")
        self.assertTrue(runner.denial_said(f"Marek tezgâhı siliyor. {unknown}"))
        self.assertFalse(runner.denial_said("Marek gülüyor. “Olur.”"))
        self.assertFalse(runner.denial_said(""))

    async def test_setup_materialize_changes_only_the_bag_in_every_scenario(self):
        """For every scenario file with a setup inventory, the setup's ``materialize`` call changes nothing in the
        world but the player's bag (now records with ids, same names in the same order) and the item counter."""
        real = equipment_economy.materialize
        seen = []

        def spy(world):
            before = copy.deepcopy(world)
            real(world)
            seen.append((before, copy.deepcopy(world)))

        paths = [path for path in sorted(runner.SCENARIO_DIR.glob("*.json"))
                 if "inventory" in load_scenario(path).setup]
        self.assertGreaterEqual(len(paths), 18)
        for path in paths:
            scenario = load_scenario(path)
            with self.subTest(scenario=scenario.id):
                seen.clear()
                campaign = await self._journey_campaign(scenario.setup)
                with patch.object(runner.equipment_economy, "materialize", side_effect=spy):
                    apply_setup(self, campaign, scenario.setup)
                (before, after), = seen
                changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
                self.assertLessEqual(changed, {"inventory", "item_sequence"}, changed)
                self.assertEqual([item["name"] for item in after["inventory"]], list(scenario.setup["inventory"]))
                self.assertTrue(all(isinstance(item.get("item_id"), str) for item in after["inventory"]))
                saved = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
                self.assertEqual(saved["inventory"], after["inventory"])

    async def test_what_was_told_survives_the_save_and_a_reload(self):
        """``npc_told_v1`` written and saved goes through the save unchanged: a reload step reads the same
        ``anlatilan`` from the fresh session as the live one holds, so the comparison raises nothing."""
        told = {"gezgin": [{"turn": 1, "text": "Babam değirmenci.", "cut": False}, {"turn": 2, "text": "Yeşilova'dan geldim."}]}

        class TellAndSaveModel(ScriptedModel):
            """Just before a reload step it writes what a person was told and saves the campaign."""

            @contextmanager
            def bind(self, case, step):
                with super().bind(case, step) as client:
                    if step.reload:
                        live = case.manager.get(case.last_session_id)
                        live.game_session.world_state["npc_told_v1"] = copy.deepcopy(told)
                        case.manager.save_campaign(live.campaign_id)
                    yield client

        results = await self.run_scenario(beer_scenario(
            {"reload": True, "expect": {"kese": 100, "anlatilan": {"gezgin": ["değirmenci", "Yeşilova"]}}}),
            model=TellAndSaveModel())
        self.assertEqual([result.status for result in results], ["pass"], results)
        self.assertEqual(self.last_observations[-1]["anlatilan"],
                         {"gezgin": ["Babam değirmenci.", "Yeşilova'dan geldim."]})
        campaign_id = self.manager.get(self.last_session_id).campaign_id
        saved = self.store.get_campaign(campaign_id).payload["engine_save"]["world_state"]
        self.assertEqual(saved["npc_told_v1"], told)

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


    async def test_gunluk_is_read_from_the_quest_log_and_the_counter_is_checked(self):
        campaign = await self.create_campaign()
        sid = campaign["session_id"]
        real = serializers.serialize_session_state
        def with_log(log):
            return patch.object(serializers, "serialize_session_state", lambda session: {**real(session), "quest_log": log})
        log = {"active_count": 1, "active": [{"title": "Teslimat: Revomar İskelesi"}],
               "done": [{"title": "Kayıp mektup", "result": "12 bakır ödendi"}],
               "trails": [{"what": "Tuna bir sorundan söz etti", "where": "Revomar İskelesi", "source": "teslim", "followed": False}]}
        with patch.object(serializers, "serialize_session_state", lambda session: {k: v for k, v in real(session).items() if k != "quest_log"}):
            self.assertIsNone(read_observed(self, sid)["gunluk"])          # no quest_log field: None (before Görev 6)
        with with_log(log):
            self.assertEqual(read_observed(self, sid)["gunluk"], {
                "sayac": 1, "suren": ["Teslimat: Revomar İskelesi"], "biten": ["Kayıp mektup (12 bakır ödendi)"],
                "iz": [{"ne": "Tuna bir sorundan söz etti", "nerede": "Revomar İskelesi", "kaynak": "teslim", "izlendi": False}]})
        with with_log({**log, "active_count": 2}):
            results = await self.run_scenario(beer_scenario({"say": "etrafıma bakıyorum", "expect": {"kese": 100}}))
        self.assertTrue(any("gunluk: sayaç ile süren sayısı farklı" in failure for failure in results[0].failures), results)

    async def test_elinde_reads_the_main_hand_name(self):
        campaign = await self.create_campaign()
        sid = campaign["session_id"]
        apply_setup(self, campaign, {"inventory": ["Greatsword"]})
        world = self.manager.get(sid).game_session.world_state
        equipment_economy.materialize(world)
        world.setdefault("equipment", {})["main_hand"] = None
        self.assertIsNone(read_observed(self, sid)["elinde"])
        sword = next(item for item in world["inventory"] if isinstance(item, dict) and item.get("name") == "Greatsword")
        world["equipment"]["main_hand"] = sword["item_id"]
        self.assertEqual(read_observed(self, sid)["elinde"], "Greatsword")
        world["equipment"]["main_hand"] = "item:not-in-the-bag"
        self.assertIsNone(read_observed(self, sid)["elinde"])               # a hand pointing at nothing reads empty

    async def test_wield_is_a_front_kind_and_item_name_becomes_the_bag_id(self):
        # Dilim 1's item_name translation (name in the bag -> that item's id) applies to wield as to consume.
        # The engine learns the kind in Görev 15; the harness accepts it now (a scripted front packet only).
        campaign = await self.create_campaign()
        apply_setup(self, campaign, {**beer_scenario().setup, "inventory": ["Greatsword"]})
        self.last_session_id = campaign["session_id"]
        (step,) = beer_scenario({"say": "kılıcımı çekiyorum",
                                 "script": {"front": {"kind": "wield", "item_name": "Greatsword"}}}).steps
        with ScriptedModel().bind(self, step) as client:
            front = client._front()
        bag = self.manager.get(campaign["session_id"]).game_session.world_state["inventory"]
        sword = next(item for item in bag if item.get("name") == "Greatsword")
        self.assertEqual((front["kind"], front["item_id"]), ("wield", sword["item_id"]))
        self.assertNotIn("item_name", front)


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


class TheMarkerCause(unittest.TestCase):
    """Ruling R19: what a known-broken marker may stand for."""

    def marked(self, *because):
        step = {"say": "x", "known_broken": [35]}
        if because:
            step["broken_because"] = list(because)
        return beer_scenario(step).steps[0]

    def test_a_server_error_an_unexpected_model_call_or_a_reload_mismatch_is_always_new(self):
        step = self.marked("HTTP", "beklenmeyen", "yenileme", "kese")
        for failure in ("HTTP 500: {\"detail\": \"boom\"}", "HTTP 503: kapalı", "beklenmeyen model çağrısı: ['verdict']",
                        "yenileme: kese: canlı 96, kayıttan 100"):
            with self.subTest(failure=failure):
                self.assertEqual(step_status(step, [failure]), "new_break")
                self.assertEqual(step_status(step, ["kese: beklenen 95, gözlenen 96", failure]), "new_break")
                self.assertEqual(step_status(self.marked(), [failure]), "new_break")
        self.assertEqual(step_status(step, ['HTTP 400: {"detail":{"code":"no_weapon"}}']), "known_broken")

    def test_every_failure_must_hold_a_named_cause(self):
        step = self.marked("no_weapon", "kese: beklenen")
        self.assertEqual(step_status(step, []), "marker_stale")
        self.assertEqual(step_status(step, ["kese: beklenen 95, gözlenen 96"]), "known_broken")
        self.assertEqual(step_status(step, ['HTTP 400: {"code":"no_weapon"}', "kese: beklenen 9, gözlenen 1"]),
                         "known_broken")
        self.assertEqual(step_status(step, ["kese: beklenen 95, gözlenen 96", "savas: beklenen True"]), "new_break")
        # A marker without a named cause still stands for any failure but the always-new ones.
        self.assertEqual(step_status(self.marked(), ["savas: beklenen True"]), "known_broken")
        unmarked = beer_scenario({"say": "x"}).steps[0]
        self.assertEqual((step_status(unmarked, []), step_status(unmarked, ["kese"])), ("pass", "new_break"))

    def test_the_summary_says_how_many_steps_wait_for_the_real_chain(self):
        def unreached(index, why):
            return StepResult(index, "unreached", (why,), (), "", 0.0)

        results = {
            "rc": [StepResult(1, "pass", (), (), "", 0.0), unreached(2, runner.REAL_CHAIN_ONLY),
                   unreached(3, runner.REAL_CHAIN_ONLY)],
            # A real-chain step cut by an earlier known break waits for the engine, not for the chain.
            "b": [StepResult(1, "known_broken", ("x",), (35,), "", 0.0), unreached(2, "adım 1 bilinen kırık; bu adım koşulmadı")],
        }
        self.assertEqual(summary_line(results), "1 geçti, 1 bilinen kırık, 0 yeni kırık (2 adım yalnız gerçek zincirde)")


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

    def test_the_arrival_call_is_its_own_kind(self):
        self.assertEqual(call_kind(ARRIVAL_SCHEMA), "arrival")
        self.assertEqual(call_kind({"properties": {"narration": {}}}), "narration")

    def test_a_scripted_arrival_answers_with_the_script(self):
        client = ScriptedClient({"arrival": "Sis kalkmamış."})
        packet = json.loads(client.chat(format=ARRIVAL_SCHEMA)["message"]["content"])
        self.assertEqual(packet, {"narration": "Sis kalkmamış.", "world_updates": {}, "lore_claims": []})
        self.assertEqual(client.kinds, ["arrival"])

    def test_a_scripted_arrival_packet_is_returned_as_written(self):
        broken = {"narration": 5, "world_updates": {"x": 1}, "lore_claims": "yok"}
        client = ScriptedClient({"arrival": broken})
        self.assertEqual(json.loads(client.chat(format=ARRIVAL_SCHEMA)["message"]["content"]), broken)

    def test_front_readings_answer_one_after_another(self):
        client = ScriptedClient({"fronts": [{"kind": "go_to"}, {"kind": "speak_to"}]})
        schema = {"properties": {"front": {}}}
        kinds = [json.loads(client.chat(format=schema)["message"]["content"])["front"]["kind"] for _ in range(3)]
        self.assertEqual(kinds, ["go_to", "speak_to", "speak_to"])  # the last reading stays for any call after it

    def test_an_unscripted_arrival_call_falls_back_quietly(self):
        client = ScriptedClient({"narration": "Başka."})
        with self.assertRaises(RuntimeError):
            client.chat(format=ARRIVAL_SCHEMA)
        self.assertEqual(client.unexpected, [])
        self.assertEqual(client.kinds, ["arrival_unscripted"])

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

    def test_speech_script_fields_reach_the_speech_packet(self):
        """``speech`` adds the speech answer's own fields; their values pass as written, a broken one too, so a
        scenario can try a missing or broken answer. An unknown field or a ``speech`` that is no object fails."""
        def speak(script):
            return json.loads(ScriptedClient(script).chat(format=SPEECH)["message"]["content"])

        packet = speak({"speech": {"coin_answer": "declines", "coin_answer_for": "tip"}})
        self.assertEqual((packet["coin_answer"], packet["coin_answer_for"]), ("declines", "tip"))
        self.assertEqual(speak({"speech": {"coin_answer": 7}})["coin_answer"], 7)
        remembered = speak({"spoken": "Demek değirmenciydi.", "speech": {"remember_player_line": True}})
        self.assertEqual((remembered["spoken_text"], remembered["remember_player_line"]), ("Demek değirmenciydi.", True))
        self.assertNotIn("coin_answer", speak({}))  # without a script the answer leaves the fields out
        for wrong in ({"speech": "declines"}, {"speech": {"coin_anwser": "declines"}},
                      {"speech": {"spoken_text": "x"}}):
            with self.subTest(wrong=wrong), self.assertRaises(ScenarioError) as raised:
                ScriptedClient(wrong)
            self.assertIn("speech", str(raised.exception))


    def test_speech_script_carries_asks_for(self):
        speech_schema = {"type": "object", "properties": {"spoken_text": {"type": "string"}, "stage_direction": {"type": "string"},
                                                          "asks_for": {"type": "string", "enum": ["room", "none"]}}}
        packet = json.loads(ScriptedClient({"speech": {"asks_for": "room"}}).chat(format=speech_schema)["message"]["content"])
        self.assertEqual(packet["asks_for"], "room")
        plain = json.loads(ScriptedClient({}).chat(format=speech_schema)["message"]["content"])
        self.assertNotIn("asks_for", plain)                                 # unscripted: the field is absent, never invented


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

    def test_arrival_calls_are_counted_and_kept_out_of_the_narrator_input(self):
        told = NarratorInput(ScriptedClient({"arrival": "A."}).chat)
        self.assertEqual(told.arrival_calls(), 0)
        told(format=ARRIVAL_SCHEMA, messages=[{"role": "user", "content": "olgular"}])
        self.assertEqual(told.arrival_calls(), 1)
        self.assertIsNone(told.text())

    def test_the_last_speech_calls_messages_are_kept_apart(self):
        listen = NarratorInput(lambda *args, **kwargs: {"message": {"content": "{}"}})
        self.assertIsNone(listen.speech_messages())
        listen(model="m", messages=[{"role": "user", "content": "Anlat."}], format={"properties": {"narration": {}}})
        self.assertIsNone(listen.speech_messages(), "a narrator call is not a speech call")
        listen(model="m", messages=[{"role": "system", "content": "Sen Marek'sin."}, {"role": "user", "content": "selam"}],
               format={"properties": {"spoken_text": {}, "stage_direction": {}}})
        self.assertEqual(listen.speech_messages(), ["Sen Marek'sin.", "selam"])
        listen(model="m", messages=[{"role": "user", "content": "ikinci"}, "bozuk"],
               format={"properties": {"spoken_text": {}}})
        self.assertEqual(listen.speech_messages(), ["ikinci"])  # the last speech call only
        listen.speech_messages().append("x")
        self.assertEqual(listen.speech_messages(), ["ikinci"])  # a copy
        self.assertEqual(listen.text(), "Anlat.")  # the narrator's input is unchanged

    def test_the_readings_the_model_gave_are_kept_for_the_report(self):
        replies = iter(['{"front": {"kind": "speak_to"}}', '{"intent": "talk"}', '{"narration": "x"}'])
        listen = NarratorInput(lambda *args, **kwargs: {"message": {"content": next(replies)}})
        self.assertEqual(listen.reading(), "")
        listen(model="m", messages=[], format={"properties": {"front": {}, "intent": {}}})
        listen(model="m", messages=[], format={"properties": {"intent": {}}})
        listen(model="m", messages=[], format={"properties": {"narration": {}}})
        self.assertEqual(listen.reading(), '{"front": {"kind": "speak_to"}} | {"intent": "talk"}')


class StageNoEventModel(ScriptedModel):
    """The default driver, but just before the step it takes the scene's ambient event away."""

    @contextmanager
    def bind(self, case, step):
        with super().bind(case, step) as client:
            world = case.manager.get(case.last_session_id).game_session.world_state
            world["scene_state"]["scenes"][world["location"]].pop("ambient_event", None)
            yield client


class TheDilim3Additions(JourneyCase):
    def world(self, campaign):
        return self.manager.get(campaign["session_id"]).game_session.world_state

    def scene(self, campaign):
        world = self.world(campaign)
        return world["scene_state"]["scenes"][world["location"]]

    async def campaign_with_setup(self, ambient_event, **extra):
        setup = {**beer_scenario().setup, "campaign_start": NEVERWINTER, "ambient_event": ambient_event, **extra}
        campaign = await self._journey_campaign(setup)
        # What the campaign's own opening already showed (Task 18 may open on this very event), before the setup.
        self.counts_before = copy.deepcopy(self.world(campaign)["scene_state"]["ambient_event_counts"])
        apply_setup(self, campaign, setup)
        return campaign

    def ambient_scenario(self, *steps, event=None):
        setup = {**beer_scenario().setup, "campaign_start": NEVERWINTER,
                 "ambient_event": event or {"event_id": "city_lost_ring", "turns_ago": 0}}
        return beer_scenario(*steps, setup=setup)

    async def test_an_ambient_step_clicks_the_scene_event_through_the_product_route(self):
        results = await self.run_scenario(self.ambient_scenario({"ambient": {"action": "interact"}}))
        self.assertEqual([result.status for result in results], ["pass"], results)
        self.assertEqual(self.last_observations[0]["ambient"],
                         {"status": "APPLIED", "reason_code": "referent_promoted"})

    async def test_an_observe_click_has_no_effect_and_an_expired_event_is_refused(self):
        results = await self.run_scenario(self.ambient_scenario({"ambient": {"action": "observe"}}))
        self.assertEqual(results[0].status, "pass", results)
        self.assertEqual(self.last_observations[0]["ambient"]["status"], "NO_EFFECT")
        await self.run_scenario(self.ambient_scenario({"ambient": {"action": "interact"}},
                                                      event={"event_id": "city_lost_ring", "turns_ago": 13}))
        self.assertEqual(self.last_observations[0]["ambient"],
                         {"status": "REJECTED", "reason_code": "event_expired"})

    async def test_an_ambient_step_with_no_event_in_the_scene_fails_plainly(self):
        results = await self.run_scenario(self.ambient_scenario({"ambient": {"action": "interact"}}),
                                          model=StageNoEventModel())
        self.assertEqual(results[0].status, "new_break")
        self.assertEqual(results[0].failures[0], "ambient: sahnede olay yok")

    async def test_an_undo_step_after_an_ambient_step_names_the_click_as_the_turn_to_take_back(self):
        # Whether the product can take the click back is the product's answer (it is checked by its own journey);
        # the harness's part is to ask for the click's own action id.
        sent = []
        post = self.http_post_recorder(sent)
        with patch.object(JourneyCase, "_journey_campaign", post):
            await self.run_scenario(self.ambient_scenario({"ambient": {"action": "interact"}}, {"undo": True}))
        click = next(body for url, body in sent if "/ambient-events/" in url)
        undo = next(body for url, body in sent if url.endswith("/undo"))
        self.assertEqual(undo["target_action_id"], click["action_id"])

    def http_post_recorder(self, sent):
        original = JourneyCase._journey_campaign

        async def campaign(case, setup):
            made = await original(case, setup)
            real = case.http.post

            async def post(url, **kwargs):
                sent.append((url, kwargs.get("json")))
                return await real(url, **kwargs)

            case.http.post = post
            return made

        return campaign

    async def test_the_ambient_event_setup_places_a_live_or_expired_event(self):
        fresh = await self.campaign_with_setup({"event_id": "city_lost_ring", "turns_ago": 0})
        stale = await self.campaign_with_setup({"event_id": "city_lost_ring", "turns_ago": 13})
        self.assertEqual(self.scene(fresh)["ambient_event"]["event_id"], "city_lost_ring")
        for campaign, live in ((fresh, True), (stale, False)):
            scene = self.scene(campaign)
            referent = next(item for item in scene["referents"] if item["id"] == scene["ambient_event"]["referent_id"])
            turn = self.world(campaign)["flags"].get("turn_index", 0)
            self.assertEqual(turn <= referent["expires_after_turn"], live)
        fresh = await self.campaign_with_setup({"event_id": "city_lost_ring", "turns_ago": 0})
        self.assertEqual(self.world(fresh)["scene_state"]["ambient_event_counts"]["city_lost_ring"],
                         self.counts_before.get("city_lost_ring", 0) + 1)  # the setup records it once
        for wrong in ({"event_id": "no_such_event", "turns_ago": 0}, {"event_id": "city_lost_ring", "turns_ago": -1},
                      {"event_id": "city_lost_ring", "turns_ago": True}, {"event_id": "city_lost_ring"},
                      {"turns_ago": 0}, "city_lost_ring"):
            with self.subTest(wrong=wrong), self.assertRaises(ScenarioError):
                await self.campaign_with_setup(wrong)

    async def test_the_setup_event_is_the_scene_event_and_counted_once_whatever_the_opening_showed(self):
        # Seeds 1-8 include openings that already showed city_lost_ring (the case that made the count 2 by chance).
        opened_on_it = []
        for seed in range(1, 9):
            with self.subTest(seed=seed):
                campaign = await self.campaign_with_setup({"event_id": "city_lost_ring", "turns_ago": 0},
                                                          campaign_seed=seed)
                if self.counts_before.get("city_lost_ring"):
                    opened_on_it.append(seed)
                scene = self.scene(campaign)
                self.assertEqual(scene["ambient_event"]["event_id"], "city_lost_ring")
                self.assertEqual([r["id"] for r in scene["referents"]], [scene["ambient_event"]["referent_id"]])
                self.assertEqual(self.world(campaign)["scene_state"]["ambient_event_counts"]["city_lost_ring"],
                                 self.counts_before.get("city_lost_ring", 0) + 1)
        self.assertTrue(opened_on_it, "no seed in 1-8 opened on city_lost_ring: the colliding case went untested")

    async def test_the_scene_event_is_observed_and_survives_a_reload(self):
        results = await self.run_scenario(self.ambient_scenario(
            {"say": "etrafa bakıyorum", "expect": {"olay": {"var": True}}},
            {"reload": True, "expect": {"olay": {"var": True}}}))
        self.assertEqual([result.status for result in results], ["pass", "pass"], results)
        self.assertEqual(self.last_observations[0]["olay"], {"var": True, "tiklanabilir": True, "neden": None})

    async def test_a_scene_without_an_event_reads_as_no_event(self):
        campaign = await self.create_campaign()
        self.assertEqual(read_observed(self, campaign["session_id"])["olay"],
                         {"var": False, "tiklanabilir": None, "neden": None})

    async def test_zirh_reads_the_armor_class(self):
        campaign = await self.create_campaign()
        sid = campaign["session_id"]
        self.manager.get(sid).game_session.character["armor_class"] = 17
        self.assertEqual(read_observed(self, sid)["zirh"], 17)


class TheStartHour(JourneyCase):
    async def campaign_at(self, **extra):
        setup = {**beer_scenario().setup, "campaign_start": NEVERWINTER, "campaign_seed": 38, **extra}
        self.campaign = await self._journey_campaign(setup)
        apply_setup(self, self.campaign, setup)
        return self.manager.get(self.campaign["session_id"]).game_session.world_state

    async def test_start_hour_sets_the_clock(self):
        world = await self.campaign_at(start_hour=18)
        public = campaign_time.public_time(world)
        self.assertEqual((public["hour"], public["time_of_day"]), (18, "evening"))
        self.assertEqual(world["campaign_time"]["start_second"], 18 * 3600)

    async def test_a_start_hour_outside_the_day_is_refused(self):
        await self.campaign_at()
        for bad in (-1, 24, "18", 18.5, True):
            with self.subTest(bad=bad), self.assertRaises(ScenarioError):
                apply_setup(self, self.campaign, {"start_hour": bad})


if __name__ == "__main__":
    unittest.main()
