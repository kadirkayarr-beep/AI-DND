#!/usr/bin/env python3
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sys
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
game_namespace = {'__name__': 'game', '__file__': r'C:\Users\Kadir\Desktop\AI-DND\game.py', 'ollama': __import__('ollama')}
exec(compile(final_source, r'C:\Users\Kadir\Desktop\AI-DND\game.py', 'exec'), game_namespace)

import builtins
builtins.input = lambda prompt='': '2'

world_state = game_namespace['world_state']
should_generate_npcs = game_namespace['should_generate_npcs']

world_state['location'] = 'tavern'
world_state['npcs'] = [{'id': 'npc_001', 'name': 'Gromm', 'role': 'Barmen', 'location': 'tavern'}]
print('NPCs in tavern:', len([n for n in world_state['npcs'] if n['location'] == 'tavern']))
print('should_generate_npcs at tavern (no change):', should_generate_npcs('test', False))
print('should_generate_npcs at tavern (location change):', should_generate_npcs('test', True))

world_state['location'] = 'forest'
print('should_generate_npcs at forest (no npcs, location change):', should_generate_npcs('test', True))

world_state['location'] = 'tavern'
print('should_generate_npcs back at tavern (location change, npcs exist):', should_generate_npcs('test', True))