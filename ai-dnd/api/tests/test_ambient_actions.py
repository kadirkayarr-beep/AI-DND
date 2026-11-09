"""Dilim 3, Task 8: one rule says whether the scene's event can be joined.

The scene view (`scene.ambient_event.actionable`) and the click route read the same rule (`ambient_actions.actionable`);
a refused click says why in Turkish and changes nothing; a joined event is undone like a typed turn (V5), and a refused
click keeps the last turn's undo. Driven through the real HTTP routes on the owner's BLUE fixture (test_owner_play1)."""
from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import living_world
from api.main import _state_fingerprint
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_lr00_grounded_human import CITY
from api.tests.test_owner_play1 import OwnerPlayBase

EVENT = "İki esnaf kısa bir tartışmaya tutuşur; biri avucunu tezgâha vurur."


class AmbientActionsTests(OwnerPlayBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.base_world = copy.deepcopy(self.world)
        self.base_journal = copy.deepcopy(self.record.journal)

    @property
    def record(self):
        return self.manager.get(self.session_id)

    @property
    def live_session(self):
        return self.record.game_session

    def scene(self, world=None):
        world = self.world if world is None else world
        return world["scene_state"]["scenes"][CITY]

    def stage(self, *, event_type="BLUE"):
        turn = self.world["flags"].setdefault("turn_index", 0)
        self.instance = str(uuid.uuid4())
        scene = living_world.ensure_scene_record(self.world, CITY, turn)
        scene["materialized"] = True
        scene.pop("ambient_event", None)                          # an earlier turn's event goes with its referent
        scene["referents"].clear()
        scene["last_beat"] = EVENT
        event = {"event_id": "city_small_argument", "instance_id": self.instance, "variation_id": "v1",
                 "event_type": event_type, "repeat_group": "conversation", "count": 1}
        if event_type == "BLUE":
            referent = living_world.create_scene_referent(
                self.world, CITY, turn, description=EVENT, aliases=["esnaf"], event_instance_id=self.instance,
            )
            event["referent_id"] = referent["id"]
        scene["ambient_event"] = event

    async def state(self):
        response = await self.http.get(f"/api/game/sessions/{self.session_id}/state")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def state_with_event(self, *, turns_later=0, fight=False, event_type="BLUE", promoted=False,
                               promotion_fails=False, keep_turn=False):
        if not keep_turn:
            self.world.clear()
            self.world.update(copy.deepcopy(self.base_world))
            self.record.journal = copy.deepcopy(self.base_journal)
        self.stage(event_type=event_type)
        self.world["flags"]["turn_index"] += turns_later
        if keep_turn:
            # The event came into the scene during the last turn: that turn's undo still stands.
            self.record.undo_checkpoint["post_turn_fingerprint"] = _state_fingerprint(self.live_session)
        if promoted:
            self.assertEqual((await self.click("interact"))["result"]["status"], "APPLIED")
        if fight:
            npc = self.live_session.create_npc_from_ai({"name": "Haydut", "role": "Bandit", "location": CITY})
            npc.update(current_hp=40, max_hp=40, hostile=True, distance_ft=5, armor_class=12)
            self.live_session.start_combat(npc)
            self.assertTrue(self.world["combat"].get("active"))
        if promotion_fails:
            self.enterContext(patch("game._promote_scene_referent", return_value=None))
        return await self.state()

    async def click(self, action, *, action_id=None):
        url = f"/api/game/sessions/{self.session_id}/ambient-events/{self.instance}/actions"
        response = await self.http.post(url, json={"action_id": action_id or str(uuid.uuid4()), "action": action})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def undo(self, *, target_action_id):
        return await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                    json={"action_id": str(uuid.uuid4()), "target_action_id": target_action_id})

    async def say(self, message):
        self.client.message = message
        action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": message, "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        return {"action_id": action_id, **response.json()}

    def fingerprint(self):
        return (_state_fingerprint(self.live_session), copy.deepcopy(self.record.journal), list(self.live_session.messages))

    def observed_in(self, record, *, live=True):
        session = record.game_session
        world = session.world_state
        scene = world["scene_state"]["scenes"][CITY]
        return {
            "npcs": sorted(npc["id"] for npc in world.get("npcs", []) if isinstance(npc, dict)),
            "referents": [(ref.get("id"), ref.get("lifecycle"), ref.get("promoted_npc_id"))
                          for ref in scene.get("referents", [])],
            "talk": {key: world["flags"].get(key) for key in ("active_npc_id", "active_npc_until_turn", "last_npc_id")},
            "journal": copy.deepcopy(record.journal),
            "narrative_memory": copy.deepcopy(record.narrative_memory),
            "world_metadata": copy.deepcopy(getattr(session, "world_metadata", None)),
            # What the narrator reads of the story; it lives in the runtime only, a reload starts it anew.
            **({"history": [(item.get("role"), item.get("content")) for item in session.messages]} if live else {}),
        }

    def observed(self):
        return self.observed_in(self.record)

    def reloaded_observed(self):
        store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        fresh = SessionManager(campaign_store=store)
        reloaded_id, *_ = fresh.resume_campaign(self.record.campaign_id)
        return {**self.observed_in(fresh.get(reloaded_id), live=False), "story": self.story(store)}

    def story(self, store=None):
        """The campaign history as the player reads it: each row's line and its read-time undo flags."""
        rows = (store or self.store).get_campaign(self.record.campaign_id).history
        return [(row["player_message"], bool(row.get("undone")), bool(row.get("undo_note")),
                 bool(row.get("undo_target_unknown"))) for row in rows]

    def count_promoted(self):
        return sum(1 for ref in self.scene()["referents"] if ref.get("lifecycle") == "promoted")

    def outcome(self):
        referent = next(ref for ref in self.scene()["referents"] if ref.get("event_instance_id") == self.instance)
        npc_id = referent.get("promoted_npc_id")
        return {
            "promoted_npc_present": any(npc.get("id") == npc_id for npc in self.world["npcs"]),
            "active_npc_is_promoted": npc_id is not None and self.world["flags"].get("active_npc_id") == npc_id,
            "referent_lifecycle": referent.get("lifecycle"),
        }

    async def fresh_with_event_then_say(self, message):
        await self.state_with_event()
        await self.say(message)
        return self.outcome()

    async def fresh_with_event_then_click(self):
        await self.state_with_event()
        await self.click("interact")
        return self.outcome()

    # --- the rule ------------------------------------------------------------------------------------------------
    async def test_the_view_and_the_click_read_one_rule(self):
        for case, setup in (("fresh", {}), ("expired", {"turns_later": 13}), ("combat", {"fight": True}),
                            ("green", {"event_type": "GREEN"}), ("resolved", {"promoted": True})):
            with self.subTest(case=case):
                state = await self.state_with_event(**setup)
                view = state["scene"]["ambient_event"]["actionable"]
                click = await self.click("interact")
                self.assertEqual(view["can_interact"], click["result"]["status"] == "APPLIED", (view, click["result"]))
                if not view["can_interact"]:
                    self.assertEqual(click["result"]["reason_code"], view["reason"])
                self.assertEqual(view["reason"], {"fresh": None, "expired": "event_expired", "combat": "combat",
                                                  "green": "event_not_interactive",
                                                  "resolved": "event_already_resolved"}[case])

    def test_the_rule_names_each_reason_in_order(self):
        import ambient_actions
        world = {"location": "here", "flags": {"turn_index": 5}, "npcs": [],
                 "scene_state": {"scenes": {"here": {"referents": []}}}}
        self.assertEqual(ambient_actions.actionable(world),
                         {"event_instance_id": None, "can_interact": False, "reason": "no_event"})
        scene = world["scene_state"]["scenes"]["here"]
        scene["ambient_event"] = {"instance_id": "e1", "event_type": "GREEN"}
        self.assertEqual(ambient_actions.actionable(world)["reason"], "event_not_interactive")
        scene["ambient_event"].update(event_type="BLUE", referent_id="r1")
        self.assertEqual(ambient_actions.actionable(world)["reason"], "event_referent_missing")
        referent = {"id": "r1", "event_instance_id": "e1", "lifecycle": "presented", "expires_after_turn": 5}
        scene["referents"].append(referent)
        self.assertEqual(ambient_actions.actionable(world),
                         {"event_instance_id": "e1", "can_interact": True, "reason": None})
        world["combat"] = {"active": True}
        self.assertEqual(ambient_actions.actionable(world)["reason"], "combat")
        world["combat"] = {"active": False}
        self.assertEqual(ambient_actions.actionable(world, current_hp=0)["reason"], "player_down")
        world["flags"]["turn_index"] = 6
        self.assertEqual(ambient_actions.actionable(world)["reason"], "event_expired")
        referent.update(lifecycle="expired", expires_after_turn=99)
        self.assertEqual(ambient_actions.actionable(world)["reason"], "event_expired")
        referent.update(lifecycle="promoted", promoted_npc_id="npc_1")
        self.assertEqual(ambient_actions.actionable(world)["reason"], "event_already_resolved")

    async def test_the_view_keeps_the_referent_as_saved(self):
        await self.state_with_event(turns_later=13)
        saved = copy.deepcopy(self.scene()["referents"])
        state = await self.state()
        self.assertEqual([ref["lifecycle"] for ref in state["scene"]["referents"]], ["presented"])
        self.assertEqual(self.scene()["referents"], saved)

    # --- a refusal ---------------------------------------------------------------------------------------------
    async def test_a_refused_click_says_why_in_turkish_and_changes_nothing(self):
        await self.state_with_event(turns_later=13)
        before = self.fingerprint()
        click = await self.click("interact")
        self.assertEqual((click["result"]["status"], click["result"]["message"]), ("REJECTED", "Onlar çoktan dağıldı."))
        self.assertEqual(self.fingerprint(), before)

    async def test_each_refusal_reads_its_own_line(self):
        for setup, text in (({"fight": True}, "Kavga sürerken buna yetişemezsin."),
                            ({"event_type": "GREEN"}, "Orada artık katılabileceğin bir şey yok.")):
            with self.subTest(setup=setup):
                await self.state_with_event(**setup)
                click = await self.click("interact")
                self.assertEqual((click["result"]["status"], click["result"]["message"]), ("REJECTED", text))

    async def test_no_place_to_approach_is_a_refusal_not_a_pause(self):
        await self.state_with_event(promotion_fails=True)          # patch _promote_scene_referent -> None
        before = self.fingerprint()
        click = await self.click("interact")
        self.assertEqual((click["result"]["status"], click["result"]["message"]),
                         ("REJECTED", "Kalabalıkta onlara yaklaşacak yer bulamıyorsun."))
        self.assertEqual(click["result"]["reason_code"], "promotion_unavailable")
        self.assertEqual(self.fingerprint(), before)

    async def test_an_applied_click_carries_no_refusal_line(self):
        await self.state_with_event()
        click = await self.click("interact")
        self.assertEqual(click["result"]["status"], "APPLIED")
        self.assertNotIn("message", click["result"])

    # --- undo ------------------------------------------------------------------------------------------------------
    async def test_undo_after_a_click_restores_the_scene_whole(self):
        await self.state_with_event()
        before = self.observed()                                   # npcs, referent lifecycle, talk, journal, history
        click = await self.click("interact")
        self.assertNotEqual(self.observed(), before)
        undo = await self.undo(target_action_id=click["result"]["action_id"])
        self.assertEqual(undo.status_code, 200, undo.text)
        self.assertIn("Yanlarına gidiyorum.", undo.json()["narration"])
        self.assertEqual(self.observed(), before)
        self.assertEqual((await self.undo(target_action_id=click["result"]["action_id"])).json()["detail"]["code"],
                         "undo_unavailable")
        reloaded = self.reloaded_observed()
        self.assertEqual(reloaded["referents"], before["referents"])
        self.assertEqual(reloaded["story"], self.story())

    async def test_the_story_marks_an_undone_click_like_an_undone_turn(self):
        await self.state_with_event()
        click = await self.click("interact")
        self.assertEqual((await self.undo(target_action_id=click["result"]["action_id"])).status_code, 200)
        story = self.story()
        self.assertEqual(story[-2], ("Yanlarına gidiyorum.", True, False, False))   # the click: undone
        self.assertEqual(story[-1][1:], (False, True, False))                      # the undo: proven, target known

    def test_the_story_and_the_click_spell_the_join_line_alike(self):
        from api import history_view
        import ambient_actions
        self.assertEqual(history_view.AMBIENT_JOIN_LINE, ambient_actions.JOIN_LINE)

    async def test_a_resolved_event_whose_person_is_gone_reads_one_reason(self):
        await self.state_with_event()
        referent = next(ref for ref in self.scene()["referents"] if ref.get("event_instance_id") == self.instance)
        referent.update(lifecycle="promoted", promoted_npc_id="npc_gone")
        view = (await self.state())["scene"]["ambient_event"]["actionable"]
        click = await self.click("interact")
        self.assertEqual(view, {"can_interact": False, "reason": "event_already_resolved"})
        self.assertEqual((click["result"]["status"], click["result"]["reason_code"], click["result"]["message"]),
                         ("REJECTED", "event_already_resolved", "Bu karşılaşma zaten gelişti."))

    async def test_a_refused_click_keeps_the_last_turns_undo(self):
        turn = await self.say("etrafıma bakıyorum")
        await self.state_with_event(turns_later=13, keep_turn=True)
        await self.click("interact")                                # refused: changes nothing
        self.assertEqual((await self.undo(target_action_id=turn["action_id"])).status_code, 200)

    async def test_a_click_without_effect_keeps_the_last_turns_undo(self):
        turn = await self.say("etrafıma bakıyorum")
        await self.state_with_event(keep_turn=True)
        self.assertEqual((await self.click("observe"))["result"]["status"], "NO_EFFECT")
        self.assertEqual((await self.undo(target_action_id=turn["action_id"])).status_code, 200)

    async def test_a_replayed_click_promotes_once(self):
        await self.state_with_event()
        first = await self.click("interact", action_id="11111111-1111-4111-8111-111111111111")
        again = await self.click("interact", action_id="11111111-1111-4111-8111-111111111111")
        self.assertEqual(first["result"]["status"], "APPLIED")
        self.assertEqual((again["result"]["status"], again["result"]["transition_id"]),
                         ("ALREADY_APPLIED", first["result"]["transition_id"]))
        self.assertEqual(self.count_promoted(), 1)
        self.assertEqual(sum(1 for npc in self.world["npcs"] if npc["id"] == first["result"]["transition_id"]), 1)

    async def test_reload_after_a_click_matches_live(self):
        await self.state_with_event()
        await self.click("interact")
        self.assertEqual(self.reloaded_observed(), {**self.observed_in(self.record, live=False), "story": self.story()})

    async def test_typing_and_clicking_end_alike(self):          # K3
        typed = await self.fresh_with_event_then_say("Esnaf ile konuşmak istiyorum.")
        clicked = await self.fresh_with_event_then_click()
        self.assertEqual(clicked, {"promoted_npc_present": True, "active_npc_is_promoted": True,
                                   "referent_lifecycle": "promoted"})
        for key in ("promoted_npc_present", "active_npc_is_promoted", "referent_lifecycle"):
            self.assertEqual(typed[key], clicked[key], key)


if __name__ == "__main__":
    unittest.main()
