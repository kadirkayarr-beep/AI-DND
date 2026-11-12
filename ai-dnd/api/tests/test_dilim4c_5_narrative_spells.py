"""Dilim 4C.5: the narrative spell layer (Mage Hand, Minor Illusion, Light, Prestidigitation) and the "not yet" line.

The engine decides and commits: a known cantrip with its components, outside a fight, writes one fact
(`world_state["spell_effects_v1"]`: spell, place, from/until second; range and duration from the PHB index); no slot, no
action budget, no time, no money, no item. A money/item line is no narrative cast (K2). A spell the PHB names with no
owner, or a narrative spell in a fight, gets a truthful line and nothing changes. The fact is validated on load and lives
in the Undo snapshot; a cantrip leaves every preparation window open (D-038 is about slot spells).

Engine fixtures: test_spell_preparation_4c2.prepper/rested (real initializer, no campaign town). HTTP: CampaignApiTests
with `fixed_town`."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import spell_effects
import spell_preparation
import spell_scope
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaign_fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_spell_preparation_4c2 import now, prepper, rested
from api.tests.town_seed import fixed_town

KEY = spell_effects.KEY


def wizard():
    s = prepper("Wizard")  # cantrips: Fire Bolt, Ray of Frost, Mage Hand
    s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
    return s


def frozen(s):
    return copy.deepcopy((s.world_state, s.character))


class NamedLines(unittest.TestCase):
    def test_the_reading_table(self):
        table = {
            "Mage Hand ile kapının mandalını kaldırıyorum": ("narrative", "Mage Hand"),
            "Büyücü Eli büyüsünü yapıyorum": ("narrative", "Mage Hand"),
            "Minor Illusion ile bir kedi sesi çıkarıyorum": ("narrative", "Minor Illusion"),
            "Işık büyüsü yapıyorum": ("narrative", "Light"),
            "I cast light on my staff": ("narrative", "Light"),
            "Prestidigitation ile mumu yakıyorum": ("narrative", "Prestidigitation"),
            "Shield büyüsünü yapıyorum": ("not_yet", "Shield"),
            "Kalkan büyüsünü yapıyorum": ("not_yet", "Shield"),
            "I cast Sleep": ("not_yet", "Sleep"),
            # no cast: K2 money/item, question, negation, everyday words, a resolver's own spell, a wizard
            "Mage Hand ile kesesini çalıyorum": None,
            "Mage Hand ile bardağı bana getiriyorum": None,
            "Mage Hand ile tezgâhtaki altını alıyorum": None,
            "Mage Hand nedir?": None,
            "Mage Hand kullanmıyorum": None,
            "ışığı yakıyorum": None,
            "I light a torch": None,
            "Büyücüye kalkanı gösteriyorum": None,
            "Fire Bolt büyüsünü atıyorum": None,
            "Konsantrasyonu bırakıyorum": None,
        }
        for line, expected in table.items():
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line), expected)

    def test_a_money_line_naming_a_narrative_spell_is_no_spell_command(self):
        line = "Mage Hand büyüsünü kullanıp kesesini çalıyorum"
        self.assertIsNone(spell_scope.natural_command(line, None))  # not "unsupported_spell": it goes on to today's paths
        self.assertFalse(spell_effects.named(line))

    def test_a_narrative_line_needs_no_model_reading(self):
        self.assertTrue(spell_scope.explicit_request("Mage Hand ile kapının mandalını kaldırıyorum"))
        self.assertTrue(spell_scope.explicit_request("Shield büyüsünü yapıyorum"))


class NarrativeCast(unittest.TestCase):
    def test_mage_hand_writes_one_fact_and_spends_nothing(self):
        s = wizard()
        before = frozen(s)
        second = now(s)
        cast = spell_effects.resolve(s, ("narrative", "Mage Hand"))
        fact = {"id": f"mage_hand-{second}", "spell_id": "Mage Hand", "kind": "narrative",
                "location_id": s.world_state["location"], "cast_second": second, "until_second": second + 60}
        self.assertEqual(s.world_state[KEY], [fact])
        self.assertEqual(cast["action_result"]["spell_effect"], fact)
        self.assertEqual({k: cast["action_result"][k] for k in ("action", "status", "spell", "slot_spent", "range",
                                                                "duration")},
                         {"action": "narrative_spell", "status": "resolved", "spell": "Mage Hand", "slot_spent": False,
                          "range": "30 feet", "duration": "1 minute"})
        self.assertEqual(cast["narration"], "Büyücü Eli (Mage Hand): 30 fit içinde hayalet bir el belirir ve dediğin "
                                            "işe uzanır; büyü bir dakika sürer. Yuva harcanmaz.")
        world, character = frozen(s)
        world.pop(KEY)
        self.assertEqual((world, character), before)  # only the fact: slots, coins, items, HP, clock untouched

    def test_light_reads_its_source_duration_and_touch_range(self):
        s = prepper("Cleric")  # the Cleric creation list offers Light: it takes Thaumaturgy's place
        for cantrips in (s.character["cantrips"], s.world_state["spellcasting_v1"]["cantrips"]):
            cantrips[cantrips.index("Thaumaturgy")] = "Light"
        s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        cast = spell_effects.resolve(s, ("narrative", "Light"))
        self.assertEqual(cast["narration"], "Işık (Light): dokunduğun nesne ışık saçmaya başlar; büyü bir saat sürer. "
                                            "Yuva harcanmaz.")
        self.assertEqual(s.world_state[KEY][0]["until_second"] - s.world_state[KEY][0]["cast_second"], 3600)

    def test_a_second_cast_replaces_the_first_and_finished_facts_go(self):
        s = wizard()
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        s.world_state["campaign_time"]["elapsed_seconds"] += 30
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual([f["cast_second"] for f in s.world_state[KEY]], [now(s)])
        s.world_state["campaign_time"]["elapsed_seconds"] += 60
        self.assertEqual(spell_effects.active(s.world_state), [])

    def test_an_unknown_cantrip_is_not_cast(self):
        s = wizard()
        before = frozen(s)
        cast = spell_effects.resolve(s, ("narrative", "Light"))
        self.assertEqual((cast["action_result"]["status"], cast["action_result"]["reason"]),
                         ("unsupported", "spell_not_available"))
        self.assertIn("bildiğin büyüler arasında değil", cast["narration"])
        self.assertEqual(frozen(s), before)

    def test_somatic_needs_a_free_hand(self):
        s = wizard()
        s.world_state["equipment"] = {"main_hand": "Quarterstaff", "off_hand": "Shield"}
        before = frozen(s)
        cast = spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(cast["action_result"]["reason"], "spell_components_unavailable")
        self.assertIn("bir elinin boş olması gerekir", cast["narration"])
        self.assertEqual(frozen(s), before)

    def test_a_silenced_caster_cannot_give_the_verbal_part(self):
        s = wizard()
        s.character["conditions"] = ["silenced"]
        before = frozen(s)
        cast = spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(cast["action_result"]["reason"], "spell_components_unavailable")
        self.assertEqual(frozen(s), before)

    def test_in_a_fight_it_is_not_yet_in_the_engine(self):
        from api.tests import test_death_system as fixtures
        s = wizard()
        fixtures.start_test_combat(s)
        before = frozen(s)
        cast = spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(cast["action_result"]["reason"], "narrative_spell_in_combat")
        self.assertIn("savaşta henüz motorda yok", cast["narration"])
        self.assertEqual(frozen(s), before)

    def test_a_spell_with_no_owner_gets_the_not_yet_line(self):
        s = wizard()
        before = frozen(s)
        cast = spell_effects.resolve(s, ("not_yet", "Shield"))
        self.assertEqual(cast["narration"], "Shield büyüsü henüz motorda yok; büyü yapılmadı, yuvan ve eylemin "
                                            "harcanmadı.")
        self.assertEqual((cast["action_result"]["status"], cast["action_result"]["slot_spent"]), ("unsupported", False))
        self.assertEqual(frozen(s), before)


class D038CantripLeavesTheWindows(unittest.TestCase):
    """D-038 is about slot spells (still refused outside a fight: test_dilim4c_4b_review_fixes.D038HasNoReachableCast).
    A narrative cantrip needs no prepared list, so it closes no preparation window (fix round 1, Ruling)."""

    def test_a_long_rest_window_stays_open(self):
        s = rested("Wizard")
        s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        window = copy.deepcopy(s.world_state["spellcasting_v1"]["prepare_window"])
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(s.world_state["spellcasting_v1"]["prepare_window"], window)
        self.assertTrue(spell_preparation.window_open(s))

    def test_a_creation_window_waits_for_its_list(self):
        s = wizard()
        window = copy.deepcopy(s.world_state["spellcasting_v1"]["prepare_window"])
        self.assertEqual(window["reason"], "creation")
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        self.assertEqual(s.world_state["spellcasting_v1"]["prepare_window"], window)


class SavedFacts(unittest.TestCase):
    def fact(self, **change):
        return {"id": "mage_hand-0", "spell_id": "Mage Hand", "kind": "narrative", "location_id": "tavern",
                "cast_second": 0, "until_second": 60, **change}

    def test_valid_and_absent_load(self):
        spell_effects.validate_saved({})
        spell_effects.validate_saved({KEY: []})
        spell_effects.validate_saved({KEY: [self.fact(), self.fact(id="light-0", spell_id="Light", until_second=3600)]})

    def test_forged_shapes_are_refused(self):
        forged = [None, {}, [self.fact(extra=1)], [self.fact(spell_id="Fire Bolt")], [self.fact(kind="bless")],
                  [self.fact(), self.fact()], [self.fact(until_second=0)], [self.fact(cast_second=-1)],
                  [self.fact(cast_second=True)], [self.fact(location_id="")], [self.fact(id="")],
                  [self.fact(spell_id=name) for name in [*spell_effects.NARRATIVE, "Mage Hand"]]]
        for value in forged:
            with self.subTest(value=value), self.assertRaises(ValueError):
                spell_effects.validate_saved({KEY: value})

    def test_the_save_loader_checks_the_fact(self):
        import game
        s = wizard()
        spell_effects.resolve(s, ("narrative", "Mage Hand"))
        game._validate_save_payload(s.serialize_game_state())  # a real fact loads
        s.world_state[KEY][0]["kind"] = "speed_penalty"
        with self.assertRaises(ValueError):
            game._validate_save_payload(s.serialize_game_state())


class NarrativeSpellHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def campaign(self, seed):
        with fixed_town(self, seed):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        record = self.manager.get(campaign["session_id"])
        s = record.game_session
        prepper("Wizard", s)
        s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        self.manager.save_campaign(campaign["campaign_id"])
        return campaign, record

    async def post(self, campaign, body):
        return await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=body)

    def stored(self, campaign):
        return self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]

    def ledger(self, s):
        return (copy.deepcopy(s.world_state.get("currency")), copy.deepcopy(s.world_state.get("inventory")),
                copy.deepcopy(s.world_state["spellcasting_v1"]["slots"]), s.character["current_hp"])

    async def test_mage_hand_receipt_store_resume_undo_and_one_fact(self):
        campaign, record = await self.campaign(4501)
        s = record.game_session
        before = self.ledger(s)
        turn = {"message": "Mage Hand ile kapının mandalını kaldırıyorum", "action_id": str(uuid4())}
        cast = await self.post(campaign, turn)
        self.assertEqual(cast.status_code, 200, cast.text)
        body = cast.json()
        self.assertTrue(body["narration"].strip())
        [fact] = s.world_state[KEY]
        self.assertEqual((fact["spell_id"], fact["until_second"] - fact["cast_second"]), ("Mage Hand", 60))
        self.assertEqual(self.ledger(s), before)  # no coin, item, slot or HP moved
        self.assertEqual(self.stored(campaign)[KEY], [fact])

        with patch("spell_effects.resolve", side_effect=AssertionError("replay recast")):
            replay = await self.post(campaign, turn)
        self.assertEqual((replay.status_code, replay.json()), (200, body))

        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, resumed, *_ = manager.resume_campaign(campaign["campaign_id"])
        self.assertEqual(resumed.game_session.world_state[KEY], [fact])

        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid4()), "target_action_id": turn["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        s = record.game_session
        self.assertNotIn(KEY, s.world_state)
        self.assertNotIn(KEY, self.stored(campaign))

        again = await self.post(campaign, {**turn, "action_id": str(uuid4())})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual([f["spell_id"] for f in s.world_state[KEY]], ["Mage Hand"])
        self.assertEqual(self.ledger(s), before)

    async def test_a_spell_not_in_the_engine_is_a_plain_line(self):
        campaign, record = await self.campaign(4502)
        s = record.game_session
        before = self.ledger(s)
        said = await self.post(campaign, {"message": "Shield büyüsünü yapıyorum", "action_id": str(uuid4())})
        self.assertEqual(said.status_code, 200, said.text)
        self.assertIn("Shield büyüsü henüz motorda yok", said.json()["narration"])
        self.assertNotIn(KEY, s.world_state)
        self.assertEqual(self.ledger(s), before)


if __name__ == "__main__":
    unittest.main()
