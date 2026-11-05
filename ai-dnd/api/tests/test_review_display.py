"""Review regressions for rendered memory rows and authoritative ammo notes."""
import copy
import unittest
import game
import equipment_economy
import npc_told

class DisplayReview(unittest.TestCase):
    def test_memory_row_including_quotes_stays_within_200_chars(self):
        rows = ['x' * 200]
        before = copy.deepcopy(rows)
        text = npc_told.view(rows, header='H:')
        rendered = text.splitlines()[1]
        self.assertLessEqual(len(rendered), 200)
        self.assertLessEqual(len(text.encode('utf-8')), 600)
        self.assertEqual(rows, before)

    def test_typed_inventory_shows_remaining_ammo_once(self):
        self.check_inventory('/item list')

    def test_natural_inventory_shows_remaining_ammo_once(self):
        self.check_inventory('\u00e7antamda ne var')

    def check_inventory(self, message):
        session = game.create_session()
        session.character['current_hp'] = 20
        session.world_state['inventory'] = []
        session.world_state['ammunition'] = {'arrow':19}
        result = equipment_economy.execute(session, message)
        self.assertTrue(result['action_result']['success'], result)
        self.assertEqual(result['narration'].count('(ok: 19)'), 1)
        self.assertEqual(session.world_state['ammunition'], {'arrow':19})