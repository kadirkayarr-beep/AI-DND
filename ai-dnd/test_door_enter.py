import sys
from pathlib import Path
PROJECT_DIR = Path(__file__).resolve().parent
GAME_FILE = PROJECT_DIR / "game.py"
sys.path.insert(0, str(PROJECT_DIR))
from unittest.mock import MagicMock

ollama_mock = MagicMock()
ollama_mock.chat.return_value = {
    "message": {"content": '{"intent":"narrative","action":"test","target":{"type":"none","reference":""},"completion":"unclear","confidence":0.5}'}
}
sys.modules['ollama'] = ollama_mock

import game
session = game.create_session()

def reset():
    session.world_state['location'] = 'tavern'
    session.world_state['npcs'] = []
    session.world_state['inventory'] = ['Macera çantası', 'Kılıç']
    session.world_state['ground_items'] = []
    session.world_state['doors'] = []
    session.world_state['containers'] = []
    session.world_state['features'] = []
    session.world_state['events'] = []
    session.world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
    session.world_state['next_npc_number'] = 1
    session.world_state['next_location_number'] = 1
    session.recent_dm_narrations.clear()

# Test 1: unlocked closed door + 'içeri giriyorum'
reset()
session.world_state['doors'].append({'name': 'Test Kapı', 'description': 'Test', 'locked': False, 'open': False, 'broken': False, 'location': 'tavern'})
result = session.run_player_turn('içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = session._current_door()
print('Test 1 - içeri giriyorum (unlocked):')
print(f'  door.open = {door["open"]}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')
assert door is not None and door["open"] is True, "Entering through an unlocked door should open it"

# Test 2: unlocked closed door + 'kapıyı açıp içeri giriyorum'
reset()
session.world_state['doors'].append({'name': 'Test Kapı', 'description': 'Test', 'locked': False, 'open': False, 'broken': False, 'location': 'tavern'})
result = session.run_player_turn('kapıyı açıp içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = session._current_door()
print('Test 2 - kapıyı açıp içeri giriyorum (unlocked):')
print(f'  door.open = {door["open"]}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')
assert door is not None and door["open"] is True, "Opening and entering through an unlocked door should leave it open"

# Test 3: locked door + 'içeri giriyorum'
reset()
session.world_state['doors'].append({'name': 'Test Kapı', 'description': 'Test', 'locked': True, 'open': False, 'broken': False, 'location': 'tavern'})
result = session.run_player_turn('içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = session._current_door()
print('Test 3 - içeri giriyorum (locked):')
print(f'  door.open = {door["open"]}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')
assert door is not None and door["locked"] is True and door["open"] is False, "Entering through a locked door should not open it"

# Test 4: no door + 'içeri giriyorum'
reset()
result = session.run_player_turn('içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = session._current_door()
print('Test 4 - içeri giriyorum (no door):')
print(f'  door = {door}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')
assert door is None, "Entering where no door is registered should not create a door"