"""Direct unit tests for api.action_contract: one receipt describes exactly the state revision that carries it (R04)."""

import copy
import unittest

from api import action_contract as contract
from api.action_contract import CommitBundleError


def _public_state(hp=7):
    return {
        "character": {"current_hp": hp, "max_hp": 10},
        "inventory": ["torch"],
        "wallet": {"cp": 120},
        "campaign_time": {"elapsed_seconds": 60},
        "death_state": {"status": "alive", "dead": False, "successes": 0, "failures": 0},
        "turn_index": 4,
    }


def _response():
    return {
        "narration": "You swing.",
        "state": _public_state(),
        "combat_history_entry": {"event_id": "ev.combat"},
        "quest_outcomes": [{"event_id": "ev.quest"}, {"event_id": 5}, "junk"],
        "combat_result": {"hit": True, "roll": 14},
    }


def _bundle(response=None, committed=("ev.combat", "ev.quest")):
    response = response if response is not None else _response()
    return {"response": response, "public_state": _public_state(), "committed_event_ids": list(committed)}


def _receipt(response=None, base=3, committed=4):
    return contract.build_receipt("camp", "act-1", response if response is not None else _response(), base, committed, 0.5)


class DigestTests(unittest.TestCase):
    def test_canonical_json_is_compact_and_refuses_nan(self):
        self.assertEqual(contract.canonical_json({"a": [1, "ü"]}), '{"a":[1,"ü"]}')
        with self.assertRaises(ValueError):
            contract.canonical_json({"a": float("nan")})

    def test_digest_follows_the_stored_bytes(self):
        self.assertEqual(contract.result_digest({"a": 1}), contract.result_digest({"a": 1}))
        self.assertNotEqual(contract.result_digest({"a": 1}), contract.result_digest({"a": 2}))
        self.assertEqual(len(contract.result_digest({})), 64)


class IdentityTests(unittest.TestCase):
    def test_event_ids_come_from_the_combat_entry_and_quest_outcomes(self):
        self.assertEqual(contract.event_ids_of(_response()), ("ev.combat", "ev.quest"))
        self.assertEqual(contract.event_ids_of({}), ())
        self.assertEqual(contract.event_ids_of({"combat_history_entry": {"event_id": 3}, "quest_outcomes": "x"}), ())

    def test_roll_ids_are_the_dice_evidence_so_a_reroll_changes_them(self):
        first = contract.roll_ids_of({"combat_result": {"roll": 14}})
        again = contract.roll_ids_of({"combat_result": {"roll": 14}})
        rerolled = contract.roll_ids_of({"combat_result": {"roll": 3}})
        self.assertEqual(first, again)
        self.assertNotEqual(first, rerolled)
        self.assertTrue(first[0].startswith("combat_result:"))
        self.assertEqual(contract.roll_ids_of({"combat_result": "x"}), ())

    def test_committed_facts_survive_missing_parts(self):
        facts = contract.committed_facts({})
        self.assertEqual(facts["hp"], (None, None))
        self.assertEqual(facts["death"], (None, None, None, None))
        self.assertEqual(contract.committed_facts(_public_state())["hp"], (7, 10))
        self.assertEqual(contract.committed_facts(_public_state())["wallet"], {"cp": 120})

    def test_build_receipt_describes_the_response(self):
        receipt = _receipt()
        self.assertEqual(receipt.key, ("camp", "act-1"))
        self.assertEqual((receipt.base_revision, receipt.committed_revision), (3, 4))
        self.assertEqual(receipt.result_digest, contract.result_digest(_response()))
        self.assertEqual(receipt.event_ids, ("ev.combat", "ev.quest"))


class ValidateCommitBundleTests(unittest.TestCase):
    def test_a_consistent_bundle_passes(self):
        contract.validate_commit_bundle(_bundle(), _receipt())

    def _refused(self, state, receipt, text):
        with self.assertRaises(CommitBundleError) as caught:
            contract.validate_commit_bundle(state, receipt)
        self.assertIn(text, str(caught.exception))

    def test_incomplete_bundle_is_refused(self):
        self._refused({}, _receipt(), "incomplete")
        self._refused({"response": {}, "public_state": "x"}, _receipt(), "incomplete")

    def test_receipt_must_be_exactly_one_revision_ahead(self):
        self._refused(_bundle(), _receipt(committed=6), "one new revision")
        self._refused(_bundle(), _receipt(base=4, committed=4), "one new revision")

    def test_digest_must_match_the_stored_result(self):
        changed = copy.deepcopy(_response())
        changed["narration"] = "Tampered."
        self._refused(_bundle(changed), _receipt(), "digest")

    def test_state_inside_the_receipt_must_match_the_committed_state(self):
        response = _response()
        response["state"]["wallet"] = {"cp": 999}
        self._refused(_bundle(response), _receipt(response), "contradicts")
        no_state = _response()
        del no_state["state"]
        self._refused(_bundle(no_state), _receipt(no_state), "contradicts")

    def test_event_ids_must_have_been_written_in_the_same_transaction(self):
        self._refused(_bundle(committed=("ev.combat",)), _receipt(), "not committed")
        self._refused(_bundle(committed=()), _receipt(), "not committed")

    def test_receipt_events_and_dice_must_match_the_result(self):
        forged = _receipt()
        self._refused(_bundle(), type(forged)(**{**forged.__dict__, "event_ids": ("ev.other",)}), "events")
        self._refused(_bundle(), type(forged)(**{**forged.__dict__, "roll_ids": ("combat_result:0",)}), "dice")


if __name__ == "__main__":
    unittest.main()
