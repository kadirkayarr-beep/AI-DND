"""Diagnostic only: inspect provenance in the unchanged legacy texture fixture."""
import copy,json,unittest
import game,living_world,exploration
class TextureProvenance(unittest.TestCase):
    def test_inventory_legacy_texture_provenance(self):
        session=game.create_session(seed=12)
        world=session.world_state
        world['features'].append({'id':'feature_hidden_road','name':'Gizli Yol','location':world['location'],'description':'Dar bir patika.'})
        before=copy.deepcopy(session.serialize_game_state())
        records={'location':world['location'],'visible_features':living_world.visible_features(world),'known_locations':exploration.known_locations(world),'inventory':world['inventory'],'npcs':world['npcs']}
        decisions={text:session._narration_safety_decision(text,'etrafa bak',None,{'action':'explore','status':'observed'}) for text in ('Gizli Yol durur.','Bardak durur.','Elara durur.')}
        print('TEXTURE_PROVENANCE='+json.dumps({'fixture':records,'decisions':decisions},ensure_ascii=False,default=str))
        self.assertEqual(before,session.serialize_game_state())
