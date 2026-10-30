"""Job9 synthetic canonical door/tool/focus API acceptance, no live provider."""
import copy
import json
import uuid
import unittest
from unittest.mock import patch
import game
import grounded_action
from api.tests import test_intent_response_consistency as fixture
from api.tests.test_campaign_api import ControlledVenueOllamaClient


class DoorToolAcceptance(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = fixture.IntentResponseConsistencyTests.asyncTearDown

    async def post(self, message, **fields):
        body = {'message':message, 'interaction_mode':'do', 'action_id':str(uuid.uuid4()), **fields}
        receipts=[]
        dispatch=game._dispatch_player_turn
        def capture(*args, **kwargs):
            result=dispatch(*args, **kwargs)
            receipts.append(copy.deepcopy(result.get('action_result')))
            return result
        with patch.object(game, '_dispatch_player_turn', side_effect=capture):
            response=await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json=body)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json(); receipt=receipts[-1] if receipts else None
        print('DOOR_TURN='+json.dumps({'input':body,'receipt':receipt,'response':result,
            'calls':self.client.calls,'turn_index':self.world.get('flags',{}).get('turn_index')},ensure_ascii=False,default=str))
        return result,receipt,body

    async def scene(self, *, active=True, tools=False, locked=True, seed=5):
        await self.post('Çevreme bakıyorum.')
        self.city=self.world['location']
        self.place=grounded_action._create_venue(grounded_action._Run(self.session,'synthetic setup'),
            self.city,name='Orryn Hanı',kind='tavern',noun='han',provenance={'kind':'synthetic_verification_setup'})
        self.other=grounded_action._create_venue(grounded_action._Run(self.session,'synthetic setup'),
            self.city,name='Alaca Hanı',kind='tavern',noun='han',provenance={'kind':'synthetic_verification_setup'})
        self.door_id='venue-door:'+self.place['id']
        self.door().update(locked=locked,open=False,broken=False)
        if tools: self.world['inventory'].append({'item_id':'synthetic_tools','name':"Thieves' Tools"})
        self.session.rng.seed(seed)
        self.npc=self.world['npcs'][0]
        await self.post("Orryn Hanı'na yaklaşıyorum.")
        await self.post('Adın nedir?',target_id=self.npc['id'])
        self.assertEqual(self.world['flags'].get('active_npc_id'),self.npc['id'])
        if not active:
            ended,_,_=await self.post('Konuşmayı bitiriyorum.')
            self.assertEqual(ended['turn_outcome']['status'],'conversation_ended')
            self.assertFalse(self.world['flags'].get('active_npc_id'))

    def door(self): return next(d for d in self.world['doors'] if d['id']==self.door_id)
    def protected(self):
        return copy.deepcopy((self.session.character,self.world['inventory'],self.world['doors'],
            self.world['location'],self.world['locations'],self.world.get('campaign_time'),self.session.rng.getstate()))

    async def missing_tools(self, active):
        await self.scene(active=active)
        for text in ('Kilidi maymuncukla açmayı deniyorum','Han kapısı kilidi maymuncukla açmayı deniyorum',
                     'Orryn Hanı Kapısının kilidini maymuncukla açmayı deniyorum'):
            for explicit in (False,True):
                with self.subTest(text=text,explicit=explicit,active=active):
                    if active:
                        await self.post('Adın nedir?',target_id=self.npc['id'])
                        self.assertEqual(self.world['flags'].get('active_npc_id'),self.npc['id'])
                    else:
                        self.assertFalse(self.world['flags'].get('active_npc_id'))
                    before=self.protected(); calls=self.client.calls
                    out,receipt,_=await self.post(text,**({'target_id':self.door_id} if explicit else {}))
                    self.assertEqual(receipt['target_id'],self.door_id)
                    self.assertEqual(receipt['reason'],'tools_required')
                    self.assertEqual(receipt['status'],'blocked')
                    self.assertIn('Elinde maymuncuk',out['narration'])
                    self.assertEqual(before,self.protected())
                    self.assertEqual(calls,self.client.calls)

    async def test_active_npc_does_not_capture_explicit_door_instrument(self):
        await self.missing_tools(True)

    async def test_ended_conversation_missing_tools_same_canonical_target(self):
        await self.missing_tools(False)

    async def tools(self,seed,success):
        await self.scene(tools=True,seed=seed)
        before=self.session.rng.getstate(); inventory=copy.deepcopy(self.world['inventory']); calls=self.client.calls
        out,receipt,body=await self.post('Orryn Hanı Kapısının kilidini maymuncukla açmayı deniyorum')
        self.assertEqual(receipt['target_id'],self.door_id)
        self.assertEqual(receipt['skill'],'Sleight of Hand')
        self.assertEqual(receipt['success'],success,receipt)
        self.assertNotEqual(before,self.session.rng.getstate())
        self.assertEqual(self.door()['locked'],not success)
        self.assertFalse(self.door()['broken'])
        self.assertEqual(inventory,self.world['inventory'])
        self.assertEqual(calls,self.client.calls)
        saved=copy.deepcopy(self.session.serialize_game_state())
        with patch.object(game,'run_player_turn',side_effect=AssertionError('replay consumed engine')):
            replay=await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json=body)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(out,replay.json())
        self.assertEqual(saved,self.session.serialize_game_state())
        self.assertEqual(calls,self.client.calls)

    async def test_tools_success_uses_rng_and_replay_once(self): await self.tools(5,True)
    async def test_tools_failure_uses_rng_and_replay_once(self): await self.tools(2,False)

    async def test_unlocked_entry_and_normal_open_keep_destination(self):
        await self.scene(locked=False)
        calls=self.client.calls
        _,receipt,_=await self.post('Orryn Hanı Kapısını açıyorum.')
        self.assertEqual(receipt['target_id'],self.door_id)
        self.assertTrue(self.door()['open'])
        out,receipt,_=await self.post('İçeri giriyorum.')
        self.assertEqual(self.world['location'],self.place['id'])
        self.assertIn('Orryn',out['narration'])
        self.assertEqual(calls,self.client.calls)

    async def test_locked_entry_stays_locked_without_model(self):
        await self.scene()
        before=self.protected();calls=self.client.calls
        out,receipt,_=await self.post('İçeri giriyorum.')
        self.assertEqual(self.world['location'],self.city)
        self.assertTrue(self.door()['locked'])
        self.assertFalse(self.door()['open'])
        self.assertIn('kilitli',out['narration'])
        self.assertEqual(before,self.protected())
        self.assertEqual(calls,self.client.calls)

    async def test_explicit_force_uses_canonical_door_and_python_check(self):
        self.assertEqual(grounded_action._verb_of('zorluyorum')[0], 'force')
        negative = grounded_action._verb_of('zorlamiyorum')
        self.assertTrue(negative is None or negative[1])
        for noun in ('zorlu', 'zorluk', 'zorunlu'):
            self.assertIsNone(grounded_action._verb_of(noun))
        await self.scene(seed=5)
        other_before=copy.deepcopy(next(d for d in self.world['doors'] if d['id']=='venue-door:'+self.other['id']))
        before=self.session.rng.getstate(); calls=self.client.calls
        out,receipt,_=await self.post('Orryn Hanı Kapısını zorluyorum.')
        self.assertEqual(receipt['target_id'],self.door_id)
        self.assertNotEqual(before,self.session.rng.getstate())
        self.assertTrue(receipt['success'])
        self.assertTrue(self.door()['broken'])
        self.assertTrue(self.door()['open'])
        self.assertFalse(self.door()['locked'])
        self.assertEqual(other_before,next(d for d in self.world['doors'] if d['id']=='venue-door:'+self.other['id']))
        self.assertEqual(calls,self.client.calls)

    async def test_speech_askdm_quote_negation_and_foreign_object_do_not_open(self):
        await self.scene(tools=True)
        for message,mode in (("Orryn Hanı Kapısının kilidini maymuncukla açmayı deniyorum",'say'),
                             ("Kilidi maymuncukla açmayı deniyorum",'ask_dm'),
                             ('“Orryn Hanı Kapısını açıyorum” dedim.','do'),
                             ('Orryn Hanı Kapısının kilidini maymuncukla açmayı denemiyorum','do'),
                             ('Kitabı maymuncukla açıyorum.','do')):
            with self.subTest(message=message,mode=mode):
                before=self.protected()
                with patch.object(self.app.state.ollama_adapter,'_client',ControlledVenueOllamaClient(intent='narrative')):
                    await self.post(message,interaction_mode=mode)
                self.assertEqual(before,self.protected())

    async def test_conditional_and_negative_force_do_not_act(self):
        await self.scene()
        for message in ('Orryn Hanı Kapısını zorlarsam ne olur?',
                        'Orryn Hanı Kapısını zorlamıyorum'):
            with self.subTest(message=message):
                before=self.protected()
                with patch.object(self.app.state.ollama_adapter,'_client',ControlledVenueOllamaClient(intent='narrative')):
                    _,receipt,_=await self.post(message)
                self.assertEqual(before,self.protected())
                self.assertNotEqual((receipt or {}).get('skill'),'Athletics')
                self.assertNotEqual((receipt or {}).get('status'),'resolved')

    async def test_want_to_force_is_python_attempt_not_automatic_success(self):
        await self.scene(seed=2)
        rng=self.session.rng.getstate(); door=copy.deepcopy(self.door()); calls=self.client.calls
        _,receipt,_=await self.post('Orryn Hanı Kapısını zorlamak istiyorum')
        self.assertEqual(receipt['target_id'],self.door_id)
        self.assertEqual(receipt['skill'],'Athletics')
        self.assertNotEqual(rng,self.session.rng.getstate())
        self.assertFalse(receipt['success'])
        self.assertEqual(door,self.door())
        self.assertEqual(calls,self.client.calls)

    async def test_normal_open_locked_door_is_blocked_without_cost(self):
        await self.scene()
        before=self.protected(); calls=self.client.calls
        _,receipt,_=await self.post('Orryn Hanı Kapısını açıyorum')
        self.assertEqual(receipt['target_id'],self.door_id)
        self.assertEqual(receipt['status'],'blocked')
        self.assertEqual(receipt['reason'],'door_locked')
        self.assertEqual(before,self.protected())
        self.assertEqual(calls,self.client.calls)

    async def test_open_with_no_visible_door_does_not_create_or_open_one(self):
        await self.post('Çevreme bakıyorum.')
        self.assertFalse(self.world.get('doors'))
        before=self.protected()
        with patch.object(self.app.state.ollama_adapter,'_client',ControlledVenueOllamaClient(intent='narrative')):
            _,receipt,_=await self.post('Kapıyı açıyorum')
        self.assertEqual(before,self.protected())
        self.assertFalse(self.world.get('doors'))
        self.assertFalse((receipt or {}).get('success'))
        self.assertEqual(receipt['status'],'blocked')
        self.assertEqual(receipt['reason'],'target_unknown')
        self.assertEqual(receipt['target_type'],'door')
        self.assertIn('kapı görünmüyor',receipt['direct_response'])

    async def test_explicit_unknown_door_keeps_absence_receipt(self):
        await self.post('Çevreme bakıyorum.')
        self.assertFalse(self.world.get('doors'))
        before=self.protected()
        with patch.object(self.app.state.ollama_adapter,'_client',ControlledVenueOllamaClient(intent='narrative')):
            _,receipt,_=await self.post('Kapıyı açıyorum',target_id='door_unknown_synthetic')
        self.assertFalse(receipt['success'])
        self.assertEqual(receipt['status'],'blocked')
        self.assertEqual(receipt['reason'],'target_unknown')
        self.assertEqual(before,self.protected())

    async def test_existing_open_door_and_other_world_reply_are_not_blocked(self):
        await self.scene(locked=False)
        await self.post('Orryn Hanı Kapısını açıyorum')
        _,receipt,_=await self.post('Orryn Hanı Kapısını açıyorum')
        self.assertTrue(receipt['success'])
        self.assertEqual(receipt['status'],'completed')
        self.assertTrue(self.door()['open'])
        # Existing successful world-action owner: close the actual open door.
        result=self.session.execute_intent({'intent':'interact'},'Kapıyı kapatıyorum')
        self.assertTrue(result['success'])
        self.assertNotEqual(result['status'],'blocked')
        self.assertFalse(self.door()['open'])

    async def test_conflicting_explicit_door_does_not_mutate_other_inn(self):
        await self.scene(locked=False)
        other_id='venue-door:'+self.other['id']
        other=copy.deepcopy(next(d for d in self.world['doors'] if d['id']==other_id))
        rng=self.session.rng.getstate(); inventory=copy.deepcopy(self.world['inventory'])
        _,receipt,_=await self.post('Orryn Hanı Kapısını açıyorum',target_id=other_id)
        self.assertEqual(other,next(d for d in self.world['doors'] if d['id']==other_id))
        self.assertEqual(rng,self.session.rng.getstate())
        self.assertEqual(inventory,self.world['inventory'])
        self.assertNotEqual(receipt.get('target_id'),other_id)
        self.assertEqual(self.world['location'],self.city)

    async def test_tools_required_receipt_replay_has_no_second_consumption(self):
        await self.scene()
        before=self.protected(); calls=self.client.calls
        out,receipt,body=await self.post('Kilidi maymuncukla açmayı deniyorum')
        self.assertEqual(receipt['reason'],'tools_required')
        self.assertEqual(receipt['status'],'blocked')
        self.assertEqual(before,self.protected())
        saved=copy.deepcopy(self.session.serialize_game_state())
        with patch.object(game,'run_player_turn',side_effect=AssertionError('blocked replay consumed engine')):
            replay=await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json=body)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(out,replay.json())
        self.assertEqual(saved,self.session.serialize_game_state())
        self.assertEqual(calls,self.client.calls)
