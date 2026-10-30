import copy,unittest
import dialogue_runtime
class DeceptionTests(unittest.TestCase):
 def test_no_motive_means_no_deception(self):
  self.assertTrue(hasattr(dialogue_runtime,'deception_context'))
  self.assertIsNone(dialogue_runtime.deception_context({'flags':{'turn_index':1}},{'id':'n'}, {'text':'Nasılsın?'}))
 def test_unsupported_motive_cannot_authorize_a_lie(self):
  self.assertTrue(hasattr(dialogue_runtime,'deception_context'))
  n={'id':'n','dialogue_deception':{'motive':'Çıkarını korumak','evidence_id':'invented','topic':'plan','remaining_uses':1}}
  self.assertIsNone(dialogue_runtime.deception_context({'flags':{'turn_index':1}},n,{'text':'Planın ne?'}))
 def test_supported_motive_is_topic_scoped_and_read_only(self):
  self.assertTrue(hasattr(dialogue_runtime,'deception_context'))
  n={'id':'n','dialogue_deception':{'motive':'Kendisini tehdit eden kişiden planını gizlemek','evidence_id':'event:threat','topic':'plan','remaining_uses':1}}
  w={'flags':{'turn_index':1},'relationships':{'n':{'score':-3,'events':['event:threat']}}};before=copy.deepcopy((w,n))
  self.assertIsNotNone(dialogue_runtime.deception_context(w,n,{'text':'Planın ne?'}));self.assertIsNone(dialogue_runtime.deception_context(w,n,{'text':'Hanın adı ne?'}));self.assertEqual(before,(w,n))
