"""Selected known-unarmored Barbarian1–5 Rage, not complete class support.

PHB gives end-next-turn and600s maximum. The soft12s/own-END−6 bridge is an
explicit engine convention: exact outside seconds survive combat reentry.
"""
from dataclasses import dataclass
import json

from combat_lifecycle import CombatRequestError, player_incapacitated

KEY = 'rage_v1'
PROOF = 'worn_armor_v1'


def _format(session):
    import game
    return getattr(session,'_persisted_engine_format',game.SAVE_FORMAT_VERSION)


def _level(character, world=None):
    value=character.get('progression_level',1)
    raw=character.get('level')
    if not (character.get('class')=='Barbarian' and type(value) is int and value in (1,2,3,4,5)
            and type(raw) is int and value<=raw<=20):
        return None
    if value in (3,4,5):
        import character_progression
        if not character_progression.berserker_eligible(character, world):
            return None
    return value


def capacity(character, world=None):
    level = _level(character, world)
    if level is None:
        raise ValueError('Invalid Rage capacity level.')
    return 3 if level in (3,4,5) else 2


def _boundary(value):
    return (type(value) is dict and set(value)=={'combat_id','turn'}
            and type(value['combat_id']) is str and bool(value['combat_id'])
            and type(value['turn']) is int and value['turn']>=0)


def validate(world,character,engine_format,*,strict_active=False):
    import equipment_economy
    equipment_economy.validate_worn_armor(world,character,engine_format)
    if KEY not in world:return
    value=world[KEY]
    if (type(engine_format) is not int or engine_format not in (4,5,6) or _level(character,world) is None
            or PROOF not in world or type(value) is not dict or set(value)!={'version','remaining','active'}
            or type(value['version']) is not int or value['version']!=1
            or type(value['remaining']) is not int or not 0<=value['remaining']<=capacity(character,world)):
        raise ValueError('Invalid saved Rage state.')
    a=value['active']
    if a is None:return
    if (type(a) is not dict or set(a)!={'started_at','remaining_seconds','settled_at','last_end','last_extended_turn'}
            or any(type(a[k]) is not int for k in ('started_at','remaining_seconds','settled_at'))
            or not 1<=a['remaining_seconds']<=12 or not 0<=a['started_at']<=a['settled_at']
            or (a['last_end'] is not None and not _boundary(a['last_end']))
            or not _boundary(a['last_extended_turn'])):
        raise ValueError('Invalid active Rage state.')
    import campaign_time
    clock=world.get('campaign_time');campaign_time.validate_clock(clock)
    now=clock['elapsed_seconds']
    if a['settled_at']>now:raise ValueError('Rage time is ahead of the canonical clock.')
    outside_expired=(not world.get('combat',{}).get('active')
                     and a['remaining_seconds']<=now-a['settled_at'])
    if strict_active and (now>=a['started_at']+600 or outside_expired or player_incapacitated(character,world)):
        raise ValueError('Expired or incapacitated Rage must be settled before saving.')


def initialize(session,*,known_unarmored):
    """Creation owner only. Never adopt on preview/load/rest."""
    world=session.world_state
    world.pop(KEY,None);world.pop(PROOF,None)
    if _level(session.character,session.world_state) is not None and known_unarmored and _format(session) in (4,5,6):
        import equipment_economy
        equipment_economy.initialize_unarmored_proof(session)
        world[KEY]={'version':1,'remaining':2,'active':None}


def _state(session):
    validate(session.world_state,session.character,_format(session))
    return session.world_state.get(KEY)


def active(session):
    state=_state(session)
    if state is None or state['active'] is None:return False
    a=state['active'];now=session.world_state['campaign_time']['elapsed_seconds']
    outside=not session.world_state.get('combat',{}).get('active')
    return (not player_incapacitated(session.character,session.world_state)
            and now<a['started_at']+600
            and (not outside or a['remaining_seconds']>now-a['settled_at']))


def settle(session,*,combat_active=None):
    state=_state(session)
    if state is None or state['active'] is None:return
    a=state['active'];now=session.world_state['campaign_time']['elapsed_seconds']
    if now>=a['started_at']+600 or player_incapacitated(session.character,session.world_state):
        state['active']=None;return
    mode=session.world_state.get('combat',{}).get('active',False) if combat_active is None else combat_active
    if not mode:a['remaining_seconds']-=now-a['settled_at']
    a['settled_at']=now
    if a['remaining_seconds']<=0:state['active']=None


def end(session):
    """Terminal status owner hook, no restoration when the condition clears."""
    state=_state(session)
    if state is not None:state['active']=None


