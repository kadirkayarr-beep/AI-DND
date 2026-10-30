"""Two real synthetic campaigns, actual session XP/HTTP/save owners; no sockets/model."""
import copy
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import httpx
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.c06_early_external_fixture_runtime import _seed_early_advancement

class ExternalEarlyFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_real_seed_campaigns_queued_choices_noncasting_confirm_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=CampaignStore(root/'campaigns.sqlite3',bound_principal=TEST_PLAYER);manager=SessionManager(campaign_store=store)
            try:seed=_seed_early_advancement(manager,store,root)
            except Exception as error:self.fail(f'Actual early seed must pass before sockets: {type(error).__name__}: {error}')
            self.assertEqual(len(manager.list_campaigns()),2)
            rows={r['class_name']:r for r in seed['campaigns']};sorc=rows['Sorcerer']['campaign_id'];barb=rows['Barbarian']['campaign_id']
            self.assertEqual((rows['Sorcerer']['after']['level'],rows['Sorcerer']['after']['applied_level'],rows['Sorcerer']['after']['xp']),(3,1,900))
            self.assertEqual((rows['Barbarian']['after']['level'],rows['Barbarian']['after']['applied_level'],rows['Barbarian']['after']['xp']),(2,1,300))
            app=create_app(session_manager=manager,ollama_adapter=None,authenticator=FixedAuthenticator(TEST_PLAYER))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                resumed=await client.post(f'/api/game/campaigns/{sorc}/resume');self.assertEqual(resumed.status_code,200,resumed.text);sid=resumed.json()['session_id']
                for target,choices,slots,count in [(2,{'prepared_spells':['Burning Hands','Chromatic Orb'],'metamagic':['Quickened Spell','Twinned Spell']},{'1':3},4),(3,{'prepared_spells':['Disguise Self','Detect Magic'],'subclass_id':'phb2024:subclass:sorcerer:aberrant-sorcery'},{'1':4,'2':2},6)]:
                    url=f'/api/game/sessions/{sid}/level-up';preview=(await client.get(url)).json();self.assertEqual((preview['status'],preview['target_level']),('ready',target))
                    request={'action_id':str(uuid4()),'campaign_id':sorc,'expected_revision':preview['revision'],'target_level':target,'choices':choices}
                    response=await client.post(url,json=request);self.assertEqual(response.status_code,200,response.text);body=response.json();c=body['state']['character']
                    self.assertEqual((c['level'],c['progression_level'],c['xp'],c['max_hp'],c['current_hp']),(3,target,900,20,20));self.assertEqual(len(c['spells']),count)
                    self.assertEqual(body['state']['spellcasting']['slots'],slots)
                    replay=await client.post(url,json=request);self.assertEqual(replay.json(),body)
                self.assertEqual((await client.post(f'/api/game/campaigns/{sorc}/save')).status_code,200)
                # Switch the actual campaign/session rather than mutate a view fixture.
                resumed=await client.post(f'/api/game/campaigns/{barb}/resume');self.assertEqual(resumed.status_code,200,resumed.text);bid=resumed.json()['session_id'];url=f'/api/game/sessions/{bid}/level-up'
                preview=(await client.get(url)).json();self.assertEqual((preview['status'],preview['target_level'],preview['choices_required']),('ready',2,{}));self.assertIsNone(preview['capacity'])
                for name in ('cantrip_ids','prepared_spell_ids','metamagic_options','subclass_options','supported_asi_choices'):self.assertEqual(preview[name],[])
                self.assertTrue(any('Reckless Attack' in x for x in preview['effects_supported']));self.assertTrue(any('Rage' in x for x in preview['effects_supported']));self.assertFalse(any(x.startswith('Rage unavailable') for x in preview['effects_pending']))
                request={'action_id':str(uuid4()),'campaign_id':barb,'expected_revision':preview['revision'],'target_level':2,'choices':{}}
                response=await client.post(url,json=request);self.assertEqual(response.status_code,200,response.text);c=response.json()['state']['character']
                self.assertEqual((c['level'],c['progression_level'],c['xp'],c['max_hp'],c['current_hp']),(2,2,300,23,23));self.assertNotIn('spellcasting_v1',manager.get(bid).game_session.world_state)
                self.assertEqual((await client.post(url,json=request)).json(),response.json());self.assertEqual((await client.post(f'/api/game/campaigns/{barb}/save')).status_code,200)
                self.assertIsNone(app.state.ollama_adapter)
            fresh_store=CampaignStore(store.path,bound_principal=TEST_PLAYER);fresh=SessionManager(campaign_store=fresh_store)
            for campaign,level,xp,maximum in [(sorc,3,900,20),(barb,2,300,23)]:
                _,record,*_=fresh.resume_campaign(campaign);c=record.game_session.character;self.assertEqual((c['progression_level'],c['xp'],c['max_hp']),(level,xp,maximum))
                if campaign==barb:self.assertNotIn('spellcasting_v1',record.game_session.world_state)
            before=[copy.deepcopy(fresh_store.get_campaign(x).payload) for x in (sorc,barb)]
            self.assertEqual(_seed_early_advancement(fresh,fresh_store,root),seed)
            self.assertEqual([fresh_store.get_campaign(x).payload for x in (sorc,barb)],before)
            self.assertEqual(len(fresh.list_campaigns()),2)
