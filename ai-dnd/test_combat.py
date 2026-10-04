#!/usr/bin/env python3
"""Quick combat mechanics test"""
import sys
import copy
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))

from offline_test_support import offline_model
from combat_lifecycle import CombatRequestError
import game
session = game.create_session()

# Extract functions
world_state = session.world_state
resolve_combat_target = session.resolve_combat_target
resolve_attack = session.resolve_attack
find_weapon_in_inventory = session.find_weapon_in_inventory
WEAPONS = game.WEAPONS
ensure_npc_combat_stats = session.ensure_npc_combat_stats
run_player_turn = session.run_player_turn

def reset_world_state():
    # Preserve the session/world aliases, but never leak combat budgets, closed
    # combat IDs, character conditions or geometry from the preceding case.
    fresh = game.create_session(seed=73)
    world_state.clear()
    world_state.update(copy.deepcopy(fresh.world_state))
    session.character.clear()
    session.character.update(copy.deepcopy(fresh.character))
    session.character.update(
        strength=10, strength_mod=0, proficiency_bonus=2,
        weapon_proficiencies=["longsword"], weapon_masteries=[], conditions=[],
    )
    session.rng.setstate(fresh.rng.getstate())
    session.messages.clear()
    session.recent_dm_narrations.clear()
    world_state["location"] = "tavern"
    world_state["npcs"] = []
    world_state["inventory"] = ["Macera çantası", "Kılıç"]
    world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
    world_state["ground_items"] = []
    world_state["ground_items_by_location"] = {}
    world_state["doors"] = []
    world_state["containers"] = []
    world_state["features"] = []
    world_state["events"] = []
    world_state["flags"] = {
        "last_npc_id": None, "active_npc_id": None,
        "active_npc_until_turn": -1, "turn_index": 0,
        "pending_destination": None,
    }
    world_state["next_npc_number"] = 1
    world_state["next_location_number"] = 1

def add_npc(name="Gromm", role="Barmen", hp=10, ac=10, *, combat=False):
    npc = {
        "id": "npc_001", "name": name, "role": role,
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": "", "max_hp": hp, "current_hp": hp,
        "armor_class": ac, "combat_status": "active",
        # Authored offline fixture geometry, not an engine distance default.
        "distance_ft": 5,
    }
    world_state["npcs"].append(npc)
    if combat:
        with patch("game.roll_initiative_player", return_value=20), \
             patch("game.roll_initiative", return_value=1):
            session.start_combat(npc)
        state = session.ensure_combat_state()
        assert set(state["participants"]) == {"player", npc["id"]}
        assert state["current_actor_id"] == "player"
    return npc


