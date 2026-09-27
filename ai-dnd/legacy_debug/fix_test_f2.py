with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """# Test F: Wrong location
print("\nTEST F: Wrong location - NPC in different location")
reset_world_state()
npc = add_npc("Test", "Dummy", hp=10, ac=10)
world_state['npcs'][0]['location'] = 'forest'
world_state['location'] = 'tavern'
weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
target = resolve_combat_target("test", npc)  # Should fail - different location
print(f"  Target resolved: {target}")
# The target should be None or fail because NPC is in different location
# Actually resolve_combat_target uses resolve_npc_reference which checks location
print("  (Target resolution handles location mismatch)")"""

new = """# Test F: Wrong location
print("\nTEST F: Wrong location - NPC in different location")
reset_world_state()
npc = add_npc("Test", "Dummy", hp=10, ac=10)
world_state['npcs'][0]['location'] = 'forest'
world_state['location'] = 'tavern'
weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
target = resolve_combat_target("test", npc)  # Should fail - different location
assert target is None, "NPC in different location should not be a valid target"
print(f"  Target resolved: {target} -> PASS")"""

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    idx = content.find("TEST F: Wrong location")
    if idx >= 0:
        print(f'Found at index {idx}')
        print(content[idx:idx+200])
    else:
        print('Not found at all')