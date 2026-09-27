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

# Test legacy format migration
print("=== Testing Legacy Format Migration ===")

# Reset with legacy format
game.world_state['location'] = 'tavern'
game.world_state['npcs'] = []
game.world_state['inventory'] = ['Macera çantası', 'Kılıç']
game.world_state['ground_items'] = ['Kılıç', 'Kalkan']  # Legacy format
game.world_state['ground_items_by_location'] = {}
game.world_state['doors'] = []
game.world_state['containers'] = []
game.world_state['features'] = []
game.world_state['events'] = []
game.world_state['flags'] = {'last_npc_id': None, 'active_npc_id': None, 'active_npc_until_turn': -1, 'turn_index': 0, 'pending_destination': None}
game.world_state['next_npc_number'] = 1
game.world_state['next_location_number'] = 1

print(f"Before migration:")
print(f"  ground_items (legacy): {game.world_state['ground_items']}")
print(f"  ground_items_by_location: {game.world_state['ground_items_by_location']}")

# Call normalization
game._normalize_ground_items()

print(f"After migration:")
print(f"  ground_items (legacy): {game.world_state['ground_items']}")
print(f"  ground_items_by_location: {game.world_state['ground_items_by_location']}")

# Verify items moved to current location (tavern)
assert game.world_state['ground_items'] == [], "Legacy list should be empty"
assert 'tavern' in game.world_state['ground_items_by_location'], "Should have tavern key"
assert 'Kılıç' in game.world_state['ground_items_by_location']['tavern'], "Kılıç should be in tavern"
assert 'Kalkan' in game.world_state['ground_items_by_location']['tavern'], "Kalkan should be in tavern"

print("\n✅ Legacy migration works correctly!")

# Test that items don't appear in other locations
game.world_state['location'] = 'forest'
game._normalize_ground_items()  # Should not duplicate items
print(f"\nAfter location change to forest:")
print(f"  ground_items_by_location: {game.world_state['ground_items_by_location']}")
assert 'forest' not in game.world_state['ground_items_by_location'] or game.world_state['ground_items_by_location'].get('forest') == [], "Forest should not have items"

print("✅ Items don't leak to other locations!")