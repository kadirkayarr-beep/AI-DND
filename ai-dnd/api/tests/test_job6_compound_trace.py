"""Task-only fixed-seed diagnostic executing the original compound oracle unchanged."""
import copy,functools,hashlib,json,unittest
from unittest.mock import patch
import game, living_world, uuid, types, itertools
from api import session_manager
from api.tests import test_intent_response_consistency as original

class CompoundTrace(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=original.IntentResponseConsistencyTests.asyncTearDown
    assert_focused_speech_without_target=original.IntentResponseConsistencyTests.assert_focused_speech_without_target
    test_compound=original.IntentResponseConsistencyTests.test_compound_personal_question_cannot_be_consumed_by_day_shortcut
    collision = False
    async def asyncSetUp(self):
        # Freeze campaign creation itself: names derive from campaign UUID, not session RNG.
        for number in range(1, 501):
            cid = str(uuid.UUID(int=number, version=4))
            world = {'scene_state': {'campaign_seed': hashlib.sha256(cid.encode()).hexdigest()[:24]}, 'npcs': [], 'next_npc_number': 1}
            first = living_world._stable_name(world, 'fr:city:neverwinter', 'Kent sakini')
            world['npcs'].append({'name': first}); world['next_npc_number'] = 2
            second = living_world._stable_name(world, 'fr:city:neverwinter', 'Muhafız')
            if (second == 'Lysa') == self.collision:
                break
        else:
            raise AssertionError('No bounded diagnostic campaign found')
        self.diagnostic_campaign = cid
        sequence = itertools.chain([uuid.UUID(cid)], (uuid.UUID(int=10000+i, version=4) for i in itertools.count()))
        self.enterContext(patch.object(session_manager, 'uuid', types.SimpleNamespace(uuid4=lambda: next(sequence))))
        factory=game.create_session
        self.enterContext(patch.object(game,'create_session',side_effect=lambda:factory(seed=2108)))
        self.trace=[]
        for name in ('_narration_safety_decision','_fallback_narration','_direct_npc_smalltalk_response'):
            real=getattr(game,name)
            def make(real,name):
                @functools.wraps(real)
                def wrapper(*args,**kwargs):
                    result=real(*args,**kwargs)
                    self.trace.append({'function':name,'args':copy.deepcopy(args),'kwargs':copy.deepcopy(kwargs),'result':copy.deepcopy(result)})
                    return result
                return wrapper
            self.enterContext(patch.object(game,name,make(real,name)))
        await original.IntentResponseConsistencyTests.asyncSetUp(self)
    async def turn(self,message,**fields):
        before=copy.deepcopy(self.session.serialize_game_state())
        rng=repr(self.session.rng.getstate())
        self.trace=[]
        response=await original.IntentResponseConsistencyTests.turn(self,message,**fields)
        print('COMPOUND_TRACE='+json.dumps({'seed':2108,'message':message,'fields':fields,'before':before,'rng':rng,'response':response,'safety':self.session.last_narration_safety,'trace':self.trace},ensure_ascii=False,default=str))
        return response

class CompoundCollisionTrace(CompoundTrace):
    collision = True
