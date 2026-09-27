#!/usr/bin/env python3
"""
Debug combat issues
"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r'C:\Users\Kadir\Desktop\AI-DND')
import builtins
builtins.input = lambda prompt='': '2'

with open(r'C:\Users\Kadir\Desktop\AI-DND\game.py', 'r', encoding='utf-8') as f:
    source = f.read()

lines = source.split('\n')
exec_lines = []
in_main_block = False
for line in lines:
    if line.startswith('if __name__ == "__main__":'):
        in_main_block = True
        continue
    if in_main_block:
        continue
    exec_lines.append(line)

final_source = '\n'.join(exec_lines)

game_namespace = {
    '__name__': 'game',
    '__file__': r'C:\Users\Kadir\Desktop\AI-DND\game.py',
    'ollama': __import__('ollama'),
}

exec(compile(final_source, r'C:\Users\Kadir\Desktop\AI-DND\game.py', 'exec'), game_namespace)

import builtins
builtins.input = lambda prompt='': '2'

# Extract functions
world_state = game_namespace['world_state']
roll_d20 = game_namespace['roll_d20']
resolve_combat_target = game_namespace['resolve_combat_target']
resolve_attack = game_namespace['resolve_attack']
resolve_enemy_attack = game_namespace['resolve_enemy_attack']
start_combat = game_namespace['start_combat']
end_combat = game_namespace['end_combat']
find_weapon_in_inventory = game_namespace['find_weapon_in_inventory']
WEAPONS = game_namespace['WEAPONS']
ensure_npc_combat_stats = game_namespace['ensure_npc_combat_stats']
ensure_npc_enemy_stats = game_namespace['ensure_npc_enemy_stats']
ensure_combat_state = game_namespace['ensure_combat_state']

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
    world_state["combat"] = {
        "active": False,
        "round": 0,
        "initiative_order": [],
        "current_turn_index": 0,
        "participants": [],
        "target_id": None,
    }
    world_state["player_combat_status"] = "active"

def add_npc(name="Gromm", role="Barmen", hp=10, ac=10):
    npc = {
        "id": "npc_001", "name": name, "role": role,
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [],
        "backstory": "", "max_hp": hp, "current_hp": hp,
        "armor_class": ac, "combat_status": "active",
    }
    world_state["npcs"].append(npc)
    return npc

def force_roll(value):
    original = game_namespace['roll_d20']
    game_namespace['roll_d20'] = lambda: value
    return original

def run_turn(player_input):
    messages = [{"role": "system", "content": "test"}]
    return game_namespace['run_player_turn'](player_input, messages)

def force_roll(value):
    original = game_namespace['roll_d20']
    game_namespace['roll_d20'] = lambda: value
    return original

def run_turn(player_input):
    messages = [{"role": "system", "content": "test"}]
    return game_namespace['run_player_turn'](player_input, messages)

# Test combat start
print("=== Testing COMBAT START ===")
world_state["location"] = "tavern"
world_state["npcs"] = [{"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern", "personality": "", "appearance": "", "relationship": "neutral", "knowledge": [], "memory": [], "backstory": "", "max_hp": 10, "current_hp": 10, "armor_class": 10, "combat_status": "active"}]
world_state["inventory"] = ["Macera çantası", "Kılıç"]
world_state["ground_items"] = []
world_state["ground_items_by_location"] = {}
world_state["doors"] = []
world_state["containers"] = []
world_state["features"] = []
world_state["events"] = []
world_state["flags"] = {"last_npc_id": None, "active_npc_id": None, "active_npc_until_turn": -1, "turn_index": 0, "pending_destination": None}
world_state["next_npc_number"] = 1
world_state["next_location_number"] = 1
world_state["combat"] = {"active": False, "round": 0, "initiative_order": [], "current_turn_index": 0, "participants": [], "target_id": None}
world_state["player_combat_status"] = "active"
world_state["inventory"] = ["Macera çantası", "Kılıç"]
world_state["ground_items"] = []
world_state["ground_items_by_location"] = {}
world_state["doors"] = []
world_state["containers"] = []
world_state["features"] = []
world_state["events"] = []
world_state["flags"] = {"last_npc_id": None, "active_npc_id": None, "active_npc_until_turn": -1, "turn_index": 0, "pending_destination": None}
world_state["next_npc_number"] = 1
world_state["next_location_number"] = 1
world_state["combat"] = {"active": False, "round": 0, "initiative_order": [], "current_turn_index": 0, "participants": [], "target_id": None}
world_state["player_combat_status"] = "active"
world_state["inventory"] = ["Macera çantası", "Kılıç"]
world_state["ground_items"] = []
world_state["ground_items_by_location"] = {}
world_state["doors"] = []
world_state["containers"] = []
world_state["features"] = []
world_state["events"] = []
world_state["flags"] = {"last_npc_id": None, "active_npc_id": None, "active_npc_until_turn": -1, "turn_index": 0, "pending_destination": None}
world_state["next_npc_number"] = 1
world_state["next_location_number"] = 1
world_state["combat"] = {"active": False, "round": 0, "initiative_order": [], "current_turn_index": 0, "participants": [], "target_id": None}
world_state["player_combat_status"] = "active"
world_state["npcs"].append({"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern", "personality": "", "appearance": "", "relationship": "neutral", "knowledge": [], "memory": [], "backstory": "", "max_hp": 10, "current_hp": 10, "armor_class": 10, "combat_status": "active"})
world_state["inventory"] = ["Macera çantası", "Kılıç"]
world_state["ground_items"] = []
world_state["ground_items_by_location"] = {}
world_state["doors"] = []
world_state["containers"] = []
world_state["features"] = []
world_state["events"] = []
world_state["flags"] = {"last_npc_id": None, "active_npc_id": None, "active_npc_until_turn": -1, "turn_index": 0, "pending_destination": None}
world_state["next_npc_number"] = 1
world_state["next_location_number"] = 1
world_state["combat"] = {"active": False, "round": 0, "initiative_order": [], "current_turn_index": 0, "participants": [], "target_id": None}
world_state["player_combat_status"] = "active"
world_state["npcs"].append({"id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern", "personality": "", "appearance": "", "relationship": "neutral", "knowledge": [], "memory": [], "backstory": "", "max_hp": 10, "current_hp": 10, "armor_class": 10, "combat_status": "active"})

# Test with enough rolls: attack, init_p, init_n, enemy attack
rolls = [15, 15, 5, 15]  # attack=15, init_p=15, init_n=5, enemy_atk=15
roll_iter = iter(rolls)
original_roll = game_namespace['roll_d20']

def mock_roll():
    val = next(roll_iter)
    print(f"  [ROLL] d20 = {val}")
    return val

game_namespace['roll_d20'] = mock_roll

def run_turn(player_input):
    messages = [{"role": "system", "content": "test"}]
    return game_namespace['run_player_turn'](player_input, messages)

print("Testing combat start...")
result = game_namespace['run_player_turn']("Gromm'a kılıcımla saldırıyorum", [{"role": "system", "content": "test"}])
ar = result["action_result"]
combat = ar.get("combat", {})
print(f"Action: {ar.get('action')}")
print(f"Combat: {combat}")
print(f"Combat active: {combat.get('active')}")
print(f"Combat round: {combat.get('round')}")
print(f"Combat initiative: {combat.get('initiative_order')}")
print(f"Combat turn index: {combat.get('current_turn_index')}")
print(f"Combat started: {combat.get('combat_started')}")
print(f"Combat active: {combat.get('active')}")
print(f"Combat round: {combat.get('round')}")
print(f"Combat initiative: {combat.get('initiative_order')}")
print(f"Combat turn index: {combat.get('current_turn_index')}")
print(f"Combat started: {combat.get('combat_started')}")
print(f"Combat keys: {list(combat.keys())}")