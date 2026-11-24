"""Direct unit tests for incidents.awareness: knowledge entries only grow from Python evidence."""

import unittest

from incidents import awareness


def _record(incident_id="inc.one", location="tavern", hidden=("fact.owner",), created=1):
    return {
        "incident_id": incident_id,
        "location_id": location,
        "lifecycle": "PRESENT",
        "created_clock": created,
        "hidden_fact_ids": list(hidden),
        "details": {"facts": {"fact.purse": "A purse.", "fact.owner": "It belongs to the cook."}},
    }


def _check(skill="Perception", success=True):
    return {"kind": "check", "success": success, "skill": skill}


class EntryAndKnowledgeTests(unittest.TestCase):
    def test_entry_format(self):
        self.assertEqual(awareness.entry("inc.one", "noticed"), "incident:inc.one:noticed")

    def test_noticed_and_known_fact_ids(self):
        world = {
            "player_knowledge": [
                "incident:inc.one:noticed",
                "incident:inc.one:fact.purse",
                "incident:other:fact.x",
                7,
            ]
        }
        self.assertTrue(awareness.noticed(world, "inc.one"))
        self.assertFalse(awareness.noticed(world, "other"))
        self.assertEqual(awareness.known_fact_ids(world, "inc.one"), ["fact.purse"])

    def test_corrupt_knowledge_fails_loudly(self):
        with self.assertRaises(ValueError):
            awareness.witness({"player_knowledge": "oops"}, _record())


class WitnessTests(unittest.TestCase):
    def test_witness_sees_surface_facts_not_hidden_ones(self):
        world = {}
        awareness.witness(world, _record())
        self.assertEqual(world["player_knowledge"], ["incident:inc.one:noticed", "incident:inc.one:fact.purse"])

    def test_witness_twice_adds_nothing_new(self):
        world = {}
        awareness.witness(world, _record())
        awareness.witness(world, _record())
        self.assertEqual(len(world["player_knowledge"]), 2)


class RevealTests(unittest.TestCase):
    def test_successful_check_reveals_a_hidden_fact_once(self):
        world = {}
        self.assertTrue(awareness.reveal(world, _record(), "fact.owner", evidence=_check()))
        self.assertIn("incident:inc.one:fact.owner", world["player_knowledge"])
        self.assertFalse(awareness.reveal(world, _record(), "fact.owner", evidence=_check()))

    def test_unknown_fact_is_not_revealed(self):
        self.assertFalse(awareness.reveal({}, _record(), "fact.nope", evidence=_check()))

    def test_bad_evidence_reveals_nothing(self):
        bad = (
            None,
            "yes",
            _check(success=False),
            _check(skill="Athletics"),
            {"kind": "guess"},
            {"kind": "introduction", "npc_id": 4},
        )
        for evidence in bad:
            with self.subTest(evidence=evidence):
                world = {}
                self.assertFalse(awareness.reveal(world, _record(), "fact.owner", evidence=evidence))
                self.assertNotIn("player_knowledge", world)

    def test_introduction_evidence_reveals(self):
        evidence = {"kind": "introduction", "npc_id": "npc.cook"}
        self.assertTrue(awareness.reveal({}, _record(), "fact.owner", evidence=evidence))


class RevealFromCheckTests(unittest.TestCase):
    def _world(self):
        return {"location": "tavern", "incidents": {"inc.one": _record(), "inc.far": _record("inc.far", "harbor")}}

    def _result(self, **over):
        result = {"action": "skill_check", "success": True, "skill": "insight"}
        result.update(over)
        return result

    def test_success_reveals_first_hidden_fact_here(self):
        world = self._world()
        self.assertEqual(awareness.reveal_from_check(world, self._result()), "incident:inc.one:fact.owner")
        self.assertNotIn("incident:inc.far:fact.owner", world["player_knowledge"])

    def test_nothing_left_to_reveal_returns_none(self):
        world = self._world()
        awareness.reveal_from_check(world, self._result())
        self.assertIsNone(awareness.reveal_from_check(world, self._result()))

    def test_wrong_result_shapes_reveal_nothing(self):
        wrong = (None, self._result(success=False), self._result(action="attack"), self._result(skill="athletics"))
        for result in wrong:
            with self.subTest(result=result):
                self.assertIsNone(awareness.reveal_from_check(self._world(), result))

    def test_closed_incident_is_skipped(self):
        world = self._world()
        world["incidents"]["inc.one"]["lifecycle"] = "RESOLVED"
        self.assertIsNone(awareness.reveal_from_check(world, self._result()))


if __name__ == "__main__":
    unittest.main()
