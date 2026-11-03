"""A worthless thing the narrator showed in this scene can be picked up once (Kadir, 2026-11-03).

When the player's line takes a thing and no real item lies here, Python makes one plain item record only if this
place's narration named it, it is no coin and nothing of worth, nobody holds it yet and no fight is on. The record
carries its source and reaches the bag by one ledger item transfer. No real model is called: session tests patch
the model boundary to fail, and the HTTP test uses the project's fake client and a temporary campaign store.
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import equipment_economy
import game
import item_transfers
import pocket
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_step0_ledger_play import coin_in_labels
from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests


def labels(world):
    return [equipment_economy.label(item) for item in world.get("inventory", [])]


def every_item(world):
    return [item for _, items in equipment_economy.containers(world) for item in items or []]


def coin(world):
    """Every copper the world holds: purses plus coin still written in a pack."""
    return sum(v for v in (world.get("currency") or {}).values() if type(v) is int) + coin_in_labels(world)


def transfers(world):
    operations = ((world.get("flags") or {}).get("economic_ledger") or {}).get("operations") or {}
    return [data for data in operations.values() if data.get("purpose") == "item_transfer"]


class Scene(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [{"id": "guest", "name": "Oren", "role": "Yolcu", "location": self.here, "current_hp": 10,
                           "inventory": []}]
        self.w["currency"] = {"player": 500, "guest": 100}
        self.w["inventory"] = [{"item_id": "item_stick", "name": "Sopa"}]
        self.w["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(self.w)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def told(self, text):
        self.s.recent_dm_narrations.append(text.casefold())

    def take(self, line="kırık halkayı çantama koyuyorum"):
        return pocket.resolve(self.s, line)

    def test_broken_ring_on_the_counter_is_taken_once(self):
        self.told("Tezgâhın üstünde kırık bir halka duruyor.")
        items_before, coin_before = len(every_item(self.w)), dict(self.w["currency"])
        taken = self.take()
        self.assertIsNotNone(taken)
        self.assertEqual(taken["action_result"]["action"], "pocket")
        self.assertEqual(labels(self.w).count("Kırık halka"), 1)
        made = [item for item in self.w["inventory"] if equipment_economy.label(item) == "Kırık halka"]
        self.assertEqual((made[0]["source"], made[0]["source_place_id"]), ("narrated_scene", self.here))
        self.assertEqual(len(every_item(self.w)), items_before + 1)
        self.assertEqual(self.w["currency"], coin_before)
        moved = transfers(self.w)
        self.assertEqual(len(moved), 1)
        self.assertEqual((moved[0]["item_id"], moved[0]["source_id"], moved[0]["recipient_id"], moved[0]["net_debit_cp"]),
                         (made[0]["item_id"], f"ground:{self.here}", "player", 0))
        self.assertFalse((self.w.get("ground_items_by_location") or {}).get(self.here))
        equipment_economy.validate_world(self.w)

    def test_a_second_take_does_nothing(self):
        self.told("Tezgâhın üstünde kırık bir halka duruyor.")
        self.assertIsNotNone(self.take())
        after = (len(every_item(self.w)), len(transfers(self.w)), labels(self.w))
        self.assertIsNone(self.take())
        self.assertIsNone(pocket.take_named(self.s, "kırık halkayı alıyorum", "kırık halka"))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w)), labels(self.w)), after)
        self.assertEqual(labels(self.w).count("Kırık halka"), 1)

    def test_thrown_away_it_is_not_made_again_from_the_same_mention(self):
        self.told("Tezgâhın üstünde boş bir kupa duruyor.")
        self.assertIsNotNone(self.take("kupayı çantama koyuyorum"))
        self.assertEqual(labels(self.w).count("Kupa"), 1)
        self.assertIsNotNone(pocket.resolve(self.s, "kupayı denize atıyorum"))
        self.assertNotIn("Kupa", labels(self.w))
        self.assertIsNone(self.take("kupayı çantama koyuyorum"))
        self.assertNotIn("Kupa", labels(self.w))

    def test_an_unmentioned_thing_is_not_created(self):
        self.told("Tezgâhın üstünde boş bir kupa duruyor.")
        before = (len(every_item(self.w)), len(transfers(self.w)))
        self.assertIsNone(self.take())
        self.assertIsNone(pocket.take_named(self.s, "kırık halkayı alıyorum", "kırık halka"))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w))), before)
        self.assertNotIn("Kırık halka", labels(self.w))

    def test_only_the_assistant_messages_are_no_scene(self):
        self.s.messages.append({"role": "assistant", "content": "Tezgâhın üstünde kırık bir halka duruyor."})
        self.assertIsNone(self.take())
        self.assertNotIn("Kırık halka", labels(self.w))

    def test_a_mentioned_priced_item_is_not_created(self):
        self.told("Tezgâhın üstünde paslı bir hançer duruyor.")
        before = (len(every_item(self.w)), len(transfers(self.w)))
        self.assertIsNone(pocket.resolve(self.s, "hançeri çantama koyuyorum"))
        self.assertIsNone(pocket.take_named(self.s, "hançeri alıyorum", "hançer"))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w))), before)
        self.assertNotIn("Hançer", labels(self.w))
        self.assertIsNone(item_transfers.pick_up_told(self.w, "Hançer", stem="hancer"))
        self.assertIsNone(item_transfers.pick_up_told(self.w, "Bira", stem="bira"))
        self.assertIsNone(item_transfers.pick_up_told(self.w, "Kalkan", stem="kalkan"))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w))), before)

    def snapshot(self):
        return len(every_item(self.w)), len(transfers(self.w)), dict(self.w["currency"]), coin(self.w)

    def assert_nothing_made(self, before, *names):
        self.assertEqual(self.snapshot(), before)
        for name in names:
            self.assertNotIn(name, labels(self.w))

    def test_a_weapon_with_an_adjective_is_not_created(self):
        """'paslı hançer' is still a dagger: any word of the name that the weapon catalog knows keeps it out."""
        self.told("Tezgâhın üstünde paslı bir hançer, kırık bir kılıç ve eski bir yay duruyor.")
        before = self.snapshot()
        self.assertIsNone(pocket.resolve(self.s, "paslı hançeri çantama koyuyorum"))
        self.assertIsNone(pocket.resolve(self.s, "kırık kılıcı çantama koyuyorum"))
        self.assertIsNone(pocket.take_named(self.s, "eski yayı alıyorum", "eski yay"))
        for name, stem in (("Paslı hançer", "hancer"), ("Kırık kılıç", "kilic"), ("Eski yay", "yay")):
            self.assertIsNone(item_transfers.pick_up_told(self.w, name, stem=stem))
        self.assert_nothing_made(before, "Paslı hançer", "Kırık kılıç", "Eski yay")

    def test_a_magic_thing_is_not_created(self):
        """A narrated 'büyülü yüzük' carries no record flag; its own words mark it magic and keep it out."""
        self.told("Tezgâhın üstünde büyülü bir yüzük ve sihirli bir tılsım duruyor.")
        before = self.snapshot()
        self.assertIsNone(pocket.resolve(self.s, "büyülü yüzüğü çantama koyuyorum"))
        self.assertIsNone(pocket.take_named(self.s, "büyülü yüzüğü alıyorum", "büyülü yüzük"))
        for name, stem in (("Büyülü yüzük", "yuzuk"), ("Sihirli tılsım", "tilsim"), ("Tılsım", "tilsim"),
                           ("Magic ring", "ring")):
            self.assertIsNone(item_transfers.pick_up_told(self.w, name, stem=stem))
        self.assert_nothing_made(before, "Büyülü yüzük", "Sihirli tılsım", "Tılsım", "Magic ring")
        self.assertIsNotNone(item_transfers.pick_up_told(self.w, "Büyük kupa", stem="kupa"))  # big is not magic

    def test_a_thing_told_in_someone_s_hand_is_not_made(self):
        """No record yet, but the narration puts it in Oren's hand: taking it would take it from him unasked."""
        self.told("Oren'in elinde kırık bir halka var.")
        before = self.snapshot()
        self.assertIsNone(self.take())
        self.assertIsNone(pocket.take_named(self.s, "kırık halkayı alıyorum", "kırık halka"))
        self.assert_nothing_made(before, "Kırık halka")

    def test_the_once_only_mark_of_this_place_is_never_evicted(self):
        """Marks of other places are bounded; a mark of the place the player stands in never falls out."""
        self.told("Tezgâhın üstünde boş bir kupa ve kırık bir halka duruyor.")
        self.assertIsNotNone(self.take("kupayı çantama koyuyorum"))
        self.assertIsNotNone(pocket.resolve(self.s, "kupayı denize atıyorum"))
        self.assertNotIn("Kupa", labels(self.w))
        marks = self.w["flags"][item_transfers.NARRATED_PICKUPS]
        marks.extend(f"elsewhere_{n}:sey" for n in range(item_transfers._NARRATED_KEPT + 5))
        self.assertIsNotNone(self.take())
        marks = self.w["flags"][item_transfers.NARRATED_PICKUPS]
        self.assertIn(f"{self.here}:kupa", marks)
        self.assertEqual(len([mark for mark in marks if mark.startswith("elsewhere_")]), item_transfers._NARRATED_KEPT)
        before = (len(every_item(self.w)), len(transfers(self.w)))
        self.assertIsNone(self.take("kupayı çantama koyuyorum"))
        self.assertNotIn("Kupa", labels(self.w))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w))), before)

    def test_a_mentioned_thing_after_a_location_change_is_not_taken(self):
        self.told("Tezgâhın üstünde kırık bir halka duruyor.")
        elsewhere = next(place for place in self.w["locations"] if place != self.here)
        self.s.commit_location_change(elsewhere)
        self.assertEqual(self.w["location"], elsewhere)
        before = (len(every_item(self.w)), len(transfers(self.w)))
        self.assertIsNone(self.take())
        self.assertIsNone(pocket.take_named(self.s, "kırık halkayı alıyorum", "kırık halka"))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w))), before)
        self.assertNotIn("Kırık halka", labels(self.w))

    def test_coin_mention_is_not_created_as_an_item(self):
        self.told("Masanın üstünde 5 altın duruyor.")
        before = (len(every_item(self.w)), len(transfers(self.w)), dict(self.w["currency"]))
        self.assertIsNone(pocket.resolve(self.s, "altınları çantama koyuyorum"))
        self.assertIsNone(pocket.take_named(self.s, "5 altını alıyorum", "5 altın"))
        self.assertIsNone(item_transfers.pick_up_told(self.w, "5 Altın", stem="altin"))
        self.assertEqual((len(every_item(self.w)), len(transfers(self.w)), dict(self.w["currency"])), before)

    def test_nothing_is_made_in_a_fight(self):
        self.told("Tezgâhın üstünde kırık bir halka duruyor.")
        self.w.setdefault("combat", {})["active"] = True
        self.assertIsNone(item_transfers.pick_up_told(self.w, "Kırık halka", stem="halka"))
        self.assertNotIn("Kırık halka", labels(self.w))

    def test_a_thing_someone_already_holds_is_not_made(self):
        self.told("Oren'in elinde kırık bir halka var.")
        self.w["npcs"][0]["inventory"].append({"item_id": "item_oren_ring", "name": "Kırık halka"})
        self.assertIsNone(self.take())
        self.assertNotIn("Kırık halka", labels(self.w))
        self.assertEqual([item["item_id"] for item in every_item(self.w)
                          if equipment_economy.label(item) == "Kırık halka"], ["item_oren_ring"])

    def test_narrator_claim_alone_makes_nothing(self):
        self.told("Tezgâhın üstünde kırık bir halka duruyor.")
        claim = {"item": "Kırık halka", "to": "player"}
        text, gone = pocket.settle_claim(self.s, claim, "Kırık halkayı alıyorsun.", line="halkaya bakıyorum")
        self.assertNotIn("Kırık halka", labels(self.w))
        self.assertTrue(gone)
        text, gone = pocket.settle_claim(self.s, claim, "Kırık halkayı alıyorsun.", line="kırık halkayı alıyorum")
        self.assertEqual(gone, "")
        self.assertEqual(labels(self.w).count("Kırık halka"), 1)


