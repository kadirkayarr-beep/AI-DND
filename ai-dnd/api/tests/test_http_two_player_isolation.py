"""Two signed-in players over HTTP: neither can see or change the other's campaign.

test_http_auth_gate.py covers anonymous callers (401) and a foreign player's GET
(404). This file covers what a *signed-in stranger* could still try: list, delete,
save, resume, play a turn, accept quests, species actions, ambient events. For
every route the foreign response must equal the response for a record that does
not exist (no way to learn that someone else's id is real), and the owner's
campaign must be unchanged afterwards. Temporary databases only.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import uuid

import game
import httpx
from api.auth import FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import PLAYER_A, PLAYER_B, SAME_SUBJECT

_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()


def _path(directory: str) -> Path:
    path = (Path(directory) / "campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return path


def _ids(listing) -> set[str]:
    rows = listing["campaigns"] if isinstance(listing, dict) else listing
    return {row["campaign_id"] for row in rows}


class TwoPlayerIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = CampaignStore(_path(self.directory.name))
        self.manager = SessionManager(campaign_store=self.store)
        self.a_campaign, self.a_session, a_record, _ = self.manager.create_campaign(
            name="Aya ait", principal=PLAYER_A,
        )
        self.b_campaign, self.b_session, _, _ = self.manager.create_campaign(
            name="Bora ait", principal=PLAYER_B,
        )
        self.a_hp = a_record.game_session.character["current_hp"]
        self.apps = {
            "a": create_app(
                session_manager=self.manager, ollama_adapter=None,
                authenticator=FixedAuthenticator(PLAYER_A),
            ),
            "b": create_app(
                session_manager=self.manager, ollama_adapter=None,
                authenticator=FixedAuthenticator(PLAYER_B),
            ),
            # Same subject string as A, different issuer: must be a different player.
            "same_subject": create_app(
                session_manager=self.manager, ollama_adapter=None,
                authenticator=FixedAuthenticator(SAME_SUBJECT),
            ),
        }

    def client(self, who: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.apps[who]),
            base_url="http://isolated-testserver",
        )

    def a_snapshot(self):
        """What the owner has, read straight from the store (not over HTTP)."""
        stored = self.store.get_campaign(self.a_campaign, principal=PLAYER_A)
        return stored.metadata["name"], stored.metadata["save_version"], stored.payload

    # ---- listing -----------------------------------------------------------------

    async def test_each_player_lists_only_their_own_campaigns(self):
        async with self.client("a") as a, self.client("b") as b, self.client("same_subject") as s:
            listed_a = await a.get("/api/game/campaigns")
            listed_b = await b.get("/api/game/campaigns")
            listed_s = await s.get("/api/game/campaigns")
        self.assertEqual(listed_a.status_code, 200, listed_a.text)
        self.assertEqual(_ids(listed_a.json()), {self.a_campaign})
        self.assertEqual(_ids(listed_b.json()), {self.b_campaign})
        self.assertEqual(_ids(listed_s.json()), set(), "same subject, other issuer, is a stranger")

    async def test_a_campaign_created_over_http_never_shows_up_for_the_other_player(self):
        async with self.client("b") as b, self.client("a") as a:
            created = await b.post("/api/game/campaigns", json={"name": "Bora ikinci"})
            self.assertEqual(created.status_code, 200, created.text)
            new_id = created.json()["campaign_id"]
            self.assertEqual(_ids((await a.get("/api/game/campaigns")).json()), {self.a_campaign})
            self.assertEqual(
                _ids((await b.get("/api/game/campaigns")).json()),
                {self.b_campaign, new_id},
            )
            self.assertEqual((await a.get(f"/api/game/campaigns/{new_id}")).status_code, 404)

    # ---- every foreign route answers exactly like a missing record ------------------

    def foreign_requests(self):
        quest, event, missing = str(uuid.uuid4()), str(uuid.uuid4()), None
        del missing

        def routes(campaign_id: str, session_id: str):
            return [
                ("GET", f"/api/game/campaigns/{campaign_id}", None),
                ("POST", f"/api/game/campaigns/{campaign_id}/save", None),
                ("POST", f"/api/game/campaigns/{campaign_id}/resume", None),
                ("GET", f"/api/game/sessions/{session_id}/state", None),
                ("POST", f"/api/game/sessions/{session_id}/turn", {"message": "Bekle."}),
                ("POST", f"/api/game/sessions/{session_id}/undo", {
                    "action_id": str(uuid.uuid4()), "target_action_id": str(uuid.uuid4()),
                }),
                ("POST", f"/api/game/sessions/{session_id}/quests/{quest}/accept", None),
                ("POST", f"/api/game/sessions/{session_id}/quests/{quest}/cancel", None),
                ("POST", f"/api/game/sessions/{session_id}/species-actions", {"action": "short_rest"}),
                (
                    "POST",
                    f"/api/game/sessions/{session_id}/ambient-events/{event}/actions",
                    {"action_id": str(uuid.uuid4()), "action": "observe"},
                ),
                ("DELETE", f"/api/game/campaigns/{campaign_id}", None),
            ]

        return routes

    @staticmethod
    def comparable(response, campaign_id: str, session_id: str):
        """Status and body with the record's own ids blanked, so only the outcome is compared."""
        text = response.text.replace(campaign_id, "<campaign>").replace(session_id, "<session>")
        return response.status_code, text

    async def test_a_signed_in_stranger_gets_the_same_answer_as_for_a_missing_record(self):
        routes = self.foreign_requests()
        foreign = routes(self.a_campaign, self.a_session)
        missing_campaign, missing_session = str(uuid.uuid4()), str(uuid.uuid4())
        absent = routes(missing_campaign, missing_session)
        for stranger in ("b", "same_subject"):
            async with self.client(stranger) as client:
                for (method, path, body), (_, missing_path, _) in zip(foreign, absent):
                    got = await client.request(method, path, json=body)
                    nothing = await client.request(method, missing_path, json=body)
                    label = f"{stranger} {method} {path}"
                    self.assertEqual(
                        self.comparable(got, self.a_campaign, self.a_session),
                        self.comparable(nothing, missing_campaign, missing_session),
                        f"{label}: a stranger can tell a real record from a missing one",
                    )
                    if method == "DELETE":
                        self.assertEqual(got.status_code, 200, label)
                        self.assertIs(got.json()["deleted"], False, label)
                    else:
                        self.assertIn(got.status_code, (404, 409), f"{label}: {got.text}")

    async def test_the_strangers_attempts_leave_the_owners_campaign_untouched(self):
        before = self.a_snapshot()
        routes = self.foreign_requests()
        for stranger in ("b", "same_subject"):
            async with self.client(stranger) as client:
                for method, path, body in routes(self.a_campaign, self.a_session):
                    await client.request(method, path, json=body)
        self.assertTrue(self.store.campaign_exists(self.a_campaign, principal=PLAYER_A))
        self.assertEqual(self.a_snapshot(), before)
        self.assertEqual(
            self.manager.get(self.a_session, principal=PLAYER_A)
            .game_session.character["current_hp"],
            self.a_hp,
        )
        async with self.client("a") as owner:
            self.assertEqual((await owner.get(f"/api/game/campaigns/{self.a_campaign}")).status_code, 200)
            self.assertEqual((await owner.post(f"/api/game/campaigns/{self.a_campaign}/save")).status_code, 200)
            self.assertEqual((await owner.post(f"/api/game/campaigns/{self.a_campaign}/resume")).status_code, 200)

    async def test_the_owner_cannot_touch_the_strangers_campaign_either(self):
        async with self.client("a") as owner, self.client("b") as other:
            for method, path, body in self.foreign_requests()(self.b_campaign, self.b_session):
                got = await owner.request(method, path, json=body)
                if method == "DELETE":
                    self.assertIs(got.json()["deleted"], False, f"{method} {path}")
                else:
                    self.assertIn(got.status_code, (404, 409), f"{method} {path}: {got.text}")
            self.assertEqual((await other.get(f"/api/game/campaigns/{self.b_campaign}")).status_code, 200)
        self.assertTrue(self.store.campaign_exists(self.b_campaign, principal=PLAYER_B))

    async def test_a_foreign_delete_is_not_a_delete(self):
        async with self.client("b") as other, self.client("a") as owner:
            gone = await other.delete(f"/api/game/campaigns/{self.a_campaign}")
            self.assertEqual(gone.status_code, 200)
            self.assertIs(gone.json()["deleted"], False, "a foreign delete must not report a delete")
            self.assertEqual((await owner.get(f"/api/game/campaigns/{self.a_campaign}")).status_code, 200)
            own = await owner.delete(f"/api/game/campaigns/{self.a_campaign}")
            self.assertEqual(own.status_code, 200, own.text)
            self.assertEqual((await owner.get(f"/api/game/campaigns/{self.a_campaign}")).status_code, 404)
            self.assertEqual((await other.get(f"/api/game/campaigns/{self.b_campaign}")).status_code, 200)


    async def test_a_saved_but_inactive_campaign_is_409_for_its_owner_and_404_for_everyone_else(self):
        """409 "no active session" is the owner's answer only. After a restart (new
        manager, same database) nothing is active: the owner is told to resume, a
        stranger gets exactly what an unknown id gets."""
        restarted = SessionManager(campaign_store=self.store)
        apps = {
            who: create_app(
                session_manager=restarted, ollama_adapter=None,
                authenticator=FixedAuthenticator(principal),
            )
            for who, principal in (("a", PLAYER_A), ("b", PLAYER_B), ("same_subject", SAME_SUBJECT))
        }

        def client(who):
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=apps[who]),
                base_url="http://isolated-testserver",
            )

        path = f"/api/game/campaigns/{self.a_campaign}/save"
        unknown = f"/api/game/campaigns/{uuid.uuid4()}/save"
        async with client("a") as owner:
            mine = await owner.post(path)
            self.assertEqual(mine.status_code, 409, mine.text)
        for stranger in ("b", "same_subject"):
            async with client(stranger) as other:
                got = await other.post(path)
                nothing = await other.post(unknown)
                self.assertEqual(got.status_code, 404, f"{stranger}: {got.text}")
                self.assertEqual(got.json(), nothing.json(), stranger)


if __name__ == "__main__":
    unittest.main()
