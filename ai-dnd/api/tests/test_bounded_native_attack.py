"""Synthetic bounded encounter regressions; no live campaign/model access."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4
import bounded_encounter
import equipment_economy
from api.tests.test_bounded_encounter import NativeBase


class BoundedNativeAttackTests(NativeBase):
    def prepare_bard(self):
        from api.character_creation import configure_character
        import game
        session=self.session
        session.rng.seed(29)
        for _ in range(100):
            configure_character(session,mode='random')
            if session.character['class']=='Bard':
                break
        self.assertEqual(session.character['class'],'Bard')
        self.walk_to_contact()
        if not session.find_weapon_in_inventory('Dagger')[0]:
            session.world_state['inventory'].append('Dagger')
        equipment_economy.materialize(session.world_state)
        session.world_state['equipment']={'main_hand':None,'off_hand':None}
        game._validate_save_payload(session.serialize_game_state())
        return session.world_state['bounded_encounter']['npc_id']

    def request(self, target, message='Hançer çekip dexterity ile saldırıyorum'):
        combat=self.session.world_state['combat']
        return {'message':message,'interaction_mode':'do','action_id':str(uuid4()),
                'combat_id':combat['combat_id'],'combat_round':combat['round'],
                'combat_turn_index':combat['current_turn_index'],'target_id':target}

    def test_draw_attack_uses_existing_native_mechanics_without_model_and_replays(self):
        target=self.prepare_bard()
        request=self.request(target)
        with patch('game.ollama.chat',side_effect=AssertionError('no model')), \
             patch('game.ask_dungeon_master',side_effect=AssertionError('no model')):
            result=self.client.post(f'/api/sessions/{self.sid}/turn',json=request)
        self.assertEqual(result.status_code,200,result.text)
        self.assertIsNotNone(self.session.world_state['equipment']['main_hand'])
        before=self.canonical()
        saved=self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json()
        replay=self.client.post(f'/api/sessions/{self.sid}/turn',json=request)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),result.json())
        self.assertEqual(self.canonical(),before)
        self.assertEqual(self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json(),saved)

    def test_failed_draw_rolls_back_and_records_no_receipt(self):
        target=self.prepare_bard()
        request=self.request(target)
        before=self.canonical()
        saved=self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json()
        import weapon_attack
        with patch.object(weapon_attack,'_resolve',side_effect=RuntimeError('synthetic failure after draw preparation')):
            result=self.client.post(f'/api/sessions/{self.sid}/turn',json=request)
        self.assertEqual(result.status_code,500,result.text)
        self.assertEqual(self.canonical(),before)
        self.assertEqual(self.client.get(f"/api/campaigns/{self.campaign['campaign_id']}").json(),saved)

    def test_gate_does_not_bypass_model_for_dialogue_negation_or_other_locations(self):
        self.prepare_bard()
        before=self.canonical()
        for message in ['Hançerle saldırmıyorum','Hançerle saldırsam?','Merhaba']:
            self.assertFalse(bounded_encounter.native_request(self.session,message,None))
        self.assertEqual(before,self.canonical())
        self.session.world_state['location']='elsewhere'
        self.assertFalse(bounded_encounter.native_request(self.session,'Hançer çekip saldırıyorum',None))


class HeldCatalogSaveTests(unittest.TestCase):
    def world(self, weapon_id="dagger"):
        from weapon_catalog import lookup
        weapon = lookup(weapon_id)
        return {"inventory": [{"item_id": "synthetic-weapon", "name": weapon["name"],
                               "weapon_id": weapon_id}],
                "equipment": {"main_hand": "synthetic-weapon", "off_hand": None}}

    def test_owned_catalog_weapons_validate_without_mutation(self):
        import held_weapon
        for identity in ("dagger", "shortsword", "longsword", "shortbow"):
            with self.subTest(weapon=identity):
                world = self.world(identity)
                before = copy.deepcopy(world)
                held_weapon.validate_saved(world)
                equipment_economy.validate_world(world)
                self.assertEqual(world, before)

    def test_unknown_and_duplicate_instances_still_rejected(self):
        import held_weapon
        world = self.world()
        world["inventory"][0]["weapon_id"] = "unknown"
        with self.assertRaises(ValueError):
            held_weapon.validate_saved(world)
        world = self.world()
        world["inventory"].append(copy.deepcopy(world["inventory"][0]))
        with self.assertRaises(ValueError):
            held_weapon.validate_saved(world)

    def test_legacy_sword_rule_preserved(self):
        import held_weapon
        for name, accepted in (("Longsword", True), ("Dagger", False)):
            world = {"inventory": [name], "equipment": {"main_hand": name, "off_hand": None}}
            if accepted:
                held_weapon.validate_saved(world)
            else:
                with self.assertRaises(ValueError):
                    held_weapon.validate_saved(world)
