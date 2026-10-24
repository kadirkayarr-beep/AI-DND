"""Redesign RED baseline: real engine/ASGI, synthetic provider, no product patches."""
import copy,json,unittest,uuid
from unittest.mock import patch
import game,grounded_action,npc_statements
from api.tests import test_door_tool_acceptance as door_fixture
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient

class DialogueRedesignBaseline(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=door_fixture.DoorToolAcceptance.asyncSetUp
    asyncTearDown=door_fixture.DoorToolAcceptance.asyncTearDown
    scene=door_fixture.DoorToolAcceptance.scene
    post=door_fixture.DoorToolAcceptance.post
    door=door_fixture.DoorToolAcceptance.door
    protected=door_fixture.DoorToolAcceptance.protected

    async def _short_door(self,text):
        await self.scene(active=False)
        before=self.protected()
        with self.app.state.ollama_adapter.engine_binding():
            plan=grounded_action.plan(self.session,text)
            owns=grounded_action.resolve_turn(self.session,text,interaction_mode='do',allow_model=False,dry_run=True)
        step=plan['steps'][0]
        print('BASELINE_PLAN',json.dumps({'input':text,'target':(step.get('target') or {}).get('id'),'verb':step['verb'],'part':step['part'],'owns':owns},ensure_ascii=False))
        self.assertEqual((step.get('target') or {}).get('id'),self.door_id)
        self.assertEqual(before,self.protected(),'classification changed gameplay state')
        self.assertTrue(owns,'bound natural door act is incorrectly deferred')

    async def test_short_open_reaches_door_owner(self):
        await self._short_door('Han kapısını açıyorum')
    async def test_short_tool_reaches_door_owner(self):
        await self._short_door('Kapıyı maymuncukla açıyorum')
    async def test_named_tool_reaches_door_owner(self):
        await self._short_door('Orryn Hanı Kapısını maymuncukla açıyorum')
    async def test_long_lock_phrase_http_control(self):
        await self.scene(active=False)
        before=self.protected()
        out,receipt,_=await self.post('Orryn Hanı Kapısının kilidini maymuncukla açmayı deniyorum')
        self.assertEqual(receipt['target_id'],self.door_id)
        self.assertEqual(receipt['reason'],'tools_required')
        self.assertIn('maymuncuk',out['narration'])
        self.assertEqual(before,self.protected())
    async def test_door_cause_is_not_physical_world_action(self):
        await self.scene(active=False)
        before=self.protected()
        with patch.object(game,'_current_door',return_value=None):
            result=self.session.resolve_python_world_action('kapı niye kilitliydi?')
        print('BASELINE_CAUSE',json.dumps(result,ensure_ascii=False))
        self.assertEqual(before,self.protected())
        self.assertIsNone(result,'a reason question was claimed by a physical-action heuristic')
    async def test_full_three_word_inn_name_is_retained(self):
        text="O büyük kule 'Gümüş Kılıç' Hanı olarak bilinir."
        result=npc_statements._named_places(text)
        print('BASELINE_NAMES',json.dumps(result,ensure_ascii=False))
        self.assertIn('Gümüş Kılıç Hanı',[r[0] for r in result])
    async def test_two_word_inn_name_control(self):
        result=npc_statements._named_places('Orryn Hanı burada.')
        self.assertIn('Orryn Hanı',[r[0] for r in result])
    async def _npc_door_question_http(self, mode):
        await self.scene(active=False)
        self.world['location']=self.place['id']
        self.npc['location']=self.place['id']
        client=ScriptedNpcSpeechClient('Kapı gece kapalıydı; nedenini ben de bilmiyorum.')
        with patch.object(self.app.state.ollama_adapter,'_client',client):
            greeting=await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json={'message':'Seninle konuşmak istiyorum.','interaction_mode':'say','target_id':self.npc['id'],'action_id':str(uuid.uuid4())})
        self.assertEqual(greeting.status_code,200,greeting.text)
        self.assertEqual(self.world['flags'].get('active_npc_id'),self.npc['id'])
        before=copy.deepcopy((self.world['location'],self.world['inventory'],self.world['doors']))
        with patch.object(self.app.state.ollama_adapter,'_client',client):
            response=await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json={'message':'kapı niye kilitliydi?','interaction_mode':mode,'action_id':str(uuid.uuid4())})
        print('BASELINE_HTTP',json.dumps({'code':response.status_code,'response':response.json(),'model_calls':client.chat_calls},ensure_ascii=False))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(before,(self.world['location'],self.world['inventory'],self.world['doors']))
        self.assertNotIn('açıp kapatabileceğin',response.json()['narration'])

    async def test_npc_door_question_http_say(self):
        await self._npc_door_question_http('say')
    async def test_npc_door_question_http_do(self):
        await self._npc_door_question_http('do')
