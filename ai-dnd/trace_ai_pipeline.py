#!/usr/bin/env python3
"""Phase 1: Runtime trace of AI gameplay pipeline"""
import sys
import io
import json
import contextlib
import copy
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))
import builtins
builtins.input = lambda prompt='': '2'

# Import the game module
with open(GAME_FILE, 'r', encoding='utf-8') as f:
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
    '__file__': str(GAME_FILE),
    'ollama': __import__('ollama'),
}

exec(compile(final_source, str(GAME_FILE), 'exec'), game_namespace)

import builtins
builtins.input = lambda prompt='': '2'

# Extract key functions
G = game_namespace

# Override ollama to capture calls
original_ask_dm = G.get('ask_dungeon_master')
original_parse_intent = G.get('parse_player_intent')
original_normalize_intent = G.get('normalize_intent')
original_validate_intent = G.get('validate_intent')
original_execute_intent = G.get('execute_intent')
original_finalize_narration = G.get('finalize_narration')

# Capture traces
traces = []

def trace_ask_dm(messages, player_input, **kwargs):
    traces.append(('ask_dungeon_master_CALL', {
        'messages': messages,
        'player_input': player_input,
        'kwargs': {k: v for k, v in kwargs.items() if k not in ['action_result']}
    }))
    return original_ask_dm(messages, player_input, **kwargs)

def trace_parse_intent(player_input):
    result = original_parse_intent(player_input)
    traces.append(('parse_player_intent', {'input': player_input, 'raw_intent': result}))
    return result

def trace_normalize_intent(raw_intent, player_input):
    result = original_normalize_intent(raw_intent, player_input)
    traces.append(('normalize_intent', {'raw_intent': raw_intent, 'player_input': player_input, 'normalized': result}))
    return result

def trace_validate_intent(normalized_intent, player_input):
    result = original_validate_intent(normalized_intent, player_input)
    traces.append(('validate_intent', {'normalized': normalized_intent, 'player_input': player_input, 'validated': result}))
    return result

def trace_execute_intent(validated_intent, player_input, npc_target=None):
    result = original_execute_intent(validated_intent, player_input, npc_target)
    traces.append(('execute_intent', {
        'validated_intent': validated_intent,
        'player_input': player_input,
        'npc_target': npc_target,
        'action_result': {k: v for k, v in result.items() if k != 'direct_response'}
    }))
    return result

def trace_finalize_narration(narration, player_input, npc_target, action_result):
    result = original_finalize_narration(narration, player_input, npc_target, action_result)
    traces.append(('finalize_narration', {
        'raw_narration': narration,
        'player_input': player_input,
        'npc_target': npc_target,
        'action_result': {k: v for k, v in action_result.items() if k != 'direct_response'},
        'final_narration': result
    }))
    return result

# Patch the functions
G['ask_dungeon_master'] = trace_ask_dm
G['parse_player_intent'] = trace_parse_intent
G['normalize_intent'] = trace_normalize_intent
G['validate_intent'] = trace_validate_intent
G['execute_intent'] = trace_execute_intent
G['finalize_narration'] = trace_finalize_narration

# Disable ollama model calls for deterministic tracing
fake_ollama = __import__('types').ModuleType('ollama')
def no_model(**kwargs):
    return {'message': {'content': '{"intent": "dialogue", "target": {}}'}}
fake_ollama.chat = no_model

import sys
sys.modules['ollama'] = fake_ollama

# Also patch the G namespace ollama
G['ollama'] = fake_ollama

# Fresh world state
world_state = G['world_state']
world_state.clear()
world_state.update({
    "location": "neverwinter",
    "npcs": [],
    "inventory": ["Macera çantası", "Kılıç"],
    "ground_items": [],
    "ground_items_by_location": {},
    "doors": [],
    "containers": [],
    "features": [],
    "events": [],
    "flags": {
        "last_npc_id": None, "active_npc_id": None,
        "active_npc_until_turn": -1, "turn_index": 0,
        "pending_destination": None,
    },
    "next_npc_number": 1,
    "next_location_number": 1,
    "combat": {
        "active": False,
        "round": 0,
        "initiative_order": [],
        "current_turn_index": 0,
        "participants": [],
        "target_id": None,
    },
    "player_combat_status": "active",
    "recent_dm_narrations": []
})

