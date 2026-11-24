"""D-234 (Kadir): "önce motorun savaşta Geri Al'ı testle doğrulanır; güvenliyse savaşta Geri Al açılır, değilse kapalı
kalır ve gerekçe yazılır."

One combat turn through the real turn route, then the real undo route: the whole saved game (positions, action economy,
initiative and turn order, conditions, hit points, deaths), the dice generator and the stored campaign must be exactly
what they were before the turn, and the same line played again must roll the same dice (no re-roll by undo).
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

from api.tests import test_campaign_api as campaign_fixtures
from api.tests.town_seed import fixed_town
import campaign_time


def _paths(before, after, prefix=""):
    """Every leaf path whose value differs."""
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(set(before) | set(after), key=str):
            out += _paths(before.get(key, "<missing>"), after.get(key, "<missing>"), f"{prefix}.{key}")
        return out
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        out = []
        for index, (left, right) in enumerate(zip(before, after)):
            out += _paths(left, right, f"{prefix}[{index}]")
        return out
    return [] if before == after else [prefix]


# uuid4 per request or per episode, never the dice: a replay mints new ones.
_NEW_PER_ACTION = {"action_id", "attack_id", "resolution_id", "event_id", "noncombat_episode_id"}


# A fight started again gets a new uuid4 combat_id; the monster's turn ids are built from it. Never the dice.
_NEW_PER_FIGHT = {"combat_id", "decision_id", "turn_id", "started_turn"}
# ...and only inside the fight's own records: the fight, the monsters' turns, the attack results.
_FIGHT_RECORDS = (".world_state.combat.", ".world_state.monster_combat.", ".world_state.attack_results[")
# A committed undo is a new revision of the same campaign, written at a new wall-clock second.
_REVISION_KEYS = {"revision", "updated_at", "last_played_at"}


class CombatTurnUndo(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def fight(self, far_ft=25, player_hp=60, far_bonus=6, weapon=None):
        """A fight on the player's turn: a 1-HP foe in reach and a tougher one `far_ft` away."""
        with fixed_town(self, 23401):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        session = self.manager.get(campaign["session_id"]).game_session
        campaign_time.initialize(session.world_state)
        here = session.world_state["location"]
        base = {"location": here, "combat_status": "active", "hostile": True, "attack_bonus": 6, "damage_die": 6,
                "damage_dice": 1, "damage_modifier": 2, "attack_damage_type": "slashing"}
        far = {**base, "id": "d234-far", "name": "Uzak Haydut", "current_hp": 30, "max_hp": 30, "armor_class": 12,
               "attack_bonus": far_bonus, "distance_ft": far_ft}
        session.world_state["npcs"] += [
            {**base, "id": "d234-weak", "name": "Zayıf Haydut", "current_hp": 1, "max_hp": 1, "armor_class": 1,
             "distance_ft": 5},
            far,
        ]
        session.character["max_hp"], session.character["current_hp"] = 60, player_hp
        if weapon:  # a weapon whose mastery the hero has, in hand
            import equipment_economy
            from weapon_catalog import lookup
            world = session.world_state
            world["inventory"] = [*world.get("inventory", []), weapon]
            equipment_economy.materialize(world)
            item = next(entry for entry in world["inventory"] if isinstance(entry, dict) and entry.get("name") == weapon)
            world.setdefault("equipment", {})["main_hand"] = item["item_id"]
            session.character["weapon_masteries"] = [lookup(weapon)["weapon_id"]]
            far.update(armor_class=1, constitution_mod=-5, saving_throw_mods={"constitution": -5})
            world["attack_environment"] = {"pairs": {"player|d234-far": {"distance_ft": 5, "push_clear_ft": 20}}}
        with patch("game.roll_d20", side_effect=[20, 10, 5]):
            session.start_combat(session.world_state["npcs"][-2])
        combat = session.world_state["combat"]
        combat["current_turn_index"] = combat["initiative_order"].index("player")
        combat["current_actor_id"] = "player"
        return campaign, session

    def whole(self, campaign, session):
        """Everything one undo must put back: the engine save, the dice, the record's journal, story memory, lore
        authority and world metadata, and the stored campaign (its payload and its non-revision metadata)."""
        record = self.manager.get(campaign["session_id"])
        stored = self.store.get_campaign(campaign["campaign_id"])
        return {
            "engine_save": copy.deepcopy(session.serialize_game_state()),
            "dice": session.rng.getstate(),
            "journal": copy.deepcopy(record.journal),
            "narrative_memory": copy.deepcopy(record.narrative_memory),
            "lore_authority": record.lore_authority,
            "world_metadata": copy.deepcopy(getattr(session, "world_metadata", None)),
            "stored_payload": copy.deepcopy(stored.payload),
            "stored_metadata": {key: value for key, value in stored.metadata.items() if key not in _REVISION_KEYS},
        }

    def assert_whole(self, now, before, message):
        for part, value in before.items():
            self.assertEqual(now[part], value, f"{message}: {part} differs "
                             f"{_paths(value, now[part]) if isinstance(value, dict) else ''}")

    async def played_then_undone(self, campaign, session, message, target_id, *, fight_before=True):
        """Play one turn, undo it, then play the same words again; return the turn's changed paths."""
        url = f"/api/game/sessions/{campaign['session_id']}"
        session.rng.seed(234)
        self.manager.save_campaign(campaign["campaign_id"])  # the stored campaign starts as the set-up scene
        before_all = self.whole(campaign, session)
        before = before_all["engine_save"]
        turn = await self.http.post(f"{url}/turn", json={
            "message": message, "target_id": target_id, "action_id": str(uuid.uuid4())})
        self.assertEqual(turn.status_code, 200, turn.text)
        after = copy.deepcopy(session.serialize_game_state())
        changed = _paths(before, after)
        self.assertTrue(session.world_state["combat"]["active"], turn.text)

        undo_request = {"action_id": str(uuid.uuid4()), "target_action_id": turn.json()["action_id"]}
        undo = await self.http.post(f"{url}/undo", json=undo_request)
        self.assertEqual(undo.status_code, 200, undo.text)
        self.assertIs(undo.json()["state"]["combat"]["active"], fight_before, "the fight is as it was before the turn")
        self.assert_whole(self.whole(campaign, session), before_all, "undo leaves no part half-restored")
        replay = await self.http.post(f"{url}/undo", json=undo_request)
        self.assertEqual((replay.status_code, replay.json()), (200, undo.json()), "the undo receipt replays as given")
        self.assert_whole(self.whole(campaign, session), before_all, "and the replay changes nothing")

        again = await self.http.post(f"{url}/turn", json={
            "message": message, "target_id": target_id, "action_id": str(uuid.uuid4())})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["narration"], turn.json()["narration"], "the same words roll the same dice")
        fresh_ids = [path for path in _paths(after, session.serialize_game_state())
                     if path.rsplit(".", 1)[-1] not in _NEW_PER_ACTION
                     and (fight_before or path.rsplit(".", 1)[-1] not in _NEW_PER_FIGHT
                          or not path.startswith(_FIGHT_RECORDS))]
        self.assertEqual(fresh_ids, [], "and lead to the very same fight (only new receipt ids differ)")
        return changed

    async def check(self, setup, target, expected):
        campaign, session = await self.fight(**setup)
        changed = await self.played_then_undone(campaign, session, "Düşmana saldırıyorum.", target)
        self.assertLessEqual(set(expected), set(changed), "the turn really changed what this case is about")
        self.assertIn(".world_state.combat.round", changed, "turn order: the round went on, and came back")
        self.assertTrue(any(path.startswith(".world_state.combat.turn_resources.") for path in changed),
                        "resources: action economy spent, and given back")

    async def test_a_kill_is_undone_whole(self):
        # Hit points, a death and the XP for it.
        await self.check({}, "d234-weak", [
            ".world_state.npcs[0].current_hp", ".world_state.npcs[0].combat_status", ".player.xp",
            ".world_state.xp_awarded_event_ids"])

    async def test_a_push_is_undone_whole(self):
        # Geometry: the Warhammer's Push moves the foe 10 feet and rewrites the distance facts.
        await self.check({"far_ft": 5, "weapon": "Warhammer"}, "d234-far", [
            ".world_state.npcs[1].distance_ft", ".world_state.attack_environment.pairs.player|d234-far.distance_ft",
            ".world_state.npcs[1].current_hp"])

    async def test_a_topple_is_undone_whole(self):
        # A condition: the Battleaxe's Topple leaves the foe Prone; the foes' blows cost the hero hit points.
        await self.check({"far_ft": 5, "weapon": "Battleaxe"}, "d234-far", [
            ".world_state.npcs[1].conditions", ".world_state.npcs[1].prone", ".player.current_hp"])

    async def test_the_turn_that_starts_a_fight_is_undone_to_peace(self):
        # Review (ORTA): a fight started by a played turn from peace; undo leaves no fight and the campaign as it was.
        with fixed_town(self, 23402):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        session = self.manager.get(campaign["session_id"]).game_session
        campaign_time.initialize(session.world_state)
        session.world_state["npcs"].append({
            "id": "d234-wolf", "name": "Kurt", "location": session.world_state["location"], "combat_status": "active",
            "hostile": True, "current_hp": 11, "max_hp": 11, "armor_class": 13, "attack_bonus": 4, "damage_die": 6,
            "damage_dice": 2, "damage_modifier": 2, "attack_damage_type": "piercing", "distance_ft": 5})
        self.assertFalse(session.world_state.get("combat", {}).get("active"), "peace before the turn")
        # The helper asserts the played turn left a fight running and the undo left none.
        await self.played_then_undone(campaign, session, "Kurda saldırıyorum.", "d234-wolf", fight_before=False)

    async def test_the_hero_dropping_to_zero_is_undone_whole(self):
        # The hero's own fall: 0 hit points, Prone and dying, then all of it back.
        await self.check({"far_ft": 5, "player_hp": 1, "far_bonus": 20}, "d234-weak", [
            ".player.current_hp", ".world_state.player_combat_status", ".world_state.death_state.prone"])


if __name__ == "__main__":
    unittest.main()
