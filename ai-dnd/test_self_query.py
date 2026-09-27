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

reset()

# Add NPC
game.world_state["npcs"].append({
    "id": "npc_001", "name": "TestNPC", "role": "Barmen",
    "location": "tavern", "personality": "", "appearance": "",
    "relationship": "neutral", "knowledge": [], "memory": [],
    "backstory": ""
})

# Test "benim adım ne?"
print("Testing 'benim adım ne?'")
result = game.run_player_turn("benim adım ne?", [{'role': 'system', 'content': 'test'}])
print(f"Action: {result['action_result'].get('action')}")
print(f"Direct response: {result['action_result'].get('direct_response')}")
print(f"Query type: {result['action_result'].get('query_type')}")
print(f"Narration: {result['narration'][:100]}")