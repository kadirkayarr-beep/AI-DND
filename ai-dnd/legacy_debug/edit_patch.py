import re

with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the unsupported action block
old_block = '''if intent_type in {"attack", "combat", "rest", "use_item"}:
        result.update({
            "success": False,
            "status": "unsupported",
            "direct_response": "Bu eylem için henüz bir Python kuralı tanımlı değil; dünya durumu değişmedi.",
            "state_changes": [],
        })
    else:
        result.update({"action": "dialogue" if intent_type == "dialogue" else intent_type, "state_changes": []})
    return result'''

new_block = '''if intent_type in {"attack", "combat"}:
        # Handle combat attack
        weapon_name, weapon_data = find_weapon_in_inventory("Kılıç")
        if not weapon_name:
            result.update({
                "action": "attack",
                "success": False,
                "status": "resolved",
                "outcome": "no_weapon",
                "direct_response": "Savaşmak için elinde bir silah olmalı. Envanterinde Kılıç yok.",
                "state_changes": [],
            })
            return result
        
        target_npc = resolve_combat_target(player_input, npc_target)
        if target_npc == "ambiguous":
            result.update({
                "action": "attack",
                "success": False,
                "status": "clarification",
                "direct_response": "Hangi hedefe saldırıyorsun? Birden fazla olası hedef var.",
                "state_changes": [],
            })
            return result
        elif not target_npc:
            result.update({
                "action": "attack",
                "success": False,
                "status": "resolved",
                "outcome": "no_target",
                "direct_response": "Saldıracağın bir hedef belirtmelisin.",
                "state_changes": [],
            })
            return result
        
        # Resolve the attack
        attack_result = resolve_attack(player_input, weapon_name, WEAPONS[weapon_name], target_npc)
        attack_result["state_changes"] = _changed_state_fields(before)
        return attack_result
    
    elif intent_type in {"rest", "use_item"}:
        result.update({
            "success": False,
            "status": "unsupported",
            "direct_response": "Bu eylem için henüz bir Python kuralı tanımlı değil; dünya durumu değişmedi.",
            "state_changes": [],
        })
    else:
        result.update({"action": "dialogue" if intent_type == "dialogue" else intent_type, "state_changes": []})
    return result'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched!")
else:
    print("Could not find the block to patch")
    # Debug: find similar text
    idx = content.find('if intent_type in {"attack"')
    if idx >= 0:
        print(f"Found at index {idx}")
        print(content[idx:idx+500])
    else:
        print("Not found at all")