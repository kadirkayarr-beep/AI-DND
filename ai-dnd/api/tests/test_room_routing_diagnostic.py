"""Diagnostic evidence; successful collection is not a fixed room-purpose contract."""
import json
from unittest.mock import patch
import bold_acts
from api.tests.test_economic_room import Counter
from api.tests.test_three_plays import PlayClient

class RoomRoutingDiagnostic(Counter):
    def test_record_explicit_say_request_route(self):
        before = self.money()
        fake = PlayClient()
        with patch('game.ollama.chat', side_effect=fake.chat):
            result = self.turn('bi oda tutayım', interaction_mode='say', target_id='barman')
        self.assertEqual(self.money(), before, 'a spoken request may not charge or grant a room')
        observed = [card['proposal']['purpose'] for card in self.prepared()]
        print('ROOM_ROUTE_DIAGNOSTIC:' + json.dumps({'case':'explicit_say_room_request',
            'desired_purposes':['room'],'observed_purposes':observed,
            'goal_met':observed == ['room'],'product_acceptance':False},ensure_ascii=False))

    def test_record_compound_gift_existing_room_predicate(self):
        before = self.money()
        self.s._coin_paid = (5, self.npc('barman'), self.here)
        result = bold_acts._room_asked(self.s,'Oda hakkında konuşup barmene 5 bakır bahşiş veriyorum')
        self.assertEqual(self.money(), before, 'diagnosis must leave purse, room, clock and ledger unchanged')
        observed = [card['proposal']['purpose'] for card in self.prepared()]
        print('ROOM_ROUTE_DIAGNOSTIC:' + json.dumps({'case':'compound_gift_mentions_room',
            'desired_room_card':False,'observed_purposes':observed,
            'goal_met':'room' not in observed,'product_acceptance':False},ensure_ascii=False))
