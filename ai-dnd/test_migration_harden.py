import sys
import io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
from unittest.mock import MagicMock

ollama_mock = MagicMock()
ollama_mock.chat.return_value = {
    "message": {"content": '{"intent":"narrative","action":"test","target":{"type":"none","reference":""},"completion":"unclear","confidence":0.5}'}
}
sys.modules['ollama'] = ollama_mock

with open(PROJECT_DIR / 'game.py', 'r', encoding='utf-8') as f:
    source = f.read()

exec(compile(source, 'game.py', 'exec'), {'__name__': 'game', '__file__': 'game.py', 'ollama': ollama_mock})
import game

print("=== Testing Legacy Migration Hardening ===")

# Scenario: ground_items_by_location key completely missing
game.world_state['location'] = 'tavern'
game.world_state['npcs'] = []
game.world_state['inventory'] = ['Macera çantası', 'Kılıç']
game.world_state['ground_items'] = ['Kılıç', 'Kalkan']
game.world_state['doors'] = []
game.world_state['containers'] = []
game.world_state['features'] = []
game.world_state['events'] = []
game.world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
game.world_state['next_npc_number'] = 1
game.world_state['next_location_number'] = 1

# Remove ground_items_by_location entirely (simulate legacy state)
if 'ground_items_by_location' in game.world_state:
    del game.world_state['ground_items_by_location']

print(f"Before migration:")
print(f"  ground_items: {game.world_state.get('ground_items')}")
print(f"  ground_items_by_location: {'MISSING' if 'ground_items_by_location' not in game.world_state else game.world_state.get('ground_items_by_location')}")

# This should NOT crash
game._normalize_ground_items()

print(f"After migration:")
print(f"  ground_items: {game.world_state.get('ground_items')}")
print(f"  ground_items_by_location: {game.world_state.get('ground_items_by_location')}")

# Verify
assert game.world_state['ground_items'] == [], "Legacy list should be empty"
assert 'tavern' in game.world_state['ground_items_by_location'], "Should have tavern key"
assert 'Kılıç' in game.world_state['ground_items_by_location']['tavern'], "Kılıç should be in tavern"
assert 'Kalkan' in game.world_state['ground_items_by_location']['tavern'], "Kalkan should be in tavern"

print("\n✅ Legacy migration hardening works!")

# Test duplicate prevention - call again
game._normalize_ground_items()
assert len(game.world_state['ground_items_by_location']['tavern']) == 2, "Should not duplicate"
print("✅ No duplicates on repeated calls!")

# Test that calling with already normalized state is no-op
game._normalize_ground_items()
game._normalize_ground_items()
assert len(game.world_state['ground_items_by_location']['tavern']) == 2, "Should still be 2"
print("✅ Idempotent - no-op when already normalized!")