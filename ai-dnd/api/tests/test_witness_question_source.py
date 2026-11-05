"""Open I2 regressions; a live source ID is not proof that it answers this question."""
from api.tests.test_witness_review import WitnessReviewSetup, FAMILY, DEED


class WitnessQuestionSources(WitnessReviewSetup):
    async def test_a_live_unrelated_source_does_not_become_the_answer_or_a_recorded_reply(self):
        await self.ready_witness()
        before = self.financial_state()
        reply, _ = await self.recall(FAMILY)
        self.assertNotEqual(reply["turn_outcome"]["status"], "answered_from_witnessed_deed")
        self.assertNotIn(DEED, reply["narration"])
        self.assertNotIn("Baban değirmenciydi", reply["narration"])
        self.assertEqual(self.financial_state(), before)
        import npc_statements
        words = npc_statements.view(self.world)["statements"].get("barman", [])
        self.assertNotIn(DEED, str(words))
        self.assertNotIn("Baban değirmenciydi", str(words))


    async def test_a_first_person_remembering_clause_does_not_turn_family_into_a_witnessed_action(self):
        await self.ready_witness()
        question = "Babamın işini sana sorduğumu hatırlıyorum; babam ne iş yapardı?"
        before = self.financial_state()
        reply, _ = await self.recall(question)
        self.assertNotEqual(reply["turn_outcome"]["status"], "answered_from_witnessed_deed")
        self.assertNotIn(DEED, reply["narration"])
        self.assertNotIn("Baban değirmenciydi", reply["narration"])
        self.assertEqual(self.financial_state(), before)
