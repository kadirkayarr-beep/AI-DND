#!/usr/bin/env python3
"""Debug test E"""
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
find_weapon_in_inventory = game_namespace['find_weapon_in_inventory']
WEAPONS = game_namespace['WEAPONS']
ensure_npc_combat_stats = game_namespace['ensure_npc_combat_stats']

world_state['location'] = 'tavern'
world_state['npcs'] = []
world_state['inventory'] = ['Macera çantası', 'Kılıç']
world_state['ground_items'] = []
world_state['ground_items_by_location'] = {}
world_state['doors'] = []
world_state['containers'] = []
world_state['features'] = []
world_state['events'] = []
world_state['flags'] = {
    'last_npc_id': None, 'active_npc_id': None,
    'active_npc_until_turn': -1, 'turn_index': 0,
    'pending_destination': None,
}
world_state['next_npc_number'] = 1
world_state['next_location_number'] = 1
world_state['combat'] = {
    'active': False, 'round': 0, 'initiative_order': [], 'current_turn_index': 0,
    'participants': [], 'target_id': None,
}
world_state['player_combat_status'] = 'active'

npc = {
    'id': 'npc_001', 'name': 'Test', 'role': 'Dummy',
    'location': 'tavern', 'personality': '', 'appearance': '',
    'relationship': 'neutral', 'knowledge': [], 'memory': [],
    'backstory': '', 'max_hp': 5, 'current_hp': 5,
    'armor_class': 5, 'combat_status': 'active',
}
world_state['npcs'].append(npc)

game_namespace['roll_d20'] = lambda: 20

weapon_name, weapon_data = find_weapon_in_inventory('Kılıç')
target = npc
print('Weapon:', weapon_name)
print('Weapon data:', WEAPONS.get(weapon_name))
print('Strength mod:', globals().get('strength_mod', 'NOT SET'))
print('Dexterity mod:', globals().get('dexterity_mod', 'NOT SET'))

result = resolve_attack('attack', weapon_name, WEAPONS[weapon_name], target)
print('Result:', result)
print('Target HP after:', result.get('target_hp_after'))