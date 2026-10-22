"""Native commands through gameplay dispatch: no inventory/consent fixture seeding."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import game
import interaction_adventure
from api.character_creation import configure_character
from api.tests import test_equipment_economy_http as contracts


class NativeEquipmentTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session()
        self.session.world_state["location"] = "tavern"

    def command(self, text):
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            result = self.session.run_player_turn(text)
        self.assertEqual(result["model_calls"], 0)
        return result

    def market(self):
        result = self.command("/item market")
        self.assertTrue(result["action_result"]["success"], result["action_result"])
        shop = self.session.world_state["shops"][-1]
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == shop["shopkeeper_id"])
        return shop, npc

    def test_native_market_stock_wallet_and_no_repeat_mint(self):
        shop, npc = self.market()
        before = copy.deepcopy(self.session.world_state)
        self.command("/item market")
        self.assertEqual(before["currency"], self.session.world_state["currency"])
        self.assertEqual(before["inventory"], self.session.world_state["inventory"])
        self.assertEqual(len(self.session.world_state["shops"]), 1)
        self.assertEqual(self.session.world_state["currency"][npc["id"]], 1000)
        self.assertEqual(list(shop["item_offers_cp"].values()), [200])

    def test_native_request_records_consent_and_cleans_source_hand(self):
        _, npc = self.market()
        identity = npc["equipment"]["main_hand"]
        received = self.command(f'/item request {identity} {npc["id"]}')
        self.assertTrue(received["action_result"]["success"], received)
        world = self.session.world_state
        source = next(n for n in world["npcs"] if n["id"] == npc["id"])
        self.assertIsNone(source["equipment"]["main_hand"])
        self.assertTrue(any(i["item_id"] == identity for i in world["inventory"]))
        self.assertTrue(any(e["kind"] == "item_consent" for e in world["interaction_adventure_v1"]["events"]))
        before = copy.deepcopy(world)
        self.assertFalse(self.command(f'/item request {identity} {npc["id"]}')["action_result"]["success"])
        self.assertEqual(before, world)

    def test_natural_interaction_request_uses_the_same_native_policy(self):
        _, npc = self.market()
        identity = npc["equipment"]["main_hand"]
        text = "Club ver"
        result = interaction_adventure.resolve(self.session, text, {
            "operation": "request", "quote": text, "requested_item": identity,
        }, npc)
        self.assertTrue(result["success"], result)
        self.assertTrue(any(i["item_id"] == identity for i in self.session.world_state["inventory"]))

    def test_price_offer_does_not_imply_gift_consent(self):
        shop, npc = self.market()
        identity = next(iter(shop["item_offers_cp"]))
        before = copy.deepcopy(self.session.world_state)
        rejected = self.command(f'/item request {identity} {npc["id"]}')
        self.assertFalse(rejected["action_result"]["success"])
        self.assertEqual(before, self.session.world_state)

    def test_translated_owned_starter_weapon_does_not_block_unrelated_sale(self):
        self.session.world_state["inventory"] = ["Uzun Kılıç"]
        self.session.world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
        shop, npc = self.market()
        identity = npc["equipment"]["main_hand"]
        self.command(f'/item request {identity} {npc["id"]}')
        result = self.command(f'/item sell {identity} {shop["id"]}')
        self.assertTrue(result["action_result"]["success"], result)
        world = self.session.world_state
        sword = next(i for i in world["inventory"] if i["name"] == "Uzun Kılıç")
        self.assertEqual(sword["weapon_id"], "longsword")
        self.assertEqual(world["equipment"]["main_hand"], sword["item_id"])
        self.assertFalse(any(i["item_id"] == identity for i in world["inventory"]))

    def test_native_work_dialogue_completion_and_funded_once_reward(self):
        _, npc = self.market()
        offer = self.command(f'/item work {npc["id"]}')
        self.assertTrue(offer["action_result"]["success"], offer)
        world = self.session.world_state
        identity = next(iter(world["item_rewards"]))
        self.assertFalse(self.command(f"/item reward {identity}")["action_result"]["success"])
        talked = self.command(f'/item talk {npc["id"]} Merhaba')
        self.assertTrue(talked["action_result"]["success"], talked)
        self.assertEqual(world["interaction_adventure_v1"]["threads"][0]["status"], "succeeded")
        claimed = self.command(f"/item reward {identity}")
        self.assertTrue(claimed["action_result"]["success"], claimed)
        self.assertEqual(world["currency"]["player"], 100)
        self.assertEqual(world["currency"][npc["id"]], 900)
        before = copy.deepcopy(world)
        self.assertFalse(self.command(f"/item reward {identity}")["action_result"]["success"])
        self.assertEqual(before, world)

    def test_live_actor_loot_denied_dead_actor_actual_item_only(self):
        _, npc = self.market()
        identity = npc["equipment"]["main_hand"]
        self.assertFalse(self.command(f'/item loot {npc["id"]} {identity}')["action_result"]["success"])
        source = next(n for n in self.session.world_state["npcs"] if n["id"] == npc["id"])
        # This fixture supplies only an existing combat owner's defeat outcome,
        # not possessions, consent, loot or a reward.
        source.update(dead=True, alive=False, current_hp=0)
        accepted = self.command(f'/item loot {source["id"]} {identity}')
        self.assertTrue(accepted["action_result"]["success"], accepted)
        self.assertIsNone(next(n for n in self.session.world_state["npcs"] if n["id"] == npc["id"])["equipment"]["main_hand"])

    def test_open_container_only_transfers_actual_contents(self):
        world = self.session.world_state
        world["containers"].append({
            "id": "chest", "name": "Chest", "location": world["location"],
            "locked": False, "opened": False, "contents": ["Dagger"],
        })
        self.command("/item list")
        identity = world["containers"][-1]["contents"][0]["item_id"]
        before = copy.deepcopy(world)
        self.assertFalse(self.command(f"/item loot chest {identity}")["action_result"]["success"])
        self.assertEqual(world, before)
        world["containers"][-1]["opened"] = True
        result = self.command(f"/item loot chest {identity}")
        self.assertTrue(result["action_result"]["success"], result)
        self.assertEqual(world["containers"][-1]["contents"], [])
        self.assertTrue(any(i["item_id"] == identity for i in world["inventory"]))

    def test_existing_shop_possessions_survive_python_stock_provisioning(self):
        world = self.session.world_state
        world["npcs"].append({
            "id": "old_keeper", "name": "Keeper", "role": "Shopkeeper",
            "location": world["location"], "current_hp": 10,
            "inventory": ["Known Relic"],
        })
        world["shops"].append({
            "id": "old_shop", "name": "Existing", "location": world["location"],
            "shopkeeper_id": "old_keeper",
        })
        shop, keeper = self.market()
        self.assertEqual(shop["id"], "old_shop")
        self.assertEqual(len(world["shops"]), 1)
        self.assertEqual([i["name"] for i in keeper["inventory"]],
                         ["Known Relic", "Dagger", "Club"])
        self.assertEqual(world["currency"]["old_keeper"], 1000)
        self.assertNotIn(keeper["inventory"][0]["item_id"], shop["item_offers_cp"])

    def test_native_reward_cash_is_reserved_from_merchant_buybacks(self):
        shop, npc = self.market()
        self.command(f'/item work {npc["id"]}')
        world = self.session.world_state
        world["currency"][npc["id"]] = 100
        self.command("/item list")
        sword = next(i for i in world["inventory"] if i["name"] == "Kılıç")
        before = copy.deepcopy(world)
        result = self.command(f'/item sell {sword["item_id"]} {shop["id"]}')
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(world, before)

    def test_historical_equipment_is_not_monetized_on_load(self):
        import tempfile
        from pathlib import Path
        from api.dnd_2024_rules import BACKGROUND_DEFINITIONS

        self.session.world_state["inventory"] = [
            "Kutsal Sembol", "15 Altın", "Dua Kitabı",
        ]
        self.session.world_state.pop("currency", None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            self.session.save_game(path)
            restored = game.create_session()
            self.assertTrue(restored.load_game(path))
        self.assertEqual(restored.world_state["inventory"],
                         ["Kutsal Sembol", "15 Altın", "Dua Kitabı"])
        self.assertNotIn("player", restored.world_state.get("currency", {}))
        self.assertEqual(BACKGROUND_DEFINITIONS["Acolyte"]["starting_gp"], 8)

    def test_new_background_currency_is_source_certified(self):
        for background, bonuses, skills, gp, item in (
            ("Acolyte", {"wisdom": 2, "intelligence": 1},
             ["Athletics", "Intimidation", "Insight", "Religion", "Perception"], 8,
             "Calligrapher's Supplies"),
            ("Artisan", {"strength": 2, "intelligence": 1},
             ["Athletics", "Intimidation", "Investigation", "Persuasion", "Perception"], 32,
             "Weaver's Tools"),
        ):
            for option, expected_gp in (("A", gp), ("B", 50)):
                session = game.create_session()
                configure_character(
                    session, mode="custom", name="Galan", species="Human",
                    character_class="Fighter", background=background,
                    alignment="Lawful Neutral", ability_score_method="standard_array",
                    background_equipment_option=option, equipment_package="A",
                    fighting_style="Defense", languages=["Common", "Orc", "Goblin"],
                    ability_scores={"strength": 15, "constitution": 14, "dexterity": 13,
                                    "wisdom": 12, "intelligence": 10, "charisma": 8},
                    background_ability_bonuses=bonuses, proficient_skills=skills,
                    proficient_tools=[item] if background == "Artisan" else ["Calligrapher's Supplies"],
                )
                self.assertEqual(session.world_state["currency"]["player"], expected_gp * 100)
                self.assertIn(item, session.world_state["inventory"] if option == "A"
                              else session.character["proficient_tools"])
                self.assertNotIn(f"{expected_gp} GP", session.world_state["inventory"])
                if option == "A":
                    self.assertIn("10 Parşömen" if background == "Acolyte" else "2 Kese",
                                  session.world_state["inventory"])


class NativeEquipmentHttpTests(contracts.EquipmentHttpTests):
    async def create_campaign(self):
        response = await self.http.post("/api/game/campaigns", json={
            "campaign_start": {
                "setting_id": "forgotten_realms",
                "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north",
                "starting_location_id": "fr:city:neverwinter",
            },
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def native_market(self, campaign):
        result = await self.post(campaign, {"message": "/item market", "action_id": str(uuid4())})
        self.assertEqual(result.status_code, 200, result.text)
        record = self.manager.get(campaign["session_id"])
        self.assertFalse(any(e["event_type"] == "item_lost"
                             for e in record.journal["notable_events"]))
        shop = record.game_session.world_state["shops"][-1]
        npc = next(n for n in record.game_session.world_state["npcs"]
                   if n["id"] == shop["shopkeeper_id"])
        return record, shop, npc

    def request_proposal(self, text, requested_item, *, intent="dialogue",
                         action="dialogue", target=None, operation="request"):
        return {
            "intent": intent,
            "action": action,
            "target": target or {"type": "none", "reference": ""},
            "completion": "unclear",
            "confidence": 1.0,
            "interaction": {
                "operation": operation,
                "quote": text,
                "requested_item": requested_item,
            },
        }

    async def post_with_proposal(self, campaign, command, proposal, narration=""):
        resolver_results = []
        actual_resolver = interaction_adventure.resolve

        def capture_resolver(*args, **kwargs):
            result = actual_resolver(*args, **kwargs)
            resolver_results.append(result)
            return result

        with (
            patch("game.parse_player_intent", return_value=proposal) as parser,
            patch("game.ask_dungeon_master", return_value={
                "valid_response": True,
                "narration": narration,
                "world_updates": {},
                "lore_claims": [],
            }),
            patch(
                "interaction_adventure.resolve",
                side_effect=capture_resolver,
            ) as resolver,
        ):
            response = await self.post(campaign, command)
        self.last_proposal_parse_calls = parser.call_count
        self.last_proposal_parse_kwargs = parser.call_args.kwargs if parser.call_args else {}
        self.last_interaction_result = resolver_results[-1] if resolver_results else None
        return response, resolver.call_count

    async def test_native_request_replay_conflict_resume_and_save_failure(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        command = {"message": f'/item request {npc["equipment"]["main_hand"]} {npc["id"]}',
                   "action_id": str(uuid4())}
        before = self.snapshot(record)
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("save failure")):
            failed = await self.post(campaign, command)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(before, self.snapshot(record))
        accepted = await self.post(campaign, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn("açık rızayla", accepted.json()["narration"])
        self.assertTrue(any(e["event_type"] == "item_gained" and e["related_item"] == "Club"
                            for e in record.journal["notable_events"]))
        after = self.snapshot(record)
        self.assertEqual((await self.post(campaign, command)).json(), accepted.json())
        self.assertEqual(after, self.snapshot(record))
        self.assertEqual((await self.post(campaign, {**command, "message": "/item list"})).status_code, 409)
        sid, restored, *_ = self.manager.resume_campaign(campaign["campaign_id"])
        campaign["session_id"] = sid
        self.assertIn("açık rızayla", (await self.post(campaign, command)).json()["narration"])
        other = await self.create_campaign()
        denied = await self.post(other, {**command, "action_id": str(uuid4())})
        self.assertIn("reddedildi", denied.json()["narration"])

    async def test_natural_request_full_turn_contract(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        identity = npc["equipment"]["main_hand"]
        text = "Elindeki Club adlı eşyayı bana ver."
        command = {"message": text, "target_id": npc["id"], "action_id": str(uuid4())}
        turn_before = record.game_session.world_state["flags"]["turn_index"]
        proposal = self.request_proposal(text, identity)
        with (
            patch("game.parse_player_intent", return_value=proposal) as parse_spy,
            patch("game.ask_dungeon_master", return_value={
                "valid_response": True,
                "narration": "Equipment Merchant sana Club adlı eşyayı verdi.",
                "world_updates": {}, "lore_claims": [],
            }),
            patch("interaction_adventure.resolve",
                  wraps=interaction_adventure.resolve) as resolve_spy,
        ):
            response = await self.post(campaign, command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(parse_spy.call_count, 1)
        self.assertEqual(resolve_spy.call_count, 1)
        self.assertEqual(response.json()["turn_outcome"]["status"], "resolved")
        world = record.game_session.world_state
        self.assertEqual(world["flags"]["turn_index"], turn_before + 1)
        self.assertEqual(sum(i.get("item_id") == identity for i in world["inventory"]), 1)
        source = next(n for n in world["npcs"] if n["id"] == npc["id"])
        self.assertIsNone(source["equipment"]["main_hand"])
        self.assertFalse(any(i.get("item_id") == identity for i in source["inventory"]))
        self.assertNotIn(identity, source.get("item_consents", {}))
        self.assertNotIn(identity, source.get("item_release_policy", {}))
        committed = self.snapshot(record)
        self.assertEqual((await self.post(campaign, command)).json(), response.json())
        self.assertEqual(committed, self.snapshot(record))

    async def test_natural_request_without_consent_reaches_permission_owner(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        identity = npc["equipment"]["main_hand"]
        npc["item_consents"] = {}
        npc["item_release_policy"] = {}
        text = "Elindeki Club adlı eşyayı bana ver."
        response, resolve_calls = await self.post_with_proposal(
            campaign,
            {"message": text, "target_id": npc["id"], "action_id": str(uuid4())},
            self.request_proposal(text, identity),
            "Equipment Merchant sana Club adlı eşyayı verdi.",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(resolve_calls, 1)
        outcome = response.json()["turn_outcome"]
        self.assertEqual(outcome["status"], "pending")
        self.assertEqual(self.last_interaction_result["item_validation"]["reason"],
                         "npc_consent_required")
        self.assertNotIn("Club adlı eşyayı verdi", response.json()["narration"])
        world = record.game_session.world_state
        source = next(n for n in world["npcs"] if n["id"] == npc["id"])
        self.assertEqual(source["equipment"]["main_hand"], identity)
        self.assertFalse(any(i.get("item_id") == identity for i in world["inventory"]))
        self.assertNotIn(identity, source.get("item_consents", {}))

    async def test_request_for_nonexistent_item_reaches_owner_without_transfer(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        text = "Elindeki Ruby adlı eşyayı bana ver."
        response, resolve_calls = await self.post_with_proposal(
            campaign,
            {"message": text, "target_id": npc["id"], "action_id": str(uuid4())},
            self.request_proposal(text, "Ruby"),
            "Equipment Merchant sana Ruby adlı eşyayı verdi.",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(resolve_calls, 1)
        outcome = response.json()["turn_outcome"]
        self.assertEqual(outcome["status"], "pending")
        self.assertEqual(self.last_interaction_result["item_validation"]["reason"],
                         "not_owned")
        self.assertNotIn("Ruby adlı eşyayı verdi", response.json()["narration"])
        self.assertFalse(any(i.get("name") == "Ruby"
                             for i in record.game_session.world_state["inventory"]))

    async def test_request_rejects_wrong_npc_or_object_identity(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        identity = npc["equipment"]["main_hand"]
        text = "Elindeki Club adlı eşyayı bana ver."
        other_identity = next(
            item["item_id"] for item in npc["inventory"]
            if isinstance(item, dict) and item.get("name") == "Dagger"
        )
        proposals = (
            self.request_proposal(
                text, identity,
                target={
                    "type": "npc", "reference": npc["name"],
                    "npc_id": "npc_not_the_target", "evidence_quote": "Club",
                },
            ),
            self.request_proposal(text, other_identity),
        )
        for proposal in proposals:
            with self.subTest(proposal=proposal):
                response, resolve_calls = await self.post_with_proposal(
                    campaign,
                    {"message": text, "target_id": npc["id"],
                     "action_id": str(uuid4())},
                    proposal,
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(resolve_calls, 0)
                self.assertNotEqual(response.json()["turn_outcome"]["status"],
                                    "resolved")
                source = next(
                    n for n in record.game_session.world_state["npcs"]
                    if n["id"] == npc["id"]
                )
                self.assertEqual(source["equipment"]["main_hand"], identity)
                self.assertFalse(any(i.get("item_id") == identity
                                     for i in record.game_session.world_state["inventory"]))

    async def test_attack_or_other_action_cannot_be_relabelled_as_request(self):
        for text, intent, action in (
            ("Club'u almak için tüccara saldırıyorum.", "attack", "attack"),
            ("Club'u almak için pazara gidiyorum.", "travel", "travel"),
            ("Elindeki Club adlı eşyayı bana ver.", "dialogue", "attack"),
        ):
            with self.subTest(intent=intent):
                campaign = await self.create_campaign()
                record, _, npc = await self.native_market(campaign)
                identity = npc["equipment"]["main_hand"]
                response, resolve_calls = await self.post_with_proposal(
                    campaign,
                    {"message": text, "target_id": npc["id"],
                     "action_id": str(uuid4())},
                    self.request_proposal(
                        text, identity, intent=intent, action=action
                    ),
                )
                if intent == "attack":
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(response.json()["detail"]["code"], "no_weapon")
                elif intent == "travel":
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["turn_outcome"]["action"], "travel")
                else:
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["turn_outcome"]["status"],
                                     "proposal_rejected")
                self.assertEqual(resolve_calls, 0)
                self.assertFalse(any(i.get("item_id") == identity
                                     for i in record.game_session.world_state["inventory"]))
                source = next(
                    n for n in record.game_session.world_state["npcs"]
                    if n["id"] == npc["id"]
                )
                self.assertEqual(source["equipment"]["main_hand"], identity)

    async def test_transfer_mentioned_only_in_quote_does_not_resolve_request(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        text = "Dükkâncı “Club'u bana ver” dediğini aktarıyorum."
        response, resolve_calls = await self.post_with_proposal(
            campaign,
            {"message": text, "target_id": npc["id"], "action_id": str(uuid4())},
            self.request_proposal(text, npc["equipment"]["main_hand"]),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(resolve_calls, 0)
        self.assertNotEqual(response.json()["turn_outcome"]["status"], "resolved")
        self.assertFalse(any(i.get("item_id") == npc["equipment"]["main_hand"]
                             for i in record.game_session.world_state["inventory"]))

    async def test_real_conversation_still_requires_conversation_proposal(self):
        campaign = await self.create_campaign()
        record, _, npc = await self.native_market(campaign)
        text = "Kuzey kapısının neden kapandığını biliyor musun?"
        proposal = {
            "intent": "dialogue",
            "action": "dialogue",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear",
            "confidence": 1.0,
            "interaction": {"operation": "none", "quote": text},
        }
        response, resolve_calls = await self.post_with_proposal(
            campaign,
            {"message": text, "target_id": npc["id"],
             "interaction_mode": "say", "action_id": str(uuid4())},
            proposal,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.last_proposal_parse_calls, 1)
        self.assertEqual(resolve_calls, 0)
        self.assertEqual(response.json()["turn_outcome"]["status"],
                         "proposal_rejected")
        self.assertFalse(any(i.get("item_id") == npc["equipment"]["main_hand"]
                             for i in record.game_session.world_state["inventory"]))
        source = next(n for n in record.game_session.world_state["npcs"]
                      if n["id"] == npc["id"])
        self.assertEqual(source["equipment"]["main_hand"], npc["equipment"]["main_hand"])

    async def test_generic_non_requests_still_require_conversation_after_parse(self):
        for text, intent in (
            ("Bir süre dinleniyorum.", "rest"),
            ("Kılıcımı kuşanıyorum.", "inventory"),
        ):
            with self.subTest(intent=intent):
                campaign = await self.create_campaign()
                record, _, npc = await self.native_market(campaign)
                world = record.game_session.world_state
                before = copy.deepcopy({
                    key: world.get(key)
                    for key in (
                        "inventory", "currency", "quests", "relationships",
                        "events", "npcs",
                    )
                })
                proposal = {
                    "intent": intent,
                    "action": intent,
                    "target": {"type": "none", "reference": ""},
                    "completion": "unclear",
                    "confidence": 1.0,
                    "interaction": {
                        "operation": "none",
                        "quote": text,
                        "requested_item": None,
                    },
                }
                response, resolve_calls = await self.post_with_proposal(
                    campaign,
                    {
                        "message": text,
                        "target_id": npc["id"],
                        "interaction_mode": "do",
                        "action_id": str(uuid4()),
                    },
                    proposal,
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(self.last_proposal_parse_calls, 1)
                self.assertFalse(
                    self.last_proposal_parse_kwargs["require_conversation"]
                )
                self.assertEqual(resolve_calls, 0)
                self.assertEqual(
                    response.json()["turn_outcome"]["status"],
                    "proposal_rejected",
                )
                after = {
                    key: record.game_session.world_state.get(key)
                    for key in before
                }
                self.assertEqual(before, after)

    async def test_native_shop_buy_sell_and_reward_through_http(self):
        campaign = await self.create_campaign()
        record, shop, npc = await self.native_market(campaign)
        sword = next(i for i in record.game_session.world_state["inventory"] if i["name"] == "Kılıç")
        for operation, identity in (
            ("sell", sword["item_id"]), ("buy", next(iter(shop["item_offers_cp"]))),
            ("sell", next(iter(shop["item_offers_cp"]))),
        ):
            response = await self.post(campaign, {
                "message": f'/item {operation} {identity} {shop["id"]}',
                "action_id": str(uuid4()),
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("atomik olarak tamamlandı", response.json()["narration"])
        for message in (f'/item work {npc["id"]}', f'/item talk {npc["id"]} Merhaba'):
            self.assertEqual((await self.post(campaign, {"message": message})).status_code, 200)
        identity = next(iter(record.game_session.world_state["item_rewards"]))
        result = await self.post(campaign, {"message": f"/item reward {identity}"})
        self.assertIn("atomik olarak tamamlandı", result.json()["narration"])
