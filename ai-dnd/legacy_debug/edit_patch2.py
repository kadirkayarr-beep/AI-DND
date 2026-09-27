import re

with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the update_npcs block
old_block = '''if isinstance(updates.get("update_npcs"), list):
        existing_by_id = {npc.get("id"): npc for npc in world_state["npcs"]}
        for proposal in updates["update_npcs"][:4]:
            if not isinstance(proposal, dict) or proposal.get("id") not in existing_by_id:
                continue
            existing_npc = existing_by_id[proposal["id"]]
            update = {"id": proposal["id"]}
            for key, limit in (("personality", 180), ("appearance", 180), ("backstory", 240), ("relationship", 40)):
                value = _clean_world_text(proposal.get(key), limit)
                if value and not _has_unregistered_person_name(value, (existing_npc.get("name", ""),)):
                    update[key] = value
            for key in ("knowledge",):
                if key in proposal:
                    additions = [
                        value for value in _clean_world_text_list(proposal[key], 180, 8)
                        if not _has_unregistered_person_name(value, (existing_npc.get("name", ""),))
                    ]
                    if additions:
                        update[key] = additions
            result["update_npcs"].append(update'''

new_block = '''if isinstance(updates.get("update_npcs"), list):
        existing_by_id = {npc.get("id"): npc for npc in world_state["npcs"]}
        for proposal in updates["update_npcs"][:4]:
            if not isinstance(proposal, dict) or proposal.get("id") not in existing_by_id:
                continue
            existing_npc = existing_by_id[proposal["id"]]
            update = {"id": proposal["id"]}
            for key, limit in (("personality", 180), ("appearance", 180), ("backstory", 240), ("relationship", 40)):
                value = _clean_world_text(proposal.get(key), limit)
                if value and not _has_unregistered_person_name(value, (existing_npc.get("name", ""),)):
                    update[key] = value
            for key in ("knowledge",):
                if key in proposal:
                    additions = [
                        value for value in _clean_world_text_list(proposal[key], 180, 8)
                        if not _has_unregistered_person_name(value, (existing_npc.get("name", ""),))
                    ]
                    if additions:
                        update[key] = additions
            # Reject Qwen attempts to modify combat state (Python owns combat mechanics)
            forbidden_combat_keys = {"max_hp", "current_hp", "armor_class", "combat_status", "hp", "ac"}
            for key in list(proposal.keys()):
                if key in forbidden_combat_keys:
                    continue
            result["update_npcs"].append(update'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched!")
else:
    print("Could not find the block to patch")
    # Debug: find similar text
    idx = content.find('if isinstance(updates.get("update_npcs")')
    if idx >= 0:
        print(f"Found at index {idx}")
        print(content[idx:idx+500])
    else:
        print("Not found at all")