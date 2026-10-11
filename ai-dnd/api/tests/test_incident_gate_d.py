"""Gate D / Neverwinter H: categories, reviewed profile, lore safety."""

import json
import unittest
from unittest.mock import patch

from api import ollama_adapter
from api.tests.test_incident_gate_a import PROFILE, _envelope, _proposal, _world
from incidents import categories, envelope, gate, profiles, triggers


class CategoryOwnerTests(unittest.TestCase):
    def test_python_owns_dc_and_gambling_never_pays(self):
        self.assertEqual(categories.dc_for("easy"), 10)
        self.assertEqual(categories.dc_for("medium"), 15)
        self.assertEqual(categories.dc_for("made_up"), 15)
        self.assertEqual(categories.skill_for("insight"), "Insight")
        self.assertFalse(categories.gambling_pays({"action": "gambling", "source": "narration", "gp": 50}))
        self.assertFalse(categories.gambling_pays({"action": "gambling", "success": True}))

    def test_motif_cooldown_silences_a_repeat(self):
        _, world = _world()
        world["emergence_state"] = {
            "budget": {}, "cooldowns": {},
            "recent_categories": ["disturbance", "disturbance", "disturbance"],
            "paid_signatures": [],
        }
        self.assertFalse(categories.motif_allowed(world, "disturbance"))
        live = {
            **PROFILE, "silence_rate": 0.0,
            "category_weights": (("disturbance", 1),),
            "reward_weights": (("none", 1),),
        }
        world["campaign_id"] = "campaign.test"
        self.assertIsNone(triggers.select(
            world, campaign_id="campaign.test",
            trigger={"kind": "arrival", "location_id": "tavern"}, profile=live,
        ))

    def test_travel_segment_is_wilderness_only(self):
        _, world = _world()
        world["location"] = "forest"
        self.assertEqual(
            triggers.detect(
                world, action_result={"action": "travel", "success": True},
                player_text="", location_changed=True,
            )["kind"],
            "travel_segment",
        )
        world["location"] = "tavern"
        self.assertEqual(
            triggers.detect(
                world, action_result={"action": "travel", "success": True},
                player_text="", location_changed=True,
            )["kind"],
            "arrival",
        )


