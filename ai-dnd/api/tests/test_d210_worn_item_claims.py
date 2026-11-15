"""D-210: on a narrative cast with no item_claims from the narrator, a line putting a thing on the player's body
("El yüzüğü parmağına geçirir.") or calling it theirs ("Kolye boynuna dolanır, artık senin.") passed the
narrative-spell claim guard and was shown, though nothing moved. Those shapes are now claims; the Python line stands.

Fixtures: test_d067_narrative_spell_claims.NarratorItemClaimOnACast (CampaignApiTests with `fixed_town`, a Wizard
with Mage Hand; the narrator is test_said_is_real.ClassifiedClient)."""
from __future__ import annotations

import unittest

import spell_effects
from api.tests import test_d067_narrative_spell_claims as d067


class WornOrOwnedIsAClaim(unittest.TestCase):
    def test_a_thing_put_on_a_body_or_called_yours_is_a_claim(self):
        for line in ("El yüzüğü parmağına geçirir.", "Kolye boynuna dolanır, artık senin.", "Yüzük artık senin.",
                     "El bileziği bileğine takar.", "Hayalet el pelerini omzuna geçirir.",
                     "El, yüzüğü parmağına usulca geçirir.", "Kolye senin olsun.",
                     "The hand slips the ring onto your finger."):
            with self.subTest(line):
                self.assertTrue(spell_effects.claims_state_change(line))

    def test_a_body_or_a_turn_with_no_thing_passes(self):
        for line in ("Işık parmağının ucunda titrer.", "Kolyesi boynunda parlıyor.",
                     "Büyü boynundaki tüyleri diken diken eder.", "Artık senin sıran.",
                     "Kulağına bir fısıltı süzülür.", "Hayalet el omzuna dokunur ve kaybolur.",
                     "Bütün gözler sende."):
            with self.subTest(line):
                self.assertFalse(spell_effects.claims_state_change(line))

    def test_a_choice_or_a_flight_past_the_body_is_not_a_claim(self):
        # Review: a choice, a verdict or a victory is not a thing, and 'koluna doğru' is a way past the arm, not on it.
        for line in ("Seçim artık senin.", "Karar artık senin!", "Zafer senin olsun.", "Ok koluna doğru geçip gidiyor."):
            with self.subTest(line):
                self.assertFalse(spell_effects.claims_state_change(line))
        for line in ("Yüzük artık senin.", "Hançer senin olsun.", "El bileziği koluna geçirir."):
            with self.subTest(line):
                self.assertTrue(spell_effects.claims_state_change(line))


class NoClaimsFromTheNarrator(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = d067.NarratorItemClaimOnACast.asyncSetUp
    asyncTearDown = d067.NarratorItemClaimOnACast.asyncTearDown
    campaign = d067.NarratorItemClaimOnACast.campaign
    post = d067.NarratorItemClaimOnACast.post
    stored = d067.NarratorItemClaimOnACast.stored
    ledger = d067.NarratorItemClaimOnACast.ledger
    cast = d067.NarratorItemClaimOnACast.cast

    async def test_a_worn_thing_with_no_item_claims_is_the_python_line(self):
        body = await self.cast(4610, "El yüzüğü parmağına geçirir.", None)
        self.assertNotIn("parmağına", body["narration"])
        self.assertIn("Büyücü Eli (Mage Hand)", body["narration"])

    async def test_a_thing_called_yours_with_no_item_claims_is_the_python_line(self):
        body = await self.cast(4611, "Kolye boynuna dolanır, artık senin.", None)
        self.assertNotIn("artık senin", body["narration"])
        self.assertIn("Büyücü Eli (Mage Hand)", body["narration"])


if __name__ == "__main__":
    unittest.main()
