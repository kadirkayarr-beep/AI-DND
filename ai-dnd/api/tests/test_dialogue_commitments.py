import copy,json,sqlite3,unittest,uuid
import httpx
import grounded_action
import local_places
import npc_statements
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_dialogue_runtime as base
from api.tests import test_front_proposal as front_tests
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.town_seed import fixed_town
class CommitmentTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def test_unbacked_named_recommendation_rolls_back(self):
  await self.setup_free();self.reply.spoken='Gümüş Kılıç Hanı burada; oraya gidebilirsin.';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_unbacked_generic_recommendation_rolls_back(self):
  await self.setup_free();self.reply.spoken='Yakında bir han var, oraya git.';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_denied_historical_and_hypothetical_names_do_not_create(self):
  await self.setup_free()
  for text in ('Gümüş Kılıç Hanı diye bir yer yok.','Eskiden Gümüş Kılıç Hanı vardı.','Gümüş Kılıç Hanı olsaydı oraya giderdim.'):
   self.reply.spoken=text;before=copy.deepcopy(self.world['locations']);r=await self.send('Han var mı?')
   self.assertEqual(r.status_code,200,r.text);self.assertEqual(before,self.world['locations'])
 async def test_denial_does_not_mask_next_unbacked_recommendation(self):
  await self.setup_free();self.reply.spoken='Eski Han yok; Gümüş Kılıç Hanı burada, oraya git.'
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text)
 async def test_job_promise_without_job_record_rolls_back(self):
  await self.setup_free();self.reply.spoken='Sana verebileceğim bir iş var, paketi götür.';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_missing_commitment_fields_is_invalid_packet(self):
  await self.setup_free();self.reply.raw=json.dumps({'spoken_text':'Merhaba.','stage_direction':''});r=await self.send('Selam.');self.assertEqual(r.status_code,503,r.text)
 async def test_discourse_prefix_does_not_become_part_of_existing_place_name(self):
  await self.setup_free();self.world['locations']['real_inn']={'id':'real_inn','name':'Gümüş Kılıç Hanı','scene_kind':'tavern','parent_location_id':self.world['location']}
  for text in ('Evet, Gümüş Kılıç Hanı burada.','Hayır, Gümüş Kılıç Hanı kapalı.'):
   self.reply.spoken=text;r=await self.send('Han var mı?');self.assertEqual(r.status_code,200,r.text);self.assertIn(text,r.json()['narration'])
 async def test_unknown_place_after_comma_is_still_unbound(self):
  await self.setup_free();self.reply.spoken='Evet, Gümüş Kılıç Hanı burada.'
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text)


Q158 = "I thank the priest and leave for Yolcu Turna Hanı, where I paid for a room the previous night."  # QA #158
Q155_SPEECH = "ben gidip kimseyi zorla getiremem, ama parmağımla gösterebilirim"  # #155: the priest's own words
INN_NAME = "Yolcu Turna Hanı"


