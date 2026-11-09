"""Journey evidence for item, weapon and starting-purse behavior.

HTTP refusals fail a scenario step rather than trivially passing empty-text checks.
Task15 now materializes an unseeded arrow pack once; a separate loose-arrow setup
and a genuinely empty bow pin both positive and negative accounting paths.
Existing eating/drinking and initial-purse known breaks stay explicit; the Greatsword one is fixed (Dilim 2 Task 14).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, apply_setup, read_observed
from api.tests.journeys.schema import load_scenario

CONSUME = SCENARIO_DIR / "04_consume.json"
GREATSWORD = SCENARIO_DIR / "05_greatsword.json"
START_PURSE = SCENARIO_DIR / "14_start_purse.json"


def scenario_variant(path: Path, change):
    """The scenario file with ``change`` applied to its data, loaded through the strict loader."""
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    folder = Path(tempfile.mkdtemp())
    variant = folder / f"{data['id']}.json"  # the loader holds the id and the file name equal
    variant.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        return load_scenario(variant)
    finally:
        variant.unlink()
        folder.rmdir()


class ItemJourneyEvidence(JourneyCase):
    async def play(self, scenario):
        """Run one scenario; return its step results and every turn's (status code, body)."""
        scenario = load_scenario(scenario) if isinstance(scenario, Path) else scenario
        turns: list[tuple[int, dict]] = []
        post = self.http.post

        async def recording_post(url, *args, **kwargs):
            response = await post(url, *args, **kwargs)
            if str(url).endswith("/turn"):
                turns.append((response.status_code, response.json()))
            return response

        with patch.object(self.http, "post", recording_post):
            results = await self.run_scenario(scenario)
        return results, turns

    def assert_refused(self, result, code: str):
        """The step's first failure is the turn's HTTP 400 with the engine's refusal code."""
        self.assertTrue(result.failures, result)
        failure = result.failures[0]
        self.assertTrue(failure.startswith("HTTP 400: "), failure)
        self.assertIn(f'"code":"{code}"', failure)

    async def test_the_greatsword_is_drawn_by_the_panel_attack_and_the_ready_blow_lands(self):
        """05 (item 39, Dilim 2 Task 14): the panel attack draws the Greatsword and the Ready attack is accepted and
        lands; every turn is a 200 with real narration, and no turn carries no_weapon."""
        results, turns = await self.play(GREATSWORD)
        self.assertEqual([result.status for result in results], ["pass"] * 5, results)
        self.assertEqual([status for status, _ in turns], [200, 200, 200, 200, 200])
        for result in results:
            self.assertEqual(result.failures, (), result)
            self.assertNotEqual(result.narration, "", result)   # a pass on real text, never on an empty one
        self.assertTrue(results[1].narration.startswith("Çantandan çektiğin Greatsword ile vuruyorsun. "), results[1])
        self.assertEqual([observed["elinde"] for observed in self.last_observations],
                         [None, "Greatsword", "Greatsword", "Greatsword", "Greatsword"])
        self.assertTrue(all(observed["savas"] for observed in self.last_observations))
        for _, body in turns:
            self.assertNotIn("no_weapon", json.dumps(body, ensure_ascii=False))

    async def test_the_bow_shot_materializes_the_pack_once(self):
        """Task15: the pack supplies 20 arrows once, the shot leaves 19; old consume breaks remain."""
        results, turns = await self.play(CONSUME)
        self.assertEqual([result.status for result in results], ["known_broken", "known_broken", "pass"], results)
        self.assertEqual([status for status, _ in turns], [200, 200, 200])
        unchanged = {"Greatsword": 1, "Uzun Yay & 20 Ok": 1, "Macera Çantası": 1, "Tabak yemek": 1, "Bira": 2}
        self.assertEqual(self.last_observations[0]["envanter"], unchanged)
        self.assertEqual(self.last_observations[1]["envanter"], unchanged)
        self.assertEqual(results[2].failures, ())
        self.assertEqual(self.last_observations[2]["cephane"], {"arrow": 19})
        world = self.manager.get(self.last_session_id).game_session.world_state
        pack = next(item for item in world["inventory"] if item.get("name") == "Uzun Yay & 20 Ok")
        self.assertTrue(pack["ammo_seeded_v1"])
        import item_use
        self.assertEqual(item_use.ensure_ammunition(world), {"arrow": 19})
        self.assertEqual(item_use.ensure_ammunition(world), {"arrow": 19})

    async def test_the_bow_shot_hits_once_the_counter_holds_arrows(self):
        """A bare bow with 20 loose arrows spends one, independently of pack materialization."""
        def seeded(data):
            data["setup"]["ammunition"] = {"arrow": 20}
            data["setup"]["inventory"] = ["Uzun Yay"]  # loose arrows; no second unseeded pack
            data["steps"] = [{key: value for key, value in data["steps"][2].items()
                              if key not in {"known_broken", "broken_because"}}]
            data["steps"][0].pop("independent", None)

        results, turns = await self.play(scenario_variant(CONSUME, seeded))
        self.assertEqual([result.status for result in results], ["pass"], results)
        self.assertEqual(turns[0][0], 200)
        self.assertEqual(self.last_observations[0]["cephane"], {"arrow": 19})

    async def test_a_bare_bow_without_counter_or_pack_is_still_refused(self):
        def empty(data):
            data["setup"]["inventory"] = ["Uzun Yay"]
            data["setup"]["ammunition"] = {}
            data["steps"] = [data["steps"][2]]
        results, turns = await self.play(scenario_variant(CONSUME, empty))
        self.assertEqual(turns[0][0], 400)
        self.assert_refused(results[0], "no_ammunition")
        self.assertEqual(self.last_observations[0]["cephane"], {})
        self.assertEqual(self.last_observations[0]["envanter"], {"Uzun Yay": 1})
    async def test_setup_inventory_and_ammunition_replace_what_creation_gave(self):
        """apply_setup puts the scenario's items and counter in place of the created character's: the pack's
        own items are gone, nothing is merged."""
        setup = load_scenario(CONSUME).setup
        campaign = await self._journey_campaign(setup)
        world = self.manager.get(campaign["session_id"]).game_session.world_state
        created = read_observed(self, campaign["session_id"])["envanter"]
        self.assertIn("Ağır Tatar Yayı & 20 Ok", created, "creation gives pack C's own bow")
        world["ammunition"] = {"bolt": 7}  # stands in for any counter creation might give
        apply_setup(self, campaign, {**setup, "ammunition": {"arrow": 20}})
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual(observed["envanter"], {"Greatsword": 1, "Uzun Yay & 20 Ok": 1, "Macera Çantası": 1,
                                                "Tabak yemek": 1, "Bira": 2})
        self.assertEqual(observed["cephane"], {"arrow": 20})
        self.assertEqual(observed["kese"], 100)

    async def test_the_creation_purse_and_the_live_purse_agree(self):
        """14 (item 34): Fighter pack C with Soldier option B. The creation response shows 6000 cp (50 gp plus
        the written '10 Altın'); the game starts with the same 6000 cp and no '10 Altın' left as an item."""
        setup = load_scenario(START_PURSE).setup
        campaign = await self._journey_campaign(setup)
        self.assertEqual(campaign["state"]["wallet"]["total_cp"], 6000)
        observed = read_observed(self, campaign["session_id"])
        self.assertEqual(observed["kese"], 6000)
        self.assertNotIn("10 Altın", observed["envanter"])

        results, _ = await self.play(START_PURSE)
        self.assertEqual([result.status for result in results], ["pass", "pass", "pass"], results)
        self.assertEqual(tuple(results[0].failures), ())
        # The first coin trade spends from the purse: 6000 - 4 = 5996, the barman holds the 4.
        self.assertEqual(self.last_observations[2]["kese"], 5996)
        self.assertEqual(self.last_observations[2]["kisi_kese"], {"barman": 4})


if __name__ == "__main__":
    import unittest

    unittest.main()