class SceneOverHttp(ThreePlaysTests):
    async def test_take_survives_reload_once_and_undo_removes_it(self):
        await self.begin(FIGHTER)
        campaign_id = self.manager.get(self.session_id).campaign_id
        self.session.world_state["npcs"].clear()
        self.session.recent_dm_narrations.append("yolun kenarında kırık bir halka duruyor.")
        self.manager.save_campaign(campaign_id)
        coin_before = coin(self.session.world_state)

        body = {"message": "kırık halkayı çantama koyuyorum", "action_id": str(uuid.uuid4())}
        response = await self.post_scene_turn(self.url, PlayClient(), body)
        self.assertEqual(response.status_code, 200, response.text[:600])
        world = self.manager.get(self.session_id).game_session.world_state
        self.assertEqual(labels(world).count("Kırık halka"), 1, response.json().get("narration"))
        self.assertEqual(coin(world), coin_before)

        stored = SessionManager(campaign_store=self.store).resume_campaign(campaign_id, principal=TEST_PLAYER)[1]
        self.assertEqual(labels(stored.game_session.world_state).count("Kırık halka"), 1)

        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": body["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text[:600])
        world = self.manager.get(self.session_id).game_session.world_state
        self.assertNotIn("Kırık halka", labels(world))
        self.assertEqual(coin(world), coin_before)
        stored = SessionManager(campaign_store=self.store).resume_campaign(campaign_id, principal=TEST_PLAYER)[1]
        self.assertNotIn("Kırık halka", labels(stored.game_session.world_state))


if __name__ == "__main__":
    unittest.main()
