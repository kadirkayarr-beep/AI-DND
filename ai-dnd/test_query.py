import sys
import io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
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

reset()

# Test "senin adın ne?"
result = session.run_player_turn('senin adın ne?', [{'role': 'system', 'content': 'test'}])
print(f"Action: {result['action_result'].get('action')}")
print(f"Direct response: {result['action_result'].get('direct_response')}")
print(f"Narration: {result['narration']}")