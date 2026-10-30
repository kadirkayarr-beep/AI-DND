"""Selected Sorcerer Sorcery Point lifecycle; selected slot-to-points conversion, not slot creation/general Metamagic.

Optional world record: legacy absence is preserved except at actual first level2
application or completed Long Rest. Capacity follows applied choices, never raw XP.
"""
import copy

KEY = 'sorcery_points_v1'


def maximum(character):
    level = character.get('progression_level')
    if character.get('class') != 'Sorcerer' or type(level) is not int or not 2 <= level <= 5:
        return None
    import character_progression as cp
    return cp.capacity(character)['sorcery_points']


def validate(state, character, engine_format):
    maximum_value = maximum(character)
    if (type(engine_format) is not int or engine_format not in (4, 5, 6)
            or maximum_value is None or type(state) is not dict
            or set(state) != {'version', 'remaining'} or type(state['version']) is not int
            or state['version'] != 1 or type(state['remaining']) is not int
            or not 0 <= state['remaining'] <= maximum_value):
        raise ValueError('Invalid saved Sorcery Point state.')


def _format(session):
    import game
    return getattr(session, '_persisted_engine_format', game.SAVE_FORMAT_VERSION)


def advanced(session, new_character):
    """Pure projected state for the existing atomic progression commit."""
    import character_progression as cp
    old = session.character
    present = KEY in session.world_state
    if present:
        validate(session.world_state[KEY], old, _format(session))
        state = copy.deepcopy(session.world_state[KEY])
        state['remaining'] += maximum(new_character) - maximum(old)
        validate(state, new_character, _format(session))
        return state
    if cp.applied_level(old) == 1 and maximum(new_character) == 2 and _format(session) in (4, 5, 6):
        return {'version': 1, 'remaining': 2}
    return None


def prepare_restore(session):
    maximum_value = maximum(session.character)
    if KEY in session.world_state:
        validate(session.world_state[KEY], session.character, _format(session))
    if maximum_value is not None and _format(session) in (4, 5, 6):
        import character_progression as cp
        import spell_scope
        cp.validate_saved(session.character, session.world_state)
        spell_scope.validate(session.world_state.get('spellcasting_v1'), session.character)
        if type(session.world_state.get('spellcasting_v1')) is not dict:
            raise ValueError('Sorcery Point adoption requires actual spell state.')
        return maximum_value
    return None


def restore(session):
    maximum_value = prepare_restore(session)
    if maximum_value is not None:
        session.world_state[KEY] = {'version': 1, 'remaining': maximum_value}


def require_quickened(session):
    import action_economy as economy
    if KEY not in session.world_state:
        economy.fail('sorcery_points_unavailable', 'Complete a Long Rest to initialize this legacy Sorcery Point pool.')
    validate(session.world_state[KEY], session.character, _format(session))
    import character_progression as cp
    import spell_scope
    cp.validate_saved(session.character, session.world_state)
    spell_scope.validate(session.world_state.get('spellcasting_v1'), session.character)
    if type(session.world_state.get('spellcasting_v1')) is not dict:
        raise ValueError('Quickened Spell requires actual spell state.')
    if 'Quickened Spell' not in session.character.get('metamagic', []):
        economy.fail('metamagic_not_selected', 'Quickened Spell was not selected.')
    if session.world_state[KEY]['remaining'] < 2:
        economy.fail('sorcery_points_insufficient', 'Quickened Spell costs two Sorcery Points.')


def spend_quickened(session):
    require_quickened(session)
    session.world_state[KEY]['remaining'] -= 2


def projection(session):
    if KEY not in session.world_state:
        return None
    validate(session.world_state[KEY], session.character, _format(session))
    return {'current': session.world_state[KEY]['remaining'], 'max': maximum(session.character)}


def quickened_availability(session):
    if KEY not in session.world_state:
        return None
    import action_economy as economy
    from combat_lifecycle import CombatRequestError
    reason = None
    try:
        require_quickened(session)
        combat = session.world_state.get('combat', {})
        if not combat.get('active'):
            economy.fail('combat_required', 'Quickened Magic Missile requires active combat.')
        economy.validate_actor(session)
        resource = economy.ensure(session)['player']
        if resource['bonus_action_spent']:
            economy.fail('bonus_action_spent', 'The Bonus Action was already taken.')
        marker = [combat['combat_id'], combat['round'], resource['attack_turn_counter']]
        if session.world_state.get('spellcasting_v1', {}).get('slot_turn') == marker:
            economy.fail('spell_slot_turn_limit', 'A level-one-or-higher spell was already cast this turn.')
    except CombatRequestError as error:
        reason = error.code
    except ValueError:
        reason = 'invalid_sorcery_points_state'
    return {'available': reason is None, 'reason': reason}


