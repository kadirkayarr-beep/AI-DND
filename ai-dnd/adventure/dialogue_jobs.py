"""Typed dialogue offers and real parcel actions over existing quest/inventory stores."""
from __future__ import annotations
import copy
import hashlib
import re
import equipment_economy
import local_dialogue
import local_places
import scheduled_events
from adventure import templates, director



def eligible_targets(world,npc_id):
    """One public target domain shared by prompt and transactional validation."""
    here=world.get('location')
    settlement=local_places.settlement_of(world,here)
    if not settlement: return []
    targets=[]
    for npc in scheduled_events.visible_npcs(world):
        location=npc.get('location');place=world.get('locations',{}).get(location)
        if (npc.get('id')==npc_id or location==here or not isinstance(place,dict)
                or npc.get('hidden') or npc.get('discovered') is False
                or npc.get('combat_status') in {'dead','defeated','unconscious'} or npc.get('current_hp',1)<=0
                or place.get('hidden') or place.get('discovered') is False
                or local_places.settlement_of(world,location)!=settlement
                or world.get('blocked_travel_routes',{}).get(settlement,{}).get(location)):
            continue
        targets.append({'npc_id':npc['id'],'name':npc.get('name',''),'location_id':location})
    return targets

def prepare(session, proposal, npc_id):
    from dialogue_runtime import DialogueResponseError
    world=session.world_state
    fields={'request_key','template_id','title','description','target_npc_id','location_id'}
    if set(proposal)!=fields or any(not isinstance(proposal[k],str) or not proposal[k].strip() for k in fields):
        raise DialogueResponseError('Invalid job proposal fields.')
    if (proposal['template_id'] not in {'DELIVERY','URBAN_INVESTIGATION'} or len(proposal['title'])>160
            or len(proposal['description'])>1000 or len(proposal['request_key'])>80):
        raise DialogueResponseError('Unsupported job proposal.')
    giver=next((n for n in world['npcs'] if n.get('id')==npc_id and n.get('location')==world['location']),None)
    recipient=next((n for n in scheduled_events.visible_npcs(world) if n.get('id')==proposal['target_npc_id']),None)
    place=world.get('locations',{}).get(proposal['location_id'])
    if (giver is None or recipient is None or recipient is giver or not isinstance(place,dict)
            or recipient.get('location')!=proposal['location_id'] or recipient.get('hidden')
            or recipient.get('discovered') is False or recipient.get('combat_status') in {'dead','defeated','unconscious'}
            or recipient.get('current_hp',1)<=0 or place.get('hidden') or place.get('discovered') is False
            or local_places.settlement_of(world,proposal['location_id'])!=local_places.settlement_of(world,world['location'])):
        raise DialogueResponseError('Job bindings unavailable.')
    settlement=local_places.settlement_of(world,world['location'])
    if world.get('blocked_travel_routes',{}).get(settlement,{}).get(proposal['location_id']):
        raise DialogueResponseError('Job route unavailable.')
    if not any(t['npc_id']==recipient['id'] and t['location_id']==proposal['location_id'] for t in eligible_targets(world,npc_id)):
        raise DialogueResponseError('Job needs a reachable different-location recipient.')
    identity='|'.join((npc_id,proposal['template_id'],proposal['target_npc_id'],proposal['location_id']))
    qid='job:'+hashlib.sha256(identity.encode()).hexdigest()[:20]
    for q in world.get('quests',[]):
        if q.get('quest_id')==qid:
            if q.get('status') in {'DISCOVERED','ACTIVE','BLOCKED'}: return q
            raise DialogueResponseError('This job is already closed.')
    if sum(q.get('status') in {'AVAILABLE','DISCOVERED','ACTIVE','BLOCKED'} for q in world.get('quests',[]))>=director.MAX_OPEN:
        raise DialogueResponseError('Job capacity unavailable.')
    turn=world.get('flags',{}).get('turn_index',0)
    q=templates.instantiate(proposal['template_id'],quest_id=qid,turn=turn,opportunity_key='dialogue-job:'+qid,
       creation_evidence='dialogue-job:'+qid,bindings=templates.prepared_bindings(source_npc_id=npc_id,
       target_npc_id=recipient['id'],location_ids=[proposal['location_id']]),rumor=(f"Paketi {place['name']} konumundaki {recipient['name']} adlı kişiye teslim et." if proposal['template_id']=='DELIVERY' else f"Tanığı dinle, {place['name']} konumuna git ve izleri araştır."))
    # Model title/description are non-authoritative labels; mechanics owns the journal.
    q['title']+=f": {place['name']}"
    world.setdefault('quests',[]).append(q)
    director.discover(world,qid)
    equipment_economy.materialize(world)
    if proposal['template_id']=='DELIVERY': giver.setdefault('inventory',[]).append({'item_id':'parcel:'+qid,'name':q['title']+' paketi','quantity':1})
    equipment_economy.validate_world(world)
    return q


