with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''# Apply damage to player
    player_hp_before = globals().get("current_hp", 10)
    player_hp_after = globals().get("current_hp", 10)
    
    if outcome in ("hit", "critical_hit"):
        damage = max(1, damage)
        # Update global current_hp
        new_hp = max(0, globals().get("current_hp", 10) - damage)
        globals()["current_hp"] = new_hp
        player_hp_after = new_hp
        
        # Check if unconscious
        if new_hp <= 0:
            world_state["player_combat_status"] = "unconscious"
    else:
        player_hp_after = globals().get("current_hp", 10)
    
    outcome_mapping = {
        "hit": "hit",
        "critical_hit": "critical_hit",
        "miss": "miss"
    }
    
    return {
        "action": "enemy_attack",
        "status": "resolved",
        "success": outcome in ("hit", "critical_hit"),
        "outcome": outcome,
        "actor": "npc",
        "target": "player",
        "attack_roll": attack_roll,
        "attack_bonus": target_npc.get("attack_bonus", 2),
        "attack_total": attack_roll + target_npc.get("attack_bonus", 2),
        "target_ac": globals().get("armor_class", 10),
        "critical": attack_roll == 20,
        "damage": damage if outcome in ("hit", "critical_hit") else 0,
        "target_hp_before": damage + max(0, globals().get("current_hp", 10)),
        "target_hp_after": max(0, globals().get("current_hp", 10)),
    }'''

new = '''# Apply damage to player
    player_hp_before = globals().get("current_hp", 10)
    player_hp_after = globals().get("current_hp", 10)
    damage = 0
    
    if outcome in ("hit", "critical_hit"):
        damage = max(1, damage)
        # Update global current_hp
        new_hp = max(0, globals().get("current_hp", 10) - damage)
        globals()["current_hp"] = new_hp
        player_hp_after = new_hp
        
        # Check if unconscious
        if new_hp <= 0:
            world_state["player_combat_status"] = "unconscious"
    else:
        player_hp_after = globals().get("current_hp", 10)
    
    outcome_mapping = {
        "hit": "hit",
        "critical_hit": "critical_hit",
        "miss": "miss"
    }
    
    return {
        "action": "enemy_attack",
        "status": "resolved",
        "success": outcome in ("hit", "critical_hit"),
        "outcome": outcome,
        "actor": "npc",
        "target": "player",
        "attack_roll": attack_roll,
        "attack_bonus": target_npc.get("attack_bonus", 2),
        "attack_total": attack_roll + target_npc.get("attack_bonus", 2),
        "target_ac": globals().get("armor_class", 10),
        "critical": attack_roll == 20,
        "damage": damage if outcome in ("hit", "critical_hit") else 0,
        "target_hp_before": damage + max(0, globals().get("current_hp", 10)),
        "target_hp_after": max(0, globals().get("current_hp", 10)),
    }'''

with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')
    idx = content.find('player_hp_before = globals().get("current_hp", 10)')
    if idx >= 0:
        print(f'Found at index {idx}')
        print(content[idx:idx+500])
    else:
        print('Not found')