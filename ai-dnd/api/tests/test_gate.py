"""Direct unit tests for incidents.gate: one verdict per proposal, no model retry."""

import json
import unittest

from incidents import envelope, gate

PROFILE = {
    "profile_id": "test.tavern",
    "tier_ceiling": 3,
    "categories": ["disturbance", "lost_property", "treasure_find"],
    "roles": ["cook", "merchant", "traveler", "guard", "laborer"],
    "subscene_kinds": ["alley", "back_room", "cellar"],
    "faction_ids": ["fr:faction:lords_alliance"],
    "faction_rank_ceiling": "member",
    "protected_names": ["Dagult Neverember"],
    "expiry_seconds": (1800, 21600),
}


def _world():
    return {
        "location": "tavern",
        "locations": {"tavern": {}},
        "campaign_time": {"elapsed_seconds": 0},
        "npcs": [{"id": "npc.keeper", "name": "Hesk", "role": "innkeeper", "location": "tavern"}],
        "incidents": {},
        "player_knowledge": [],
    }


def _envelope(reward="coin_small", hidden=None):
    decisions = {"silent": False, "significance": "minor", "category": "disturbance", "reward_class": reward}
    return envelope.build(
        _world(),
        campaign_id="campaign.t",
        trigger_id="trg:1",
        trigger_kind="arrival",
        location_id="tavern",
        profile=PROFILE,
        decisions=decisions,
        hidden_context=hidden or {"fact.owner": "The purse belongs to the cook's missing sister."},
        faction_ids=["fr:faction:lords_alliance"],
    )


def _proposal(**overrides):
    data = {
        "category": "disturbance",
        "significance": "minor",
        "premise": "A spilled crate of apples blocks the back door.",
        "surface_facts": ["Apples roll across the floorboards."],
        "hidden_facts": ["The crate was kicked over on purpose."],
        "people": [
            {"label": "flustered cook", "role": "cook", "name": "Mirel", "traits": ["anxious"], "backstory": "Works late."}
        ],
        "existing_refs": ["npc.keeper"],
        "props": [{"label": "crate", "appearance": "A split pine crate."}],
        "subscene": None,
        "hooks": ["help_cook"],
        "check_categories": ["insight"],
        "consequence_classes": ["gratitude"],
        "reward_class": "none",
        "persistence_tier": 1,
        "affiliation": None,
        "expiry_hours": 1,
        "narrative_seed": "The cook mutters while gathering apples.",
    }
    data.update(overrides)
    return data


class GateVerdictTests(unittest.TestCase):
    def setUp(self):
        self.envelope = _envelope()

    def _reject(self, reason, **overrides):
        result = gate.evaluate(self.envelope, _proposal(**overrides))
        self.assertEqual((result.outcome, result.reason), (gate.HARD_REJECT, reason))

    def test_clean_proposal_is_accepted_with_seconds_not_hours(self):
        result = gate.evaluate(self.envelope, _proposal())
        self.assertEqual(result.outcome, gate.ACCEPT)
        self.assertEqual(result.notes, ())
        self.assertEqual(result.normalized["expiry_seconds"], 3600)
        self.assertNotIn("expiry_hours", result.normalized)

    def test_raw_json_text_is_parsed(self):
        result = gate.evaluate(self.envelope, json.dumps(_proposal()))
        self.assertEqual(result.outcome, gate.ACCEPT)

    def test_garbage_text_is_rejected_not_raised(self):
        result = gate.evaluate(self.envelope, "not json at all")
        self.assertEqual(result.outcome, gate.HARD_REJECT)
        self.assertTrue(result.reason)

    def test_category_outside_the_draw_is_rejected(self):
        self._reject("category", category="lost_property")

    def test_entity_outside_the_envelope_is_rejected(self):
        self._reject("entity_ref", existing_refs=["npc.invented"])

    def test_protected_name_is_rejected_even_in_another_case(self):
        self._reject("protected_identity", premise="DAGULT NEVEREMBER is seen near the crate.")

    def test_new_deity_is_rejected(self):
        self._reject("new_deity", narrative_seed="A god watches the cook.")

    def test_forbidden_or_unlisted_role_is_rejected(self):
        people = [{"label": "man", "role": "dragon", "name": "X", "traits": ["a"], "backstory": "b"}]
        self._reject("forbidden_role", people=people)

    def test_coin_amounts_belong_to_mechanics(self):
        self._reject("mechanical_ownership", surface_facts=["The cook holds 50 gold."])

    def test_magic_items_are_rejected(self):
        self._reject("magic_item", props=[{"label": "blade", "appearance": "A vorpal edge."}])

    def test_published_adventure_outcome_is_rejected(self):
        self._reject("adventure_canon", premise="The adventure already concluded here.")

    def test_check_category_not_owned_by_python_is_rejected(self):
        self._reject("mechanical_ownership", check_categories=["wish"])

    def test_hidden_context_must_not_leak_into_player_text(self):
        leak = "The purse belongs to the cook's missing sister."
        self._reject("hidden_information", surface_facts=[leak])

    def test_tier_five_is_rejected_and_lower_tiers_are_clamped(self):
        self._reject("tier5", persistence_tier=5)
        result = gate.evaluate(self.envelope, _proposal(persistence_tier=4))
        self.assertEqual(result.outcome, gate.NORMALIZE)
        self.assertEqual(result.normalized["persistence_tier"], 3)
        self.assertEqual(result.notes, ("persistence_tier",))

    def test_reward_above_ceiling_is_lowered(self):
        envelope_none = _envelope(reward="none")
        result = gate.evaluate(envelope_none, _proposal(reward_class="coin_small"))
        self.assertEqual(result.outcome, gate.NORMALIZE)
        self.assertEqual(result.normalized["reward_class"], "none")
        self.assertIn("reward_class", result.notes)

    def test_expiry_is_clamped_to_the_window(self):
        result = gate.evaluate(self.envelope, _proposal(expiry_hours=100))
        self.assertEqual(result.normalized["expiry_seconds"], 21600)
        self.assertEqual(result.notes, ("expiry",))


class GateResultTests(unittest.TestCase):
    def test_result_is_frozen(self):
        result = gate.GateResult(gate.ACCEPT)
        with self.assertRaises(Exception):
            result.outcome = gate.HARD_REJECT

    def test_faction_ranks_are_ordered_low_to_high(self):
        self.assertEqual(gate.FACTION_RANKS[0], "associate")
        self.assertEqual(gate.FACTION_RANKS[-1], "leader")


if __name__ == "__main__":
    unittest.main()