# Add some NPCs for testing
npc_gromm = {
    "id": "npc_gromm", "name": "Gromm", "role": "Barmen",
    "location": "tavern", "personality": "", "appearance": "",
    "relationship": "neutral", "knowledge": [], "memory": [],
    "backstory": "", "max_hp": 50, "current_hp": 50,
    "armor_class": 12, "combat_status": "active",
    "attack_bonus": 2, "damage_die": 6, "damage_dice": 2, "damage_modifier": 3
}
world_state["npcs"].append(npc_gromm)

# Set player stats
G['current_hp'] = 30
G['max_hp'] = 30
G['armor_class'] = 12
G['strength_mod'] = 2
G['dexterity_mod'] = 2
G['proficiency_bonus'] = 2

# Mock qwen intent responses for specific inputs
mock_intents = {
    "neverwinter şehir kapılarından içeri giriyorum": {"intent": "travel", "target": {"reference": "tavern"}},
    "neredeyim": {"intent": "query", "query_type": "location"},
    "nerdeyim": {"intent": "query", "query_type": "location"},
    "tavernaya gidiyorum": {"intent": "travel", "target": {"reference": "tavern"}},
    "etrafımda neler var": {"intent": "explore", "explore_type": "observe"},
    "random ne var etrafımda": {"intent": "explore", "explore_type": "observe"},
    "barmene selam veriyorum": {"intent": "dialogue", "target": {"reference": "barmen"}},
    "tavernada kimler var": {"intent": "query", "query_type": "presence"},
    "ormana gidiyorum": {"intent": "travel", "target": {"reference": "orman"}},
    "haydut görüyorum": {"intent": "dialogue"},  # This should be player assertion
}

def mock_parse_intent(player_input):
    result = mock_intents.get(player_input, {"intent": "dialogue"})
    traces.append(('parse_player_intent', {'input': player_input, 'raw_intent': result}))
    return result

G['parse_player_intent'] = mock_parse_intent

# Trace the specific inputs
test_inputs = [
    "neverwinter şehir kapılarından içeri giriyorum",
    "neredeyim",
    "nerdeyim",
    "tavernaya gidiyorum",
    "etrafımda neler var",
    "random ne var etrafımda",
    "barmene selam veriyorum",
    "tavernada kimler var",
    "ormana gidiyorum",
    "haydut görüyorum",
]

def run_trace(player_input):
    traces.append(('=== INPUT ===', player_input))
    
    # Reset per-input traces
    input_traces = []
    
    # Run the turn
    result = G['run_player_turn'](player_input, [{"role": "system", "content": "test"}])
    
    # Capture all relevant state
    w = G['world_state']
    trace_data = {
        'input': player_input,
        'raw_intent': None,
        'normalized_intent': None,
        'validated_intent': None,
        'action_result': None,
        'direct_response_early_return': False,
        'previous_location': None,
        'current_location': w.get('location'),
        'combat': copy.deepcopy(w.get('combat', {})),
        'npcs': [{'id': n['id'], 'name': n['name'], 'location': n.get('location')} for n in w.get('npcs', [])],
        'features': [{'id': f.get('id'), 'name': f.get('name'), 'location': f.get('location')} for f in w.get('features', [])],
        'final_narration': result.get('narration'),
    }
    
    # Extract traces for this input
    for t in traces[-1:]:
        pass
    
    # Get the action_result traces
    for t in reversed(traces):
        if t[0] in ('execute_intent', 'parse_player_intent', 'normalize_intent', 'validate_intent'):
            input_traces.insert(0, t)
        if t[0] == '=== INPUT ===' and t[1] == player_input:
            break
    
    return trace_data

# Run all traces
for inp in test_inputs:
    trace_data = run_trace(inp)
    print(f"\n{'='*60}")
    print(f"INPUT: {inp}")
    print(f"RESULT: {trace_data['final_narration'][:100]}...")
    print(f"LOCATION: {trace_data['current_location']}")
    print(f"COMBAT: {trace_data['combat']}")

print("\n\n=== FULL TRACE DUMP ===")
for t in traces:
    print(f"\n{t[0]}:")
    print(json.dumps(t[1], ensure_ascii=False, indent=2, default=str)[:500])