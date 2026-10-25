import copy,uuid,unittest
from unittest.mock import patch
import npc_speech_boundary
from api.tests.test_route_focus_regressions import RouteFocusRegressionTests
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient

class PlayerQuoteTests(unittest.TestCase):
 def test_single_quote_is_removed_and_an_apostrophe_stays(self):
  said = "Gülümseyip 'Kitaplar bile kimlik gösteriyor mu?' diyorum."
  speech = "Hlin'in yüzü: Kitaplar bile kimlik gösteriyor mu? Bence yüz daha dürüst."
  self.assertEqual(npc_speech_boundary.player_supplied_quote(said), "Kitaplar bile kimlik gösteriyor mu?")
  cleaned = npc_speech_boundary.strip_player_quote(speech, said)
  self.assertNotIn("Kitaplar bile kimlik gösteriyor mu?", cleaned)
  self.assertIn("Hlin'in", cleaned)
  self.assertIn("dürüst", cleaned)
 def test_gesture_and_quote_word_leave_the_npc_line(self):
  said = "Gülümseyip 'Kitaplar bile kimlik gösteriyor mu?' diyorum."
  speech = "Gülümsediğiniz bu yüz hatları bana bir kimlik kartı gibi duruyor."
  cleaned = npc_speech_boundary.strip_player_echo(speech, said)
  self.assertNotIn("ülümse", cleaned.casefold())
  self.assertNotIn("kimlik", cleaned.casefold())
  live = "Gülüşünüz, dostum, bu şehirde işlenmiş bir maskeden daha tehlikeli olabilir."
  self.assertEqual(npc_speech_boundary.strip_player_echo(live, said), "")

 def test_words_without_a_quote_stay(self):
  self.assertIsNone(npc_speech_boundary.player_supplied_quote("O espriye neden öyle tepki verdin?"))
  self.assertEqual(npc_speech_boundary.strip_player_quote("Hlin omuz silker.", "Nasılsın dostum?"), "Hlin omuz silker.")

 def test_spinning_cups_and_bread_leave_the_barman_line(self):
  facts = [{
   "name": "Ahşap masa",
   "description": "Kenarında sıradan bir kil bardak duran sağlam bir masa.",
   "aliases": ["masa", "ahşap masa", "bardak", "kil bardak"],
  }]
  spoken = (
   "Günün gidişi, tezgâhın üzerinde dönen bardaklar kadar kaotik ama tatlı. "
   "Mutfaktan gelen o taze ekmek kokusu işte bu."
  )
  cleaned = npc_speech_boundary.drop_ungrounded_prop_sentences(spoken, facts)
  self.assertNotIn("bardak", cleaned.casefold())
  self.assertNotIn("ekmek", cleaned.casefold())
  kept = npc_speech_boundary.drop_ungrounded_prop_sentences(
   "Kenarında sıradan bir kil bardak duruyor.", facts
  )
  self.assertIn("bardak", kept.casefold())

class BoundSpeechLabelTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=RouteFocusRegressionTests.asyncSetUp
 asyncTearDown=RouteFocusRegressionTests.asyncTearDown
 prepare=RouteFocusRegressionTests.prepare
 snap=RouteFocusRegressionTests.snap
 replay_cold=RouteFocusRegressionTests.replay_cold
 async def test_npc_does_not_speak_the_players_quote(self):
  await self.prepare()
  self.client=ScriptedNpcSpeechClient('Kitaplar bile kimlik gösteriyor mu? Yüz daha dürüst.', stage_direction="Hlin süpürgeyi çevirir.")
  body={'message':"Gülümseyip 'Kitaplar bile kimlik gösteriyor mu?' diyorum.",'target_id':self.npc['id'],'interaction_mode':'say','action_id':str(uuid.uuid4())}
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):r=await self.http.post(self.url,json=body)
  self.assertEqual(r.status_code,200,r.text)
  shown=r.json()['narration']
  self.assertNotIn('Kitaplar bile kimlik gösteriyor mu?', shown)
  self.assertIn('dürüst', shown)

 async def test_http_label_history_save_replay(self):
  await self.prepare()
  raw='Marek: “Bunu tam bilmiyorum; bugün burası bana da sakin geliyor.”'
  self.client=ScriptedNpcSpeechClient(raw)
  body={'message':'Bugün burası nasıl?','target_id':self.npc['id'],'interaction_mode':'say','action_id':str(uuid.uuid4())}
  before=self.snap()
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):r=await self.http.post(self.url,json=body)
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['narration'],raw);self.assertEqual(self.client.chat_calls,1)
  import game
  token=game._ACTIVE_SESSION.set(self.session)
  try:log=game._experimental_recent_exchanges(self.npc['id'])
  finally:game._ACTIVE_SESSION.reset(token)
  self.assertEqual(len(log),1);self.assertEqual(log[0]['npc'],'Bunu tam bilmiyorum; bugün burası bana da sakin geliyor.')
  self.assertEqual(before['inventory'],self.snap()['inventory']);self.assertEqual(before['rng'],self.snap()['rng'])
  # replay_cold expects the diagnostic client's recorded list, not a new call.
  self.client.calls=[None]*self.client.chat_calls
  await self.replay_cold(body,r)
  self.assertEqual(self.client.chat_calls,1)

 async def test_exact_label_only_normalization(self):
  await self.prepare();n=self.npc
  f=npc_speech_boundary.normalize_bound_speech_label
  self.assertEqual(f('Marek: “Merhaba.”',n,visible=True),'Merhaba.')
  for raw in ['Sera: “Merhaba.”','marek: “Merhaba.”','Marek: “Merhaba.','Marek: “Sera: “Merhaba.””','Marek (gülümser): “Merhaba.”','Sera bana Marek dedi.','Marek: “Ben Sera.” Sonra gider.']:
   with self.subTest(raw=raw):self.assertEqual(f(raw,n,visible=True),raw)
  for flags in [{'name_known_to_player':False},{'hidden':True},{'discovered':False}]:
   other={**n,**flags};self.assertEqual(f('Marek: “Merhaba.”',other,visible=True),'Marek: “Merhaba.”')
  self.assertEqual(f('Marek: “Merhaba.”',n,visible=False),'Marek: “Merhaba.”')

 async def test_inner_wrong_identity_not_hidden_by_self_label(self):
  await self.prepare();client=ScriptedNpcSpeechClient('Marek: “Benim adım Sera.”')
  with patch.object(self.app.state.ollama_adapter,'_client',client):r=await self.http.post(self.url,json={'message':'Bugün keyfin nasıl?','target_id':self.npc['id'],'interaction_mode':'say','action_id':str(uuid.uuid4())})
  self.assertEqual(r.status_code,200);self.assertNotIn('Benim adım Sera',r.json()['narration']);self.assertEqual(client.chat_calls,1)

 async def test_stage_and_internal_names_not_cleaned(self):
  await self.prepare();client=ScriptedNpcSpeechClient('Marek: “Sera diye birini tanımıyorum.”',stage_direction='Marek başını sallar.')
  with patch.object(self.app.state.ollama_adapter,'_client',client):r=await self.http.post(self.url,json={'message':'Sera diye birini tanıyor musun?','target_id':self.npc['id'],'interaction_mode':'say','action_id':str(uuid.uuid4())})
  self.assertEqual(r.status_code,200);self.assertIn('Sera diye birini tanımıyorum.',r.json()['narration']);self.assertIn('başını sallar',r.json()['narration']);self.assertEqual(client.chat_calls,1)
