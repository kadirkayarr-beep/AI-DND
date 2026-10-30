"""Narrow content-reference integrity, not a prose style/quality judge.

Canonical offer cards own playable names, objectives and rewards. Lexical
tripwires catch common omitted references; they are not semantic proof of all
arbitrary natural-language claims. Live quality acceptance remains separate.
"""
from __future__ import annotations
import re
import local_dialogue
import npc_statements
import local_places


def validate(world,reply,places,jobs,npc_id):
    from dialogue_runtime import DialogueResponseError
    allowed_jobs=jobs or [q for q in world.get('quests',[]) if q.get('giver_npc_id')==npc_id and q.get('status') in {'DISCOVERED','ACTIVE','BLOCKED'}]
    settlement=local_places.settlement_of(world,world.get('location'))
    names=[local_dialogue.normalize_text(p.get('name','')) for p in world.get('locations',{}).values()
           if isinstance(p,dict) and not p.get('hidden') and p.get('discovered') is not False]
    for clause in re.split(r'[,;.!?]|\b(?:ama|ancak|fakat)\b',reply['spoken_text']):
        folded=local_dialogue.normalize_text(clause)
        if re.search(r'\b(?:eskiden|gecmiste|olsaydi|olsaydi|olsa|varsayalim|dediler|demisti)\b',folded):
            continue
        for name,noun,kind in npc_statements._named_places(clause):
            if kind=='generic': continue
            key=local_dialogue.normalize_text(name)
            if not any(key==known or (key.startswith(known) and key[len(known):] in {'na','ne','nda','nde','ni','nin','nina','nini','ndan','nden'}) for known in names if known):
                raise DialogueResponseError('Unbound named place commitment.')
        if re.search(r'\b(?:bir han var|hana git|bir dukkan var|dukkana git)\b',folded):
            kind='tavern' if 'han' in folded else 'shop'
            if not any((r.get('scene_kind')==kind or r.get('place_kind')==kind) and r.get('parent_location_id')==settlement and not r.get('hidden') and r.get('discovered') is not False for r in world.get('locations',{}).values() if isinstance(r,dict)):
                raise DialogueResponseError('Unbound unnamed destination.')
        if re.search(r'\b(?:isim var|bir is var|gorevim var|gorev veriyorum|paketi gotur)\b',folded) and not allowed_jobs:
            raise DialogueResponseError('Unbound job commitment.')
        if len(allowed_jobs)==1:
            reward=allowed_jobs[0]['reward_plan']['success']
            for count,unit in re.findall(r'\b(\d+)\s*(altin|xp)\b',folded):
                if int(count)!=reward['gold' if unit=='altin' else 'xp']:
                    raise DialogueResponseError('Spoken reward contradicts committed job.')


def job_cards(world,jobs):
    cards=[]
    for q in jobs:
        b=q['bindings'];target=next(n for n in world['npcs'] if n['id']==b['target_npc_id'])
        location=world['locations'][b['location_ids'][0]]
        objective=(f"Paketi al, {location['name']} konumuna git ve {target['name']} adlı kişiye teslim et."
                   if q['template_id']=='DELIVERY' else f"Görevi vereni dinle, {location['name']} konumuna git ve izleri araştır.")
        reward=q['reward_plan']['success']
        cards.append({'quest_id':q['quest_id'],'title':q['title'],'objective':objective,
                      'reward':{'gold':reward['gold'],'xp':reward['xp']},'status':q['status']})
    return cards


def render_cards(cards):
    result=[]
    for c in cards:
        label='İş teklifi' if c['status']=='DISCOVERED' else 'Devam eden iş'
        suffix=' Görev günlüğünden kabul edebilirsin.' if c['status']=='DISCOVERED' else ''
        result.append(f"\n{label}: {c['title']}. {c['objective']} Ödül: {c['reward']['gold']} altın, {c['reward']['xp']} XP.{suffix}")
    return ''.join(result)
