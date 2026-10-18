"""Focused acceptance regressions for resolved narration and explicit targets."""
import copy
import json
import unittest
from unittest.mock import patch
import game
import living_world
from api.tests.test_stage10a_gameplay_repairs import city_session, place_npc
from api.tests.test_explicit_shop_creation import REQUEST


def finalize(session, *args, **kwargs):
    token = game._ACTIVE_SESSION.set(session)
    try:
        return game.finalize_narration(*args, **kwargs)
    finally:
        game._ACTIVE_SESSION.reset(token)


class NarrationIntentTests(unittest.TestCase):
    def test_successful_check_survives_lore_rejection_and_does_not_create_evidence(self):
        session = city_session()
        before = copy.deepcopy(session.world_state)
        result = {"action": "skill_check", "status": "resolved", "skill": "Investigation",
                  "outcome": "success", "success": True, "total": 15, "dc": 15}
        with patch("game.ollama.chat", side_effect=AssertionError("no retry")):
            reply = finalize(session, "Invented lore", "I investigate signs that Neverwinter is rebuilding.",
                                              action_result=result, fallback_reason_code="UNVERIFIED_LORE_CLAIM")
        self.assertIn("başarılı", reply)
        self.assertEqual(session.world_state, before)
        self.assertEqual(result["total"], result["dc"])
        self.assertEqual(session.last_narration_safety["handling"], "python_fallback")

    def test_failure_does_not_become_success(self):
        session = city_session()
        reply = finalize(session, "Invented", "I investigate", action_result={
            "action": "skill_check", "skill": "Investigation", "outcome": "failure"},
            fallback_reason_code="UNVERIFIED_LORE_CLAIM")
        self.assertIn("sonuç vermedi", reply)
        self.assertNotIn("başarılı", reply)

    def test_find_reuses_existing_shop_without_explicit_creation_or_model(self):
        session = city_session()
        import shop_creation
        shop_creation.resolve_explicit_request(session)
        shop_before = copy.deepcopy(session.world_state["shops"])
        ids_before = [n["id"] for n in session.world_state["npcs"]]
        with patch("game.ollama.chat", side_effect=AssertionError("no model")):
            reply = session.run_player_turn("Find a local merchant for this campaign.")
        self.assertFalse(game._explicit_campaign_shop_request("Find a local merchant for this campaign."))
        self.assertTrue(game._explicit_campaign_shop_request("Create a local shop and merchant."))
        self.assertEqual(reply["action_result"]["status"], "found")
        self.assertEqual(session.world_state["shops"], shop_before)
        self.assertEqual([n["id"] for n in session.world_state["npcs"]], ids_before)
        self.assertIn("dükkâncı", reply["narration"])
        self.assertNotIn("yer kalmamış", reply["narration"])

    def test_unknown_vocative_does_not_use_bartender_memory(self):
        session = city_session()
        place_npc(session, "npc_001", "Barmen")
        session.world_state["flags"].update(active_npc_id="npc_001", active_npc_until_turn=6)
        before = copy.deepcopy(session.world_state["npcs"])
        with patch("game.ollama.chat", side_effect=AssertionError("no model")):
            reply = session.run_player_turn("Elara, ben sana daha önce adımı söylemiştim. Ne demiştim?")
        self.assertEqual(reply["action_result"]["status"], "invalid_target")
        self.assertNotIn("npc_id", reply["action_result"])
        self.assertIn("Elara", reply["narration"])
        self.assertEqual(session.world_state["npcs"], before)

    def test_creation_rejects_ephemeral_props_and_first_person_without_retry(self):
        session = city_session()
        inventory_before = copy.deepcopy(session.world_state["inventory"])
        packet = {"narration": "Kalabalık titriyor, elimde kılıç var; hizmet vermeye hazırım.",
                  "world_updates": {}, "lore_claims": []}
        with patch("game.ollama.chat", return_value={"message": {"content": json.dumps(packet)}}) as model:
            reply = session.run_player_turn(REQUEST)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(reply["narration"], reply["action_result"]["direct_response"])
        self.assertEqual(len(session.world_state["shops"]), 1)
        self.assertEqual(session.world_state["inventory"], inventory_before)

    def test_public_labels_do_not_mutate_roles_or_promote_appearance_to_name(self):
        npc = {"name": "Mira", "role": "Shopkeeper", "name_known_to_player": False}
        self.assertEqual(living_world.public_npc_name(npc), "Bir dükkâncı")
        self.assertEqual(npc["role"], "Shopkeeper")
        npc.update(role_known_to_player=False, appearance="Sade giysili biri. Uzun açıklama.")
        self.assertEqual(living_world.public_npc_name(npc), "Yakındaki kişi")

    def test_shop_refusal_and_economy_are_player_facing_and_non_mutating(self):
        session = city_session()
        with patch("game.ollama.chat", side_effect=AssertionError("no model")):
            refusal = session.run_player_turn("Never add or create a local shop or merchant in this campaign.")
        self.assertIn("aramadan", refusal["narration"])
        import shop_creation
        shop_creation.resolve_explicit_request(session)
        before = copy.deepcopy(session.world_state["inventory"])
        with patch("game.ollama.chat", side_effect=AssertionError("no model")):
            economy = session.run_player_turn("What stock and prices does the shop have? Can I buy a sword?")
        # The player tried to buy: told plainly that nothing can be bought (a mere
        # look at the counter gets an observation instead; see the continuity tests).
        self.assertIn("satın alamıyorsun", economy["narration"])
        self.assertEqual(session.world_state["inventory"], before)
        for reply in (refusal, economy):
            for word in ("kampanya durumu", "ekonomisi uygulanmıyor", "sistem", "envanter ve para"):
                self.assertNotIn(word, reply["narration"].casefold())

    def test_loaded_rebuilding_fact_can_ground_a_successful_check(self):
        session = city_session()
        session.lore_authority_context = game._empty_lore_authority_context()
        session.lore_authority_context["sections"]["official_forgotten_realms_lore"] = [{
            "fact_id": "fr:fact:neverwinter_rebuilding", "subject_id": "fr:city:neverwinter",
            "predicate": "current_status", "object_id_or_value": "rebuilding"}]
        reply = finalize(session, "Invented detail", "I investigate signs that Neverwinter is rebuilding.",
                         action_result={"action": "skill_check", "skill": "Investigation", "outcome": "success"},
                         fallback_reason_code="UNVERIFIED_LORE_CLAIM")
        self.assertIn("başarılı", reply)
        self.assertIn("yeniden inşa", reply)
        self.assertEqual(session.last_narration_safety["reason_code"], "UNVERIFIED_LORE_CLAIM")

    def test_road_safety_is_rendered_only_when_the_loaded_fact_exists(self):
        context = game._empty_lore_authority_context()
        context["sections"]["verified_entities"] = [{"entity_id": "fr:road:high_road",
            "canonical_name": "High Road", "aliases": []}]
        context["sections"]["official_forgotten_realms_lore"] = [{
            "fact_id": "fr:fact:high_road_safety_restored", "subject_id": "fr:road:high_road",
            "predicate": "safety_status", "object_id_or_value": "renewed"}]
        world = {"locations": {}, "npcs": [], "features": []}
        reply = game._supported_lore_question_response("Describe High Road's current safety.", context, world)
        self.assertIn("safe to travel", reply)
        context["sections"]["official_forgotten_realms_lore"] = []
        self.assertIsNone(game._supported_lore_question_response("Describe High Road's current safety.", context, world))

    def test_scene_list_is_prose_and_has_no_raw_role_or_appearance_name(self):
        people = [{"name": "Mira", "role": "Shopkeeper", "name_known_to_player": False},
                  {"name": "Elin", "role_known_to_player": False, "name_known_to_player": False,
                   "appearance": "Very long scene description, not a name"},
                  {"name": "Dorn", "role": "Guard", "name_known_to_player": False}]
        before = copy.deepcopy(people)
        self.assertEqual(living_world.public_scene_people(people), "bir dükkâncı, bir kişi ve bir muhafız")
        self.assertEqual(people, before)

    def test_rebuilding_investigation_rejects_accepted_but_ungrounded_model_prose(self):
        for seed in (1, 5):
            with self.subTest(seed=seed):
                session = city_session(seed=seed)
                session.lore_authority_context = game._empty_lore_authority_context()
                session.lore_authority_context["sections"]["official_forgotten_realms_lore"] = [{
                    "fact_id": "fr:fact:neverwinter_rebuilding", "subject_id": "fr:city:neverwinter",
                    "predicate": "current_status", "object_id_or_value": "rebuilding"}]
                session.lore_authority_context["sections"]["verified_entities"] = [{
                    "entity_id": "fr:city:neverwinter", "canonical_name": "Neverwinter", "aliases": []}]
                packet = {"narration": "You crouch low and discover half-repaired buildings and workers.",
                          "world_updates": {}, "lore_claims": []}
                before_shops = copy.deepcopy(session.world_state["shops"])
                with patch("game.parse_player_intent", return_value={"intent": "investigation", "difficulty": "medium"}), patch(
                    "game.ollama.chat", return_value={"message": {"content": json.dumps(packet)}}) as model:
                    reply = session.run_player_turn("I investigate signs that Neverwinter is rebuilding.")
                self.assertEqual(model.call_count, 1)
                outcome = reply["action_result"].get("outcome")
                self.assertIn("başarılı" if outcome in {"success", "critical_success"} else "sonuç vermedi", reply["narration"])
                self.assertNotIn("workers", reply["narration"])
                self.assertNotIn("crouch", reply["narration"])
                self.assertEqual(session.world_state["shops"], before_shops)

    def test_bounded_check_does_not_replace_unrelated_investigation(self):
        import resolved_presentation
        self.assertIsNone(resolved_presentation.bounded_rebuilding_check({
            "action": "skill_check", "skill": "Investigation", "outcome": "success"},
            "I investigate the door in Neverwinter.", game._empty_lore_authority_context()))
