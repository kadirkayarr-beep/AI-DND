with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''# Reject Qwen attempts to modify combat state (Python owns combat mechanics)
            forbidden_combat_keys = {"max_hp", "current_hp", "armor_class", "combat_status", "hp", "ac"}
            for key in list(proposal.keys()):
                if key in forbidden_combat_keys:
                    continue
            result["update_npcs"].append(update)'''

new = '''# Reject Qwen attempts to modify combat state (Python owns combat mechanics)
            forbidden_combat_keys = {"max_hp", "current_hp", "armor_class", "combat_status", "hp", "ac",
                                    "attack_bonus", "damage_die", "damage_dice", "damage_modifier",
                                    "combat", "player_combat_status", "initiative_order", "round",
                                    "current_turn_index", "participants", "target_id"}
            for key in list(proposal.keys()):
                if key in forbidden_combat_keys:
                    continue
            result["update_npcs"].append(update)'''

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')