class EscortOnlyWhenAsked(unittest.IsolatedAsyncioTestCase):
    """Dilim 3D Task 6 (#155, #158, #161): a person who offered to point the way (an open `show` promise with no
    destination) walks along only when the line asks them along, and goes back to where they were half an hour
    after; saved, undone and reloaded with the turn."""
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc, open_job = front_tests.FrontTable.campaign_with_npc, front_tests.FrontTable.open_job
    the_inn = front_tests.FrontTable.the_inn

    async def asyncSetUp(self):
        await front_tests.FrontTable.asyncSetUp(self)
        with fixed_town(self, 4551):
            await front_tests.FrontTable.begin(self)
        self.street = self.world["location"]
        self.inn = self.the_inn()
        self.world["locations"][self.inn]["name"] = INN_NAME  # #158's line names the inn by this name
        next(d for d in self.world["doors"] if d.get("id") == f"venue-door:{self.inn}").update(locked=False, open=False)
        self.temple = local_places.create_local_place(self.world, self.street, "temple")["id"]
        self.priest = "npc_t6_rahip"
        self.world["npcs"].append({"id": self.priest, "name": "Teron", "role": "Rahip", "current_hp": 10,
                                   "status": "active", "location": self.temple, "place_role_of": self.temple})
        self.world["location"] = self.temple
        self.world["flags"].update(active_npc_id=self.priest, last_npc_id=self.priest, active_npc_until_turn=99)
        # #155: "getiremem" is a refusal to fetch anyone; the clause after it is the promise to point the way.
        promise = npc_statements.commit(self.world, self.person(self.priest), "show", "yolu",
                                        Q155_SPEECH.split(", ", 1)[1], "Yolu gösterir misin?")
        self.assertIsNotNone(promise)
        self.assertFalse(promise.get("destination"))

    def live(self):
        return self.manager.get(self.session_id).game_session

    def world_now(self):
        return self.live().world_state

    def person(self, npc_id):
        return next(n for n in self.world_now()["npcs"] if n.get("id") == npc_id)

    def npc_location(self, npc_id):
        return self.person(npc_id)["location"]

    def location(self):
        return self.world_now()["location"]

    def elapsed(self):
        return self.world_now()["campaign_time"]["elapsed_seconds"]

    def snapshot(self):
        session = self.live()
        return copy.deepcopy({"world_state": session.world_state, "messages": session.messages})

    async def turn(self, line, *, front=None):
        self.client.front = front or {"kind": "unclear"}
        self._last_action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": line, "action_id": self._last_action_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    async def wait(self, line):
        return await self.turn(line, front={"kind": "wait"})

    async def undo(self):
        reply = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                     json={"action_id": str(uuid.uuid4()), "target_action_id": self._last_action_id})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply

    async def escort_to_inn(self):
        await self.turn("Rahiple birlikte hana gidiyorum.", front={"kind": "go_to", "place_id": self.inn, "inside": True})
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(self.npc_location(self.priest), self.inn)

    def _stored_payload(self):
        with sqlite3.connect(self.store.path) as connection:
            row = connection.execute("SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                                     (self.campaign_id,)).fetchone()
        return json.loads(row[0])

    def _store_payload(self, payload):
        connection = sqlite3.connect(self.store.path)
        try:
            connection.execute("UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                               (json.dumps(payload, ensure_ascii=False), self.campaign_id))
            connection.commit()
        finally:
            connection.close()

    async def reload(self, *, edit_saved_world=None):
        """Save, optionally rewrite the stored world, and resume the campaign through a fresh app and manager."""
        self.campaign_id = self.manager.get(self.session_id).campaign_id
        self.manager.save_campaign(self.campaign_id)
        if edit_saved_world is not None:
            payload = self._stored_payload()
            edit_saved_world(payload["engine_save"]["world_state"])
            self._store_payload(payload)
        old_http = self.http
        self.manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        self.app = create_app(session_manager=self.manager, ollama_adapter=AuthenticatedOllamaAdapter(self.client),
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        await old_http.aclose()
        resumed = await self.http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.session_id = resumed.json()["session_id"]
        self.turn_url = f"/api/game/sessions/{self.session_id}/turn"
        self.world = self.world_now()

    async def load_save_from_before_this_task(self):
        """A save written before this task holds the priest at the inn with no `escort_return` key."""
        await self.escort_to_inn()

        def strip(world):
            npc = next(n for n in world["npcs"] if n.get("id") == self.priest)
            self.assertIn("escort_return", npc)
            del npc["escort_return"]
        await self.reload(edit_saved_world=strip)
        self.assertNotIn("escort_return", self.person(self.priest))

    def start_combat_here(self):
        self.world_now().setdefault("combat", {})["active"] = True

    async def test_158_the_priest_stays(self):
        reply = await self.turn(Q158, front={"kind": "go_to", "place_id": self.inn, "inside": True})
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(self.npc_location(self.priest), self.temple)
        self.assertNotIn("yanında yürüyor", reply.json()["narration"])
        self.assertNotIn("escort_return", self.person(self.priest))
        self.assertTrue(npc_statements.open_commitments(self.world_now(), npc_id=self.priest, kind="show"))

    async def test_asked_along_he_comes_and_remembers_home(self):
        before = self.elapsed()
        reply = await self.turn("Rahiple birlikte hana gidiyorum.",
                                front={"kind": "go_to", "place_id": self.inn, "inside": True})
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(self.npc_location(self.priest), self.inn)
        self.assertIn("Teron yanında yürüyor", reply.json()["narration"])
        field = self.person(self.priest)["escort_return"]
        self.assertEqual(field["home"], self.temple)
        self.assertGreaterEqual(field["at"], before + npc_statements.ESCORT_STAY_SECONDS)
        self.assertEqual(field["at"], self.elapsed() + npc_statements.ESCORT_STAY_SECONDS)
        self.assertFalse(npc_statements.open_commitments(self.world_now(), npc_id=self.priest, kind="show"))

    async def test_asks_along_reads_name_or_role_with_a_together_word(self):
        priest = self.person(self.priest)
        for line in ("Rahiple birlikte hana gidiyorum.", "Teron benimle gelsin, hana gidiyoruz.",
                     "Teron, come with me to the inn.", "Teron and I go to the inn together.", "Rahip bana eşlik etsin.",
                     "Come with me to the inn, Teron."):
            with self.subTest(line=line):
                self.assertTrue(grounded_action._asks_along(self.world_now(), line, priest))
        for line in (Q158, "Hana gidiyorum.", "Rahibe teşekkür edip hana gidiyorum.", "Birlikte hana gidelim.",
                     # Fix round 1 (F3): a no, 'alone', or a together-word that belongs to another doing is no ask
                     "Rahip benimle gelmesin, hana yalnız gidiyorum.", "Rahip benimle gelmeden hana gidiyorum.",
                     "Rahip kilisede diğerleriyle birlikte dua ediyor; ben hana gidiyorum.",
                     "Rahiple birlikte dua ettikten sonra hana gidiyorum.", "Rahip benimle gelmek istemedi; hana gidiyorum.",
                     "Teron'un dediği gibi, Sera ile birlikte hana gidiyorum.", "Teron, don't come with me to the inn.",
                     "Rahiple birlikte değil, tek başıma hana gidiyorum."):
            with self.subTest(line=line):
                self.assertFalse(grounded_action._asks_along(self.world_now(), line, priest))

    async def assert_stays_home(self, line):
        reply = await self.turn(line, front={"kind": "go_to", "place_id": self.inn, "inside": True})
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(self.npc_location(self.priest), self.temple)
        self.assertNotIn("yanında yürüyor", reply.json()["narration"])
        self.assertNotIn("escort_return", self.person(self.priest))
        self.assertTrue(npc_statements.open_commitments(self.world_now(), npc_id=self.priest, kind="show"))

    async def test_a_no_in_the_same_breath_leaves_him_home(self):
        await self.assert_stays_home("Rahip benimle gelmesin, hana yalnız gidiyorum.")

    async def test_a_together_that_is_someone_elses_leaves_him_home(self):
        await self.assert_stays_home("Rahip kilisede diğerleriyle birlikte dua ediyor; ben hana gidiyorum.")

    def strike_down(self, how):
        self.person(self.priest).update(current_hp=0 if how == "dead" else 1, combat_status=how)

    async def test_a_dead_or_unconscious_priest_does_not_walk(self):
        for how in ("dead", "unconscious"):
            with self.subTest(how=how):
                self.strike_down(how)
                await self.assert_stays_home("Rahiple birlikte hana gidiyorum.")
                self.world_now()["location"] = self.temple

    async def test_a_dead_or_unconscious_escort_is_not_sent_home(self):
        await self.escort_to_inn()
        for how in ("dead", "unconscious"):
            with self.subTest(how=how):
                self.strike_down(how)
                self.assertEqual(npc_statements.return_escorts(self.world_now(), self.elapsed() + 3600), [])
                self.assertEqual(self.npc_location(self.priest), self.inn)
        await self.wait("yarım saat bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.inn)

    async def test_a_locked_door_leaves_him_beside_the_player_in_the_street(self):
        next(d for d in self.world["doors"] if d.get("id") == f"venue-door:{self.inn}").update(locked=True, open=False)
        reply = await self.turn("Rahiple birlikte hana gidiyorum.",
                                front={"kind": "go_to", "place_id": self.inn, "inside": True})
        self.assertEqual(self.location(), self.street)
        self.assertEqual(self.npc_location(self.priest), self.street)  # he walked along; the state says so too
        self.assertIn("Teron yanında yürüyor", reply.json()["narration"])
        self.assertIn("kilitli", reply.json()["narration"])
        self.assertEqual(self.person(self.priest)["escort_return"]["home"], self.temple)
        self.assertFalse(npc_statements.open_commitments(self.world_now(), npc_id=self.priest, kind="show"))
        await self.wait("yarım saat bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.temple)

    async def test_he_goes_home_after_half_an_hour(self):
        await self.escort_to_inn()
        await self.wait("yarım saat bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.temple)
        self.assertNotIn("escort_return", self.person(self.priest))

    async def test_not_before(self):
        await self.escort_to_inn()
        await self.wait("10 dakika bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.inn)
        self.assertEqual(self.person(self.priest)["escort_return"]["home"], self.temple)

    async def test_a_second_walk_keeps_the_first_home(self):
        await self.escort_to_inn()
        first = dict(self.person(self.priest)["escort_return"])
        smithy = local_places.create_local_place(self.world_now(), self.street, "smithy")["id"]
        self.assertIsNotNone(npc_statements.commit(self.world_now(), self.person(self.priest), "show", "demirhaneyi",
                                                   "Demirhaneyi de gösterebilirim.", "Demirhane nerede?"))
        await self.turn("Rahiple birlikte demirhaneye gidiyorum.", front={"kind": "go_to", "place_id": smithy})
        self.assertEqual(self.location(), smithy)
        self.assertEqual(self.npc_location(self.priest), smithy)
        self.assertEqual(self.person(self.priest)["escort_return"]["home"], first["home"])
        self.assertGreater(self.person(self.priest)["escort_return"]["at"], first["at"])

    async def test_return_survives_reload(self):
        await self.escort_to_inn()
        await self.reload()
        self.assertEqual(self.person(self.priest)["escort_return"]["home"], self.temple)
        await self.wait("yarım saat bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.temple)
        self.assertNotIn("escort_return", self.person(self.priest))

    async def test_a_replayed_walk_writes_the_field_once(self):
        await self.escort_to_inn()
        first = copy.deepcopy(self.person(self.priest))
        self.client.front = {"kind": "go_to", "place_id": self.inn, "inside": True}
        again = await self.http.post(self.turn_url, json={"message": "Rahiple birlikte hana gidiyorum.",
                                                           "action_id": self._last_action_id})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(self.person(self.priest), first)

    async def test_undo_takes_the_escort_back_whole(self):
        before = self.snapshot()
        await self.escort_to_inn()
        self.assertNotEqual(self.snapshot(), before)
        await self.undo()
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("escort_return", self.person(self.priest))

    async def test_undo_of_the_return_brings_him_back_to_the_inn(self):
        await self.escort_to_inn()
        before = self.snapshot()
        await self.wait("yarım saat bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.temple)
        await self.undo()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.person(self.priest)["escort_return"]["home"], self.temple)

    async def test_no_return_during_combat(self):
        await self.escort_to_inn()
        self.start_combat_here()
        self.assertEqual(npc_statements.return_escorts(self.world_now(), self.elapsed() + 3600), [])
        self.assertEqual(self.npc_location(self.priest), self.inn)
        self.assertEqual(self.person(self.priest)["escort_return"]["home"], self.temple)

    async def test_return_escorts_direct(self):
        await self.escort_to_inn()
        world = self.world_now()
        at = self.person(self.priest)["escort_return"]["at"]
        self.assertEqual(npc_statements.return_escorts(world, at - 1), [])
        self.assertEqual(self.npc_location(self.priest), self.inn)
        self.assertEqual(npc_statements.return_escorts(world, at), [self.priest])
        self.assertEqual(self.npc_location(self.priest), self.temple)
        self.assertNotIn("escort_return", self.person(self.priest))
        self.assertEqual(npc_statements.return_escorts(world, at), [])  # the same moment twice does nothing

    async def test_a_home_that_is_gone_leaves_him_where_he_is(self):
        await self.escort_to_inn()
        world = self.world_now()
        del world["locations"][self.temple]
        self.assertEqual(npc_statements.return_escorts(world, self.elapsed() + 3600), [])
        self.assertEqual(self.npc_location(self.priest), self.inn)
        self.assertNotIn("escort_return", self.person(self.priest))

    async def test_a_save_without_the_field_loads(self):
        await self.load_save_from_before_this_task()
        self.assertEqual((await self.turn("etrafa bakıyorum")).status_code, 200)
        await self.wait("yarım saat bekliyorum")
        self.assertEqual(self.npc_location(self.priest), self.inn)  # nothing written says he was anywhere else
