"""Turkish first letters keep their dot: one helper, no str.upper on a first letter anywhere in product code."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import living_world
import tr_case
import world_threads
from adventure import dialogue_jobs
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, apply_setup
from api.tests.journeys.schema import load_scenario

ROOT = Path(__file__).resolve().parents[2]          # ai-dnd/, as in test_coin_writers


def _product_files():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if ("/tests/" in f"/{rel}" or rel.startswith(("legacy_debug/", "docs/", "reports/")) or "__pycache__" in rel
                or ("/" not in rel and (rel.startswith("test_") or rel.endswith("_test.py")))):
            continue
        yield rel, path


class TurkishFirstLetter(JourneyCase):
    async def errand_with_giver(self, item_noun="iade takımı"):
        """Scenario 19's setup (the potter's errand, pay 12) through the journey harness; the giver is in the room."""
        setup = load_scenario(SCENARIO_DIR / "19_quest_item_no_duplicate.json").setup
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        session = self.manager.get(campaign["session_id"]).game_session
        world = session.world_state
        [thread] = [t for t in world_threads.view(world)["threads"] if t.get("status") == "offered"]
        thread["item_noun"] = item_noun
        giver = next(npc for npc in world["npcs"] if npc.get("id") == thread["owner_npc_id"])
        recipient = {"id": "npc_tuna", "name": "Tuna", "role": "Dok işçisi", "location": thread["target_place_id"],
                     "status": "active", "combat_status": "active", "current_hp": 8, "max_hp": 8, "memory": [],
                     "knowledge": [], "reality_layer": "PROCEDURAL_LOCAL_FICTION", "personal_profile": {},
                     "inventory": []}
        world["npcs"].append(recipient)
        thread["recipient_npc_id"] = recipient["id"]
        return session, thread, giver, recipient

    def test_upper_first_keeps_the_turkish_dot(self):
        self.assertEqual(tr_case.upper_first("iade takımı"), "İade takımı")
        self.assertEqual(tr_case.upper_first("ırmak suyu"), "Irmak suyu")
        self.assertEqual(tr_case.upper_first("çömlek"), "Çömlek")
        self.assertEqual(tr_case.upper_first("İade"), "İade")
        self.assertEqual(tr_case.upper_first("x"), "X")
        self.assertEqual(tr_case.upper_first(""), "")

    def test_the_old_helper_is_the_same_rule(self):
        for text in ("iade", "ırmak", "çömlek", "", "Zaten"):
            self.assertEqual(living_world.turkish_initial_upper(text), tr_case.upper_first(text))

    async def test_the_job_parcel_is_named_with_the_dot(self):
        session, thread, giver, recipient = await self.errand_with_giver(item_noun="iade takımı")
        with patch("world_threads.recipient_of", return_value=recipient):
            self.assertTrue(dialogue_jobs.accept_thread_job(session, thread, giver))
        [parcel] = [item for item in giver["inventory"] if str(item.get("item_id", "")).startswith("parcel:")]
        self.assertEqual(parcel["name"], "İade takımı")
        self.assertNotIn("Iade", dialogue_jobs.shown_line(session.world_state, thread, "taken"))

    def test_no_product_code_raises_a_first_letter_with_str_upper(self):
        found = [f"{rel}:{number}" for rel, path in _product_files() if rel != "tr_case.py"
                 for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1)
                 if "[:1].upper()" in line]
        self.assertEqual(found, [])
