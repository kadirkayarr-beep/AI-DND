with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''# If combat still active and player is alive, trigger enemy response
        elif world_state["combat"]["active"] and world_state.get("player_combat_status") == "active":
            # Check if it's NPC's turn (advance turn after player's action)
            combat = world_state["combat"]
            if combat["initiative_order"] and combat["current_turn_index"] < len(combat["initiative_order"]):
                current_turn = combat["initiative_order"][combat["current_turn_index"]]
                if current_turn != "player":
                    # NPC's turn - resolve enemy attack
                    enemy_result = resolve_enemy_attack(target_npc)
                    
                    # Update player HP
                    if enemy_result.get("success") or enemy_result.get("outcome") in ("hit", "critical_hit"):
                        pass  # HP already updated in resolve_enemy_attack
                    
                    # Check if player died
                    if world_state.get("player_combat_status") != "active":
                        end_combat("player_defeated")
                        result_data["combat_ended"] = True
                        result_data["end_reason"] = "player_defeated"
                    
                    result_data["enemy_action"] = enemy_result
                    
                    # Advance turn
                    combat["current_turn_index"] = (combat["current_turn_index"] + 1) % len(combat["initiative_order"])
                    if combat["current_turn_index"] == 0:
                        combat["round"] += 1
                else:
                    # It's player's turn again (or end of round), just advance
                    combat["current_turn_index"] = (combat["current_turn_index"] + 1) % len(combat["initiative_order"])
                    if combat["current_turn_index"] == 0:
                        combat["round"] += 1'''

new = '''# If combat still active and player is alive, trigger enemy response
        elif world_state["combat"]["active"] and world_state.get("player_combat_status") == "active":
            # Check if it's NPC's turn (advance turn after player's action)
            combat = world_state["combat"]
            if combat["initiative_order"] and combat["current_turn_index"] < len(combat["initiative_order"]):
                # Advance turn after player's action
                combat["current_turn_index"] = (combat["current_turn_index"] + 1) % len(combat["initiative_order"])
                if combat["current_turn_index"] == 0:
                    combat["round"] += 1
                
                # Check if it's now NPC's turn
                if combat["current_turn_index"] < len(combat["initiative_order"]):
                    current_turn = combat["initiative_order"][combat["current_turn_index"]]
                    if current_turn != "player":
                        # NPC's turn - resolve enemy attack
                        enemy_result = resolve_enemy_attack(target_npc)
                        
                        # Update player HP
                        if enemy_result.get("success") or enemy_result.get("outcome") in ("hit", "critical_hit"):
                            pass  # HP already updated in resolve_enemy_attack
                        
                        # Check if player died
                        if world_state.get("player_combat_status") != "active":
                            end_combat("player_defeated")
                            result_data["combat_ended"] = True
                            result_data["end_reason"] = "player_defeated"
                        
                        result_data["enemy_action"] = enemy_result
                        
                        # Advance turn for next round
                        combat["current_turn_index"] = (combat["current_turn_index"] + 1) % len(combat["initiative_order"])
                        if combat["current_turn_index"] == 0:
                            combat["round"] += 1'''

if old in content:
    content = content.replace(old, new)
    with open('C:/Users/Kadir/Desktop/AI-DND/game.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched!')
else:
    print('Not found')