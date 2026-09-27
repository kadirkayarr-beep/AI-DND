with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "find_weapon_in_inventory = game_namespace['find_weapon_in_inventory']\nWEAPONS = game_namespace['WEAPONS']\nensure_npc_combat_stats = game_namespace['ensure_npc_combat_stats']"
new = "find_weapon_in_inventory = game_namespace['find_weapon_in_inventory']\nWEAPONS = game_namespace['WEAPONS']\nensure_npc_combat_stats = game_namespace['ensure_npc_combat_stats']\nrun_turn = game_namespace['run_turn']"

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/test_combat.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    idx = content.find("ensure_npc_combat_stats = game_namespace")
    if idx >= 0:
        print(f'Found at index {idx}')
        print(repr(content[idx:idx+200]))
    else:
        print('Not found at all')