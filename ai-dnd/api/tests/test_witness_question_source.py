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

    async def test_an_explicit_quoted_engine_source_is_recalled_with_one_speech_call(self):
        await self.ready_witness()
        question = DEED + ". Bu olayı hatırlıyor musun?"
        before = self.financial_state()
        reply, _ = await self.recall(question)
        self.assertEqual(reply["turn_outcome"]["status"], "answered_from_witnessed_deed")
        self.assertIn(DEED, reply["narration"])
        self.assertNotIn("Baban değirmenciydi", reply["narration"])
        self.assertEqual(self.financial_state(), before)

    async def test_a_supported_personal_memory_wins_over_an_unrelated_witness_selection(self):
        import npc_told
        await self.ready_witness()
        self.assertTrue(npc_told.remember(self.world, "barman", "Babam değirmenciydi.", turn=0))
        reply, _ = await self.recall(FAMILY)
        self.assertIn("Baban değirmenciydi", reply["narration"])
        self.assertNotIn(DEED, reply["narration"])
        self.assertEqual(npc_told.context_rows(self.world, "barman"), ["Babam değirmenciydi."])

    async def test_normal_speech_is_not_replaced_because_a_witness_record_exists(self):
        import uuid
        from api.tests import test_campaign_api as fixtures
        from api.tests.test_three_plays import PlayClient
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        body = {"message": "Bugün nasılsın?", "action_id": str(uuid.uuid4()),
                "interaction_mode": "say", "target_id": "barman"}
        response = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url,
            PlayClient(spoken="İyiyim, sağ ol."), body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("İyiyim, sağ ol.", response.json()["narration"])

    async def test_unclear_reference_writes_no_new_personal_or_witness_source(self):
        import copy
        import npc_told
        import npc_statements
        await self.ready_witness()
        npc = next(n for n in self.world["npcs"] if n["id"] == "barman")
        before = copy.deepcopy((npc.get("memory"), npc_told.context_rows(self.world, "barman"),
                                npc_statements.view(self.world)["statements"].get("barman", []), self.world["flags"]["deeds"]))
        reply, _ = await self.recall(FAMILY)
        after_npc = next(n for n in self.world["npcs"] if n["id"] == "barman")
        after = (after_npc.get("memory"), npc_told.context_rows(self.world, "barman"),
                 npc_statements.view(self.world)["statements"].get("barman", []), self.world["flags"]["deeds"])
        self.assertEqual(after, before)
        self.assertEqual(reply["turn_outcome"]["status"], "unverified")

    async def test_an_old_three_field_selection_cannot_bypass_the_missing_literal_link(self):
        import uuid
        from api.tests import test_campaign_api as fixtures
        from api.tests.test_witness_review import ReviewClient
        await self.ready_witness()
        client = ReviewClient(FAMILY)
        client.omit_source_quote = True
        body = {"message": FAMILY, "action_id": str(uuid.uuid4()),
                "interaction_mode": "say", "target_id": "barman"}
        response = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(client.offered), 1)
        self.assertEqual(response.json()["turn_outcome"]["status"], "unverified")
        self.assertNotIn(DEED, response.json()["narration"])

    async def profile_answer_with_witness(self, experimental, *, decline=False):
        import json
        import uuid
        import interaction_adventure
        import witness_recall
        from api.tests import test_campaign_api as fixtures
        from api.tests.test_three_plays import PlayClient
        await self.ready_witness(kind="assault", text="Birinin üzerine yürüdü")
        card = await self.card(purpose="gift", recipient_id="barman", amount_cp=5) if decline else None
        finances = self.financial_state()
        self.record.game_session._experimental_npc_dialogue_enabled = experimental
        npc = next(n for n in self.world["npcs"] if n["id"] == "barman")
        npc["reality_layer"] = "PROCEDURAL_LOCAL_FICTION"
        npc.setdefault("personal_profile", {})["origin"] = "Kuzey kıyısında büyüdüm."
        question = "Buraya varmadan önceki hayatını hatırlıyor musun?"
        interaction = {"operation": "none", "quote": question, "conversation": {
            "addressee_id": "barman", "subject_phrase": "", "subject_role": "addressee",
            "meaning": "origin", "topic_relation": "new",
            "candidate_evidence_ids": ["npc-profile:barman:v1:origin"]}}
        resolution = interaction_adventure.resolve_conversation(self.world, question, interaction, npc)
        self.assertEqual(resolution["answer_field"], "origin", "the real profile owner accepts this source")
        source = witness_recall.candidates(self.world, npc)[0]

        class ProfileWitnessClient(PlayClient):
            def chat(inner, *args, **kwargs):
                inner.calls += 1
                return {"message": {"content": json.dumps({"intent": "dialogue", "action": "dialogue",
                    "target": {"type": "none", "reference": ""}, "completion": "unclear", "confidence": 1.0,
                    "interaction": interaction, "spoken_text": "Yanlış cevap.", "stage_direction": "",
                    "coin_answer": "declines" if decline else "none", "coin_answer_for": "gift",
                    "narration": "Yanlış cevap.", "world_updates": {}, "lore_claims": [],
                    "witness_recall": {"scope": "witnessed_deed", "source_id": source["source_id"],
                        "source_quote": source["text"], "evidence_quote": question}}, ensure_ascii=False)}}

        client = ProfileWitnessClient()
        body = {"message": question, "action_id": str(uuid.uuid4()),
                "interaction_mode": "say", "target_id": "barman"}
        response = await fixtures.CampaignApiTests.post_scene_turn(self, self.turn_url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.calls, 1, "profile answer exercises the same speech path")
        self.assertEqual(response.json()["turn_outcome"]["status"], "answered_personal_question")
        self.assertIn("Kuzey kıyısında büyüdüm.", response.json()["narration"])
        self.assertNotIn(source["text"], response.json()["narration"])
        if decline:
            await self.confirm(card)
            self.assertEqual(self.financial_state(), finances)
            self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")

    async def test_profile_answer_with_default_switch_precedes_an_unrelated_witness_selection(self):
        await self.profile_answer_with_witness(False)

    async def test_profile_answer_with_opt_in_precedes_an_unrelated_witness_selection(self):
        await self.profile_answer_with_witness(True)

    async def test_a_profile_answer_with_witness_selection_keeps_the_same_coin_veto(self):
        await self.profile_answer_with_witness(True, decline=True)