def native_conversion_request(command):
    """Exact typed single conversion only; never prose/general model bypass."""
    if type(command) is not dict or set(command) != {'steps'}:
        return False
    steps = command['steps']
    if type(steps) is not list or len(steps) != 1 or type(steps[0]) is not dict:
        return False
    step = steps[0]
    return (set(step) <= {'kind', 'slot_level', 'resource'}
            and step.get('kind') == 'convert_spell_slot'
            and type(step.get('slot_level')) is int and 1 <= step['slot_level'] <= 3
            and step.get('resource', 'action') == 'action')


def _validate_conversion(session, slot_level):
    """Pure admission. No-action is not an Action budget/condition permission."""
    import action_economy as economy
    import character_progression as cp
    import spell_scope
    if type(slot_level) is not int or not 1 <= slot_level <= 3:
        economy.fail('invalid_conversion_slot', 'Choose one supported slot level, one through three.')
    if KEY not in session.world_state:
        economy.fail('sorcery_points_unavailable', 'Complete a Long Rest to initialize this legacy Sorcery Point pool.')
    validate(session.world_state[KEY], session.character, _format(session))
    cp.validate_saved(session.character, session.world_state)
    state = session.world_state.get('spellcasting_v1')
    spell_scope.validate(state, session.character)
    if type(state) is not dict:
        raise ValueError('Font of Magic requires actual spell state.')
    # Pure counterpart of the existing player death/presence guard. The combat
    # actor_data/present helper deliberately refuses outside combat.
    if (session.character.get('current_hp', 0) <= 0
            or session.world_state.get('player_combat_status', 'active') != 'active'
            or session.world_state.get('death_state', {}).get('dead', False)):
        economy.fail('actor_cannot_act', 'The player must be alive and present.')
    combat = session.world_state.get('combat', {})
    if combat.get('active'):
        if not economy.present(session, 'player'):
            economy.fail('actor_cannot_act', 'The player must be alive and present.')
        if combat.get('current_actor_id') != 'player':
            economy.fail('out_of_turn', 'Convert slots on the current player turn.')
        if combat.get('turn_resources', {}).get('player', {}).get('opportunity'):
            economy.fail('reaction_pending', 'Resolve or decline the pending reaction first.')
    if state['slots'].get(str(slot_level), 0) < 1:
        economy.fail('spell_slot_unavailable', 'No slot of that level remains.')
    if session.world_state[KEY]['remaining'] + slot_level > maximum(session.character):
        economy.fail('sorcery_points_capacity', 'This bounded conversion requires room for all gained points.')


def convert_slot(session, slot_level):
    """One slot→its level in points, no action and no casting marker change."""
    import initiative
    with initiative.atomic(session):
        _validate_conversion(session, slot_level)
        session.require_player_can_act()  # existing zero-HP/death consistency, not Action conditions
        session.world_state['spellcasting_v1']['slots'][str(slot_level)] -= 1
        session.world_state[KEY]['remaining'] += slot_level
        return {'slot_level': slot_level, 'slot_spent': 1, 'points_gained': slot_level,
                'points_remaining': session.world_state[KEY]['remaining']}


def conversion_options(session):
    """Pure current capability projection; historical receipts keep their own view."""
    if KEY not in session.world_state:
        return None
    import character_progression as cp
    from combat_lifecycle import CombatRequestError
    validate(session.world_state[KEY], session.character, _format(session))
    options = []
    for key in cp.slot_capacity(session.character):
        level = int(key)
        if not 1 <= level <= 3:
            continue
        reason = None
        try:
            _validate_conversion(session, level)
        except CombatRequestError as error:
            reason = error.code
        except ValueError:
            reason = 'invalid_conversion_state'
        options.append({'slot_level': level, 'points_gained': level,
                        'available': reason is None, 'reason': reason})
    return options