@offline_model(game, content=(
    '{"intent":"attack","action":"attack",'
    '"target":{"type":"npc","reference":"Test Enemy"},'
    '"completion":"completed","confidence":1.0}'
))
def run_tests():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    print("=== COMBAT MECHANICS TEST ===\n")

    # Test A: Normal hit
    print("TEST A: Normal hit (d20=15, AC=10)")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=10, ac=10, combat=True)
    # Control the underlying die; keep roll_attack's session-bound wrapper.
    original_roll = game.roll_d20
    game.roll_d20 = lambda: 15
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        assert result["attack_roll"] == 15
        assert result["attack_bonus"] == 2
        assert result["attack_total"] == 17
        assert result["weapon_id"] == "longsword"
        assert result["combat_id"] == world_state["combat"]["combat_id"]
        print(f"  Attack total: {result['attack_total']} vs AC 10 -> {result['outcome']}")
        print(f"  Damage: {result['damage']}")
        print(f"  Target HP: {result['target_hp_before']} -> {result['target_hp_after']}")
        assert result['outcome'] == 'hit', "Should hit"
        assert result['target_hp_after'] < result['target_hp_before'], "HP should decrease"
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test B: Miss
    print("\nTEST B: Miss (d20=5, AC=20)")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=10, ac=20, combat=True)
    game.roll_d20 = lambda: 5
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        assert result["attack_roll"] == 5
        assert result["attack_total"] == 7
        assert result["damage"] == 0
        print(f"  Attack total: {result['attack_total']} vs AC 20 -> {result['outcome']}")
        print(f"  Target HP: {result['target_hp_before']} -> {result['target_hp_after']}")
        assert result['outcome'] == 'miss', "Should miss"
        assert result['target_hp_after'] == result['target_hp_before'], "HP should not change"
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test C: Natural 1 = auto miss
    print("\nTEST C: Natural 1 = auto miss (even with AC 0)")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=10, ac=0, combat=True)
    game.roll_d20 = lambda: 1
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Attack roll: 1 vs AC 0 -> {result['outcome']}")
        assert result['outcome'] == 'miss', "Natural 1 should always miss"
        assert result["natural_1"] is True
        assert result["damage"] == 0
        assert result["target_hp_after"] == result["target_hp_before"]
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test D: Natural 20 = critical hit
    print("\nTEST D: Natural 20 = critical hit")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=20, ac=30, combat=True)
    game.roll_d20 = lambda: 20
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Attack roll: 20 vs AC 30 -> {result['outcome']}")
        print(f"  Damage: {result['damage']} (2d8+0)")
        print(f"  Target HP: {result['target_hp_before']} -> {result['target_hp_after']}")
        assert result['outcome'] == 'critical_hit', "Should be critical hit"
        assert result['critical'] == True, "Should be critical"
        assert result["natural_20"] is True
        assert result["damage_rolls"][0]["count"] == 2
        assert result["target_hp_after"] == result["target_hp_before"] - result["damage"]
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test E: Zero HP -> unconscious
    print("\nTEST E: Zero HP -> unconscious")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=5, ac=5, combat=True)
    original_roll = game.roll_d20
    original_randint = session.rng.randint
    try:
        game.roll_d20 = lambda: 20
        # Mock damage roll to be deterministic
        session.rng.randint = lambda low, high: high  # Always max damage
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Critical hit damage: {result['damage']}")
        print(f"  Target HP: {result['target_hp_before']} -> {result['target_hp_after']}")
        print(f"  Status: {result['target_status']}")
        assert result['target_hp_after'] == 0, f"HP should be 0, got {result['target_hp_after']}"
        assert result['target_status'] == 'unconscious', "Should be unconscious"
        assert result["damage"] == 16
        assert npc["current_hp"] == 0
        assert npc["combat_status"] == "unconscious"
        print("  PASS")
    finally:
        game.roll_d20 = original_roll
        session.rng.randint = original_randint

    # Test F: Wrong location
    print("\nTEST F: Wrong location - NPC in different location")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=10, ac=10)
    world_state['npcs'][0]['location'] = 'forest'
    world_state['location'] = 'tavern'
    weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
    target = resolve_combat_target("test", npc)  # Should fail - different location
    print(f"  Target resolved: {target}")
    # The target should be None or fail because NPC is in different location
    # Actually resolve_combat_target uses resolve_npc_reference which checks location
    assert target is None, "NPC in different location should not be a valid target"
    print(f"  Target resolved: {target} -> PASS")

    # Test G: No target
    print("\nTEST G: No valid target")
    reset_world_state()
    target = resolve_combat_target("saldırıyorum", None)
    print(f"  Target: {target}")
    assert target is None, "Should return None when no target"
    print("  PASS")

    # Test H: No weapon
    print("\nTEST H: No weapon in inventory")
    reset_world_state()
    world_state["inventory"].remove("Kılıç")
    weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
    print(f"  Weapon found: {weapon_name}")
    assert weapon_name is None, "Should not find weapon"
    print("  PASS")

    # Test I: Forged / detached NPC dict
    print("\nTEST I: Forged / detached NPC dict")
    reset_world_state()
    add_npc()  # Real Gromm in tavern
    fake_npc = {
        "id": "npc_fake",
        "name": "Fake",
        "location": world_state["location"],
        "max_hp": 10,
        "current_hp": 10,
        "armor_class": 10,
        "combat_status": "active"
    }
    # Not in world_state["npcs"]
    weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
    target = resolve_combat_target("test", fake_npc)
    assert target is None, "Forged NPC not in world_state should not be a valid target"
    print(f"  Target resolved: {target} -> PASS")

    # Test J: Full pipeline cross-location
    print("\nTEST J: Full pipeline cross-location attack")
    reset_world_state()
    npc = add_npc("Gromm", "Barmen", hp=10, ac=10)
    # Move NPC to forest, player in tavern
    world_state['npcs'][0]['location'] = 'forest'
    world_state['location'] = 'tavern'
    before = copy.deepcopy((world_state, session.character, session.rng.getstate(),
                            session.messages, session.recent_dm_narrations))
    model = game.ollama
    calls_before = model.chat.call_count
    # Request validation now rejects nonlocal targets before intent/model work.
    messages = [{"role": "system", "content": "test"}]
    try:
        run_player_turn("Gromm'a kılıcımla saldırıyorum", messages)
    except CombatRequestError as error:
        assert error.code == "invalid_combat_target"
        assert error.status_code == 400
    else:
        raise AssertionError("Nonlocal attack must be rejected")
    assert (world_state, session.character, session.rng.getstate(),
            session.messages, session.recent_dm_narrations) == before
    assert messages == [{"role": "system", "content": "test"}]
    assert model.chat.call_count == calls_before
    print("  Nonlocal target rejected without state, RNG or model work -> PASS")

    # Explicit geometry/participation are prerequisites, never test-driven
    # defaults in production. Neither invalid request may reach attack dice.
    for code in ("distance_unknown", "invalid_combat_target"):
        print(f"\nTEST: Authoritative prerequisite refusal ({code})")
        reset_world_state()
        npc = add_npc("Test", "Dummy", combat=True)
        if code == "distance_unknown":
            del npc["distance_ft"]
        else:
            npc = add_npc("Bystander", "Dummy")
            npc["id"] = "npc_002"
        before = copy.deepcopy((world_state, session.character, session.rng.getstate()))
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        with patch.object(session.rng, "randint", side_effect=AssertionError("invalid attack rolled")):
            try:
                resolve_attack("attack", weapon_name, weapon_data, npc)
            except CombatRequestError as error:
                assert error.code == code
            else:
                raise AssertionError(f"Expected {code}")
        assert (world_state, session.character, session.rng.getstate()) == before
        print("  Rejected without state or RNG mutation -> PASS")

    print("\n=== ALL COMBAT TESTS PASSED ===")

if __name__ == '__main__':
    run_tests()
