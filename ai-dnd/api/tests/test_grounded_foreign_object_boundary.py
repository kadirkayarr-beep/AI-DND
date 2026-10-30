"""An explicit unknown object must not become a nearby door by typo matching."""
import copy
import unittest
import uuid
from unittest.mock import patch
import campaign_time
import grounded_action
import living_world
from api.tests import test_campaign_api as fixture


class ForeignObjectTokenTests(unittest.TestCase):
    def test_similar_name_does_not_own_branch_object(self):
        candidates=[{'names':['dalia hani'],'nouns':['han']}]
        self.assertEqual(grounded_action._foreign_object(['bir','dali','kiriyorum'],2,{},candidates),'dali')
        self.assertIsNone(grounded_action._foreign_object(['dalia','hanini','kiriyorum'],2,{},candidates))


class ForeignObjectHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):await fixture.CampaignApiTests.asyncSetUp(self)
    async def asyncTearDown(self):await fixture.CampaignApiTests.asyncTearDown(self)

    async def fixture(self):
        original=living_world.stable_local_name
        with patch.object(living_world,'stable_local_name',lambda world,location,role: 'Dalia' if 'tavern' in role else original(world,location,role)):
            _,_,session,url,venue,door=await fixture.create_city_with_locked_tavern(self)
        self.assertEqual(session.world_state['locations'][venue]['name'],'Dalia Hanı')
        door.update(name='Eski Han Kapısı',description='Eski Han Kapısı',open=False,locked=True,broken=False)
        session.rng.seed(1776)
        return session,url,door['id']

    async def test_branch_clause_never_forces_dalia_tavern_door(self):
        session,url,door_id=await self.fixture()
        def state():
            # Always re-read the canonical collection; rollback can replace records.
            return copy.deepcopy({'door':next(d for d in session.world_state['doors'] if d['id']==door_id),
                'character':session.character,'inventory':session.world_state['inventory'],
                'rng':session.rng.getstate(),'clock':campaign_time.public_time(session.world_state)})
        before=state()
        with patch.object(self.app.state.ollama_adapter,'_client',fixture.ControlledVenueOllamaClient(intent='narrative')):
            response=await self.http.post(url,json={'message':'Eski Han Kapısını inceliyorum ve bir dalı kırıyorum.','action_id':str(uuid.uuid4())})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(before,state())

    async def test_actual_named_door_force_still_runs_authoritative_check(self):
        session,url,door_id=await self.fixture();before=session.rng.getstate()
        with patch.object(self.app.state.ollama_adapter,'_client',fixture.ControlledVenueOllamaClient(intent='narrative')):
            response=await self.http.post(url,json={'message':'Eski Han Kapısını kırıyorum.','action_id':str(uuid.uuid4())})
        self.assertEqual(response.status_code,200,response.text)
        door=next(d for d in session.world_state['doors'] if d['id']==door_id)
        self.assertTrue(door['open']);self.assertFalse(door['locked']);self.assertTrue(door['broken'])
        self.assertNotEqual(before,session.rng.getstate())
