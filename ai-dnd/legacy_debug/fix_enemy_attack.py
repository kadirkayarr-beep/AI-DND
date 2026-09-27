with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''def resolve_enemy_attack(target_npc):
    """Resolve enemy basic attack against player."""
    ensure_combat_state()
    ensure_npc_enemy_stats(target_npc)
    
    # Check if target is valid for combat
    if target_npc.get("combat_status") != "active":
        return {
            "action": "enemy_attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "actor": target_npc.get("id"),
            "target": "player",
            "reason": "Target not combat active"
        }
    
    # Check if player is combat active
    if world_state.get("player_combat_status") != "active":
        return {
            "action": "enemy_attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "actor": target_npc.get("id"),
            "target": "player",
            "reason": "Player not combat active"
        }
    
    # Roll enemy attack
    attack_roll = roll_d20()
    attack_bonus = target_npc.get("attack_bonus", 2)
    attack_total = attack_roll + attack_bonus
    target_ac = armor_class  # Player's AC
    
    # Natural 1 = auto miss
    if attack_roll == 1:
        outcome = "miss"
        critical = False
    # Natural 20 = critical hit
    elif attack_roll == 20:
        critical = True
        outcome = "critical_hit"
        damage_die = target_npc.get("damage_die", 6)
        damage_dice = target_npc.get("damage_dice", 1) * 2
        damage = roll_damage(damage_die, damage_dice, target_npc.get("damage_modifier", 0))
    # Normal hit/miss
    elif attack_roll + target_npc.get("attack_bonus", 2) >= armor_class:
        outcome = "hit"
        critical = False
        damage_die = target_npc.get("damage_die", 6)
        damage_dice = 1
        damage = roll_damage(target_npc.get("damage_die", 6), 1, target_npc.get("damage_modifier", 0))
    else:
        outcome = "miss"
        critical = False
        damage = 0
    
    # Apply damage to player
    player_hp_before = current_hp
    player_hp_after = current_hp
    
    if outcome in ("hit", "critical_hit"):
        damage = max(1, damage)
        current_hp = max(0, current_hp - damage)
        
        # Check if unconscious
        if current_hp <= 0:
            world_state["player_combat_status"] = "unconscious"
    
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
        "target_ac": armor_class,
        "critical": attack_roll == 20,
        "damage": damage if outcome in ("hit", "critical_hit") else 0,
        "target_hp_before": damage + max(0, current_hp),
        "target_hp_after": max(0, current_hp),
    }'''

new = '''def resolve_enemy_attack(target_npc):
    """Resolve enemy basic attack against player."""
    ensure_combat_state()
    ensure_npc_enemy_stats(target_npc)
    
    # Check if target is valid for combat
    if target_npc.get("combat_status") != "active":
        return {
            "action": "enemy_attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "actor": target_npc.get("id"),
            "target": "player",
            "reason": "Target not combat active"
        }
    
    # Check if player is combat active
    if world_state.get("player_combat_status") != "active":
        return {
            "action": "enemy_attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "actor": target_npc.get("id"),
            "target": "player",
            "reason": "Player not combat active"
        }
    
    # Roll enemy attack
    attack_roll = roll_d20()
    attack_bonus = target_npc.get("attack_bonus", 2)
    attack_total = attack_roll + attack_bonus
    target_ac = globals().get("armor_class", 10)  # Player's AC
    
    # Natural 1 = auto miss
    if attack_roll == 1:
        outcome = "miss"
        critical = False
    # Natural 20 = critical hit
    elif attack_roll == 20:
        critical = True
        outcome = "critical_hit"
        damage_die = target_npc.get("damage_die", 6)
        damage_dice = target_npc.get("damage_dice", 1) * 2
        damage = roll_damage(damage_die, damage_dice, target_npc.get("damage_modifier", 0))
    # Normal hit/miss
    elif attack_roll + target_npc.get("attack_bonus", 2) >= globals().get("armor_class", 10):
        outcome = "hit"
        critical = False
        damage_die = target_npc.get("damage_die", 6)
        damage_dice = 1
        damage = roll_damage(target_npc.get("damage_die", 6), 1, target_npc.get("damage_modifier", 0))
    else:
        outcome = "miss"
        critical = False
        damage = 0
    
    # Apply damage to player
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

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')