"""Direct unit tests for incidents.faction: rank ceiling and fail-closed standing writes."""

import unittest
from types import SimpleNamespace

from incidents import faction


class RankAllowedTests(unittest.TestCase):
    def test_rank_at_or_below_ceiling_is_allowed(self):
        self.assertTrue(faction.rank_allowed("associate", "member"))
        self.assertTrue(faction.rank_allowed("member", "member"))

    def test_rank_above_ceiling_is_refused(self):
        self.assertFalse(faction.rank_allowed("agent", "member"))
        self.assertFalse(faction.rank_allowed("leader", "officer"))

    def test_unknown_rank_or_ceiling_is_refused(self):
        self.assertFalse(faction.rank_allowed("emperor", "leader"))
        self.assertFalse(faction.rank_allowed("associate", "emperor"))


class ApplyFailClosedTests(unittest.TestCase):
    def _apply(self, state, rank="associate"):
        return faction.apply(
            state, faction_id="faction.x", rank=rank, source_action_id="act-1", turn_index=1, evidence=None
        )

    def test_no_lore_state_returns_none(self):
        self.assertIsNone(self._apply(None))

    def test_rank_outside_allowed_deltas_returns_state_unchanged(self):
        state = SimpleNamespace(binding_status="bound")
        self.assertIs(self._apply(state, rank="officer"), state)

    def test_unbound_campaign_returns_state_unchanged(self):
        state = SimpleNamespace(binding_status="legacy")
        self.assertIs(self._apply(state), state)
        bare = SimpleNamespace()
        self.assertIs(self._apply(bare), bare)


class ApplyBoundTests(unittest.TestCase):
    def test_bound_state_without_valid_evidence_is_refused(self):
        from api.lore_authority.models import BindingStatus

        state = SimpleNamespace(binding_status=BindingStatus.BOUND, faction_standings=())
        result = faction.apply(
            state, faction_id="faction.x", rank="member", source_action_id="act-1", turn_index=1, evidence=None
        )
        self.assertIs(result, state)


if __name__ == "__main__":
    unittest.main()