def _turn(session):
    c=session.world_state.get('combat',{})
    return {'combat_id':c.get('combat_id'),'turn':c.get('turn_resources',{}).get('player',{}).get('attack_turn_counter',0)}


def end_player_turn(session,combat_id,turn):
    settle(session,combat_active=True)
    state=_state(session)
    if state is None or state['active'] is None:return
    identity={'combat_id':combat_id,'turn':turn}
    if not _boundary(identity):raise ValueError('Invalid Rage turn boundary.')
    a=state['active']
    if a['last_end']==identity:return
    a['last_end']=identity;a['remaining_seconds']-=6
    if a['remaining_seconds']<=0:state['active']=None


def _reason(session,extend=False):
    import action_economy as economy
    state=_state(session)
    if state is None:return 'rage_not_adopted'
    c=session.world_state.get('combat',{})
    if not c.get('active') or c.get('current_actor_id')!='player':return 'rage_current_combat_turn_required'
    if player_incapacitated(session.character,session.world_state):return 'rage_incapacitated'
    if 'concentration' in session.character:return 'rage_concentration_state_unsupported'
    r=c.get('turn_resources',{}).get('player',{})
    if r.get('opportunity'):return 'reaction_pending'  # pure projection, no ensure() mutation
    if r.get('bonus_action_spent'):return 'bonus_action_spent'
    if not _boundary(_turn(session)):return 'rage_turn_state_invalid'
    if 'campaign_time' not in session.world_state:return 'rage_clock_required'
    if extend:
        if not active(session):return 'rage_not_active'
        if state['active']['last_extended_turn']==_turn(session):return 'rage_already_extended_this_turn'
    else:
        if active(session):return 'rage_already_active'
        if state['remaining']<=0:return 'rage_uses_exhausted'
    return None


def projection(session):
    try:
        state=_state(session)
        if state is None:return None
        enabled=active(session)
        a=state['active']
        remaining=None
        if enabled:
            remaining=a['remaining_seconds']
            if not session.world_state.get('combat',{}).get('active'):
                remaining-=session.world_state['campaign_time']['elapsed_seconds']-a['settled_at']
        activate_reason=_reason(session);extend_reason=_reason(session,True)
        return {'uses_remaining':state['remaining'],'max_uses':capacity(session.character,session.world_state),'active':enabled,'remaining_seconds':remaining,
                'activate':{'available':activate_reason is None,'reason':activate_reason},
                'extend':{'available':extend_reason is None,'reason':extend_reason}}
    except ValueError:
        return None


def activate(session):
    from initiative import atomic
    import action_economy
    with atomic(session):
        settle(session)
        reason=_reason(session)
        if reason:raise CombatRequestError(reason,'Rage activation is unavailable: '+reason)
        action_economy.consume_feature_bonus(session)
        state=_state(session);now=session.world_state['campaign_time']['elapsed_seconds']
        state['remaining']-=1
        state['active']={'started_at':now,'remaining_seconds':12,'settled_at':now,
                         'last_end':None,'last_extended_turn':_turn(session)}
        return {'active':True,'uses_remaining':state['remaining'],'remaining_seconds':12}


def extend(session):
    from initiative import atomic
    import action_economy
    with atomic(session):
        settle(session)
        reason=_reason(session,True)
        if reason:raise CombatRequestError(reason,'Rage extension is unavailable: '+reason)
        action_economy.consume_feature_bonus(session)
        a=_state(session)['active'];a['remaining_seconds']=12;a['last_extended_turn']=_turn(session)
        return {'active':True,'uses_remaining':_state(session)['remaining'],'remaining_seconds':12}


def native_command(command):
    if type(command) is not dict or set(command)!={'steps'} or type(command['steps']) is not list or len(command['steps'])!=1:return False
    step=command['steps'][0]
    return (type(step) is dict and set(step)=={'kind','resource'}
            and step['kind'] in ('activate_rage','extend_rage') and step['resource']=='bonus')


def observe_enemy_roll_or_save(session,target_id):
    settle(session)
    if not active(session):return
    c=session.world_state.get('combat',{})
    if not c.get('active') or c.get('current_actor_id')!='player':return
    from effect_targeting import EffectSpec,eligible_effect_targets
    if target_id not in eligible_effect_targets(session,'player',EffectSpec(effect_id='rage_extension',range_ft=None,source_ref='PHB2024:Barbarian:Rage',excludes_allies=True)):return
    a=_state(session)['active'];identity=_turn(session)
    if a['last_extended_turn']!=identity:
        a['remaining_seconds']=12;a['last_extended_turn']=identity


def damage_bonus(session,ability):
    return 2 if ability=='strength' and active(session) else 0


