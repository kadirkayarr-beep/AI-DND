"""Direct unit tests for adventure.completion: optional objectives never block success, secrets stay hidden."""

import unittest

from adventure import completion


def _objective(state, **extra):
    row = {"objective_id": "o", "graph_state": state}
    row.update(extra)
    return row


class CompletionTests(unittest.TestCase):
    def test_required_skips_optional_and_junk_rows(self):
        quest = {"objectives": [_objective("ACTIVE"), _objective("ACTIVE", optional=True), "junk"]}
        self.assertEqual(len(completion.required(quest)), 1)
        self.assertEqual(completion.required({}), [])

    def test_primary_success_needs_every_required_objective_complete(self):
        done = {"objectives": [_objective("COMPLETE"), _objective("ACTIVE", optional=True)]}
        self.assertTrue(completion.primary_success(done))
        partial = {"objectives": [_objective("COMPLETE"), _objective("ACTIVE")]}
        self.assertFalse(completion.primary_success(partial))

    def test_no_required_objective_is_not_success(self):
        self.assertFalse(completion.primary_success({"objectives": [_objective("COMPLETE", optional=True)]}))
        self.assertFalse(completion.primary_success({}))

    def test_secret_descriptions_list_only_hidden_objectives(self):
        quest = {
            "objectives": [
                _objective("HIDDEN", visibility="hidden", description="The cook did it."),
                _objective("ACTIVE", visibility="visible", description="Ask around."),
                "junk",
            ]
        }
        self.assertEqual(completion.secret_descriptions(quest), ["The cook did it."])


if __name__ == "__main__":
    unittest.main()
