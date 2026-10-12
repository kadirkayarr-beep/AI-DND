"""Release security gate: anonymous HTTP must not read or change a campaign.

The fixture is created through the store as a synthetic owner. The HTTP app
stays fail-closed. This never opens the live campaign database.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import game
import httpx

from api.auth import FailClosedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import PLAYER_A


_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()


def _temporary_store(directory: str) -> CampaignStore:
    path = (Path(directory) / "isolated_campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return CampaignStore(path)


async def probe() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ai-dnd-security-gate-") as directory:
        store = _temporary_store(directory)
        session = game.create_session()
        campaign_id = str(uuid.uuid4())
        store.create_campaign(campaign_id, "Gate", session, principal=PLAYER_A)
        manager = SessionManager(campaign_store=store)
        session_id, record, *_ = manager.resume_campaign(campaign_id, principal=PLAYER_A)
        hp = record.game_session.character["current_hp"]
        app = create_app(
            session_manager=manager,
            ollama_adapter=None,
            authenticator=FailClosedAuthenticator(),
        )
        prefixes = ("/api", "/api/game")
        requests = []
        for prefix in prefixes:
            requests.extend([
                ("POST", f"{prefix}/campaigns", {}),
                ("GET", f"{prefix}/campaigns", None),
                ("GET", f"{prefix}/campaigns/{campaign_id}", None),
                ("POST", f"{prefix}/campaigns/{campaign_id}/resume", None),
                ("POST", f"{prefix}/campaigns/{campaign_id}/save", None),
                ("DELETE", f"{prefix}/campaigns/{campaign_id}", None),
                ("POST", f"{prefix}/sessions/{session_id}/turn", {"message": "Bekle."}),
            ])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://isolated-testserver",
        ) as client:
            results = []
            for method, path, body in requests:
                response = await client.request(
                    method,
                    path,
                    json=body,
                    headers={
                        "Authorization": "Bearer client-token",
                        "X-Replit-User-Id": "spoofed",
                    },
                )
                results.append({
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                })
        exposed = any(item["status"] == 200 for item in results)
        still_owned = store.campaign_exists(campaign_id, principal=PLAYER_A)
        unchanged = record.game_session.character["current_hp"] == hp
        passed = not exposed and still_owned and unchanged
        return {
            "status": "PASS" if passed else "FAIL",
            "scope": "temporary_sqlite_anonymous_http",
            "results": results,
            "campaign_still_owned": still_owned,
            "turn_did_not_change_hp": unchanged,
            "release_ready": False,
        }


if __name__ == "__main__":
    result = asyncio.run(probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "PASS" else 1)
