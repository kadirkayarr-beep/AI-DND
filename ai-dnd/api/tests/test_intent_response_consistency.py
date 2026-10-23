"""Natural player intent, committed state and visible response must agree.

Real ASGI/engine and temporary SQLite with fake or scripted model clients.
Resolved physical/identity actions must not call the model. No live model or
production data is used.
"""
import unittest
import copy
import json
import uuid
from unittest.mock import patch
import game
import local_dialogue
import living_world
import resolved_presentation
from api.tests import test_campaign_api


class NoNarrationClient(test_campaign_api.FakeOllamaClient):
    def __init__(self):
        self.calls = 0
        self.allow_narration = False
        self.intent_calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        if "intent" in (kwargs.get("format", {}).get("properties") or {}):
            self.intent_calls += 1
        elif self.allow_narration:
            return {"message": {"content": json.dumps({"narration": "Çevrene bakıyorsun.", "world_updates": {}, "lore_claims": []}, ensure_ascii=False)}}
        raise AssertionError("Resolved physical/identity action must not call the model")


class IntentResponseConsistencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = NoNarrationClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": "fr:city:neverwinter",
        }})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign_id = created.json()["campaign_id"]
        self.session_id = created.json()["session_id"]
        self.session = self.manager.get(self.session_id).game_session
        self.world = self.session.world_state

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def turn(self, message, **fields):
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn",
                                       json={"message": message, "action_id": str(uuid.uuid4()), **fields})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def arrive(self):
        await self.turn("Çevreme bakıyorum.")
        await self.turn("dükkan gidiyorum")
        door = self.world["doors"][0]
        door["open"], door["locked"] = False, False
        place = next(v for v in self.world["locations"].values() if v.get("scene_kind") == "building")
        return door, place

    async def test_implicit_enter_commits_destination(self):
        door, place = await self.arrive()
        result = await self.turn("içeri giriyorum")
        self.assertEqual(self.world["location"], place["id"])
        self.assertTrue(door["open"])
        self.assertIn(place["name"], result["narration"])
        self.assertEqual(self.client.calls, 0)

    def known_shop(self, *, locked=False):
        import grounded_action
        city = self.world['location']
        living_world.materialize_scene(self.world, city, 0,
                                      create_npc=self.session.create_npc_from_ai,
                                      create_feature=self.session.create_local_feature)
        place = grounded_action._create_venue(
            grounded_action._Run(self.session, 'synthetic setup'), city,
            name='Orin Dükkânı', kind='building', noun='dukkan',
            provenance={'kind': 'synthetic_verification_setup'},
        )
        door = next(d for d in self.world['doors'] if d['id'] == 'venue-door:' + place['id'])
        door.update(open=False, locked=locked, broken=False)
        # Feature creation is deliberately current-scene only. Seed the room
        # before measured turns, then restore the starting location.
        self.world['location'] = place['id']
        try:
            feature = self.session.create_local_feature({
                'location': place['id'], 'name': 'Ahşap raf',
                'description': 'Sıradan boş bir raf.', 'kind': 'furnishing',
            })
        finally:
            self.world['location'] = city
        self.assertIsNotNone(feature)
        self.assertIn(feature, self.world['features'])
        return city, place, door

    async def test_known_named_shop_arrival_then_implicit_entry_uses_local_owner(self):
        city, place, door = self.known_shop()
        await self.turn('Çevreme bakıyorum.', interaction_mode='do')
        await self.turn('Adını öğrenebilir miyim?', target_id=self.world['npcs'][0]['id'])
        arrival = await self.turn("Orin Dükkânı'na gidiyorum.", interaction_mode='do')
        self.assertEqual(self.world['location'], city)
        self.assertFalse(door['open'])
        self.assertEqual(arrival['turn_outcome']['status'], 'blocked')
        self.assertEqual(self.world['scene_state']['entry_target_reference']['source_kind'], 'blocked_travel')
        entered = await self.turn('İçeri giriyorum.', interaction_mode='do')
        self.assertEqual(self.world['location'], place['id'])
        self.assertTrue(door['open'])
        self.assertIn('içeri giriyorsun', entered['narration'])
        contents = await self.turn('İçeride neler var?', interaction_mode='do')
        self.assertIn('Ahşap raf', contents['narration'])
        self.assertIsNone(contents.get('skill_check_result'))
        self.assertEqual(self.client.calls, 0)

    async def test_known_named_shop_arrival_does_not_open_a_locked_door(self):
        city, place, door = self.known_shop(locked=True)
        inventory = copy.deepcopy(self.world['inventory'])
        arrival = await self.turn("Orin Dükkânı'na gidiyorum.", interaction_mode='do')
        self.assertEqual(arrival['turn_outcome']['status'], 'blocked')
        entered = await self.turn('İçeri giriyorum.', interaction_mode='do')
        self.assertEqual(self.world['location'], city)
        self.assertTrue(door['locked'])
        self.assertFalse(door['open'])
        self.assertIn('kilitli', entered['narration'])
        self.assertEqual(self.world['inventory'], inventory)
        self.assertEqual(self.client.calls, 0)

    async def test_known_local_route_requires_a_visible_unique_owned_door(self):
        city, place, door = self.known_shop()
        def reference():
            living_world.record_entry_target_reference(
                self.world, action_result={'action': 'travel', 'status': 'blocked',
                                           'success': False, 'target_id': place['id']},
                source_action_id='fixture', source_turn_index=1, source_location_id=city,
            )
            return self.world['scene_state']['entry_target_reference']
        self.assertIsNotNone(reference())
        # A route paused before a closed destination is not a local arrival.
        for status in ('TRAVELLING', 'INTERRUPTED'):
            with self.subTest(journey_status=status):
                self.world['journey'] = {'status': status, 'origin': city,
                                         'destination': place['id']}
                self.assertIsNone(reference())
        self.world['journey'] = None
        self.assertIsNotNone(reference())
        door['open'] = True
        self.assertIsNone(reference())
        door['open'] = False
        door['hidden'] = True
        self.assertIsNone(reference())
        door.pop('hidden')
        door['location'] = 'elsewhere'
        self.assertIsNone(reference())
        door['location'] = city
        self.world['doors'].append(copy.deepcopy(door))
        self.assertIsNone(reference())

    async def test_registered_venue_names_do_not_start_combat(self):
        door, place = await self.arrive()
        city = self.world["location"]
        for name in ("Kestrin Hanı", "Keser Hanı"):
            with self.subTest(name=name):
                self.world["location"] = city
                self.world["combat"]["active"] = False
                place["name"] = name
                door["name"] = name + " Kapısı"
                door["open"], door["locked"] = False, False
                result = await self.turn(name + " içine giriyorum.", target_id=place["id"])
                self.assertEqual(self.world["location"], place["id"])
                self.assertTrue(door["open"])
                self.assertFalse(self.world["combat"]["active"])
                self.assertIn(name, result["narration"])
                self.assertTrue(self.session._has_explicit_attack_verb("Keser'e vuruyorum."))
        npc = self.world["npcs"][0]
        npc.update(name="Kes", name_known_to_player=True, location=place["id"])
        self.assertTrue(self.session._has_explicit_attack_verb("Onu kes."))
        self.assertTrue(self.session._has_explicit_attack_verb("Onu kesiyorum."))
        self.assertEqual(self.client.calls, 0)

    async def test_registered_building_name_precedes_tavern_keyword_fallback(self):
        import grounded_action
        city, place, door = self.known_shop()
        other = grounded_action._create_venue(
            grounded_action._Run(self.session, "synthetic setup"), city,
            name="Başka Han", kind="tavern", noun="han",
            provenance={"kind": "synthetic_verification_setup"},
        )
        ids = set(self.world["locations"])
        for name in ("Finnan Dükkânı", "Hanife Dükkânı", "Tavernacı Dükkânı"):
            with self.subTest(name=name):
                self.world["location"] = city
                place.update(name=name, aliases=[name, "dükkan"])
                door.update(name=name + " Kapısı", open=False, locked=False)
                result = await self.turn(name + " içine giriyorum.")
                self.assertEqual(self.world["location"], place["id"])
                self.assertNotEqual(self.world["location"], other["id"])
                self.assertEqual(set(self.world["locations"]), ids)
                self.assertIn(name, result["narration"])
                self.assertTrue(door["open"])
        self.assertEqual(self.client.calls, 0)

    async def test_registered_locked_building_cannot_be_replaced_by_an_open_inn(self):
        import grounded_action
        city, place, door = self.known_shop(locked=True)
        place.update(name="Finnan Dükkânı", aliases=["Finnan Dükkânı", "dükkan"])
        door["name"] = "Finnan Dükkânı Kapısı"
        grounded_action._create_venue(
            grounded_action._Run(self.session, "synthetic setup"), city,
            name="Açık Han", kind="tavern", noun="han",
            provenance={"kind": "synthetic_verification_setup"},
        )
        ids = set(self.world["locations"])
        result = await self.turn("Finnan Dükkânı içine giriyorum.")
        self.assertEqual(self.world["location"], city)
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])
        self.assertEqual(set(self.world["locations"]), ids)
        self.assertIn("kilitli", result["narration"])
        self.assertEqual(self.client.calls, 0)

    async def test_named_enter_opens_unlocked_door(self):
        door, place = await self.arrive()
        result = await self.turn(place["name"] + " içine giriyorum")
        self.assertEqual(self.world["location"], place["id"],
                         json.dumps({"requested_place": place, "locations": self.world["locations"],
                                     "narration": result["narration"]}, ensure_ascii=False))
        self.assertTrue(door["open"])
        self.assertNotIn("kilitli", result["narration"])
        self.assertEqual(self.client.calls, 0)

    async def test_locked_enter_preserves_location_and_lock(self):
        door, place = await self.arrive()
        door["locked"] = True
        before = self.world["location"]
        result = await self.turn("içeri giriyorum")
        self.assertEqual(self.world["location"], before)
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])
        self.assertIn("kilitli", result["narration"])
        self.assertEqual(self.client.calls, 0)

    async def test_grounded_arrival_reference_survives_save_resume(self):
        door, place = await self.arrive()
        await self.assert_entry_reference_survives_resume(place, 'grounded_arrival')

    async def test_blocked_travel_reference_survives_save_resume(self):
        city, place, door = self.known_shop()
        await self.turn("Orin Dükkânı'na gidiyorum.", interaction_mode='do')
        await self.assert_entry_reference_survives_resume(place, 'blocked_travel')

    async def assert_entry_reference_survives_resume(self, place, source_kind):
        reference = self.world["scene_state"]["entry_target_reference"]
        self.assertEqual(reference["source_kind"], source_kind)
        saved = await self.http.post(f"/api/game/campaigns/{self.campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        manager = test_campaign_api.SessionManager(campaign_store=self.store)
        app = test_campaign_api.create_app(
            session_manager=manager, ollama_adapter=self.app.state.ollama_adapter,
            authenticator=test_campaign_api.FixedAuthenticator(test_campaign_api.TEST_PLAYER))
        async with test_campaign_api.httpx.AsyncClient(
            transport=test_campaign_api.httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            payload = {"message": "İçeri giriyorum.", "action_id": str(uuid.uuid4())}
            url = f"/api/game/sessions/{session_id}/turn"
            entered = await http.post(url, json=payload)
            self.assertEqual(entered.status_code, 200, entered.text)
            self.assertEqual(manager.get(session_id).game_session.world_state["location"], place["id"])
            replay = await http.post(url, json=payload)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(entered.json(), replay.json())
            self.assertEqual(self.client.calls, 0)

    async def test_visible_contents_are_observation_not_a_dice_gate(self):
        door, place = await self.arrive()
        await self.turn("içeri giriyorum")
        self.client.allow_narration = True
        before_rng = self.session.rng.getstate()
        for message in ("dükkanda neler var diye bakıyorum", "İçeride neler var?", "Burada ne var?"):
            with self.subTest(message=message):
                result = await self.turn(message)
                self.assertEqual(self.world["location"], place["id"])
                self.assertTrue(result["narration"].strip())
                self.assertEqual(self.session.rng.getstate(), before_rng)
                self.assertEqual(self.client.intent_calls, 0)

    async def test_visible_contents_describes_current_room_without_model(self):
        door, place = await self.arrive()
        await self.turn("İçeri giriyorum.")
        place["description"] = "Duvar boyunca boş raflar uzanıyor."
        self.world["features"].extend([
            {"id": "fixture_public_shelf", "location": place["id"], "name": "Ahşap raf",
             "description": "Üzerinde boş kavanozlar var.", "kind": "furnishing", "aliases": ["raf"]},
            {"id": "fixture_hidden_panel", "location": place["id"], "name": "Gizli bölme",
             "description": "Gizli bir kasa saklı.", "kind": "furnishing", "aliases": ["bölme"], "hidden": True},
        ])
        before_rng = self.session.rng.getstate()
        result = await self.turn("İçeride neler var?")
        self.assertIn("Duvar boyunca boş raflar", result["narration"])
        self.assertIn("Ahşap raf", result["narration"])
        self.assertNotIn("Gizli bölme", result["narration"])
        self.assertNotIn("Gizli bir kasa", result["narration"])
        self.assertEqual(self.client.calls, 0)
        self.assertEqual(self.session.rng.getstate(), before_rng)
        self.assertEqual(self.world["location"], place["id"])
        self.assertTrue(door["open"])
        self.client.allow_narration = True
        ordinary = await self.turn("Çevreme bakıyorum.")
        self.assertNotIn("Gizli bölme", ordinary["narration"])
        self.assertNotIn("Gizli bir kasa", ordinary["narration"])

    async def test_active_conversation_needs_no_reselected_target_for_city_opinion(self):
        await self.assert_focused_speech_without_target(
            "Bu şehirde yaşamayı seviyor musun?", "Burada yaşamaktan memnunum."
        )

    async def test_nominal_speech_preference_does_not_request_another_actor(self):
        await self.assert_focused_speech_without_target(
            "İnsanlarla sohbet etmeyi mi seversin, tek başına kalmayı mı?",
            "İnsanlarla konuşmayı tercih ederim."
        )

    async def test_compound_personal_question_cannot_be_consumed_by_day_shortcut(self):
        await self.assert_focused_speech_without_target(
            "Adın neydi, bir de günün nasıl geçiyor?", "Adım Lysa. Günüm sakin geçiyor."
        )

    async def assert_focused_speech_without_target(self, question, reply):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        npc.update(name="Lysa", name_known_to_player=False)
        await self.turn("İsmin nedir?", target_id=npc["id"])
        before = copy.deepcopy((self.session.character, self.world["inventory"], self.world["location"]))
        for mode in (None, "do", "say"):
            # Omitted mode is the public API default, distinct from explicitly do.
            answer = reply + (" Senin fikrin ne?" if mode == "say" else " Böyle düşünüyorum." if mode is None else "")
            client = ScriptedNpcSpeechClient(answer)
            with self.subTest(mode=mode), patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
                result = await self.turn(question, **({} if mode is None else {"interaction_mode": mode}))
                self.assertIn(answer, result["narration"])
                self.assertEqual(client.chat_calls, 1)
                self.assertIn("spoken_text", client.schemas[0]["properties"])
                self.assertEqual(self.world["flags"]["active_npc_id"], npc["id"])
                self.assertEqual(before, (self.session.character, self.world["inventory"], self.world["location"]))

    async def test_unknown_explicit_address_does_not_reuse_active_interlocutor(self):
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        npc.update(name="Lysa", name_known_to_player=False)
        await self.turn("İsmin nedir?", target_id=npc["id"])
        before = copy.deepcopy((self.world["npcs"], self.world["inventory"]))
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}):
            result = await self.turn("Garrick, günün nasıl geçiyor?")
        self.assertIn("Garrick", result["narration"])
        self.assertNotIn("Lysa:", result["narration"])
        self.assertEqual(before, (self.world["npcs"], self.world["inventory"]))

    async def test_explicit_selected_npc_owns_unnamed_city_question(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        npc.update(name="Lysa", name_known_to_player=True)
        client = ScriptedNpcSpeechClient("Burada yaşamaktan memnunum.")
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
            result = await self.turn("Bu şehirde yaşamayı seviyor musun?", target_id=npc["id"])
        self.assertIn("Burada yaşamaktan memnunum.", result["narration"])
        self.assertEqual(client.chat_calls, 1)

    async def test_rejected_observation_decoration_preserves_native_scene_receipt(self):
        import grounded_action
        city = self.world["location"]
        place = grounded_action._create_venue(
            grounded_action._Run(self.session, "synthetic setup"), city,
            name="Hlin Hanı", kind="tavern", noun="han",
            provenance={"kind": "synthetic_verification_setup"},
        )
        place["description"] = "Halka açık sakin bir han. Masalar ve tezgâh görünür."
        door = next(d for d in self.world["doors"] if d["id"] == "venue-door:" + place["id"])
        door.update(open=False, locked=False)
        await self.turn("Hlin Hanı'na gidiyorum.")
        await self.turn("İçeri giriyorum.")
        before = copy.deepcopy((self.session.character, self.world["inventory"], self.world["location"]))
        client = test_campaign_api.FakeOllamaClient()
        payload = {"narration": "Hlin Hanı çevresine göz gezdiriyorsun. Yakındaki bir kapı sertçe kapanır; ardından içeriden anlaşılmayan birkaç söz duyulur. Etrafında sessizlik hakimken, içerdeki gürültü artar ve biraz daha netleşir: Gecenin geçmesi gereken zamanı ver. Dışarıda hâlâ gün batmadan önceydi, ama içerideki havada bir gerilim hissediliyor.", "world_updates": {}, "lore_claims": []}
        with patch.object(client, "chat", return_value={"message": {"content": json.dumps(payload, ensure_ascii=False)}}) as chat, patch.object(self.app.state.ollama_adapter, "_client", client):
            result = await self.turn("Etrafıma bakıyorum.")
        self.assertEqual(chat.call_count, 1)
        self.assertIn("Hlin Hanı", result["narration"])
        self.assertNotIn("hiçbir söz sağlam", result["narration"])
        self.assertNotIn("Gecenin geçmesi", result["narration"])
        self.assertEqual(before, (self.session.character, self.world["inventory"], self.world["location"]))

    async def test_compound_identity_and_day_keeps_both_answers(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        await self.turn("İsmin nedir?", target_id=npc["id"])
        client = ScriptedNpcSpeechClient(
            f"Adım {npc['name']}. Günüm iyi geçiyor.", conversation={
                "addressee_id": npc["id"], "subject_phrase": npc["name"],
                "subject_role": "addressee", "meaning": "other", "topic_relation": "new",
                "candidate_evidence_ids": [],
            })
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
            result = await self.turn(npc["name"] + ", ismin nedir? Günün nasıl geçiyor?", interaction_mode="say", target_id=npc["id"])
        self.assertIn("Adım " + npc["name"], result["narration"])
        self.assertIn("Günüm iyi geçiyor", result["narration"])
        self.assertGreater(client.chat_calls, 0)

    async def test_focused_city_opinion_uses_same_dialogue_route_in_do_and_say(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        await self.turn("İsmin nedir?", target_id=npc["id"])
        location = self.world["location"]
        inventory = json.dumps(self.session.character.get("inventory"), sort_keys=True)
        hp = self.session.character["current_hp"]
        for mode, reply in (("do", "Bana kalırsa hareketli bir yer."), ("say", "Burada yaşamaktan memnunum.")):
            client = ScriptedNpcSpeechClient(reply, conversation={
                "addressee_id": npc["id"], "subject_phrase": npc["name"],
                "subject_role": "addressee", "meaning": "other", "topic_relation": "new",
                "candidate_evidence_ids": [],
            })
            with self.subTest(mode=mode), patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
                result = await self.turn(npc["name"] + ", bu şehirde yaşamayı seviyor musun?", interaction_mode=mode, target_id=npc["id"])
                self.assertIn(reply, result["narration"])
                self.assertGreater(client.chat_calls, 0)
                prompt = next(item["content"] for item in reversed(client.message_batches[0]) if item.get("role") == "user")
                marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
                context, _ = json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])
                self.assertEqual(context["scene"]["location"]["id"], location)
                self.assertEqual(context["scene"]["location"]["kind"], "city")
                self.assertEqual(self.world["location"], location)
                self.assertEqual(json.dumps(self.session.character.get("inventory"), sort_keys=True), inventory)
                self.assertEqual(self.session.character["current_hp"], hp)

    async def test_explicit_city_question_selects_named_npc_not_previous_focus(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        first, second = self.world["npcs"][:2]
        await self.turn("İsmin nedir?", target_id=first["id"])
        await self.turn("İsmin nedir?", target_id=second["id"])
        client = ScriptedNpcSpeechClient("Bana kalırsa hareketli bir yer.", conversation={
            "addressee_id": first["id"], "subject_phrase": first["name"],
            "subject_role": "addressee", "meaning": "other", "topic_relation": "new",
            "candidate_evidence_ids": [],
        })
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
            result = await self.turn(first["name"] + ", bu şehirde yaşamayı seviyor musun?", interaction_mode="do")
        prompt = next(item["content"] for item in reversed(client.message_batches[0]) if item.get("role") == "user")
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        context, _ = json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])
        self.assertEqual(context["npc_id"], first["id"])
        self.assertEqual(self.world["flags"]["active_npc_id"], first["id"])
        self.assertTrue(result["narration"].startswith(first["name"] + ":"))
        self.assertIn("Bana kalırsa hareketli bir yer", result["narration"])
        self.assertGreater(client.chat_calls, 0)

    async def test_unaddressed_world_question_does_not_become_npc_identity(self):
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        await self.turn("İsmin nedir?", target_id=npc["id"])
        result = await self.turn("Şehrin yöneticisi kim?", interaction_mode="do")
        self.assertFalse(result["narration"].startswith(npc["name"] + ":"))
        self.assertNotIn("Ben " + npc["name"], result["narration"])
        self.assertEqual(self.client.calls, 0)

    async def test_attributed_questions_are_not_blocked_by_topic_words(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        await self.turn("İsmin nedir?", target_id=npc["id"])
        before = (self.world["location"], sorted(self.world["locations"]),
                  json.dumps(self.world["inventory"], sort_keys=True), self.session.character["current_hp"])
        cases = (
            ("bu mahallede yaşamayı seviyor musun?", "Burada yaşamaktan memnunum.", "say"),
            ("vergi hakkında ne düşünüyorsun?", "Bana sorarsan insanı yoruyor.", "do"),
            ("kasabada bir demirci tanıyor musun?", "Tanıdığım bir demirci yok.", "say"),
            ("Brom adlı birini tanıyor musun?", "Öyle birini tanımıyorum.", "say"),
        )
        for question, reply, mode in cases:
            client = ScriptedNpcSpeechClient(reply, conversation={
                "addressee_id": npc["id"], "subject_phrase": npc["name"],
                "subject_role": "addressee", "meaning": "other", "topic_relation": "new",
                "candidate_evidence_ids": [],
            })
            with self.subTest(question=question), patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
                result = await self.turn(npc["name"] + ", " + question, interaction_mode=mode, target_id=npc["id"])
                self.assertEqual(client.chat_calls, 1)
                self.assertIn(reply, result["narration"])
                after = (self.world["location"], sorted(self.world["locations"]),
                         json.dumps(self.world["inventory"], sort_keys=True), self.session.character["current_hp"])
                self.assertEqual(after, before)

    async def test_attributed_topic_route_keeps_output_and_narrator_guards(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        await self.turn("İsmin nedir?", target_id=npc["id"])
        before = json.dumps(self.world["inventory"], sort_keys=True)
        unsafe = "Sana on altın verdim."
        client = ScriptedNpcSpeechClient(unsafe, conversation={
            "addressee_id": npc["id"], "subject_phrase": npc["name"],
            "subject_role": "addressee", "meaning": "other", "topic_relation": "new",
            "candidate_evidence_ids": [],
        })
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
            result = await self.turn(npc["name"] + ", vergi hakkında ne düşünüyorsun?", interaction_mode="say", target_id=npc["id"])
        self.assertEqual(client.chat_calls, 1)
        self.assertNotIn(unsafe, result["narration"])
        self.assertEqual(json.dumps(self.world["inventory"], sort_keys=True), before)
        # The narrator path is still authoritative, not attributed NPC speech.
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}):
            result = await self.turn("Vergi hakkında ne biliyoruz?", interaction_mode="ask_dm", target_id=npc["id"])
        self.assertFalse(result["narration"].startswith(npc["name"] + ":"))
        self.assertEqual(self.client.calls, 0)

    async def test_negated_identity_request_does_not_disclose_name(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        npc["name_known_to_player"] = False
        npc["role_known_to_player"] = True
        client = ScriptedNpcSpeechClient("Peki, söylemeyeceğim.", conversation={
            "addressee_id": npc["id"], "subject_phrase": npc["role"],
            "subject_role": "addressee", "meaning": "other", "topic_relation": "new",
            "candidate_evidence_ids": [],
        })
        with patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}), patch.object(self.app.state.ollama_adapter, "_client", client):
            result = await self.turn(npc["role"] + ", adını söyleme.", interaction_mode="say", target_id=npc["id"])
        self.assertFalse(living_world.npc_name_known_to_player(npc))
        self.assertNotIn(npc["name"], result["narration"])
        self.assertIn("Peki, söylemeyeceğim", result["narration"])

    async def test_polite_identity_has_same_state_and_visible_answer(self):
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        for mode in ("do", "say"):
            for message in ("Adını öğrenebilir miyim?", "Lütfen, adınızı söyler misiniz?"):
                with self.subTest(mode=mode, message=message), patch.dict("os.environ", {"AI_DND_NPC_SPEECH": "1"}):
                    npc["name_known_to_player"] = False
                    result = await self.turn(message, interaction_mode=mode, target_id=npc["id"])
                    self.assertIn("Ben " + npc["name"], result["narration"])
                    self.assertTrue(living_world.npc_name_known_to_player(npc))
                    self.assertEqual(self.client.calls, 0)

    async def test_identity_is_consistent_in_do_and_say(self):
        await self.turn("Çevreme bakıyorum.")
        npc = self.world["npcs"][0]
        for mode in ("do", "say"):
            for speech in ("0", "1"):
                with self.subTest(mode=mode, speech=speech), patch.dict("os.environ", {"AI_DND_NPC_SPEECH": speech}):
                    npc["name_known_to_player"] = False
                    result = await self.turn("Selamlar, ismin nedir?", interaction_mode=mode, target_id=npc["id"])
                    self.assertIn("Ben " + npc["name"], result["narration"])
                    self.assertTrue(living_world.npc_name_known_to_player(npc))
                    confirmation = await self.turn(npc["name"] + " mi?", interaction_mode=mode, target_id=npc["id"])
                    self.assertIn("Ben " + npc["name"], confirmation["narration"])
                    self.assertEqual(self.client.calls, 0)


    async def test_attributed_words_do_not_create_narrated_people(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc.update(name='Lysa', name_known_to_player=True)
        identities = [(n['id'], n['name'], n.get('location')) for n in self.world['npcs']]
        inventory = copy.deepcopy(self.world['inventory'])
        for spoken in (
            'Brom? Hayır, tanımadım. Ama burada yaşayan birçok kişi var. Belki sana yardımcı olabilirler.',
            "Brom'u tanımıyorum; adını senden duyuyorum.",
            'Bence sana en iyi cevabı kendisi verebilir.',
        ):
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(spoken=spoken), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Lysa, Brom adlı birini tanıyor musun?', interaction_mode='say', target_id=npc['id'])
                self.assertIn(spoken, result['narration'])
                self.assertEqual(client.chat_calls, 1)
                self.assertEqual([(n['id'], n['name'], n.get('location')) for n in self.world['npcs']], identities)
                self.assertEqual(self.world['inventory'], inventory)

    async def test_attributed_stage_still_cannot_introduce_a_person(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        self.assertFalse(any(n['name'] == 'Zorveth' for n in self.world['npcs']))
        identities = [n['id'] for n in self.world['npcs']]
        client = ScriptedNpcSpeechClient('Hayır, tanımıyorum.', stage_direction='Zorveth içeri girer.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Brom adlı birini tanıyor musun?', interaction_mode='say', target_id=npc['id'])
        self.assertIn('Hayır, tanımıyorum.', result['narration'])
        self.assertNotIn('Zorveth', result['narration'])
        self.assertEqual([n['id'] for n in self.world['npcs']], identities)

    async def test_attributed_speech_keeps_identity_and_mechanical_guards(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc.update(name='Lysa', name_known_to_player=True)
        inventory = copy.deepcopy(self.world['inventory'])
        hp = self.session.character['current_hp']
        for spoken in ('Adım Zorveth.', 'Altını sana verdim.', 'Masaya oturuyorsun.'):
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(spoken=spoken), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Lysa, günün nasıl geçiyor?', interaction_mode='say', target_id=npc['id'])
                self.assertNotIn(spoken, result['narration'])
                self.assertEqual(self.world['inventory'], inventory)
                self.assertEqual(self.session.character['current_hp'], hp)

    async def test_first_identity_and_day_question_answers_both_parts(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc.update(name='Lysa', name_known_to_player=False)
        client = ScriptedNpcSpeechClient('Adım Lysa. Günüm iyi geçiyor.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('İsmin nedir? Günün nasıl geçiyor?', interaction_mode='say', target_id=npc['id'])
        self.assertIn('Adım Lysa.', result['narration'])
        self.assertIn('Günüm iyi geçiyor.', result['narration'])
        self.assertTrue(living_world.npc_name_known_to_player(npc))


    async def test_npc_invitation_is_not_a_completed_player_action(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        location = self.world['location']
        inventory = copy.deepcopy(self.world['inventory'])
        for spoken in ('İstersen birlikte oturalım.', 'Birlikte oturmayalım.'):
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(spoken=spoken), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Biraz konuşabilir miyiz?', interaction_mode='say', target_id=npc['id'])
            self.assertIn(spoken, result['narration'])
            self.assertEqual(client.chat_calls, 1)
            self.assertEqual(self.world['location'], location)
            self.assertEqual(self.world['inventory'], inventory)

    async def test_npc_history_denial_is_not_a_past_event_assertion(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        for spoken in ('Seninle daha önce karşılaştığımızı hatırlamıyorum.', 'Dün karşılaşmadık.'):
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(spoken=spoken), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Beni tanıyor musun?', interaction_mode='say', target_id=npc['id'])
            self.assertIn(spoken, result['narration'])
            self.assertEqual(client.chat_calls, 1)

    async def test_collective_possibility_condition_and_denial_do_not_move_player(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        location = self.world['location']
        inventory = copy.deepcopy(self.world['inventory'])
        hp = self.session.character['current_hp']
        for form in ('oturabiliriz', 'oturabilir miyiz', 'otursak', 'oturabilirdik',
                     'oturmayız', 'oturmuyoruz', 'oturmadık', 'oturmayacağız'):
            spoken = 'Birlikte ' + form + '.'
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(form=form), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Biraz konuşabilir miyiz?', interaction_mode='say', target_id=npc['id'])
            self.assertIn(spoken, result['narration'])
            self.assertEqual(client.chat_calls, 1)
            self.assertEqual(self.world['location'], location)
            self.assertEqual(self.world['inventory'], inventory)
            self.assertEqual(self.session.character['current_hp'], hp)

    async def test_collective_event_or_reversed_denial_remains_rejected(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        location = self.world['location']
        for spoken in ('Birlikte oturuyoruz.', 'Birlikte oturduk.', 'Birlikte oturacağız.',
                       'Birlikte oturmadık diyemem.', 'Birlikte oturmadık değil.',
                       'Birlikte oturmayız denemez.'):
            self.session.recent_dm_narrations.clear()
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(spoken=spoken), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Biraz konuşabilir miyiz?', interaction_mode='say', target_id=npc['id'])
            self.assertNotIn(spoken, result['narration'])
            self.assertEqual(self.session.last_narration_safety['reason_code'], 'INVENTED_PLAYER_ACTION')
            self.assertEqual(self.world['location'], location)

    async def test_collective_mood_exception_does_not_apply_to_stage_directions(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        client = ScriptedNpcSpeechClient('Elbette, seni dinliyorum.', stage_direction='Birlikte oturabiliriz.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Biraz konuşabilir miyiz?', interaction_mode='say', target_id=npc['id'])
        self.assertIn('Elbette, seni dinliyorum.', result['narration'])
        self.assertNotIn('oturabiliriz', result['narration'])
        self.assertEqual(client.chat_calls, 1)

    async def test_sitting_word_in_a_refusal_does_not_authorize_player_motion(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        client = ScriptedNpcSpeechClient('Birlikte oturduk.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Oturmak istemiyorum. Biraz konuşabilir miyiz?', interaction_mode='say', target_id=npc['id'])
        self.assertEqual(client.chat_calls, 1)
        self.assertNotIn('Birlikte oturduk.', result['narration'])
        self.assertEqual(self.session.last_narration_safety['reason_code'], 'INVENTED_PLAYER_ACTION')

    async def test_history_denial_does_not_mask_affirmation_or_double_negative(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        for spoken in (
            'Dün karşılaştık.',
            'Dün karşılaştığımızı hatırlamıyorum diyemem.',
            'Dün karşılaşmadık. Daha önce burada buluştuk.',
            'Daha önce buluştuk, hatırlamıyorum.',
        ):
            # Independent rejection probes: fallback deduplication must not
            # replace the first guard's reason with REPEATED_NARRATION.
            self.session.recent_dm_narrations.clear()
            client = ScriptedNpcSpeechClient(spoken)
            with self.subTest(spoken=spoken), patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
                result = await self.turn('Beni tanıyor musun?', interaction_mode='say', target_id=npc['id'])
            self.assertNotIn(spoken, result['narration'])
            self.assertNotIn('burada buluştuk', result['narration'])
            self.assertEqual(self.session.last_narration_safety['reason_code'], 'UNSUPPORTED_CAMPAIGN_HISTORY_CLAIM')

    async def test_invitation_does_not_mask_a_later_completed_sitting_claim(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc['name_known_to_player'] = True
        client = ScriptedNpcSpeechClient('İstersen birlikte oturalım. Birlikte oturuyoruz.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Biraz konuşabilir miyiz?', interaction_mode='say', target_id=npc['id'])
        self.assertNotIn('oturuyoruz', result['narration'])
        self.assertIn('oturalım', result['narration'])
        self.assertEqual(self.session.last_narration_safety['reason_code'], 'INVENTED_PLAYER_ACTION')


    async def test_compound_query_repair_cannot_turn_a_gesture_into_an_answer(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc.update(name='Lysa', name_known_to_player=False)
        client = ScriptedNpcSpeechClient('Masaya oturuyorsun.', stage_direction='Lysa gülümsüyor.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('İsmin nedir? Günün nasıl geçiyor?', interaction_mode='say', target_id=npc['id'])
        self.assertNotIn('oturuyorsun', result['narration'])
        self.assertNotIn('“”', result['narration'])
        self.assertNotEqual(result['narration'], 'Lysa gülümsüyor.')
        self.assertEqual(self.session.last_narration_safety['handling'], 'python_fallback')
        self.assertEqual(client.chat_calls, 1)

    async def test_compound_query_keeps_valid_speech_when_only_stage_is_repaired(self):
        from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc.update(name='Lysa', name_known_to_player=False)
        client = ScriptedNpcSpeechClient('Adım Lysa. Günüm iyi geçiyor.', stage_direction='Masaya oturuyorsun.')
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH': '1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('İsmin nedir? Günün nasıl geçiyor?', interaction_mode='say', target_id=npc['id'])
        self.assertIn('Adım Lysa.', result['narration'])
        self.assertIn('Günüm iyi geçiyor.', result['narration'])
        self.assertNotIn('oturuyorsun', result['narration'])
        self.assertEqual(self.session.last_narration_safety['handling'], 'repaired')
        self.assertEqual(client.chat_calls, 1)


class IntentLanguageBoundaryTests(unittest.TestCase):
    def test_attack_stems_require_verb_forms_not_names_or_adjectives(self):
        for name in living_world._LOCAL_NAMES:
            self.assertEqual(game._attack_verb_tokens(game._normalize_turkish_typos(name)), [], name)
        for word in ("keskin", "kesik", "saldırgan", "vurgulu"):
            self.assertEqual(game._attack_verb_tokens(game._normalize_turkish_typos(word)), [], word)
        for word in ("vur", "kes", "saldırıyorum", "vuruyorum", "kesiyorum", "vurdum", "vurmayacağım", "vurmuyorum"):
            normalized = game._normalize_turkish_typos(word)
            self.assertEqual(game._attack_verb_tokens(normalized), [normalized], word)

    def test_rendered_stage_does_not_repeat_its_server_speaker(self):
        npc = {"id": "npc_kael", "name": "Kael"}
        payload = {"spoken_text": "Burada yaşamayı seviyorum.", "stage_direction": "Kael, çevresine bakıp gülümser."}
        before = copy.deepcopy(payload)
        rendered = game._render_experimental_npc_speech(payload, npc)
        self.assertEqual(rendered, "Kael (çevresine bakıp gülümser): “Burada yaşamayı seviyorum.”")
        self.assertEqual(payload, before)
        payload["stage_direction"] = "Rashid kapıya bakar."
        self.assertIn("Rashid kapıya bakar", game._render_experimental_npc_speech(payload, npc))

    def test_scene_facts_are_read_only_public_and_current(self):
        world = {
            "location": "room", "locations": {"room": {"name": "Dükkân", "type": "building", "description": "Açık raflar var."}},
            "npcs": [
                {"id": "public", "location": "room", "name": "Zelra", "name_known_to_player": False, "role_known_to_player": False, "personal_profile": {"secret": "GIZLI_PROFIL"}},
                {"id": "hidden", "location": "room", "name": "Veyra", "hidden": True},
                {"id": "away", "location": "elsewhere", "name": "Brom"},
                {"id": "unseen_arrival", "location": "room", "name": "GizliGeliş"},
            ],
            "scheduled_events": [{"status": "OCCURRED", "player_observed": False, "visibility": "hidden",
                                  "effects": [{"kind": "npc_location", "npc_id": "unseen_arrival"}]}],
            "features": [
                {"id": "shelf", "location": "room", "name": "Raf", "description": "Boş raf."},
                {"id": "secret", "location": "room", "name": "Gizli kasa", "hidden": True},
                {"id": "unseen", "location": "room", "name": "Keşfedilmemiş iz", "discovered": False},
            ],
        }
        before = copy.deepcopy(world)
        facts = living_world.visible_scene_facts(world)
        self.assertEqual(world, before)
        self.assertEqual(facts["location"]["id"], "room")
        self.assertEqual(facts["people"], [{"name": "Yakındaki kişi", "role": ""}])
        self.assertEqual(facts["features"], [{"name": "Raf", "description": "Boş raf."}])
        serialized = json.dumps(facts, ensure_ascii=False)
        for private in ("Zelra", "Veyra", "Brom", "GIZLI_PROFIL", "Gizli kasa", "Keşfedilmemiş iz", "GizliGeliş"):
            self.assertNotIn(private, serialized)

    def test_identity_shortcut_cannot_consume_another_question(self):
        npc = {"name": "Marek", "role": "Muhafız"}
        for text in ("Selamlar, ismin nedir?", "Marek mi?", "Muhafız, adın ne?"):
            self.assertTrue(local_dialogue.is_identity_only_question(text, npc), text)
        for text in ("İsmin nedir? Günün nasıl geçiyor?", "Adın ne ve ne iş yapıyorsun?", "Kimsin ve neden buradasın?", "Adını öğrenebilir miyim? Günün nasıl geçiyor?", "Adını söyleme."):
            self.assertFalse(local_dialogue.is_identity_only_question(text, npc), text)

    def test_nominal_speech_reference_is_not_a_later_finite_action(self):
        for text in ("İnsanlarla sohbet etmeyi mi seversin?", "Onunla konuşmaktan hoşlanır mısın?", "Brom'la konuşmayı tercih eder misin?"):
            self.assertTrue(local_dialogue.is_nominal_speech_reference(text), text)
        for text in ("Brom'la konuşuyorum", "Garrick'e selam veriyorum", "Brom'la konuşuyorum ve sohbet etmeyi severim"):
            self.assertFalse(local_dialogue.is_nominal_speech_reference(text), text)

    def test_venue_words_are_not_substrings_of_names_or_items(self):
        for text in ("Finnan arıyorum", "Hanife arıyorum", "Kalem arıyorum", "Tavernacı arıyorum"):
            self.assertFalse(living_world.is_tavern_search(text), text)
        for text in ("Bir han arıyorum", "Tavernayı arıyorum", "Meyhaneye yakın bir yer arıyorum", "an inn nearby", "ale nearby"):
            self.assertTrue(living_world.is_tavern_search(text), text)
        self.assertNotEqual(living_world.classify_scene_action("Carpenter ile konuşuyorum"), "enter")

    def test_greeting_is_not_unknown_canonical_name(self):
        for word in ("Selamlar", "Merhabalar", "Günaydın", "Hey", "Dostum", "Affedersiniz", "Pardon"):
            with self.subTest(word=word):
                self.assertIsNone(local_dialogue.unresolved_named_address(word + ", ismin nedir?", []))
        self.assertEqual(local_dialogue.unresolved_named_address("Garrick, ismin nedir?", []), "Garrick")

    def test_visible_contents_does_not_swallow_search_or_dialogue(self):
        for message in ("Gizli bölme arıyorum", "Burada neler var diye soruyorum", "İçeride neler var diye bakmıyorum", "Burada ne var ve sandalyeye oturuyorum"):
            with self.subTest(message=message):
                self.assertFalse(living_world.is_visible_contents_query(message))

    def test_registered_speaker_has_a_spoken_sentence_boundary(self):
        for spoken in ("Evet.", "Bilmiyorum.", "Yolcuyum; burada dinleniyorum."):
            with self.subTest(spoken=spoken):
                self.assertFalse(game._has_unregistered_narrative_entity('Marek: “' + spoken + '”', {"marek"}, {"marek"}))
        self.assertTrue(game._has_unregistered_narrative_entity('Marek: “Brom adlı kişi burada.”', {"marek"}, {"marek"}))
        self.assertTrue(game._has_unregistered_narrative_entity('Yolda Brom adlı kişi var.', {"marek"}, {"marek"}))

    def test_lore_rejection_preserves_committed_physical_result(self):
        for action in ("enter", "travel", "grounded_action"):
            with self.subTest(action=action):
                result = {"action": action, "status": "completed", "direct_response": "Kapıdan içeri giriyorsun."}
                self.assertEqual(resolved_presentation.lore_rejected_action(result), result["direct_response"])
        self.assertIsNone(resolved_presentation.lore_rejected_action({"action": "dialogue", "direct_response": "Uydurma bilgi"}))
        observed = {"action": "explore", "status": "observed", "success": True,
                    "direct_response": "Hlin Hanı çevresine göz gezdiriyorsun."}
        self.assertEqual(resolved_presentation.lore_rejected_action(observed), observed["direct_response"])
        self.assertIsNone(resolved_presentation.lore_rejected_action({**observed, "status": "unresolved"}))



class AttributedSpeechBoundaryTests(unittest.TestCase):
    def test_only_exact_server_bound_speech_scopes_entity_heuristics(self):
        import npc_speech_boundary
        npc = {"id": "npc_1"}
        result = {"action": "dialogue", "status": "experimental_attributed_speech", "npc_id": "npc_1"}
        payload = {"source": "experimental_attributed_speech", "speaker_id": "npc_1", "spoken_text": "Belki sana yardımcı olabilir.", "stage_direction": "Marek gülümser."}
        text = "Marek gülümser. Belki sana yardımcı olabilir."
        self.assertEqual(npc_speech_boundary.narrated_entity_text(text, payload, npc, result), "Marek gülümser.")
        for changes in ({"source": "model"}, {"speaker_id": "npc_2"}, {"spoken_text": "Farklı cevap"}, {"stage_direction": None}):
            with self.subTest(changes=changes):
                self.assertEqual(npc_speech_boundary.narrated_entity_text(text, {**payload, **changes}, npc, result), text)
        for changes in ({"npc_id": "npc_2"}, {"status": "accepted"}, {"action": "attack"}):
            with self.subTest(changes=changes):
                self.assertEqual(npc_speech_boundary.narrated_entity_text(text, payload, npc, {**result, **changes}), text)
        self.assertEqual(npc_speech_boundary.narrated_entity_text(text, None, npc, result), text)