class ProfileLoaderTests(unittest.TestCase):
    def test_neverwinter_loads_from_reviewed_pack(self):
        loaded = profiles.load("neverwinter.v1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["pack_id"], "fr:pack:the_north:neverwinter:v1")
        self.assertEqual(loaded["review_status"], "VERIFIED_PARTIAL")
        self.assertIn("Dagult Neverember", loaded["protected_names"])
        self.assertIn("Waterdeep", loaded["protected_names"])
        self.assertIn("fr:faction:lords_alliance", loaded["faction_ids"])
        self.assertEqual(loaded["faction_rank_ceiling"], "member")

    def test_waterdeep_and_baldurs_gate_stay_off(self):
        self.assertIsNone(profiles.load("waterdeep.v1"))
        self.assertIsNone(profiles.load("baldurs_gate.v1"))
        _, world = _world()
        world["locations"]["waterdeep"] = {"id": "waterdeep", "name": "Waterdeep", "type": "city"}
        world["locations"]["baldurs_gate"] = {"id": "baldurs_gate", "name": "Baldur's Gate", "type": "city"}
        self.assertIsNone(profiles.resolve(world, "waterdeep"))
        self.assertIsNone(profiles.resolve(world, "fr:city:waterdeep"))
        self.assertIsNone(profiles.resolve(world, "baldurs_gate"))

    def test_unreviewed_and_missing_source_refuse(self):
        with patch("incidents.profiles._pack_coverage", return_value="INCOMPLETE"):
            self.assertIsNone(profiles.load("neverwinter.v1"))
        with patch("incidents.profiles._pack_coverage", return_value=None):
            self.assertIsNone(profiles.load("neverwinter.v1"))

    def test_tavern_and_neverwinter_resolve_castle_does_not(self):
        _, world = _world()
        self.assertEqual(profiles.resolve(world, "tavern")["profile_id"], "neverwinter.v1")
        world["locations"]["fr:city:neverwinter"] = {
            "id": "fr:city:neverwinter", "name": "Neverwinter", "type": "city",
        }
        self.assertEqual(profiles.resolve(world, "fr:city:neverwinter")["profile_id"], "neverwinter.v1")
        self.assertIsNone(profiles.resolve(world, "castle"))
        self.assertFalse(profiles.generation_enabled(world))
        world["flags"]["emergence_live"] = True
        self.assertTrue(profiles.generation_enabled(world))


class LoreSafetyGateTests(unittest.TestCase):
    def setUp(self):
        _, self.world = _world()
        self.envelope = _envelope(self.world, reward="none")

    def _eval(self, **overrides):
        return gate.evaluate(self.envelope, _proposal(**overrides))

    def test_invented_waterdeep_district_and_foreign_city(self):
        profile = profiles.load("neverwinter.v1")
        built = envelope.build(
            self.world, campaign_id="campaign.test",
            trigger_id=self.envelope["trigger_id"], trigger_kind="arrival",
            location_id="tavern", profile=profile,
            decisions={"silent": False, "significance": "minor", "category": "disturbance",
                       "reward_class": "none", "rarity_roll": 0.1, "candidate_order": [], "density": 1},
        )
        result = gate.evaluate(built, _proposal(
            premise="A new Waterdeep district opens behind the inn.",
        ))
        self.assertEqual((result.outcome, result.reason), (gate.HARD_REJECT, "protected_identity"))

    def test_invented_faction_leadership_is_refused(self):
        result = self._eval(affiliation={"faction_id": "fr:faction:lords_alliance", "rank": "leader"})
        self.assertEqual((result.outcome, result.reason), (gate.HARD_REJECT, "premise_change"))

    def test_protected_named_death_is_refused(self):
        result = self._eval(premise="Dagult Neverember died in the alley last night.")
        self.assertEqual((result.outcome, result.reason), (gate.HARD_REJECT, "protected_identity"))

    def test_published_adventure_is_not_campaign_canon(self):
        result = self._eval(premise="The Dragon Delves published adventure already concluded here.")
        self.assertEqual((result.outcome, result.reason), (gate.HARD_REJECT, "adventure_canon"))

    def test_historical_source_does_not_override_current(self):
        result = self._eval(premise="Netheril now rules Neverwinter in 1501 DR.")
        self.assertEqual((result.outcome, result.reason), (gate.HARD_REJECT, "historical_override"))

    def test_combat_without_creatures_and_unknown_check(self):
        combat = dict(self.envelope)
        combat["allowed_categories"] = ["combat"]
        combat["allowed_creature_ids"] = []
        combat["decisions"] = {**combat["decisions"], "category": "combat"}
        refused = gate.evaluate(combat, _proposal(category="combat"))
        self.assertEqual((refused.outcome, refused.reason), (gate.HARD_REJECT, "combat_bind"))
        unknown = self._eval(check_categories=["made_up_skill"])
        self.assertEqual((unknown.outcome, unknown.reason), (gate.HARD_REJECT, "mechanical_ownership"))

    def test_gambling_winnings_are_not_a_payout(self):
        gambling = dict(self.envelope)
        gambling["allowed_categories"] = ["gambling"]
        gambling["decisions"] = {**gambling["decisions"], "category": "gambling"}
        refused = gate.evaluate(gambling, _proposal(category="gambling", reward_class="coin_small"))
        self.assertEqual((refused.outcome, refused.reason), (gate.HARD_REJECT, "premise_change"))

    def test_permitted_rank_and_hidden_context_stay_split(self):
        accepted = self._eval(affiliation={"faction_id": "fr:faction:lords_alliance", "rank": "associate"})
        self.assertIn(accepted.outcome, (gate.ACCEPT, gate.NORMALIZE))
        leaked = self._eval(premise="The purse belongs to the cook's missing sister.")
        self.assertEqual(leaked.reason, "hidden_information")

    def test_live_hook_stays_off_without_the_flag(self):
        from incidents import hooks
        from incidents.attempts import MemoryAttemptStore

        session, world = _world()
        world["campaign_id"] = "campaign.test"
        session.emergence_store = MemoryAttemptStore()
        called = {"n": 0}

        def propose(_packet):
            called["n"] += 1
            return json.dumps(_proposal(), ensure_ascii=False)

        with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
            result = hooks.before_narration(
                session, action_result={"action": "travel", "success": True},
                player_text="tavernaya gidiyorum", location_changed=True,
            )
        self.assertIsNone(result["status"])
        self.assertEqual(called["n"], 0)
        world["flags"]["emergence_live"] = True
        with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
            with patch("incidents.profiles.resolve", return_value={
                **PROFILE, "silence_rate": 0.0,
                "category_weights": (("disturbance", 1),),
                "reward_weights": (("none", 1),),
            }):
                live = hooks.before_narration(
                    session, action_result={"action": "travel", "success": True},
                    player_text="tavernaya gidiyorum", location_changed=True, propose=propose,
                )
        self.assertEqual(live["status"], "accepted")
        self.assertEqual(called["n"], 1)


if __name__ == "__main__":
    unittest.main()
