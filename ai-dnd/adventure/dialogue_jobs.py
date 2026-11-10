"""Typed dialogue offers and real parcel actions over existing quest/inventory stores."""
from __future__ import annotations
import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Literal
import equipment_economy
import living_world
import tr_case
import local_dialogue
import local_places
import relationships
import scheduled_events
from adventure import templates, director



THREAD_EVIDENCE='thread-job:'
_KEPT=('quests','scheduled_events','inventory','currency','world_threads_v1','locations','next_location_number',
       'next_npc_number','relationships','flags','quest_processed_event_ids')


def _keep(world):
    """What a job write may touch. People are kept whole so a held reference stays the real person."""
    return ({key:copy.deepcopy(world[key]) for key in _KEPT if key in world},copy.deepcopy(world.get('npcs',[])))


def _restore(world,kept):
    saved,people=kept
    for key in _KEPT:
        if key in saved: world[key]=saved[key]
        else: world.pop(key,None)
    live={n.get('id'):n for n in world.get('npcs',[]) if isinstance(n,dict)}
    world['npcs'][:]=[]
    for row in people:
        npc=live.get(row.get('id'),{})
        npc.clear();npc.update(row)
        world['npcs'].append(npc)


def thread_job_active_count(world):
    return sum(isinstance(q,dict) and q.get('status')=='ACTIVE' and str(q.get('creation_evidence') or '').startswith(THREAD_EVIDENCE)
               for q in world.get('quests',[]))


def _quest_of(world,thread):
    return next((q for q in world.get('quests',[]) if isinstance(q,dict) and q.get('quest_id')==thread.get('quest_id')),None)


def holds_parcel(world,thread):
    return any(isinstance(i,dict) and i.get('item_id')==f"parcel:{thread.get('quest_id')}" for i in world.get('inventory',[]))


def due_parcel(world,person):
    """The one job whose parcel is in the bag and goes to this person; None when there is none or more than one."""
    import world_threads
    due=[t for t in world_threads.deliveries_to(world,person) if holds_parcel(world,t)]
    return due[0] if len(due)==1 else None


def already_in_hand(world,thread):
    """The job's parcel is already in the bag: taking it again makes nothing."""
    return holds_parcel(world,thread)


@dataclass(frozen=True)
class WordMatch:
    """Which accepted job a word names: one, none, or many (many means it is not told which)."""
    status: Literal['one','none','many']
    thread: dict|None


def parcel_for_word(world,word):
    """The accepted job whose item name the word starts with. 'none' and 'many' are different answers."""
    import world_threads
    words=living_world.normalize_text(word).split()
    found=[t for t in ((world_threads.view(world) or {}).get('threads') or [])
           if t.get('status')=='accepted' and t.get('quest_id')
           and any(w.startswith(stem) for stem in world_threads._item_stems(t) for w in words)]
    return WordMatch('one',found[0]) if len(found)==1 else WordMatch('many',None) if found else WordMatch('none',None)


def _recipient_for(thread,world):
    """The person it goes to exists from the moment the job does, not from the player's arrival."""
    import game
    import world_threads
    place=world.get('locations',{}).get(thread.get('target_place_id'))
    if not isinstance(place,dict): return None
    npc=world_threads.recipient_of(world,thread)
    if npc is None and place.get('place_kind') in local_places.PLACE_KINDS:
        npc,_=local_places.furnish(world,place,create_feature=game.create_local_feature,
            create_npc=lambda fields:game.create_npc_from_ai(fields,allow_other_location=True))
    return npc


