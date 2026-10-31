"""An attempt with no mechanical owner reaches the model and writes no state."""

from __future__ import annotations

import copy
import json
import unittest
import uuid

import everyday_actions
import game
import grounded_action
import living_world
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech


class NarratingClient:
    """Answers each schema the way the local model does."""

    def __init__(self, narration="Sesin salonda yankılanıyor, birkaç baş dönüyor.",
                 spoken="Tabii, hemen koyuyorum.", steps=None):
        self.narration, self.spoken, self.steps = narration, spoken, steps or []
        self.kinds, self.batches = [], []

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        self.batches.append(copy.deepcopy(kwargs.get("messages", [])))
        if "steps" in properties:
            self.kinds.append("grounded")
            body = {"steps": self.steps}
        elif "spoken_text" in properties:
            self.kinds.append("speech")
            body = {"spoken_text": self.spoken, "stage_direction": ""}
        elif "narration" in properties:
            self.kinds.append("narration")
            body = {"narration": self.narration, "world_updates": {}, "lore_claims": []}
        else:
            self.kinds.append("classifier")
            body = {"intent": "narrative", "action": "narrative",
                    "target": {"type": "none", "reference": ""},
                    "completion": "unclear", "confidence": 1.0}
        return {"message": {"content": json.dumps(body, ensure_ascii=False)}}


class FreeAttemptTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def play(self, client, message, turn_url=None):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url or self.turn_url, client,
            {"message": message, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def asyncSetUpScene(self):
        _, _, self.session, self.turn_url, self.npc = await self.campaign_with_npc(experimental=False)

    async def assert_narrated_without_state(self, message, narration="Sesin salonda yankılanıyor, birkaç baş dönüyor."):
        await self.asyncSetUpScene()
        world = self.session.world_state
        before = {key: copy.deepcopy(world.get(key)) for key in ("location", "inventory", "gold", "doors", "npcs")}
        client = NarratingClient(narration=narration)
        data = await self.play(client, message)
        self.assertIn("narration", client.kinds, data["narration"])
        for key, value in before.items():
            current = world.get(key)
            if key == "npcs":
                current = [{k: v for k, v in n.items() if k != "memory"} for n in current]
                value = [{k: v for k, v in n.items() if k != "memory"} for n in value]
            self.assertEqual(current, value, key)
        return data["narration"]

    async def test_singing_on_a_table_reaches_the_model(self):
        shown = await self.assert_narrated_without_state("Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.")
        self.assertIn("yankılanıyor", shown)
        self.assertNotIn("ıslık", shown)

    async def test_a_sentence_of_two_clauses_is_narrated_not_handed_back(self):
        shown = await self.assert_narrated_without_state("Teklifimi geri çekiyorum, kimseyle uğraşmak istemiyorum.")
        self.assertIn("yankılanıyor", shown)
        self.assertNotIn("İlk adımın", shown)

    async def test_a_new_proposal_marker_with_no_proposal_costs_only_the_marker(self):
        shown = await self.assert_narrated_without_state(
            "Yan masadakilere yazı tura oynamayı teklif ediyorum.",
            "Köşedeki [[n1]] Marek göz ucuyla bakıyor. Birkaç kişi başını kaldırıyor.",
        )
        self.assertEqual(shown, "Köşedeki Marek göz ucuyla bakıyor. Birkaç kişi başını kaldırıyor.")

    async def test_an_id_copied_from_the_context_becomes_the_public_label(self):
        await self.asyncSetUpScene()
        self.npc["name_known_to_player"] = False
        client = NarratingClient(narration=f"Köşedeki [[{self.npc['id']}]] başını kaldırıp sana bakıyor.")
        shown = (await self.play(client, "Yan masadakilere yazı tura oynamayı teklif ediyorum."))["narration"]
        self.assertNotIn("[[", shown)
        self.assertNotIn(self.npc["id"], shown)
        self.assertNotIn("Marek", shown)
        label = living_world.public_npc_name(self.npc)
        self.assertIn(label[:1].lower() + label[1:], shown)

    async def test_the_player_is_not_told_what_they_feel(self):
        shown = await self.assert_narrated_without_state(
            "Sokaktaki adamın kesesine göz atıyorum.",
            "Omuzlarının üzerinden bakarken anlık bir gerginlik hissediyorsun. Kese basit bir kumaştan.",
        )
        self.assertNotIn("hissediyorsun", shown)
        self.assertIn("Kese basit bir kumaştan.", shown)

    async def test_the_order_after_the_walk_still_reaches_the_person(self):
        await self.asyncSetUpScene()
        self.npc["role"] = "Barmen"
        self.npc["role_known_to_player"] = True
        client = NarratingClient(spoken="Hemen koyuyorum.")
        data = await self.play(client, "Marek'in yanına gidiyorum, bir bira istiyorum.")
        self.assertIn("speech", client.kinds, (data["narration"], data.get("action_result"), self.session.world_state.get("flags")))
        self.assertIn("Hemen koyuyorum.", data["narration"])
        prompt = "\n".join(item["content"] for item in client.batches[-1])
        self.assertIn("bir bira istiyorum", prompt)

    async def test_an_order_after_a_walk_the_words_alone_could_not_bind(self):
        await self.asyncSetUpScene()
        world = self.session.world_state
        door = next(d for d in world["doors"] if d["id"].startswith("venue-door:"))
        door.update(open=True, locked=False)
        tavern = door["id"].split(":", 1)[1]
        self.npc.update(role="Barmen", role_known_to_player=True, name_known_to_player=False, location=tavern)
        world["location"] = tavern
        steps = [{"verb": "go", "target_id": self.npc["id"], "negated": False,
                  "conditional": False, "new_thing": ""}] * 2
        client = NarratingClient(spoken="Hemen koyuyorum.", steps=steps)
        data = await self.play(client, "İçeri girip tezgâha geçiyorum, bir bira istiyorum.")
        self.assertIn("speech", client.kinds, data["narration"])
        self.assertIn("Hemen koyuyorum.", data["narration"])

    async def test_an_npc_may_ask_what_the_player_would_do(self):
        await self.asyncSetUpScene()
        self.session.world_state["inventory"].append("Kılıç")
        client = NarratingClient(spoken="Kılıçla ne yaparsın ki? Bir bira, parayla alınır.")
        data = await self.play(client, "Marek, kılıcımı hafifçe gösterip içkinin bedava olması gerektiğini söylüyorum.")
        self.assertIn("parayla alınır", data["narration"])
        self.assertNotIn("envanterinde", data["narration"])

    async def test_catching_the_eye_is_not_a_hammer(self):
        shown = await self.assert_narrated_without_state(
            "Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.",
            "Bu, salonda dikkat çekici bir hareket oluyor. Birkaç kişi başını çeviriyor.",
        )
        self.assertIn("dikkat çekici", shown)

    async def test_a_prop_the_scene_lacks_costs_one_sentence_not_the_turn(self):
        shown = await self.assert_narrated_without_state(
            "Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.",
            "Yerdeki eski sandık açık duruyor. Birkaç kişi başını çeviriyor.",
        )
        self.assertNotIn("sandık", shown, self.session.last_narration_safety)
        self.assertIn("Birkaç kişi başını çeviriyor.", shown, self.session.last_narration_safety)

    async def test_single_brackets_and_a_marker_used_as_a_subject_read_as_prose(self):
        await self.asyncSetUpScene()
        world = self.session.world_state
        for npc in world["npcs"]:
            if npc is not self.npc:
                npc["location"] = "tavern"
        client = NarratingClient(narration="Yanındaki [Marek] sakin. Köşedeki [[n1]] sakinlikle işine devam ediyor.")
        shown = (await self.play(client, "Yan masadakilere yazı tura oynamayı teklif ediyorum."))["narration"]
        self.assertEqual(shown, "Yanındaki Marek sakin. Köşedeki Marek sakinlikle işine devam ediyor.")

    async def test_the_plan_receipt_never_reaches_the_prompt_as_a_line_to_copy(self):
        await self.asyncSetUpScene()
        client = NarratingClient()
        await self.play(client, "Teklifimi geri çekiyorum, kimseyle uğraşmak istemiyorum.")
        prompt = "\n".join(item["content"] for item in client.batches[-1])
        self.assertNotIn("tartıyorsun", prompt)
        self.assertIn("Önce oyuncunun denediği şeyin", prompt)

    async def test_people_setting_down_their_cups_cost_a_sentence_at_most(self):
        shown = await self.assert_narrated_without_state(
            "Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.",
            "Sesin yankılanıyor. Bazıları rahatsız olmuş gibi kadehlerini masalara bıraktılar.",
        )
        self.assertIn("Sesin yankılanıyor.", shown)

    async def test_two_bad_sentences_still_leave_the_good_one(self):
        shown = await self.assert_narrated_without_state(
            "Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.",
            "Sesin yankılanıyor. Bazıları kadehlerini masalara bıraktılar. Yerdeki eski sandık açık duruyor.",
        )
        self.assertEqual(shown, "Sesin yankılanıyor.")

    async def test_a_sentence_from_the_last_turn_is_not_told_twice(self):
        await self.asyncSetUpScene()
        first = NarratingClient(narration="Salon bir an susuyor. Birkaç kişi bakıyor.")
        await self.play(first, "Yan masadakilere yazı tura oynamayı teklif ediyorum.")
        second = NarratingClient(narration="Salon bir an susuyor. Teklifin havada kalıyor.")
        shown = (await self.play(second, "Yan masadakilere yeniden sesleniyorum."))["narration"]
        self.assertEqual(shown, "Teklifin havada kalıyor.")

    async def test_an_id_before_the_name_does_not_double_the_name(self):
        shown = await self.assert_narrated_without_state(
            "Yan masadakilere yazı tura oynamayı teklif ediyorum.",
            "Köşedeki [[npc_experimental_marek]] Marek başını kaldırıyor.",
        )
        self.assertEqual(shown, "Köşedeki Marek başını kaldırıyor.")

    async def test_walking_up_to_a_feature_reads_as_turkish(self):
        await self.asyncSetUpScene()
        world = self.session.world_state
        world.setdefault("features", []).append({
            "id": "f1", "location": world["location"], "name": "Ahşap masa",
            "description": "Sağlam bir masa.", "aliases": ["masa"],
        })
        shown = (await self.play(NarratingClient(), "Masaya yaklaşıyorum."))["narration"]
        self.assertIn("Ahşap masanın yanına geliyorsun.", shown)

    def test_stock_performance_lines_are_gone(self):
        for message in ("Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.", "ıslık çalıyorum", "dans ediyorum"):
            self.assertIsNone(everyday_actions.classify(message))

    def test_spoken_request_finds_the_clause_and_not_a_wish_to_move(self):
        self.assertEqual(
            grounded_action.spoken_request("İçeri girip tezgâha geçiyorum, bir bira istiyorum."),
            "bir bira istiyorum",
        )
        self.assertIsNone(grounded_action.spoken_request("Handan çıkmak istiyorum."))
        self.assertIsNone(grounded_action.spoken_request("Kapıya gidiyorum."))

    def test_the_narrator_prompt_carries_the_free_attempt_rules(self):
        self.assertIn("denemeyi yok sayma", game.system_prompt)
        self.assertIn("duruma özgü esprili", game.system_prompt)


if __name__ == "__main__":
    unittest.main()
