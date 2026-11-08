"""New Barbarian source packages through actual creation/item/save HTTP owners."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4
from api.tests import test_roadmap_c10_rage_http as helpers
from api.tests.test_roadmap_c06_barbarian_creation_http import request

class StartingEquipmentHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=helpers.RageHttpTests.asyncSetUp
    asyncTearDown=helpers.RageHttpTests.asyncTearDown
    post=helpers.RageHttpTests.post
    snapshot=helpers.RageHttpTests.snapshot
    reopen=helpers.RageHttpTests.reopen

    async def create(self,package='A',level=2,background_option='B',edit=None):
        data=request(level);data.update(equipment_package=package,background_equipment_option=background_option)
        if edit:edit(data)
        response=await self.http.post('/api/game/campaigns',json={'character':data})
        self.assertEqual(response.status_code,200,response.text)
        a=response.json();return a,self.manager.get(a['session_id'])

    async def materialize(self,a):
        response=await self.post(a,{'message':'/item list','action_id':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text)
        return response

    async def test_actual_custom_one_two_a_b_wallet_quantity_and_hands(self):
        for level in (1,2):
            for package,cash in (('A',6500),('B',12500)):
                a,r=await self.create(package,level)
                self.assertEqual(r.game_session.world_state.get('currency',{}).get('player'),cash)
                await self.materialize(a);w=r.game_session.world_state
                handaxes=[i for i in w['inventory'] if i.get('weapon_id')=='handaxe']
                self.assertEqual(len(handaxes),4 if package=='A' else 0)
                self.assertEqual(len({i['item_id'] for i in handaxes}),len(handaxes))
                self.assertFalse(any('javelin' in str(i).lower() for i in w['inventory']))
                if package=='B':self.assertEqual(w['equipment'],{'main_hand':None,'off_hand':None})
                else:
                    axe=next(i for i in w['inventory'] if i.get('weapon_id')=='greataxe')
                    self.assertEqual(w['equipment'],{'main_hand':axe['item_id'],'off_hand':None})
                before=copy.deepcopy(r.game_session.serialize_game_state())
                self.manager.save_campaign(a['campaign_id']);self.manager.save_campaign(a['campaign_id'])
                r=await self.reopen(a)
                self.assertEqual(r.game_session.serialize_game_state(),before)

    async def test_actual_source_catalogue_exact_packages(self):
        response=await self.http.get('/api/game/character-creation-catalog')
        self.assertEqual(response.status_code,200,response.text)
        packages=response.json()['classes']['Barbarian']['equipment_packages']
        self.assertEqual({p['id']:p['items'] for p in packages},{'A':['Büyük Balta (Greataxe)','4 Handaxes',"Explorer's Pack",'15 GP'],'B':['75 GP']})

    async def test_certified_artisan_and_uncertified_background_currency_both_reach_the_purse(self):
        def artisan(data):
            data.update(background='Artisan',background_ability_bonuses={'strength':2,'intelligence':1},
                proficient_skills=['Athletics','Intimidation','Investigation','Persuasion','Perception'],
                proficient_tools=["Weaver's Tools"])
        for package,cash in (('A',4700),('B',10700)):
            a,r=await self.create(package,background_option='A',edit=artisan)
            self.assertEqual(r.game_session.world_state['currency']['player'],cash)
            self.assertNotIn('32 GP',r.game_session.world_state['inventory'])
        for package,cash in (('A',3100),('B',9100)):
            a,r=await self.create(package,background_option='A')
            self.assertEqual(r.game_session.world_state['currency']['player'],cash)
            self.assertNotIn('16 Altın',r.game_session.world_state['inventory'])

    async def test_random_selected_barbarian_uses_source_package_without_guessing(self):
        # Existing random route supports level1 only; force source class, not final character state.
        with patch('game.CLASSES',['Barbarian']),patch('game.RACES',['Human']):
            response=await self.http.post('/api/game/campaigns',json={'character':{'mode':'random'}})
        self.assertEqual(response.status_code,200,response.text)
        a=response.json();r=self.manager.get(a['session_id']);w=r.game_session.world_state
        self.assertEqual(r.game_session.character['class'],'Barbarian')
        self.assertEqual(r.game_session.character['level'],1)
        self.assertEqual(w['currency']['player'],4000)
        self.assertNotIn('25 Altın',w['inventory'])  # Farmer's written 25 gold joins the class 15 in the purse.
        await self.materialize(a)
        self.assertEqual(sum(i.get('weapon_id')=='handaxe' for i in w['inventory']),4)

    async def test_extra_background_handaxe_survives_and_one_exact_id_drop_replays(self):
        from api.dnd_2024_rules import BACKGROUND_DEFINITIONS
        background=copy.deepcopy(BACKGROUND_DEFINITIONS['Criminal'])
        background['equipment'].append('Handaxe')  # Synthetic source-boundary multiplicity, not a source claim.
        with patch.dict(BACKGROUND_DEFINITIONS,{'Criminal':background}):a,r=await self.create(background_option='A')
        await self.materialize(a)
        axes=[i['item_id'] for i in r.game_session.world_state['inventory'] if i.get('weapon_id')=='handaxe']
        self.assertEqual(len(axes),5);self.assertEqual(len(set(axes)),5)
        command={'message':f'/item drop {axes[0]}','action_id':str(uuid4())}
        from contextlib import contextmanager
        import sqlite3
        before=self.snapshot(r);transaction=self.store._transaction;reached=[]
        @contextmanager
        def fail_after_drop_receipt():
            with transaction() as connection:
                yield connection
                row=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (a['campaign_id'],command['action_id'])).fetchone()
                if row:
                    reached.append(True)
                    raise sqlite3.OperationalError('synthetic exact-ID drop receipt precommit')
        with patch.object(self.store,'_transaction',side_effect=fail_after_drop_receipt):
            failed=await self.post(a,command)
        self.assertGreaterEqual(failed.status_code,500,failed.text)
        self.assertEqual(reached,[True]);self.assertEqual(self.snapshot(r),before)
        accepted=await self.post(a,command);self.assertEqual(accepted.status_code,200,accepted.text)
        remaining=[i['item_id'] for i in r.game_session.world_state['inventory'] if i.get('weapon_id')=='handaxe']
        self.assertEqual(set(remaining),set(axes[1:]))
        before=self.snapshot(r)
        self.assertEqual((await self.post(a,command)).json(),accepted.json());self.assertEqual(self.snapshot(r),before)
        r=await self.reopen(a);expected=accepted.json();expected['session_id']=a['session_id']
        self.assertEqual((await self.post(a,command)).json(),expected)
        self.assertEqual(r.game_session.world_state['currency']['player'],3100)
        self.assertEqual({i['item_id'] for i in r.game_session.world_state['inventory'] if i.get('weapon_id')=='handaxe'},set(axes[1:]))

    async def test_stale_package_labels_and_client_money_overrides_reject(self):
        for extra in ({'equipment_choices':['4 Cirit']},{'equipment_choices':['2 El Baltası (Handaxe)']},
                      {'starting_gold':999},{'currency_cp':999},{'quantity':99}):
            data=request();data.update(extra)
            response=await self.http.post('/api/game/campaigns',json={'character':data})
            self.assertEqual(response.status_code,422,response.text)
        with self.store._connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM campaigns').fetchone()[0],0)

    async def test_real_create_insert_failure_publishes_no_wallet_or_character(self):
        from contextlib import contextmanager
        import sqlite3,json
        transaction=self.store._transaction;reached=[];before=dict(self.manager._sessions)
        @contextmanager
        def failing_transaction():
            with transaction() as connection:
                yield connection
                row=connection.execute('SELECT payload_json FROM campaigns').fetchone()
                if row:
                    reached.append(True)
                    self.assertEqual(json.loads(row[0])['engine_save']['world_state']['currency']['player'],12500)
                    raise sqlite3.OperationalError('synthetic new cash-only package INSERT precommit')
        data=request();data.update(equipment_package='B',background_equipment_option='B')
        with patch.object(self.store,'_transaction',side_effect=failing_transaction):
            response=await self.http.post('/api/game/campaigns',json={'character':data})
        self.assertGreaterEqual(response.status_code,500,response.text)
        self.assertEqual(reached,[True]);self.assertEqual(self.manager._sessions,before)
        with self.store._connect() as connection:self.assertEqual(connection.execute('SELECT count(*) FROM campaigns').fetchone()[0],0)
        # Creation has no action receipt/idempotency promise: this is a fresh successful attempt.
        response=await self.http.post('/api/game/campaigns',json={'character':data})
        self.assertEqual(response.status_code,200,response.text)
        r=self.manager.get(response.json()['session_id'])
        self.assertEqual(r.game_session.world_state['currency']['player'],12500)

    async def test_newly_authored_legacy_inventory_characterization_is_not_migrated(self):
        # This is an explicit compatibility fixture, NOT a purported historical receipt.
        a,r=await self.create('B')
        w=r.game_session.world_state
        w['inventory']=['4 Cirit','15 Altın',"Macera Çantası"]
        w['currency']['player']=321
        self.manager.save_campaign(a['campaign_id'])
        before=copy.deepcopy(r.game_session.serialize_game_state())
        r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),before)
        self.assertEqual(r.game_session.world_state['inventory'],['4 Cirit','15 Altın',"Macera Çantası"])
        self.assertEqual(r.game_session.world_state['currency']['player'],321)