def accept_thread_job(session,thread,giver):
    """The job, its journal row, its deadline and its parcel, all or none. False leaves nothing."""
    import world_threads
    from adventure import deadlines, play
    world=session.world_state
    if thread_job_active_count(world)>=1 or thread.get('quest_id') or type(thread.get('terms',{}).get('pay')) is not int:
        return False
    kept=_keep(world)
    try:
        place_id=thread.get('target_place_id')
        recipient=_recipient_for(thread,world)
        place=world.get('locations',{}).get(place_id)
        if not _job_checks(world,giver,recipient,place,place_id):
            raise ValueError('Job bindings unavailable.')
        qid='job:'+hashlib.sha256(thread['thread_id'].encode()).hexdigest()[:20]
        noun=thread.get('item_noun') or 'paket'
        label=tr_case.upper_first(noun)
        turn=world.get('flags',{}).get('turn_index',0)
        q=templates.instantiate('DELIVERY',quest_id=qid,turn=turn,opportunity_key='thread-job:'+qid,
           creation_evidence=THREAD_EVIDENCE+thread['thread_id'],
           bindings=templates.prepared_bindings(source_npc_id=giver['id'],target_npc_id=recipient['id'],location_ids=[place_id]),
           rumor=f"{label}: {place['name']} içinde {living_world.public_npc_name(recipient)} bekliyor.")
        q['title']+=f": {place['name']}"
        q['reward_plan']={'success':{'xp':0,'gold':thread['terms']['pay']},'failed':{'xp':0,'gold':0}}
        world.setdefault('quests',[]).append(q)
        director.discover(world,qid)
        if deadlines.arm(world,q,duration_seconds=86400) is None:
            raise ValueError('The job has no deadline.')
        play.accept(session,qid)
        equipment_economy.materialize(world)
        item_id='parcel:'+qid
        if not any(isinstance(i,dict) and i.get('item_id')==item_id for _,items in equipment_economy.containers(world) for i in items):
            giver.setdefault('inventory',[]).append({'item_id':item_id,'name':label,'quantity':1})
        equipment_economy.validate_world(world)
        if not world_threads.accept_hired(world,thread):
            raise ValueError('The thread cannot be accepted.')
        thread.update(quest_id=qid,recipient_npc_id=recipient['id'],owner_npc_id=giver['id'])
        thread.pop('work_until',None)
        world_threads.validate(world[world_threads.KEY])
        return True
    except Exception:
        _restore(world,kept)
        raise


def _lines(kind):
    import world_threads
    return world_threads.job_lines('errand','shown',kind) or []


def shown_line(world,thread,kind,amount=None):
    import world_threads
    lines=_lines(kind)
    if not lines: return ''
    line=lines[world_threads._rank(living_world._campaign_seed(world),thread['thread_id'],kind)%len(lines)]
    noun=thread.get('item_noun') or 'paket'
    return world_threads.sentence(world_threads._fill(line,item=tr_case.upper_first(noun),owner=world_threads.spoken_owner(world,thread),
        recipient=world_threads.spoken_recipient(world,thread),pay_text=world_threads.pay_text(thread),amount=amount))


_PAPER=('mektu','mektub','not','pusula','kagit','tezkere','zarf','yazi','duyuru','ilan','belge')
# Only the speaker doing it now: 'okumadım', 'okumak istemiyorum', 'okudum sanma' and 'ne yazık ki' are not reading.
_READING=re.compile(r'\boku(?:yorum|yom|yoruz|yayim|yalim|yacagim|yacam|dum|yup)?\b(?!\s+(?:mi|mu|san\w*|degil\w*)\b)')
_ASKS_WHAT_IT_SAYS=re.compile(r'\bne\s+yazi(?:yor\w*|yo|li)\b')


def sealed(thread):
    return 'muhr' in living_world.normalize_text(thread.get('owner_line'))


def _paper_in_hand(world,text):
    """The letter or note in the bag this line means, or None."""
    import world_threads
    words=living_world.normalize_text(text).split()
    for thread in (world_threads.view(world) or {'threads':[]})['threads']:
        noun=living_world.normalize_text(thread.get('item_noun')).split()
        if (thread.get('status')=='accepted' and any(part.startswith(_PAPER) for part in noun) and holds_parcel(world,thread)
                and any(word.startswith(stem) for stem in (*world_threads._item_stems(thread),'muhr') for word in words)):
            return thread
    return None


def _paper_with_its_owner(session,text):
    """The job is the player's and the paper is in reach: reading it starts with it changing hands."""
    import world_threads
    world=session.world_state
    words=living_world.normalize_text(text).split()
    for thread in (world_threads.view(world) or {'threads':[]})['threads']:
        owner=world_threads.owner_of(world,thread)
        noun=living_world.normalize_text(thread.get('item_noun')).split()
        if (thread.get('status')=='accepted' and thread.get('quest_id') and any(part.startswith(_PAPER) for part in noun)
                and isinstance(owner,dict) and owner.get('location')==world.get('location')
                and not holds_parcel(world,thread)
                and any(word.startswith(stem) for stem in world_threads._item_stems(thread) for word in words)
                and hand_over(session,thread,owner,own_turn=False)):
            return thread
    return None


