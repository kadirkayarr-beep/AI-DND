with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """# Test J: Full pipeline cross-location
print("\nTEST J: Full pipeline cross-location attack")
reset_world_state()
npc = add_npc("Gromm", "Barmen", hp=10, ac=10)
# Move NPC to forest, player in tavern
world_state['npcs'][0]['location'] = 'forest'
world_state['location'] = 'tavern'
hp_before = world_state['npcs'][0]['current_hp']
# Try to attack through full pipeline
result = run_turn("Gromm'a kılıcımla saldırıyorum")
ar = result["action_result"]
hp_after = world_state['npcs'][0]['current_hp']
# Should fail gracefully
assert ar.get("action") == "attack", f"Action should be attack, got {ar.get('action')}"
assert ar.get("success") == False, "Attack should fail"
assert hp_after == hp_before, f"HP should not change (was {hp_before}, now {hp_after})"
print(f"  Action: {ar.get('action')}, Status: {ar.get('status')}, Success: {ar.get('success')}")
print(f"  HP before: {hp_before}, HP after: {hp_after} -> PASS")"""

new = """# Test J: Full pipeline cross-location attack
print("\nTEST J: Full pipeline cross-location attack")
reset_world_state()
add_npc()
# Move NPC to forest, player in tavern
world_state['npcs'][0]['location'] = 'forest'
world_state['location'] = 'tavern'
hp_before = world_state['npcs'][0]['current_hp']
# Try to attack through full pipeline
messages = [{"role": "system", "content": "test"}]
result = run_player_turn("Gromm'a kılıcımla saldırıyorum", messages)
ar = result["action_result"]
hp_after = world_state['npcs'][0]['current_hp']
# Should fail gracefully
assert ar.get("action") == "attack", f"Action should be attack, got {ar.get('action')}"
assert ar.get("success") == False, "Attack should fail"
assert hp_after == hp_before, f"HP should not change (was {hp_before}, now {hp_after})"
print(f"  Action: {ar.get('action')}, Status: {ar.get('status')}, Success: {ar.get('success')}")
print(f"  HP before: {hp_before}, HP after: {hp_after} -> PASS")"""

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    idx = content.find('Test J: Full pipeline')
    if idx >= 0:
        print(f'Found at index {idx}')
    else:
        print('Not found at all')