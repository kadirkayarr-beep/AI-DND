with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the NPCs context block
old_block = '''"npcs": [
            {key: npc.get(key) for key in (
                "id", "name", "role", "personality", "appearance", "relationship",
                "knowledge", "backstory"
            ) if npc.get(key) not in (None, "", [])}
            | {"verified_npc_memory": _format_npc_memory(npc.get("memory", []))}
            for npc in npcs[:8]
        ],'''

new_block = '''"npcs": [
            {key: npc.get(key) for key in (
                "id", "name", "role", "personality", "appearance", "relationship",
                "knowledge", "backstory",
                "current_hp", "max_hp", "armor_class", "combat_status"
            ) if npc.get(key) not in (None, "", [])}
            | {"verified_npc_memory": _format_npc_memory(npc.get("memory", []))}
            for npc in npcs[:8]
        ],'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched build_world_context!")
else:
    print("Could not find the block to patch")
    # Debug
    idx = content.find('"npcs": [')
    if idx >= 0:
        print(f"Found at index {idx}")
        print(content[idx:idx+300])
    else:
        print("Not found at all")