def _in_conversation(world):
    flags=world.get('flags') or {}
    return bool(flags.get('active_npc_id')) and flags.get('turn_index',0)<=flags.get('active_npc_until_turn',-1)


def letter_text(world,thread):
    """What it says. Picked once by the campaign's seed, so a second reading finds the same words."""
    import world_happenings
    import world_threads
    if thread.get('letter_line'): return thread['letter_line']
    matter=world_happenings.letter_matter(world,thread)
    lines=[line for line in world_threads.job_lines('errand','letters') or () if ('{matter}' in line)==bool(matter)]
    if not lines: return ''
    line=lines[world_threads._rank(living_world._campaign_seed(world),thread['thread_id'],'letter')%len(lines)]
    place=world.get('locations',{}).get(thread.get('target_place_id')) or {}
    return world_threads._fill(line,target=place.get('name') or 'orası',matter=matter or '')


def read_parcel(session,text):
    """Reading what the player carries: the words are Python's, and a broken seal stays broken."""
    world=session.world_state
    if not isinstance(text,str) or world.get('combat',{}).get('active'):
        return None
    folded=living_world.normalize_text(text)
    reads='?' not in text and bool(_READING.search(folded))
    if not reads and not _ASKS_WHAT_IT_SAYS.search(folded):
        return None
    thread=_paper_in_hand(world,text)
    if thread is None:
        thread=_paper_with_its_owner(session,text)
    words=letter_text(world,thread) if thread is not None else ''
    if not words:
        return None
    breaks=sealed(thread) and not thread.get('seal_broken')
    if not reads and (breaks or _in_conversation(world)):
        return None  # a question opens no seal, and with someone there it is theirs to answer
    thread['seal_broken']=True
    flags=world.setdefault('flags',{})
    flags['turn_index']=flags.get('turn_index',0)+1
    import world_happenings
    world_happenings.letter_read(world,thread,words,flags['turn_index'])
    if breaks: world_happenings.seal_broken(world,thread)
    shown=('Mührü kırıyorsun. ' if breaks else '')+f'Kâğıtta şunlar yazıyor: “{words}”'
    session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
    return {'messages':session.messages,'narration':shown,'model_calls':0,
            'action_result':{'action':'read_parcel','status':'resolved','success':True,
                             'state_changes':['world_threads'],'direct_response':shown}}


def _move_parcel(session,thread,npc,to_player,text='',own_turn=True):
    """The parcel really changes hands and the journal hears of it from that change alone."""
    import adventure
    world=session.world_state
    q=_quest_of(world,thread)
    item_id='parcel:'+q['quest_id']
    equipment_economy.materialize(world)
    source=npc.get('inventory',[]) if to_player else world.get('inventory',[])
    destination=world.setdefault('inventory',[]) if to_player else npc.setdefault('inventory',[])
    item=next((i for i in source if isinstance(i,dict) and i.get('item_id')==item_id),None)
    if item is None: return False
    if not to_player and q.get('status')=='ACTIVE':  # someone reached the door without the journal seeing the walk
        road=next((o for o in q['objectives'] if o['objective_id']=='road'),None)
        if road is not None and road.get('graph_state')=='ACTIVE':
            elsewhere=copy.deepcopy(world)
            elsewhere['location']=None
            adventure.apply_dynamic_evidence(world,elsewhere,{'action':'travel','status':'resolved'})
    before=copy.deepcopy(world)
    import item_transfers
    moved=item_transfers.transfer_now(world,item_id=item_id,source_id=npc['id'] if to_player else 'player',
                                      recipient_id='player' if to_player else npc['id'])
    if moved.status!='applied': equipment_economy.fail(moved.reason_code or 'item_transfer_refused')
    equipment_economy.validate_world(world)
    flags=world.setdefault('flags',{})
    if own_turn:
        flags['turn_index']=flags.get('turn_index',0)+1
    action={'action':'item_transfer','status':'completed','success':True,'npc_id':npc['id'],'action_id':f"turn:{flags.get('turn_index',0)}",
            'state_changes':['inventory','npcs','quests']}
    action['quest_outcomes']=session.evaluate_quest_events(before,action)
    return action


