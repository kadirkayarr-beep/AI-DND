#!/usr/bin/env python3
"""Quick combat mechanics test"""
import sys
import io
import json
import types
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))

ollama_mock = types.SimpleNamespace(
    chat=lambda **kwargs: {
        "message": {
            "content": (
                '{"intent":"attack","action":"attack",'
                '"target":{"type":"npc","reference":"Test Enemy"},'
                '"completion":"completed","confidence":1.0}'
            )
        }
    }
)
sys.modules["ollama"] = ollama_mock
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
    world_state["location"] = "tavern"
    world_state["npcs"] = []
    world_state["inventory"] = ["Macera çantası", "Kılıç"]
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

def add_npc(name="Gromm", role="Barmen", hp=10, ac=10):
    npc = {
        "id": "npc_001", "name": name, "role": role,
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": "", "max_hp": hp, "current_hp": hp,
        "armor_class": ac, "combat_status": "active"
    }
    world_state["npcs"].append(npc)
    return npc


def run_tests():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    sys.modules['ollama'] = ollama_mock
    game.ollama = ollama_mock
    print("=== COMBAT MECHANICS TEST ===\n")

    # Test A: Normal hit
    print("TEST A: Normal hit (d20=15, AC=10)")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=10, ac=10)
    original_roll = game.roll_d20
    game.roll_d20 = lambda: 15
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Attack roll: 15+0=15 vs AC 10 -> {result['outcome']}")
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
    npc = add_npc("Test", "Dummy", hp=10, ac=20)
    game.roll_d20 = lambda: 5
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Attack roll: 5+0=5 vs AC 20 -> {result['outcome']}")
        print(f"  Target HP: {result['target_hp_before']} -> {result['target_hp_after']}")
        assert result['outcome'] == 'miss', "Should miss"
        assert result['target_hp_after'] == result['target_hp_before'], "HP should not change"
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test C: Natural 1 = auto miss
    print("\nTEST C: Natural 1 = auto miss (even with low AC)")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=10, ac=5)
    game.roll_d20 = lambda: 1
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Attack roll: 1 vs AC 5 -> {result['outcome']}")
        assert result['outcome'] == 'miss', "Natural 1 should always miss"
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test D: Natural 20 = critical hit
    print("\nTEST D: Natural 20 = critical hit")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=20, ac=15)
    game.roll_d20 = lambda: 20
    try:
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        target = resolve_combat_target("test", npc)
        result = resolve_attack("attack", weapon_name, WEAPONS[weapon_name], target)
        print(f"  Attack roll: 20 vs AC 15 -> {result['outcome']}")
        print(f"  Damage: {result['damage']} (2d8+0)")
        print(f"  Target HP: {result['target_hp_before']} -> {result['target_hp_after']}")
        assert result['outcome'] == 'critical_hit', "Should be critical hit"
        assert result['critical'] == True, "Should be critical"
        print("  PASS")
    finally:
        game.roll_d20 = original_roll

    # Test E: Zero HP -> unconscious
    print("\nTEST E: Zero HP -> unconscious")
    reset_world_state()
    npc = add_npc("Test", "Dummy", hp=5, ac=5)
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
    hp_before = world_state['npcs'][0]['current_hp']
    # Try to attack through full pipeline
    messages = [{"role": "system", "content": "test"}]
    result = run_player_turn("Gromm'a kılıcımla saldırıyorum", messages)
    ar = result["action_result"]
    hp_after = world_state['npcs'][0]['current_hp']
    # Should fail gracefully
    assert ar.get("action") == "attack", f"Action should be attack, got {ar.get('action')}"
    assert ar.get("success") == False, "Attack should fail"
    assert hp_after == hp_before, f"HP should not change (was {hp_before}, now {hp_after})"
    print(f"  Action: {ar.get('action')}, Status: {ar.get('status')}, Success: {ar.get('success')}")
    print(f"  HP before: {hp_before}, HP after: {hp_after} -> PASS")

    print("\n=== ALL COMBAT TESTS PASSED ===")

if __name__ == '__main__':
    run_tests()
