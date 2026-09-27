def find_weapon_in_inventory():
    """Find a usable weapon in player inventory."""
    for item in world_state.get("inventory", []):
        for weapon_name, weapon_data in WEAPONS.items():
            if item.casefold() == weapon_name.casefold() or any(item.casefold() == alias.casefold() for alias in weapon_data.get("aliases", [])):
                return weapon_name, weapon_data
    return None, None


def calculate_attack_bonus():
    """Calculate player's melee attack bonus."""
    return strength_mod + proficiency_bonus


def roll_attack():
    """Roll d20 for attack."""
    return roll_d20()


def roll_damage(damage_die, damage_dice, ability_mod):
    """Roll damage dice."""
    total = 0
    for _ in range(damage_dice):
        total += random.randint(1, damage_die)
    return total + ability_mod


def resolve_combat_target(player_input, npc_target=None):
    """Resolve the combat target from player input or current NPC target."""
    # If explicit NPC target from reference resolution, use it
    if npc_target:
        ensure_npc_combat_stats(npc_target)
        return npc_target
    
    # Try to resolve NPC reference from player input
    resolution = resolve_npc_reference(player_input)
    if resolution["status"] == "found":
        ensure_npc_combat_stats(resolution["npc"])
        return resolution["npc"]
    elif resolution["status"] == "ambiguous":
        return "ambiguous"
    
    return None


def resolve_attack(player_input, weapon_name, weapon_data, target_npc):
    """Resolve a melee attack against a target NPC."""
    ensure_npc_combat_stats(target_npc)
    
    # Check if target is valid for combat
    if target_npc.get("combat_status") != "active":
        return {
            "action": "attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "target_id": target_npc.get("id"),
            "target_name": target_npc.get("name"),
            "reason": "Target not combat active"
        }
    
    # Roll attack
    attack_roll = roll_attack()
    attack_bonus = calculate_attack_bonus()
    attack_total = attack_roll + attack_bonus
    target_ac = target_npc.get("armor_class", 10)
    
    # Natural 1 = auto miss
    if attack_roll == 1:
        outcome = "miss"
        critical = False
    # Natural 20 = critical hit
    elif attack_roll == 20:
        critical = True
        outcome = "critical_hit"
        damage_die = WEAPONS[weapon_name]["damage_die"]
        damage_dice = WEAPONS[weapon_name]["damage_dice"] * 2
        ability_mod = globals().get(f"{WEAPONS[weapon_name]['ability']}_mod", 0)
        damage = roll_damage(damage_die, damage_dice, ability_mod)
    # Normal hit/miss
    elif attack_total >= target_ac:
        outcome = "hit"
        critical = False
        damage_die = WEAPONS[weapon_name]["damage_die"]
        damage_dice = WEAPONS[weapon_name]["damage_dice"]
        ability_mod = globals().get(f"{WEAPONS[weapon_name]['ability']}_mod", 0)
        damage = roll_damage(damage_die, damage_dice, ability_mod)
    else:
        outcome = "miss"
        critical = False
        damage = 0
    
    # Apply damage if hit
    target_hp_before = target_npc.get("current_hp", target_npc.get("max_hp", 10))
    target_hp_after = target_hp_before
    
    if outcome in ("hit", "critical_hit"):
        damage = max(1, damage)  # Minimum 1 damage
        target_hp_after = max(0, target_hp_before - damage)
        target_npc["current_hp"] = target_hp_after
        
        # Check if unconscious
        if target_hp_after <= 0:
            target_npc["combat_status"] = "unconscious"
    
    outcome_mapping = {
        "hit": "hit",
        "critical_hit": "critical_hit",
        "miss": "miss"
    }
    
    return {
        "action": "attack",
        "status": "resolved",
        "success": outcome in ("hit", "critical_hit"),
        "outcome": outcome_mapping.get(outcome, outcome),
        "target_id": target_npc.get("id"),
        "target_name": target_npc.get("name"),
        "weapon": weapon_name,
        "attack_roll": attack_roll,
        "attack_bonus": attack_bonus,
        "attack_total": attack_total,
        "target_ac": target_ac,
        "critical": critical,
        "damage": damage if outcome in ("hit", "critical_hit") else 0,
        "target_hp_before": target_hp_before,
        "target_hp_after": target_hp_after,
        "target_status": target_npc.get("combat_status", "active")
    }