def hand_over(session,thread,giver,*,own_turn=True):
    """Owner to player, as this turn's own act or inside a turn already counted. A word of 'oraya' after this means where it is going."""
    import grounded_action
    world=session.world_state
    kept=_keep(world)
    try:
        action=_move_parcel(session,thread,giver,True,own_turn=own_turn)
        if action and thread.get('target_place_id'):
            grounded_action.note_last(world,thread['target_place_id'])
        if action:
            import world_threads
            world_threads.note_event(world,thread,'handed',f"{thread.get('item_noun') or 'paket'} oyuncuya geçti",npc=giver)
        return action
    except Exception:
        _restore(world,kept)
        raise


def deliver(session,thread,recipient,text):
    """Player to recipient. Paid through the wallet by the journal row, in this same reply."""
    import world_threads
    world=session.world_state
    if not holds_parcel(world,thread):
        shown=shown_line(world,thread,'thrown' if thread.get('parcel_gone') else 'not_in_hand')
        session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
        return {'messages':session.messages,'narration':shown,'model_calls':0,
                'action_result':{'action':'item_transfer','status':'blocked','success':False,'state_changes':[],'direct_response':shown}}
    kept=_keep(world)
    try:
        opened=sealed(thread) and thread.get('seal_broken') is True
        pay=max(1,thread['terms']['pay']//2) if opened else thread['terms']['pay']
        _quest_of(world,thread)['reward_plan']['success']['gold']=pay
        action=_move_parcel(session,thread,recipient,False)
        if not action: raise ValueError('The parcel did not move.')
        world_threads.sync_from_quests(world)
        closed=world_threads.by_id(world,thread['thread_id'])
        if closed is None or closed.get('status')!='done':
            raise ValueError('The delivery did not finish the job.')
        closed['paid_cp']=pay
        world_threads.note_event(world,closed,'paid',f"{pay} bakır ödendi",npc=recipient)
        if opened:
            for person in (recipient.get('id'),thread.get('owner_npc_id')):
                if isinstance(person,str): relationships.note(world,person,-1,'broke_seal:'+thread['thread_id'])
        shown=shown_line(world,closed,'delivered_opened' if opened else 'delivered',amount=pay)
        action['direct_response']=shown
        session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
        return {'messages':session.messages,'narration':shown,'action_result':action,'model_calls':0}
    except Exception:
        _restore(world,kept)
        raise


def deliver_late(session,thread,person,text):
    """The job is over but the parcel still reaches someone it belongs with: it changes hands and nobody pays."""
    import world_threads
    world=session.world_state
    kept=_keep(world)
    try:
        action=_move_parcel(session,thread,person,False)
        if not action: raise ValueError('The parcel did not move.')
        to_owner=person.get('id')==thread.get('owner_npc_id')
        if not to_owner: thread['delivered_late']=True
        world_threads.note_event(world,thread,'parcel_returned' if to_owner else 'parcel_late',
            f"{thread.get('item_noun') or 'paket'} geç de olsa yerine ulaştı",npc=person)
        shown=shown_line(world,thread,'returned' if to_owner else 'late')
        action['direct_response']=shown
        session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
        return {'messages':session.messages,'narration':shown,'action_result':action,'model_calls':0}
    except Exception:
        _restore(world,kept)
        raise


def give_plain(world,item_id,person):
    """Something of the bag that no job names goes to this person, and their hands hold it from now on.

    Only a plain thing goes this way; a valued or held one waits for `/item give` and its card (K5, O3).
    """
    import item_transfers
    item=next((i for i in world.get('inventory',[]) if isinstance(i,dict) and i.get('item_id')==item_id),None)
    if item is None or item_transfers.item_needs_card(world,item): return None
    kept=_keep(world)
    try:
        equipment_economy.materialize(world)
        moved=item_transfers.transfer_now(world,item_id=item_id,source_id='player',recipient_id=person['id'])
        if moved.status!='applied':
            _restore(world,kept)
            return None
        equipment_economy.validate_world(world)
        return item
    except Exception:
        _restore(world,kept)
        raise


def take_reply(session,thread,text,action):
    shown=shown_line(session.world_state,thread,'taken')
    action=dict(action,direct_response=shown)
    session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
    return {'messages':session.messages,'narration':shown,'action_result':action,'model_calls':0}


def already_reply(session,thread,text):
    shown=shown_line(session.world_state,thread,'already_in_hand')
    session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
    return {'messages':session.messages,'narration':shown,'model_calls':0,
            'action_result':{'action':'pocket','status':'resolved','success':False,'state_changes':[],'direct_response':shown}}


def lapsed_reply(session,thread,person,text):
    """A yes to an offer the clock already took back: the engine's own line, and nothing is taken or paid."""
    import world_threads
    shown=(world_threads.job_lines('text') or {}).get('offer_lapsed') or ''
    session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
    return {'messages':session.messages,'narration':shown,'model_calls':0,
            'action_result':{'action':'dialogue','status':'blocked','success':False,'npc_id':person.get('id'),
                             'state_changes':[],'direct_response':shown}}


def abandon_thread_job(session,thread,owner):
    """Walking away from a job: the journal row closes and a parcel in hand goes back."""
    import world_threads
    from adventure import play
    world=session.world_state
    kept=_keep(world)
    try:
        if holds_parcel(world,thread):
            # The one sourced transfer, so the parcel's way back is written in the ledger like every other move.
            import item_transfers
            moved=item_transfers.transfer_now(world,item_id=f"parcel:{thread['quest_id']}",source_id='player',recipient_id=owner['id'])
            if moved.status!='applied': equipment_economy.fail(moved.reason_code or 'item_transfer_refused')
            equipment_economy.validate_world(world)
        play.abandon(session,thread['quest_id'])
        world_threads.sync_from_quests(world)
        return True
    except Exception:
        _restore(world,kept)
        raise


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
        targets.append({'npc_id':npc['id'],'name':living_world.public_npc_name(npc),'location_id':location})
    return targets

def _job_checks(world,giver,recipient,place,place_id):
    """A job can bind only between two different living people, one reachable place away."""
    here=world.get('location')
    settlement=local_places.settlement_of(world,here)
    return not (giver is None or recipient is None or recipient is giver or not isinstance(place,dict)
            or recipient.get('location')!=place_id or recipient.get('hidden')
            or recipient.get('discovered') is False or recipient.get('combat_status') in {'dead','defeated','unconscious'}
            or recipient.get('current_hp',1)<=0 or place.get('hidden') or place.get('discovered') is False
            or local_places.settlement_of(world,place_id)!=settlement
            or world.get('blocked_travel_routes',{}).get(settlement,{}).get(place_id))


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
    if not _job_checks(world,giver,recipient,place,proposal['location_id']):
        raise DialogueResponseError('Job bindings unavailable.')
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
       target_npc_id=recipient['id'],location_ids=[proposal['location_id']]),rumor=(f"Paketi {place['name']} konumundaki {living_world.public_recipient_phrase(recipient)} teslim et." if proposal['template_id']=='DELIVERY' else f"Tanığı dinle, {place['name']} konumuna git ve izleri araştır."))
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
    if not quest.get('creation_evidence','').startswith(('dialogue-job:',THREAD_EVIDENCE)) or quest.get('status')!='ACTIVE': return None
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
        shown=f"{living_world.public_npc_name(npc)} şimdilik el uzatmıyor; önce yolun geri kalanı var."
        session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
        return {'messages':session.messages,'narration':shown,'model_calls':0,'action_result':{'action':'item_transfer','status':'blocked','success':False,'state_changes':[],'direct_response':shown}}
    before=copy.deepcopy(w)
    source=npc.get('inventory',[]) if take else w.get('inventory',[])
    item=next((i for i in source if isinstance(i,dict) and i.get('item_id')=='parcel:'+q['quest_id']),None)
    if item is None: return None
    import item_transfers  # the one sourced transfer: every parcel move writes its ledger operation
    moved=item_transfers.transfer_now(w,item_id=item['item_id'],source_id=npc_id if take else 'player',
                                      recipient_id='player' if take else npc_id)
    if moved.status!='applied': equipment_economy.fail(moved.reason_code or 'item_transfer_refused')
    equipment_economy.validate_world(w)
    flags=w.setdefault('flags',{});flags['turn_index']=flags.get('turn_index',0)+1
    shown='Teslimat paketini alıyorsun.' if take else f"Paketi {living_world.public_recipient_phrase(npc)} teslim ediyorsun."
    action={'action':'item_transfer','status':'completed','success':True,'npc_id':npc_id,'action_id':f"turn:{flags['turn_index']}",
      'state_changes':['inventory','npcs','quests'],'direct_response':shown}
    action['quest_outcomes']=session.evaluate_quest_events(before,action)
    session.messages.extend([{'role':'user','content':text},{'role':'assistant','content':shown}])
    return {'messages':session.messages,'narration':shown,'action_result':action,'model_calls':0}