def transfer_evidence(quest, before, after):
    """Derive progress from exclusive parcel ownership changes, never prose."""
    if not quest.get('creation_evidence','').startswith('dialogue-job:') or quest.get('status')!='ACTIVE': return None
    item_id='parcel:'+quest['quest_id']
    def owners(w):
        return [owner for owner,items in equipment_economy.containers(w)
                for item in items if isinstance(item,dict) and item.get('item_id')==item_id]
    old,new=owners(before),owners(after)
    b=quest['bindings']
    if old==[b['source_npc_id']] and new==['player']: return b['source_npc_id']
    if old==['player'] and new==[b['target_npc_id']]: return b['target_npc_id']
    return None


def resolve(session,text,mode):
    if mode in {'say','ask_dm'}: return None
    t=local_dialogue.normalize_text(text)
    # Only unambiguous present-tense parcel actions. Negation/questions/history
    # remain dialogue/clarification, never inventory authority.
    import game
    import grounded_action
    check=game.deterministic_check_for_action(text.replace('İ','i').replace('I','ı'))
    plan=grounded_action.plan(session,text)
    physical=any(s['verb'] in {'search','inspect'} and not any(s.get(k) for k in ('question','reported','not_now','negated')) for s in plan['steps'])
    if physical and isinstance(check,dict) and check.get('skill')=='Investigation':
        active=[q for q in session.world_state.get('quests',[]) if q.get('status')=='ACTIVE' and q.get('template_id')=='URBAN_INVESTIGATION' and q.get('creation_evidence','').startswith('dialogue-job:') and session.world_state['location'] in q['bindings']['location_ids']]
        if len(active)==1:
            import game
            session.require_player_can_act()
            return game._adventure_check_reply(session,'Investigation')
    if '?' in text or any(c in text for c in ('\"','“','”','«','»')): return None
    if any(any(step.get(k) for k in ('question','reported','not_now','negated')) for step in plan['steps']): return None
    take=bool(re.fullmatch(r'(?:bu |gorev )?paketi (?:aliyorum|al)',t.strip(' .!')))
    give=bool(re.fullmatch(r'paketi (?:[\w ]+ )?teslim (?:ediyorum|et)',t.strip(' .!')))
    if not (take or give): return None
    w=session.world_state
    qs=[q for q in w.get('quests',[]) if q.get('status')=='ACTIVE' and q.get('template_id')=='DELIVERY' and q.get('creation_evidence','').startswith('dialogue-job:')]
    if len(qs)!=1: return None
    q=qs[0];b=q['bindings'];npc_id=b['source_npc_id'] if take else b['target_npc_id']
    from dialogue_runtime import _visible_npc
    npc=_visible_npc(w,npc_id)
    if npc is None: return None
    if give:
        named=re.fullmatch(r'paketi (?:(.*?) )?teslim (?:ediyorum|et)',t.strip(' .!')).group(1)
        if named and local_dialogue.normalize_text(npc.get('name','')) not in named: return None
    session.require_player_can_act()
    objective=next((o for o in q['objectives'] if o['objective_id']==('take' if take else 'hand')),None)
    if objective is None or objective.get('graph_state')!='ACTIVE':
        shown='Bu aktarım aşaması henüz hazır değil; önce görev günlüğündeki sıradaki adımı tamamlamalısın.'
        session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
        return {'messages':session.messages,'narration':shown,'model_calls':0,'action_result':{'action':'item_transfer','status':'blocked','success':False,'state_changes':[],'direct_response':shown}}
    before=copy.deepcopy(w)
    source=npc.get('inventory',[]) if take else w.get('inventory',[])
    destination=w.setdefault('inventory',[]) if take else npc.setdefault('inventory',[])
    item=next((i for i in source if isinstance(i,dict) and i.get('item_id')=='parcel:'+q['quest_id']),None)
    if item is None: return None
    equipment_economy.move(w,item,source,destination,npc_id if take else 'player')
    equipment_economy.validate_world(w)
    flags=w.setdefault('flags',{});flags['turn_index']=flags.get('turn_index',0)+1
    shown='Teslimat paketini alıyorsun.' if take else f"Paketi {npc.get('name')} adlı kişiye teslim ediyorsun."
    action={'action':'item_transfer','status':'completed','success':True,'npc_id':npc_id,'action_id':f"turn:{flags['turn_index']}",
      'state_changes':['inventory','npcs','quests'],'direct_response':shown}
    action['quest_outcomes']=session.evaluate_quest_events(before,action)
    session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
    return {'messages':session.messages,'narration':shown,'action_result':action,'model_calls':0}
