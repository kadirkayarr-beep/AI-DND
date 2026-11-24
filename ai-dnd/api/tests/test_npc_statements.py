"""Direct unit tests for npc_statements promise identities: stable ids, pinned so a hash call change cannot move them."""

import unittest

import npc_statements

SCOPE = {"kind": "deliver", "objects": ["bread", "Su"], "destination": "tavern"}


class ScopeKeyTests(unittest.TestCase):
    def test_scope_key_is_pinned(self):
        self.assertEqual(npc_statements._scope_key("npc.a", "player", SCOPE), "e991ac5fe42c7a2d")

    def test_commitment_identity_is_pinned(self):
        self.assertEqual(
            npc_statements.commitment_identity("npc.a", "player", SCOPE, "evt1"), "promise:4270158c16e299a6"
        )

    def test_identity_depends_on_who_what_and_origin(self):
        base = npc_statements.commitment_identity("npc.a", "player", SCOPE, "evt1")
        self.assertNotEqual(base, npc_statements.commitment_identity("npc.b", "player", SCOPE, "evt1"))
        self.assertNotEqual(base, npc_statements.commitment_identity("npc.a", "player", SCOPE, "evt2"))
        other = dict(SCOPE, objects=["lantern"])
        self.assertNotEqual(base, npc_statements.commitment_identity("npc.a", "player", other, "evt1"))

    def test_case_endings_agree_but_filler_does_not_count(self):
        lantern = {"kind": "deliver", "objects": ["fener"]}
        lantern_acc = {"kind": "deliver", "objects": ["feneri"]}
        self.assertEqual(
            npc_statements._scope_key("npc.a", "player", lantern),
            npc_statements._scope_key("npc.a", "player", lantern_acc),
        )

    def test_strip_case_keeps_a_three_letter_stem(self):
        self.assertEqual(npc_statements._strip_case("feneri"), "fener")
        self.assertEqual(npc_statements._strip_case("kapı"), "kap")
        self.assertEqual(npc_statements._strip_case("evi"), "evi")
        self.assertEqual(npc_statements._strip_case("at"), "at")

    def test_commitment_scope_key_prefers_the_saved_one(self):
        self.assertEqual(npc_statements._commitment_scope_key({"scope_key": "saved"}), "saved")
        derived = npc_statements._commitment_scope_key({"npc_id": "npc.a", "kind": "deliver", "objects": ["bread"]})
        self.assertEqual(len(derived), 16)


if __name__ == "__main__":
    unittest.main()
