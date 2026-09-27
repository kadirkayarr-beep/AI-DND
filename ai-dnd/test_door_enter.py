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

with open(GAME_FILE, 'r', encoding='utf-8') as f:
    source = f.read()

exec(compile(source, str(GAME_FILE), 'exec'), {'__name__': 'game', '__file__': str(GAME_FILE), 'ollama': ollama_mock})
import game

def reset():
    game.world_state['location'] = 'tavern'
    game.world_state['npcs'] = []
    game.world_state['inventory'] = ['Macera çantası', 'Kılıç']
    game.world_state['ground_items'] = []
    game.world_state['doors'] = []
    game.world_state['containers'] = []
    game.world_state['features'] = []
    game.world_state['events'] = []
    game.world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
    game.world_state['next_npc_number'] = 1
    game.world_state['next_location_number'] = 1
    game.recent_dm_narrations.clear()

# Test 1: unlocked closed door + 'içeri giriyorum'
reset()
game.world_state['doors'].append({'name': 'Test Kapı', 'description': 'Test', 'locked': False, 'open': False, 'broken': False, 'location': 'tavern'})
result = game.run_player_turn('içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = game._current_door()
print('Test 1 - içeri giriyorum (unlocked):')
print(f'  door.open = {door["open"]}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')

# Test 2: unlocked closed door + 'kapıyı açıp içeri giriyorum'
reset()
game.world_state['doors'].append({'name': 'Test Kapı', 'description': 'Test', 'locked': False, 'open': False, 'broken': False, 'location': 'tavern'})
result = game.run_player_turn('kapıyı açıp içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = game._current_door()
print('Test 2 - kapıyı açıp içeri giriyorum (unlocked):')
print(f'  door.open = {door["open"]}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')

# Test 3: locked door + 'içeri giriyorum'
reset()
game.world_state['doors'].append({'name': 'Test Kapı', 'description': 'Test', 'locked': True, 'open': False, 'broken': False, 'location': 'tavern'})
result = game.run_player_turn('içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = game._current_door()
print('Test 3 - içeri giriyorum (locked):')
print(f'  door.open = {door["open"]}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')

# Test 4: no door + 'içeri giriyorum'
reset()
result = game.run_player_turn('içeri giriyorum', [{'role': 'system', 'content': 'test'}])
door = game._current_door()
print('Test 4 - içeri giriyorum (no door):')
print(f'  door = {door}')
print(f'  action = {result["action_result"].get("action")}')
print(f'  narration: {result["narration"][:80]}...')