def strength_advantage(session,actor,ability):
    return actor=='player' and ability=='strength' and active(session)


def resistance_types(session,target):
    return {'bludgeoning','piercing','slashing'} if target=='player' and active(session) else set()


def prepare_restore(session):
    _state(session)


def restore(session,kind):
    settle(session)
    state=_state(session)
    if state is not None:
        maximum=capacity(session.character,session.world_state)
        state['remaining']=min(maximum,state['remaining']+1) if kind=='short_rest' else maximum


PRIMAL_KNOWLEDGE_SKILLS = ('Acrobatics', 'Intimidation', 'Perception', 'Stealth', 'Survival')


def primal_knowledge_reason(session):
    """Pure selected-engine entitlement and current-Rage check, not a saved grant."""
    import character_progression
    if not character_progression.berserker_eligible(session.character, session.world_state):
        return 'primal_knowledge_not_selected'
    try:
        if not active(session):
            return 'primal_knowledge_rage_required'
    except (ValueError, TypeError, KeyError):
        return 'primal_knowledge_rage_invalid'
    if session.world_state.get('combat', {}).get('active'):
        return 'primal_knowledge_immediate_check_only'
    return None


def require_primal_knowledge(session, skill, check_feature):
    if type(check_feature) is not str or check_feature != 'primal_knowledge':
        raise CombatRequestError('invalid_check_feature', 'Unknown check feature.', 400)
    if type(skill) is not str or skill not in PRIMAL_KNOWLEDGE_SKILLS:
        raise CombatRequestError('primal_knowledge_skill_unsupported', 'This skill cannot use Primal Knowledge.', 400)
    reason = primal_knowledge_reason(session)
    if reason:
        raise CombatRequestError(reason, 'Primal Knowledge is unavailable: ' + reason, 400)


@dataclass(frozen=True)
class _PrimalKnowledgeEvidence:
    """At-roll in-process provenance, never a request, save, or model field."""
    action_id: str | None
    resolution_id: str | None
    skill: str
    original_ability: str
    ability_modifier: int
    rage_activation: tuple
    resolution_json: str


def record_primal_knowledge(session, result):
    """Called only by the check owner after its active-Rage roll completes."""
    import game
    state = session.world_state[KEY]['active']
    boundary = state['last_extended_turn']
    resolution = result['resolution']
    return _PrimalKnowledgeEvidence(
        resolution['action_id'], resolution['resolution_id'], result['skill'],
        game.SKILLS[result['skill']], result['modifier'],
        (state['started_at'], boundary['combat_id'], boundary['turn']),
        json.dumps(resolution, sort_keys=True, separators=(',', ':')),
    )


def primal_knowledge_annotation(evidence, action_result):
    """Verify a completed live roll without rechecking historical Rage state.

    The caller owns the separate evidence sink. A JSON feature label alone
    never authorizes an exceptional ability; all normal serializer checks stay.
    """
    import game
    if type(evidence) is not _PrimalKnowledgeEvidence or type(action_result) is not dict:
        raise ValueError('Missing trusted Primal Knowledge roll evidence.')
    resolution = action_result.get('resolution')
    if (type(resolution) is not dict
            or not evidence.action_id or not evidence.resolution_id
            or evidence.skill not in PRIMAL_KNOWLEDGE_SKILLS
            or evidence.original_ability != game.SKILLS[evidence.skill]
            or action_result.get('action') != 'skill_check'
            or action_result.get('skill') != evidence.skill
            or action_result.get('ability') != 'strength'
            or action_result.get('modifier') != evidence.ability_modifier
            or action_result.get('action_id') != evidence.action_id
            or action_result.get('resolution_id') != evidence.resolution_id
            or json.dumps(resolution, sort_keys=True, separators=(',', ':')) != evidence.resolution_json):
        raise ValueError('Primal Knowledge evidence does not match the completed roll.')
    for field, resolved in (('dice', 'selected_roll'), ('dice_rolls', 'raw_rolls'),
                            ('total', 'total'), ('dc', 'dc'),
                            ('advantage', 'advantage'), ('disadvantage', 'disadvantage'),
                            ('expertise', 'expertise')):
        if action_result.get(field) != resolution.get(resolved):
            raise ValueError('Primal Knowledge result disagrees with its resolution.')
    return {'check_feature': 'primal_knowledge', 'original_ability': evidence.original_ability}


def primal_knowledge_projection(session):
    import character_progression
    if not character_progression.berserker_eligible(session.character, session.world_state):
        return None
    reason = primal_knowledge_reason(session)
    return {'available': reason is None, 'reason': reason, 'skills': list(PRIMAL_KNOWLEDGE_SKILLS)}
