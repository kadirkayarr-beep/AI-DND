"""Representative V1 contracts; fixtures are not live-model acceptance evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
import httpx
import interaction_adventure as adventure
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures


from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
def npc(identity="gromm", name="Gromm", location="here"):
    return {
        "id": identity, "name": name, "role": "yerel işçi", "location": location,
        "personality": "temkinli", "appearance": "tozlu giysiler",
        "relationship": "neutral", "knowledge": ["HIDDEN TRUTH: the mayor is guilty"],
        "memory": [], "aliases": [name], "current_hp": 10, "max_hp": 10,
        "armor_class": 10, "status": "active",
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
    }


def session():
    s = game.GameSession(seed=9)
    s.world_state.update(location="here",
                         locations={"here": {"id": "here", "name": "Burada", "type": "building"},
                                    "there": {"id": "there", "name": "Dışarı", "type": "building"}},
                         npcs=[npc(), npc("other", "Mira"), npc("remote", "Uzak", "there")])
    s.world_state["flags"]["turn_index"] = 1
    s.ensure_campaign_clock()
    return s


def envelope(operation, quote, **values):
    return {**adventure.Envelope(operation=operation, quote=quote).model_dump(), **values}


def candidate(kind="inquiry", target="other"):
    return {"kind": kind, "impact": "local", "npc_id": "gromm", "location_id": "here",
            "routes": [{"kind": "talk", "target": target}]}


class InteractionContracts(unittest.TestCase):
    def test_compound_source_spans_and_conditions_not_keyword_hacks(self):
        texts = [
            "Vardiya değişince bekleyeyim, arkadan gizlice gireyim, kayıt odasını bulayım; yakalanırsam tüccarın adamı olduğumu söyleyeyim.",
            "Kapı açılınca, sessizce geçeyim; izleri takip edeyim; sorarlarsa yoldan geldiğimi söyleyeyim.",
            "Önce bir dakika bekliyorum, sonra Mira ile konuşuyorum.",
            "Biraz bekleyeceğim; ardından depoyu inceleyeceğim.",
            "Biraz bekleyeyim ve içeriden ses gelirse kapıya yaklaşayım.",
        ]
        for text in texts:
            with self.subTest(text=text):
                proposal = adventure.compound_plan(text)
                self.assertIsNotNone(proposal)
                self.assertEqual(adventure.hint(text), "plan")
                result = adventure.resolve(self.s, text, proposal)
                self.assertEqual(result["status"], "recorded")
                plan = self.w[adventure.KEY]["plan"]
                self.assertEqual(plan["cursor"], 0)
                for index, step in enumerate(plan["steps"]):
                    self.assertIn(step["quote"], text)
                    self.assertIn(step["precondition"], text)
                    self.assertEqual(step["depends_on"], index - 1 if index else None)
        proposal = adventure.compound_plan(texts[0])
        self.assertEqual(len(proposal["steps"]), 4)
        self.assertEqual(proposal["steps"][0]["precondition"], "Vardiya değişince")
        self.assertEqual(proposal["steps"][-1]["precondition"], "yakalanırsam")

    def test_single_search_noun_lists_and_quoted_actions_are_not_plans(self):
        for text in ["tüccar bul", "Tüccarı bulayım.", "Kılıcım, kalkanım; çantam.",
                     'Mira "bekleyeyim, gireyim" dedi.',
                     'Şunu söyleyeyim: "gireyim, bulayım".']:
            with self.subTest(text=text):
                self.assertIsNone(adventure.compound_plan(text))
        self.assertTrue(game.living_world.is_merchant_search("tüccar bul"))
        quote = 'Biraz bekleyeyim; "tüccar, kayıt odası" diyeyim.'
        self.assertEqual(len(adventure.compound_plan(quote)["steps"]), 2)

    def test_plan_rejections_have_distinct_reasons_and_never_commit(self):
        text = "Biraz bekleyeyim; kapıyı açayım."
        cases = [
            ([], "plan_empty_steps"),
            ([{"quote": "Kapıyı aç"}], "plan_ungrounded_step"),
            ([{"quote": "Biraz bekleyeyim", "precondition": "nöbet bitince"}],
             "plan_ungrounded_condition"),
            ([{"quote": "Biraz bekleyeyim", "depends_on": 0}],
             "plan_invalid_dependency"),
        ]
        before = copy.deepcopy(self.w)
        for steps, reason in cases:
            result = adventure.resolve(self.s, text, envelope("plan", text, steps=steps))
            self.assertEqual(result["reason_code"], reason)
            self.assertEqual(self.w, before)
        oversized = "; ".join(["Biraz bekleyeyim"] * 7)
        result = adventure.resolve(self.s, oversized, adventure.compound_plan(oversized))
        self.assertEqual(result["reason_code"], "invalid_interaction_proposal")
        self.assertEqual(self.w, before)

    def test_compound_spell_plan_does_not_cast_or_bypass_combat_owner(self):
        self.s.character.update(name="Denetçi", current_hp=10, max_hp=10)
        self.w["player_combat_status"] = "active"
        text = "Magic Missile büyüsünü kullanayım; kenara çekileyim."
        with patch("spell_scope.natural_command", side_effect=AssertionError("not a cast")), \
             patch("bounded_encounter.resolve_command", side_effect=AssertionError("not an action")), \
             patch("game.ollama.chat", return_value={"message": {"content": "{}"}}):
            result = self.s.run_player_turn(text)
        self.assertEqual(result["action_result"]["operation"], "plan")
        self.assertEqual(self.w[adventure.KEY]["plan"]["cursor"], 0)
        self.w["combat"]["active"] = True
        with patch("spell_scope.natural_command", side_effect=ValueError("locked owner")):
            with self.assertRaisesRegex(ValueError, "locked owner"):
                self.s.run_player_turn(text)

    def setUp(self):
        self.s = session()
        self.w = self.s.world_state
        self.n = self.w["npcs"][0]

    def resolve(self, operation, quote, **fields):
        return adventure.resolve(self.s, quote, envelope(operation, quote, **fields), self.n)

    def test_real_model_contract_requires_interaction_and_exact_quote_fields(self):
        schema = adventure.intent_schema(game.INTENT_SCHEMA)
        self.assertIn("interaction", schema["required"])
        self.assertIn("quote", schema["properties"]["interaction"]["required"])
        self.assertEqual(schema["properties"]["interaction"]["additionalProperties"], False)
        with patch("game.ollama.chat", return_value={"message": {"content": "{}"}}) as model:
            self.s.parse_player_intent("Hedefim araştırmak",
                interaction_context=adventure.context(self.w, self.n), operation_hint="goal")
        returned_schema = model.call_args.kwargs["format"]
        self.assertEqual(returned_schema["properties"]["interaction"]["properties"]["operation"]["enum"], ["goal"])
        with patch("game.ollama.chat", return_value={"message": {"content": "{}"}}) as model:
            self.s.parse_player_intent("Planım: bekle", interaction_context=adventure.context(self.w, self.n),
                                       operation_hint="plan")
        schema = model.call_args.kwargs["format"]["properties"]["interaction"]
        self.assertIn("steps", schema["required"])
        self.assertEqual(schema["properties"]["steps"]["minItems"], 1)

    def goal(self, routes=()):
        quote = ("Hedefim Mira ile konuşmak veya Dışarı ziyaret etmek" if routes
                 else "Hedefim bu sorunun peşine düşmek")
        self.resolve("goal", quote, routes=list(routes))
        return self.w[adventure.KEY]["threads"][0]

    def test_owned_item_counteroffer_rejects_gold_without_inventory_transaction(self):
        self.n["inventory"] = [{"item_id": "sword-1", "name": "Kılıç", "weapon_id": "longsword"}]
        before = copy.deepcopy((self.w["inventory"], self.n["inventory"]))
        result = self.resolve("negotiate", "100 GP istemiyorum, Kılıç istiyorum.",
                              requested_item="Kılıç", rejected_consideration="100 GP")
        self.assertTrue(result["item_validation"]["owned"])
        self.assertFalse(result["item_validation"]["transfer_possible"])
        self.assertFalse(result["npc_consent"])
        self.assertEqual((self.w["inventory"], self.n["inventory"]), before)
        self.assertEqual(result["rejected_consideration"], "100 GP")

    def test_nonowned_and_equipment_defaults_cannot_grant_ownership(self):
        self.n["equipment"] = {"main_hand": "longsword", "off_hand": None}
        result = self.resolve("negotiate", "Bana longsword ver.", requested_item="longsword")
        self.assertEqual(result["item_validation"]["reason"], "not_owned")
        self.assertNotIn("longsword", self.w["inventory"])

    def test_personal_goal_is_intent_not_corruption_truth(self):
        result = self.resolve("goal", "Başkanın yolsuz olup olmadığını öğrenmek istiyorum.")
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(self.w[adventure.KEY]["threads"][0]["origin"], "player")
        self.assertEqual(self.w["quests"], [])
        self.assertEqual(self.w["player_knowledge"], [])

    def test_alternate_route_progresses_after_missed_route_without_auto_success(self):
        thread = self.goal([{"kind": "visit", "target": "there"},
                            {"kind": "talk", "target": "other"}])
        before = copy.deepcopy(self.w)
        adventure.consume(self.s, {"action": "check", "success": False}, before)
        self.assertEqual(thread["status"], "active")
        adventure.consume(self.s, {"action": "dialogue", "npc_id": "other", "success": True}, before)
        current = self.w[adventure.KEY]["threads"][0]
        self.assertEqual(current["status"], "succeeded")
        self.assertTrue(current["objectives"][0]["evidence_id"])

    def test_reframing_requires_verified_evidence_and_keeps_alternative_routes(self):
        thread = self.goal([{"kind": "talk", "target": "other"}])
        bad = self.resolve("reframe", "Hedefi değiştiriyorum", thread_id=thread["thread_id"],
                           evidence_id="invented")
        self.assertEqual(bad["status"], "no_effect")
        self.w["player_knowledge"].append({"fact_id": "fact:1", "authority": "python_engine"})
        good = self.resolve("reframe", "Hedefi değiştiriyorum: Dışarı ziyaret etmek", thread_id=thread["thread_id"],
                            evidence_id="fact:1", routes=[{"kind": "visit", "target": "there"}])
        current = self.w[adventure.KEY]["threads"][0]
        self.assertEqual(good["status"], "reframed")
        self.assertEqual(len(current["objectives"][0]["routes"]), 2)

    def test_voluntary_betrayal_changes_local_allegiance_and_breaks_bound_promise(self):
        thread = self.goal()
        self.resolve("promise", "Söz veriyorum yardım edeceğim", thread_id=thread["thread_id"])
        self.resolve("betray", "Mira ile birlikte hareket edeceğim", thread_id=thread["thread_id"],
                     side_id="other")
        current = self.w[adventure.KEY]
        self.assertEqual(current["threads"][0]["allegiance_id"], "other")
        self.assertEqual(current["commitments"][0]["status"], "broken")
        self.assertNotIn("factions", self.w)

    def test_unmentioned_side_cannot_be_chosen_by_model(self):
        thread = self.goal()
        result = self.resolve("switch_side", "Taraf değiştirmek istiyorum",
                              thread_id=thread["thread_id"], side_id="other")
        self.assertEqual(result["status"], "no_effect")
        self.assertIsNone(self.w[adventure.KEY]["threads"][0]["allegiance_id"])

    def test_private_and_public_speech_have_explicit_nontelepathic_listeners(self):
        self.resolve("promise", "Gromm'a fısıldıyorum: söz veriyorum.", privacy="public")
        state = self.w[adventure.KEY]
        self.assertEqual(set(state["perspectives"]), {"gromm"})
        self.assertTrue(state["events"][-1]["private"])
        self.resolve("promise", "Herkese yüksek sesle söz veriyorum.", privacy="public")
        self.assertEqual(set(self.w[adventure.KEY]["perspectives"]), {"gromm", "other"})
        self.assertNotIn("remote", self.w[adventure.KEY]["perspectives"])

    def test_addressee_filter_excludes_hidden_truth_unrelated_beliefs_and_secrets(self):
        state = adventure.State().model_dump()
        state["perspectives"] = {
            "gromm": [adventure.PerspectiveEntry(entry_id="secret", kind="belief",
                text="SECRET", source_id="local:profile", secret=True).model_dump()],
            "other": [adventure.PerspectiveEntry(entry_id="other-belief", kind="belief",
                text="OTHER SECRET", source_id="local:profile").model_dump()],
        }
        self.w[adventure.KEY] = state
        content = json.dumps(adventure.context(self.w, self.n))
        self.assertNotIn("SECRET", content)
        self.assertNotIn("mayor is guilty", content)
        self.assertEqual(adventure.perspective(self.w, self.n)["npc_id"], "gromm")
        self.resolve("goal", "Hedefim özel bir sırrı araştırmak")
        own = adventure.context(self.w, self.n)
        unrelated = json.dumps(adventure.context(self.w, self.w["npcs"][1]), ensure_ascii=False)
        self.assertNotIn("özel bir sırrı", unrelated)
        self.assertNotIn("objectives", own["threads"][0])
        self.assertNotIn("status", own["threads"][0])

    def test_belief_lie_and_ignorance_never_rewrite_truth(self):
        state = adventure.State().model_dump()
        state["perspectives"]["gromm"] = [
            adventure.PerspectiveEntry(entry_id="belief", kind="belief",
                text="Başkanın dürüst olduğunu sanıyorum.", source_id="profile:1").model_dump(),
            adventure.PerspectiveEntry(entry_id="lie", kind="lie",
                text="Oraya hiç gitmedim.", source_id="profile:2").model_dump(),
        ]
        self.w[adventure.KEY] = state
        belief = self.resolve("information", "Ne biliyorsun?", evidence_id="belief")
        self.assertIn("Bana kalırsa", belief["direct_response"])
        lie = self.resolve("information", "Oraya gittin mi?", evidence_id="lie")
        self.assertIn("Oraya hiç gitmedim", lie["direct_response"])
        unknown = self.resolve("information", "Bu sembolü biliyor musun?")
        self.assertTrue(adventure.safe_narration(unknown["direct_response"]))
        self.assertEqual(self.w["player_knowledge"], [])

    def test_social_proposal_cannot_set_roll_consent_or_impossible_outcome(self):
        raw = envelope("negotiate", "Her şeyi bana ver.")
        raw.update(roll=20, npc_consent=True)
        before = copy.deepcopy(self.w)
        result = adventure.resolve(self.s, raw["quote"], raw, self.n)
        self.assertEqual(result["status"], "proposal_rejected")
        self.assertEqual(self.w, before)
        self.assertFalse(self.resolve("request", "Her şeyi bana ver.")["npc_consent"])
        result = {"operation": "negotiate", "npc_consent": False}
        self.assertFalse(adventure.outcome_consistent(result, "Gromm teklifini kabul ediyor."))
        self.assertFalse(adventure.outcome_consistent(result, "Kılıç artık senin."))
        self.assertFalse(adventure.outcome_consistent({"operation": "goal"}, "Hedef tamamlandı."))
        self.assertFalse(adventure.outcome_consistent({"operation": "plan"}, "Kayıt odasına giriyorsun."))
        self.assertTrue(adventure.outcome_consistent(result, "Gromm teklifini tartıyor; henüz bir şey el değiştirmedi."))

    def test_model_completion_state_and_ungrounded_intent_fail_closed(self):
        thread = self.goal()
        before = copy.deepcopy(self.w)
        forged = envelope("goal", "Tamamlandı")
        forged["status"] = "succeeded"
        adventure.resolve(self.s, forged["quote"], forged, self.n)
        adventure.resolve(self.s, "Selam", envelope("goal", "Benim uydurduğum hedef"), self.n)
        self.assertEqual(self.w, before)
        self.assertEqual(thread["status"], "active")

    def test_plan_is_bounded_and_returns_control_without_executing_steps(self):
        quote = "Önce dışarı gidiyorum, sonra Mira ile konuşuyorum."
        result = self.resolve("plan", quote, steps=[
            {"quote": "dışarı gidiyorum", "depends_on": None, "precondition": ""},
            {"quote": "Mira ile konuşuyorum", "depends_on": 0, "precondition": ""}])
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(self.w["location"], "here")
        self.resolve("continue_plan", "Plana devam")
        self.assertEqual(self.w[adventure.KEY]["plan"]["cursor"], 0)
        before = copy.deepcopy(self.w)
        adventure.consume(self.s, {"action": "dialogue", "status": "resolved", "success": True},
                          before, "dışarı gidiyorum")
        self.assertEqual(self.w[adventure.KEY]["plan"]["cursor"], 1)
        self.w["combat"]["active"] = True
        adventure.consume(self.s, {"action": "attack"}, before)
        self.assertEqual(self.w[adventure.KEY]["plan"]["status"], "paused")
        self.w["combat"]["active"] = False
        self.w[adventure.KEY]["plan"]["steps"][1]["precondition"] = "Tehlike geçince"
        adventure.consume(self.s, {"action": "dialogue", "status": "resolved", "success": True},
                          copy.deepcopy(self.w), "Mira ile konuşuyorum")
        self.assertEqual(self.w[adventure.KEY]["plan"]["cursor"], 1)
        self.assertEqual(self.w[adventure.KEY]["plan"]["status"], "paused")
        malformed = copy.deepcopy(self.w[adventure.KEY])
        malformed["plan"]["cursor"] = len(malformed["plan"]["steps"])
        with self.assertRaises(ValueError):
            adventure.validate(malformed, self.w)

    def test_cyclic_or_unstated_plan_steps_are_rejected(self):
        result = self.resolve("plan", "Bir plan düşünüyorum",
                              steps=[{"quote": "Kralı öldür", "depends_on": 0}])
        self.assertEqual(result["status"], "proposal_rejected")
        self.assertNotIn(adventure.KEY, self.w)

    def test_recording_a_single_step_plan_does_not_count_as_executing_it(self):
        quote = "Planım: Mira ile konuşmak."
        result = self.resolve("plan", quote, steps=[{"quote": quote}])
        adventure.consume(self.s, result, copy.deepcopy(self.w), quote)
        self.assertEqual(self.w[adventure.KEY]["plan"]["cursor"], 0)
        self.assertEqual(self.w[adventure.KEY]["plan"]["status"], "awaiting_confirmation")

    def test_time_deadline_occurs_once_and_restart_reads_do_not_advance_clock(self):
        thread = self.goal()
        thread["deadline"] = 60
        before = copy.deepcopy(self.w)
        self.w["campaign_time"]["elapsed_seconds"] = 60
        adventure.consume(self.s, {"action": "wait"}, before)
        current = copy.deepcopy(self.w)
        adventure.consume(self.s, {"action": "wait"}, before)
        adventure.public(self.w)
        adventure.validate(self.w[adventure.KEY], self.w)
        self.assertEqual(self.w, current)
        self.assertEqual(self.w[adventure.KEY]["threads"][0]["status"], "expired")

    def test_generation_selects_one_same_call_candidate_and_respects_novelty(self):
        self.resolve("generate", "İş arıyorum", candidates=[
            {**candidate(), "location_id": "there"}, candidate()])
        self.assertEqual(len(self.w[adventure.KEY]["threads"]), 1)
        self.w["flags"]["turn_index"] += 6
        before_count = len(self.w[adventure.KEY]["threads"])
        result = self.resolve("generate", "Bir iş arıyorum", candidates=[candidate()])
        self.assertEqual(result["status"], "no_effect")
        self.assertEqual(len(self.w[adventure.KEY]["threads"]), before_count)

    def test_high_impact_and_lore_actor_generation_are_rejected(self):
        result = self.resolve("generate", "İş arıyorum",
                              candidates=[{**candidate(), "impact": "regional"}])
        self.assertEqual(result["status"], "no_effect")
        self.assertEqual(self.w[adventure.KEY]["threads"], [])
        self.n["reality_layer"] = "CANONICAL_SOURCE"
        self.assertEqual(self.resolve("generate", "Bir iş arıyorum",
                                     candidates=[candidate()])["status"], "no_effect")
        self.n["reality_layer"] = "PROCEDURAL_LOCAL_FICTION"
        self.assertEqual(self.resolve("generate", "İş arıyorum",
            candidates=[candidate(target="remote")])["status"], "no_effect")
        self.assertEqual(self.resolve("generate", "İş arıyorum",
            candidates=[{**candidate(), "routes": [{"kind": "defeat", "target": "other"}]}])["status"], "no_effect")

    def test_optional_only_objectives_do_not_succeed_automatically(self):
        thread = self.goal()
        thread["objectives"][0]["optional"] = True
        adventure.consume(self.s, {"action": "query"}, copy.deepcopy(self.w))
        self.assertEqual(self.w[adventure.KEY]["threads"][0]["status"], "active")

    def test_callback_is_local_persisted_selective_and_cooldown_bound(self):
        self.resolve("promise", "Söz veriyorum")
        self.w["flags"]["turn_index"] = 8
        beat = adventure.initiative_beat(self.w)
        self.assertEqual(beat["npc_id"], "gromm")
        self.assertIsNone(adventure.initiative_beat(self.w))
        self.w["location"] = "there"
        self.w["flags"]["turn_index"] = 20
        self.assertIsNone(adventure.initiative_beat(self.w))

    def test_present_malformed_save_extension_rejects_and_absent_is_read_only(self):
        self.assertEqual(adventure.public(self.w)["threads"], [])
        self.assertNotIn(adventure.KEY, self.w)
        self.w[adventure.KEY] = {"version": 99}
        with self.assertRaises(ValueError):
            adventure.validate(self.w[adventure.KEY], self.w)
        with self.assertRaises(ValueError):
            adventure.validate(None, self.w)

    def test_separate_sessions_do_not_share_goals_beliefs_or_commitments(self):
        other = session()
        before = copy.deepcopy(other.world_state)
        self.goal()
        self.resolve("promise", "Söz veriyorum")
        self.assertEqual(other.world_state, before)
        self.assertEqual(adventure.public(other.world_state)["threads"], [])


class InteractionApiContracts(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def prepare(self):
        campaign = await self.create_campaign()
        record = self.manager.get(campaign["session_id"])
        s = record.game_session
        s.world_state["locations"]["here"] = {"id": "here", "name": "Yerel oda", "type": "building",
                                            "reality_layer": "PROCEDURAL_LOCAL_FICTION"}
        s.world_state["location"] = "here"
        s.ensure_campaign_clock()
        s.world_state["npcs"] = [npc(location=s.world_state["location"]),
                                 npc("other", "Mira", s.world_state["location"])]
        self.manager.save_campaign(campaign["campaign_id"])
        return campaign, record

    async def post(self, campaign, quote, packet, *, action_id=None, narration=None):
        responses = [{"message": {"content": json.dumps({"intent": "dialogue", "interaction": packet})}}]
        if narration is not None:
            responses.append({"message": {"content": json.dumps(narration)}})
        with patch("game.ollama.chat", side_effect=responses) as model:
            response = await self.http.post(
                f"/api/game/sessions/{campaign['session_id']}/turn",
                json={"message": quote, "target_id": "gromm",
                      "action_id": action_id or str(uuid4())})
        return response, model

    async def test_optative_plan_http_preserves_world_rng_replay_and_resume(self):
        a, record = await self.prepare()
        text = "Vardiya değişince bekleyeyim, arkadan gizlice gireyim, kayıt odasını bulayım; yakalanırsam tüccarın adamı olduğumu söyleyeyim."
        s = record.game_session
        world = copy.deepcopy(s.world_state)
        rng = s.rng.getstate()
        action_id = str(uuid4())
        response, model = await self.post(a, text, envelope("none", text), action_id=action_id)
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()["state"]["adventure"]["plan"]
        self.assertEqual(len(plan["steps"]), 4)
        self.assertEqual(plan["cursor"], 0)
        self.assertEqual(plan["status"], "paused")
        self.assertLessEqual(model.call_count, 1)
        self.assertEqual(s.rng.getstate(), rng)
        for key in set(world) | set(s.world_state):
            if key not in {adventure.KEY, "flags"}:
                self.assertEqual(s.world_state.get(key), world.get(key), key)
        committed = copy.deepcopy(s.world_state)
        with patch("game.ollama.chat") as replay_model:
            replay = await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",
                json={"message": text, "target_id": "gromm", "action_id": action_id})
        self.assertEqual(replay.json(), response.json())
        replay_model.assert_not_called()
        self.assertEqual(s.world_state, committed)
        resumed = await self.http.post(f"/api/game/campaigns/{a['campaign_id']}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"]["adventure"]["plan"], plan)

    async def test_compound_plan_failed_save_rolls_back_and_other_session_is_unchanged(self):
        a, record = await self.prepare()
        _, other = await self.prepare()
        before = copy.deepcopy(record.game_session.world_state)
        isolated = copy.deepcopy(other.game_session.world_state)
        rng = record.game_session.rng.getstate()
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("save failed")):
            response, model = await self.post(a, "Biraz bekleyeyim; gizlice geçeyim.",
                                              envelope("none", ""))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(record.game_session.world_state, before)
        self.assertEqual(record.game_session.rng.getstate(), rng)
        self.assertEqual(other.game_session.world_state, isolated)
        self.assertLessEqual(model.call_count, 1)

    async def test_goal_promise_receipt_replay_conflict_restart_and_campaign_isolation(self):
        a, record = await self.prepare()
        b, other = await self.prepare()
        other_before = copy.deepcopy(other.game_session.serialize_game_state())
        quote = "Hedefim başkanın yolsuz olup olmadığını öğrenmek"
        identity = str(uuid4())
        first, model = await self.post(a, quote, envelope("goal", quote), action_id=identity,
                                      narration={"narration": "Bu sorunun peşine düşmeye karar veriyorsun.",
                                                 "world_updates": {}, "lore_claims": []})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(model.call_count, 2)
        saved = copy.deepcopy(record.game_session.serialize_game_state())
        with patch("game.ollama.chat", side_effect=AssertionError("Receipt replay cannot call Qwen")):
            replay = await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",
                json={"message": quote, "target_id": "gromm", "action_id": identity})
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(record.game_session.serialize_game_state(), saved)
        conflict = await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",
                json={"message": quote + " başka", "target_id": "gromm", "action_id": identity})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(other.game_session.serialize_game_state(), other_before)
        promise = "Gromm'a söz veriyorum yardım edeceğim"
        response, calls = await self.post(a, promise, envelope("promise", promise))
        self.assertEqual(response.status_code, 200, response.text)
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        sid, restored, *_ = fresh.resume_campaign(a["campaign_id"])
        self.assertEqual(adventure.public(restored.game_session.world_state),
                         response.json()["state"]["adventure"])
        self.assertEqual(len(restored.game_session.world_state[adventure.KEY]["commitments"]), 1)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(
            app=create_app(session_manager=fresh, ollama_adapter=self.app.state.ollama_adapter, authenticator=FixedAuthenticator(TEST_PLAYER))),
            base_url="http://testserver")
        try:
            with patch("game.ollama.chat", side_effect=AssertionError("Restart replay cannot call Qwen")):
                restarted = await client.post(f"/api/game/sessions/{sid}/turn",
                    json={"message": quote, "target_id": "gromm", "action_id": identity})
            # Runtime session identity is replaced by the existing replay owner;
            # the saved gameplay response is otherwise byte-for-byte identical.
            self.assertEqual(restarted.json(), {**first.json(), "session_id": sid})
        finally:
            await client.aclose()

    async def test_generation_replay_never_creates_another_thread_or_consumes_rng(self):
        a, record = await self.prepare()
        quote, identity = "İş arıyorum", str(uuid4())
        here = record.game_session.world_state["location"]
        proposal = {**candidate(), "location_id": here}
        result, calls = await self.post(a, quote, envelope("generate", quote, candidates=[proposal]),
            action_id=identity)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(result.json()["state"]["adventure"]["threads"]), 1)
        before = copy.deepcopy((record.game_session.serialize_game_state(),
                                record.game_session.rng.getstate()))
        with patch("game.ollama.chat", side_effect=AssertionError("Duplicate generation")):
            replay = await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",
                json={"message": quote, "target_id": "gromm", "action_id": identity})
        self.assertEqual(replay.json(), result.json())
        self.assertEqual((record.game_session.serialize_game_state(),
                          record.game_session.rng.getstate()), before)

    async def test_invalid_candidates_and_meta_narration_never_retry_model(self):
        a, record = await self.prepare()
        response, model = await self.post(a, "İş arıyorum",
            envelope("generate", "İş arıyorum", candidates=[{**candidate(), "npc_id": "absent"}]))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.call_count, 1)
        quote = "Hedefim bu gizemi çözmek"
        response, model = await self.post(a, quote, envelope("goal", quote),
            narration={"narration": "The backend cannot access the canonical database.",
                       "world_updates": {}, "lore_claims": []})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.call_count, 2)
        self.assertTrue(adventure.safe_narration(response.json()["narration"]))
        self.assertNotIn("backend", response.json()["narration"])

    async def test_narration_cannot_complete_thread_or_become_canonical_npc_memory(self):
        a, record = await self.prepare()
        quote = "Hedefim bunu araştırmak"
        response, model = await self.post(a, quote, envelope("goal", quote),
            narration={"narration": "Her şeyi çözdün; görev tamamlandı ve kılıç artık senin.",
                       "world_updates": {"events": ["all quests succeeded"]}, "lore_claims": []})
        self.assertEqual(response.status_code, 200, response.text)
        state = record.game_session.world_state
        self.assertEqual(state[adventure.KEY]["threads"][0]["status"], "active")
        self.assertEqual(state["npcs"][0]["memory"], [])
        self.assertTrue(adventure.safe_narration(response.json()["narration"]))
        self.assertEqual(model.call_count, 2)

    async def test_save_failure_rolls_back_new_goals_events_rng_and_receipt(self):
        a, record = await self.prepare()
        before = copy.deepcopy((record.game_session.serialize_game_state(),
                                record.game_session.rng.getstate(), record.journal))
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("disk failure")):
            quote = "Hedefim bu konuyu araştırmak"
            response, calls = await self.post(a, quote, envelope("goal", quote))
        self.assertEqual(response.status_code, 500)
        self.assertEqual((record.game_session.serialize_game_state(),
                          record.game_session.rng.getstate(), record.journal), before)

    async def test_multi_step_wait_plan_does_not_execute_time_owner_before_confirmation(self):
        a, record = await self.prepare()
        quote = "Önce bir dakika bekliyorum, sonra Mira ile konuşuyorum."
        before_time = copy.deepcopy(record.game_session.world_state["campaign_time"])
        response, model = await self.post(a, quote, envelope("plan", quote, steps=[
            {"quote": "bir dakika bekliyorum", "depends_on": None, "precondition": ""},
            {"quote": "Mira ile konuşuyorum", "depends_on": 0, "precondition": ""},
        ]))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNotNone(response.json()["state"]["adventure"]["plan"])
        self.assertEqual(record.game_session.world_state["campaign_time"], before_time)
        self.assertEqual(record.game_session.world_state[adventure.KEY]["plan"]["cursor"], 0)
        # A records-room noun must not let the scene owner's ordinary "look"
        # result swallow the complete wait/stealth/search plan.
        quote = "Önce nöbet değişene kadar bekliyorum, sonra arka girişten gizlice giriyorum, sonra kayıt odasını arıyorum."
        response, model = await self.post(a, quote, envelope("plan", quote, steps=[
            {"quote": "nöbet değişene kadar bekliyorum", "depends_on": None, "precondition": ""},
            {"quote": "arka girişten gizlice giriyorum", "depends_on": 0, "precondition": ""},
            {"quote": "kayıt odasını arıyorum", "depends_on": 1, "precondition": ""},
        ]))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["state"]["adventure"]["plan"]["steps"]), 3)
        self.assertEqual(record.game_session.world_state["campaign_time"], before_time)
        self.assertEqual(record.game_session.world_state[adventure.KEY]["plan"]["cursor"], 0)
