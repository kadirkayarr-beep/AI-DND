"""Deterministic regression corpus for narration safety calibration."""
import copy
import unittest
from unittest.mock import patch

import game
from api.narrative_memory import _scene_type


class NarrativeSafetyCalibrationTests(unittest.TestCase):
    def setUp(self):
        model_guard = patch("game.ollama.chat", side_effect=AssertionError(
            "Unexpected model call in an offline narrative release gate"
        ))
        guarded_chat = model_guard.start()
        self.addCleanup(model_guard.stop)
        self.addCleanup(guarded_chat.assert_not_called)
        self.session = game.create_session(seed=42)
        self.session.character["name"] = "Mira"
        self.session.world_state["location"] = "tavern"
        self.session.world_state["locations"] = {
            "tavern": {"name": "Taverna", "aliases": ["Taverna"]},
            "forest": {"name": "Orman", "aliases": ["Orman"]},
        }
        self.session.world_state["inventory"] = ["Macera çantası", "Kılıç"]
        self.gromm = {
            "id": "npc_001",
            "name": "Gromm",
            "role": "Barmen",
            "location": "tavern",
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 9,
        }
        self.session.world_state["npcs"] = [self.gromm]

    def decide(
        self,
        narration,
        player_input="Etrafıma bakıyorum.",
        action_result=None,
        npc_target=None,
    ):
        if action_result is None:
            action_result = {
                "action": "explore",
                "status": "resolved",
                "explore_type": "observe",
            }
        return self.session._narration_safety_decision(
            narration, player_input, npc_target, action_result
        )

    def finalize_narration(self, *args, **kwargs):
        with patch.object(game, "_session", return_value=self.session):
            return game.finalize_narration(*args, **kwargs)

    def test_temporary_texture_corpus_is_not_rejected_as_unregistered_canon(self):
        cases = (
            ("Gromm, kahve fincanını elinde sallarken başını kaldırır.", self.gromm),
            ("Taverna'nın köşesinde şömine çıtırdar.", None),
            ("Yağmur pencere camına vurur.", None),
            ("Masaların arasında isimsiz müşteriler alçak sesle konuşur.", None),
            ("Gromm kaşını kaldırır ve sessizce gülümser.", None),
            ("Taş kemer tavernanın tavanına uzanır.", None),
            ("Kahve kokusu ve bira aroması havada asılı kalır.", None),
            ("Uzakta bardaklar çınlar.", None),
            ("Gromm'un sesi kısık ve yorgun çıkar.", None),
            ("Pencereden serin bir esinti geçer.", None),
            ("Tütün kokusu odaya yayılır.", None),
            ("İsimsiz müşteriler masaların çevresinde fısıldaşır.", None),
            ("Gromm bardağını sessizce siler.", None),
            ("Yağmur vururken ıslak taşların kokusu belirginleşir.", None),
        )
        for narration, target in cases:
            with self.subTest(narration=narration):
                decision = self.decide(
                    narration,
                    player_input="Tavernayı dikkatlice gözlemliyorum.",
                    npc_target=target,
                )
                self.assertFalse(decision["unsafe"], decision)

    def test_saved_smoke_narrations_no_longer_fail_on_ordinary_texture(self):
        cases = (
            (
                "Gromm, kahve fincanını elinde sallarken gözlerini kaldırıp seni süzdü. "
                "'Arven mi?' dedi, ses tonu sakin ama ilgiyle. 'Kendinizi tanıtmak "
                "istediniz, öyleyse ben de kendimi tanıtayım.' Dediğine hem "
                "gülümsemeyerek hem de biraz başını eğerek karşılık verdi.",
                "Gromm, benim adım Arven. Kendimi tanıtıyorum.",
                {"action": "dialogue", "status": "resolved"},
                self.gromm,
            ),
            (
                "Taverna içeriği sadece biraz daha netleşti. Düşük ışıklandırma, kahve "
                "ve bira kokusu ile dolu ortamda Gromm, masanın diğer tarafında "
                "dikkatle karıştırmaktaydı. Sessizlik hâlâ devam ediyordu; yalnızca "
                "bardakların çalkalanması ve zaman zaman yemeklerin servis edilmesi "
                "sesleri duyuluyor gibiydi.",
                "Etrafıma bakıyorum.",
                {"action": "explore", "status": "resolved", "explore_type": "observe"},
                None,
            ),
            (
                "Kılıç ve macera çantası, içine birkaç küçük eşya sığmaktadır. "
                "Gromm, elinde bir bardak suyu tutarken sana baktı ve sessizce "
                "başını salladı.",
                "Envanterimde neler var?",
                {"action": "inventory", "status": "resolved"},
                None,
            ),
            (
                "Gromm, gözleri hâlâ kahve makinesine tutkun olarak durdu. 'İşler "
                "biraz sıkıntılı,' dedi, 'gece geç saatlere kadar açık kalıyorum ve "
                "her zaman müşteri beklemek zorunda hissediyorum.' Kollarını "
                "sıvayarak ekledi: 'Ama bu işin içinden çıkamadığım için de benim "
                "gibi birçok kişi burada kalmaya devam ediyor.'",
                "Gromm, işler nasıl gidiyor?",
                {"action": "dialogue", "status": "resolved"},
                self.gromm,
            ),
            (
                "Taverna iç mekanı, taş duvarlar ve ahşap masalarla çevrilmiş bir "
                "şekilde düzenlenmiş. Gromm, kahve makinesinin yanında duruyor; "
                "elinde küçük bir bardak çay var. Sessizce karıştırıyor ve gözlerini "
                "sana doğru çeviriyor. Ortamda hafif bir tütün kokusu dolaşıyor.",
                "Tavernayı dikkatlice gözlemliyorum.",
                {"action": "explore", "status": "resolved", "explore_type": "observe"},
                None,
            ),
        )
        for narration, player_input, result, target in cases:
            with self.subTest(player_input=player_input):
                decision = self.decide(
                    narration,
                    player_input=player_input,
                    action_result=result,
                    npc_target=target,
                )
                self.assertFalse(decision["unsafe"], decision)

    def test_travel_trace_still_rejects_absent_npc_and_unchosen_search_goal(self):
        elira = {
            "id": "npc_002",
            "name": "Korucu Elira",
            "role": "Korucu",
            "location": "forest",
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 8,
        }
        self.gromm["location"] = "tavern"
        self.session.world_state["npcs"].append(elira)
        self.session.world_state["location"] = "forest"
        narration = (
            'Gromm, "Ben Gromm; rolüm Barmen," diye yanıt verir. '
            "Ormana girerken, doğanın sessizliği sizi bekler. "
            "Yürüyüşünüzü sürdürüp, doğa koruyucusu Elira'nın izini bulmak için "
            "ileri doğru gitmelisiniz. Gölge Yolu’nun üzerinden geçerek, doğa "
            "seslerinin arasında kaybolursunuz."
        )
        decision = self.decide(
            narration,
            player_input="Ormana gidiyorum.",
            action_result={"action": "travel", "status": "completed", "success": True},
        )
        self.assertTrue(decision["unsafe"])
        self.assertEqual(
            decision["reason_code"], "CANONICAL_NPC_LOCATION_CONTRADICTION"
        )

    def test_perception_and_subjective_impression_are_allowed(self):
        narration = (
            "Korucu Elira, toprağı incelerken sessizce yanına gelir. "
            '"Orman seninle konuşmak istiyor," diye mırıldanır. '
            "Sessizliğin içinde, doğal sesler arasında bir şeylerin farklı "
            "olduğunu hissedersin."
        )
        elira = {
            "id": "npc_002",
            "name": "Korucu Elira",
            "role": "Korucu",
            "location": "forest",
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
        }
        self.session.world_state["npcs"].append(elira)
        self.session.world_state["location"] = "forest"
        decision = self.decide(
            narration,
            player_input="Bir süre sessizce bekliyorum.",
            action_result={"action": "explore", "status": "resolved", "explore_type": "observe"},
        )
        self.assertFalse(decision["unsafe"], decision)

    def test_place_inflection_and_modal_offers_preserve_safe_narration(self):
        self.session.world_state["location"] = "forest"
        place_decision = self.decide(
            "Ormanın sessizliği yaprakların hışırtısıyla bozulur."
        )
        self.assertFalse(place_decision["unsafe"], place_decision)

        offer_decision = self.decide("Sorun varsa, beni bulabilirsin.")
        self.assertFalse(offer_decision["unsafe"], offer_decision)

    def test_player_agency_corpus_is_rejected_with_reason_codes(self):
        cases = (
            ("Kılıcını savurursun.", "INVENTED_PLAYER_ACTION"),
            ("Gromm'a gerçek adını söylersin.", "INVENTED_PLAYER_ACTION"),
            ("Pazarlığı kabul edersin.", "INVENTED_PLAYER_ACTION"),
            ("Onun yalan söylediğine karar verirsin.", "INVENTED_PLAYER_ACTION"),
            ("Mahzene doğru yürürsün.", "INVENTED_PLAYER_ACTION"),
            ("Gizli yolu ararsın.", "INVENTED_PLAYER_ACTION"),
        )
        for narration, expected_reason in cases:
            with self.subTest(narration=narration):
                decision = self.decide(narration)
                self.assertTrue(decision["unsafe"], decision)
                self.assertEqual(decision["reason_code"], expected_reason)

    def test_unverified_player_mental_state_claims_are_rejected(self):
        cases = (
            ("Bu hareketin ne anlama geldiğini henüz anlamadın.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Karanlıkta korktun.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Bu haber seni memnun etti.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Mutlusun.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Pazarlığı kabul ettin.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Onun yalan söylediğine karar verdin.", "INVENTED_PLAYER_ACTION"),
            ("Bu fikri istedin.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Oyuncu bunu anladı.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Oyuncu bunu kabul etti.", "INVENTED_PLAYER_MENTAL_STATE"),
            ("Karakter mutlu oldu.", "INVENTED_PLAYER_MENTAL_STATE"),
        )
        for narration, expected_reason in cases:
            with self.subTest(narration=narration):
                decision = self.decide(narration)
                self.assertTrue(decision["unsafe"], decision)
                self.assertEqual(decision["reason_code"], expected_reason)

    def test_npc_gestures_and_temporary_atmosphere_remain_allowed(self):
        cases = (
            "Gromm sessizce gülümser.",
            "Gromm başını sallayarak selam verir.",
            "Atmosferdeki sıcaklık hafifçe değişiyor.",
        )
        for narration in cases:
            with self.subTest(narration=narration):
                decision = self.decide(narration)
                self.assertFalse(decision["unsafe"], decision)

    def test_mental_state_repair_removes_only_the_unsafe_sentence(self):
        output = self.finalize_narration(
            "Gromm kaşını kaldırır. "
            "Bu hareketin ne anlama geldiğini henüz anlamadın. "
            "Yağmur pencereye vurur.",
            "Etrafıma bakıyorum.",
            action_result={
                "action": "explore",
                "status": "resolved",
                "explore_type": "observe",
            },
        )
        self.assertIn("Gromm kaşını kaldırır.", output)
        self.assertIn("Yağmur pencereye vurur.", output)
        self.assertNotIn("anlamadın", output)
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "INVENTED_PLAYER_MENTAL_STATE",
        )
        self.assertEqual(self.session.last_narration_safety["handling"], "repaired")

    def test_canonical_assertion_corpus_is_rejected(self):
        cases = (
            ("Can puanın 20'ye çıkar.", "CANONICAL_HP_CONTRADICTION"),
            ("4 puan hasar alırsın.", "CANONICAL_DAMAGE_CONTRADICTION"),
            ("Gromm sana kahve ikram eder.", "UNSUPPORTED_ITEM_TRANSFER"),
            ("Envanterine özel bir iksir eklenir.", "UNSUPPORTED_ITEM_TRANSFER"),
            ("500 altın kazanırsın.", "CANONICAL_REWARD_CONTRADICTION"),
            ("50 deneyim puanı kazanırsın.", "CANONICAL_XP_CONTRADICTION"),
            ("Seviye atlarsın.", "CANONICAL_LEVEL_CONTRADICTION"),
            ("Ellerinde ateş büyüsü belirir.", "CANONICAL_SPELL_CONTRADICTION"),
            ("Yağmur aniden başlar.", "CANONICAL_WEATHER_CHANGE"),
            ("Görev tamamlandı.", "CANONICAL_QUEST_CONTRADICTION"),
        )
        for narration, expected_reason in cases:
            with self.subTest(narration=narration):
                decision = self.decide(narration)
                self.assertTrue(decision["unsafe"], decision)
                self.assertEqual(decision["reason_code"], expected_reason)

    def test_unregistered_persistent_object_is_rejected_but_registered_object_is_allowed(self):
        claim = "Yerdeki sandık açılmış duruyor."
        decision = self.decide(claim)
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(
            decision["reason_code"], "UNREGISTERED_PERSISTENT_OBJECT"
        )

        self.session.world_state["features"].append({
            "location": "tavern",
            "name": "Sandık",
            "description": "Tahta bir sandık",
        })
        registered_decision = self.decide(claim)
        self.assertFalse(registered_decision["unsafe"], registered_decision)

    def test_carried_item_does_not_authorize_a_ground_object_claim(self):
        claim = "Yerdeki kılıç yerde duruyor."
        decision = self.decide(claim)
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(
            decision["reason_code"], "UNREGISTERED_PERSISTENT_OBJECT"
        )

        self.session.world_state["ground_items_by_location"] = {
            "tavern": ["Kılıç"]
        }
        registered_decision = self.decide(claim)
        self.assertFalse(registered_decision["unsafe"], registered_decision)

    def test_location_npc_and_defeat_authority_remain_strict(self):
        self.session.world_state["location"] = "forest"
        self.gromm["location"] = "forest"
        location_decision = self.decide(
            "Taverna'ya varış gerçekleşir.",
            action_result={"action": "explore", "status": "resolved"},
        )
        self.assertEqual(
            location_decision["reason_code"], "CANONICAL_LOCATION_CONTRADICTION"
        )

        self.gromm["combat_status"] = "defeated"
        self.gromm["current_hp"] = 0
        resurrection = self.decide("Gromm ayağa kalkıp yeniden konuşur.")
        self.assertEqual(
            resurrection["reason_code"], "DEFEATED_ENTITY_RESURRECTION"
        )

    def test_named_npc_skill_and_door_contradictions_remain_strict(self):
        unknown_name = self.decide(
            'Halric, "Ben Halric, muhafızım," diye konuşur.'
        )
        self.assertEqual(
            unknown_name["reason_code"], "UNREGISTERED_NAMED_ENTITY"
        )

        failed_check = self.decide(
            "Başarılı olur ve izleri bulursun.",
            action_result={
                "action": "skill_check",
                "status": "resolved",
                "outcome": "failure",
            },
        )
        self.assertEqual(
            failed_check["reason_code"], "SKILL_RESULT_CONTRADICTION"
        )

        failed_door = self.decide(
            "Kapı açılır.",
            player_input="Kapıyı açmaya çalışıyorum.",
            action_result={"action": "skill_check", "outcome": "failure"},
        )
        self.assertEqual(
            failed_door["reason_code"], "DOOR_RESULT_CONTRADICTION"
        )

    def test_combat_target_and_damage_must_match_python_rendering(self):
        result = {
            "action": "attack",
            "status": "resolved",
            "outcome": "hit",
            "target_name": "Goblin",
            "damage": 4,
        }
        canonical = self.session._combat_narration(result)
        self.assertFalse(self.decide(
            canonical,
            player_input="Goblin'e saldırıyorum.",
            action_result=result,
        )["unsafe"])
        for narration in (
            "Kılıcın başka bir düşmana isabet eder.",
            "Goblin 40 hasar alır ve yere düşer.",
        ):
            with self.subTest(narration=narration):
                decision = self.decide(
                    narration,
                    player_input="Goblin'e saldırıyorum.",
                    action_result=result,
                )
                self.assertEqual(
                    decision["reason_code"], "COMBAT_RESULT_CONTRADICTION"
                )

    def test_memory_contradiction_is_replaced_and_reason_is_internal(self):
        self.gromm["memory"] = [
            {
                "speaker": "player",
                "text": "Gromm, benim adım Arven. Kendimi tanıtıyorum.",
            },
        ]
        output = self.finalize_narration(
            'Gromm, gözlerini kadehe çevirir. "Arven dediğin kişiyi duydum. '
            "Sana adını söylemen gerekirdi.\"",
            "Gromm, daha önce sana adımı söylemiş miydim?",
            npc_target=self.gromm,
            action_result={"action": "dialogue", "status": "resolved"},
        )
        self.assertIn("Arven", output)
        self.assertNotIn("söylemen gerekirdi", output)
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "NPC_MEMORY_SUPPORTED_PLAYER_NAME",
        )
        self.assertNotIn("reason_code", output)
        self.assertNotIn("last_narration_safety", self.session.world_state)

    def test_selected_player_name_claim_is_id_bound_and_narrow(self):
        query = "Gromm, daha önce sana adımı söylemiş miydim?"
        supported_claim = [{
            "npc_id": "npc_001",
            "text": "Gromm, benim adım Arven. Kendimi tanıtıyorum.",
        }]
        self.gromm["memory"] = []
        output = self.finalize_narration(
            "Gromm gülümser. 'Evet, Arven; adını daha önce söylemiştin.'",
            query,
            npc_target=self.gromm,
            action_result={"action": "dialogue", "status": "resolved"},
            supported_player_claims=supported_claim,
        )
        self.assertIn("Arven", output)
        self.assertIn("söylemiştin", output)
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "NPC_MEMORY_SUPPORTED_PLAYER_NAME",
        )
        self.assertNotIn("reason_code", output)

        self.gromm["memory"] = [{
            "speaker": "player",
            "text": "Gromm, benim adım Arven. Kendimi tanıtıyorum.",
        }]
        output = self.finalize_narration(
            "Gromm başını hafifçe eğer.",
            query,
            npc_target=self.gromm,
            action_result={"action": "dialogue", "status": "resolved"},
            supported_player_claims=[{
                "npc_id": "npc_001",
                "text": "Gromm, benim adım Mira. Kendimi tanıtıyorum.",
            }],
        )
        self.assertIn("Arven", output)
        self.assertNotIn("Mira", output)
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "NPC_MEMORY_SUPPORTED_PLAYER_NAME",
        )

        unsupported_cases = (
            (
                query,
                [{"npc_id": "npc_099", "text": supported_claim[0]["text"]}],
            ),
            (
                query,
                [{"npc_id": "npc_001", "text": "Gromm remembers Arven's name."}],
            ),
            (
                "Gromm, daha önce nereden geldiğini söylemiş miydin?",
                supported_claim,
            ),
        )
        for player_input, claims in unsupported_cases:
            with self.subTest(player_input=player_input, claims=claims):
                self.gromm["memory"] = []
                output = self.finalize_narration(
                    "Gromm, 'Evet, Arven ve başka sırları da anlattım,' diye yanıt verir.",
                    player_input,
                    npc_target=self.gromm,
                    action_result={"action": "dialogue", "status": "resolved"},
                    supported_player_claims=claims,
                )
                self.assertEqual(
                    self.session.last_narration_safety["reason_code"],
                    "NPC_MEMORY_UNSUPPORTED_CLAIM",
                )
                self.assertNotIn("Arven", output)

    def test_historical_claim_without_a_stable_npc_id_stays_unverified(self):
        self.session.world_state["npcs"] = []
        output = self.finalize_narration(
            "Elara smiles. 'Yes, you told me your name was Mira.'",
            "Elara, daha önce sana adımı söylemiş miydim?",
            npc_target=None,
            action_result={"action": "dialogue", "status": "resolved"},
        )

        self.assertIn("Bu konuşmayı kiminle yaptığını", output)
        self.assertNotIn("Mira", output)
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "NPC_MEMORY_UNVERIFIED_NO_STABLE_ID",
        )
        self.assertEqual(self.session.world_state["npcs"], [])

    def test_safe_sentence_is_preserved_when_one_agency_sentence_is_removed(self):
        output = self.finalize_narration(
            "Gromm kaşını kaldırır. Sen kılıcını savurursun. Yağmur pencereye vurur.",
            "Etrafıma bakıyorum.",
            action_result={"action": "explore", "status": "resolved", "explore_type": "observe"},
        )
        self.assertIn("Gromm kaşını kaldırır.", output)
        self.assertIn("Yağmur pencereye vurur.", output)
        self.assertNotIn("savurursun", output)
        self.assertEqual(self.session.last_narration_safety["handling"], "repaired")
        self.assertEqual(self.session.last_narration_safety["tier"], "tier_2_repair")

    def test_unrepairable_agency_violation_uses_python_fallback_reason(self):
        before = copy.deepcopy(self.session.world_state)
        output = self.finalize_narration(
            "Kılıcını savurursun.",
            "Etrafıma bakıyorum.",
            action_result={"action": "explore", "status": "resolved", "explore_type": "observe"},
        )
        self.assertNotEqual(output, "Kılıcını savurursun.")
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "INVENTED_PLAYER_ACTION",
        )
        self.assertEqual(self.session.world_state, before)

    def test_long_five_paragraph_narration_and_state_are_preserved(self):
        narration = "\n\n".join(
            f"{paragraph}. Gromm sessizce çevreyi gözlemler."
            for paragraph in (
                "Lambaların ışığı masaların üzerinde yumuşak gölgeler bırakır",
                "Pencerede yağmurun düzenli sesi duyulur",
                "Şömine taş duvarın yanında çıtırdar",
                "Uzak masalarda isimsiz müşteriler alçak sesle konuşur",
                "Gromm bardağını silerken başını hafifçe eğer",
            )
        )
        before = copy.deepcopy(self.session.world_state)
        decision = self.decide(narration)
        self.assertFalse(decision["unsafe"], decision)
        self.assertEqual(self.session.world_state, before)

    def test_same_name_npcs_remain_distinct_by_stable_id(self):
        second = dict(self.gromm)
        second.update({"id": "npc_099", "location": "tavern", "memory": []})
        self.session.world_state["npcs"].append(second)
        resolution = self.session.resolve_npc_reference("Gromm")
        self.assertEqual(resolution["status"], "ambiguous")
        self.assertEqual(
            {npc["id"] for npc in resolution["npcs"]},
            {"npc_001", "npc_099"},
        )

    def test_scene_classifier_distinguishes_queries_and_skill_checks(self):
        self.assertEqual(
            self.session._narration_scene_type({"action": "inventory"}),
            "direct_query",
        )
        self.assertEqual(
            self.session._narration_scene_type({"action": "skill_check"}),
            "skill_check",
        )
        self.assertEqual(_scene_type({"action": "inventory"}), "direct_query")
        self.assertEqual(_scene_type({"action": "skill_check"}), "skill_check")

    def test_explicit_name_disclosure_memory_and_unsupported_claim_rejection(self):
        # CASE A: Explicit name disclosure allows NPC to learn player's name
        self.gromm["memory"] = []
        player_intro = "Benim adım Arven."
        safe_reply = 'Gromm başını kaldırır ve "Memnun oldum Arven," der.'

        # Verify safe reply passes claim check
        self.assertIsNone(
            game._unsupported_npc_history_or_relationship_claim(
                safe_reply, self.gromm, player_intro
            )
        )
        # Record into memory
        game.record_npc_interaction(self.gromm, safe_reply, player_intro, self.gromm)
        self.assertTrue(
            any(
                entry.get("speaker") == "player" and "Arven" in entry.get("text", "")
                for entry in self.gromm.get("memory", [])
            )
        )
        # Verify subsequent query remembers Arven
        query_out = self.finalize_narration(
            'Gromm kadehini silerken "Adını bilmiyorum," der.',
            "Gromm, daha önce sana adımı söylemiş miydim?",
            npc_target=self.gromm,
            action_result={"action": "dialogue", "status": "resolved"},
        )
        self.assertIn("Arven", query_out)
        self.assertEqual(
            self.session.last_narration_safety["reason_code"],
            "NPC_MEMORY_SUPPORTED_PLAYER_NAME",
        )

        # CASE B: Unsupported history/relationship claim rejected and NOT recorded
        mem_before = copy.deepcopy(self.gromm.get("memory", []))
        malicious_narration = "Gromm seni yıllardır tanıyor ve eski maceralarınızı hatırlıyor."

        decision_b = self.decide(
            malicious_narration,
            player_input=player_intro,
            npc_target=self.gromm,
        )
        self.assertTrue(decision_b["unsafe"])
        self.assertEqual(
            decision_b["reason_code"],
            "UNSUPPORTED_CAMPAIGN_HISTORY_CLAIM",
        )

        # Verify record_npc_interaction refuses to store malicious claim
        game.record_npc_interaction(
            self.gromm, malicious_narration, player_intro, self.gromm
        )
        self.assertEqual(self.gromm.get("memory", []), mem_before)

        # Threat Case: Name disclosure + longstanding acquaintance / past adventures claim
        threat_intro = "Gromm, benim adım Arven. Kendimi tanıtıyorum."
        threat_narration = "Gromm seni yıllardır tanıyormuş gibi gülümser ve eski maceralarınızdan söz eder."

        decision_threat = self.decide(
            threat_narration,
            player_input=threat_intro,
            npc_target=self.gromm,
        )
        self.assertTrue(decision_threat["unsafe"])
        self.assertEqual(
            decision_threat["reason_code"],
            "UNSUPPORTED_CAMPAIGN_HISTORY_CLAIM",
        )
        game.record_npc_interaction(
            self.gromm, threat_narration, threat_intro, self.gromm
        )
        self.assertEqual(self.gromm.get("memory", []), mem_before)


if __name__ == "__main__":
    unittest.main()
