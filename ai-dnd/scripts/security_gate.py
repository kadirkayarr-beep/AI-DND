"""Release security gate: probe anonymous campaign access in a TEMPORARY app.

Never touches the configured campaign database or sends HTTP requests to
Replit/live deployments. Exit code 1 means DO NOT publish.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


async def probe() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ai-dnd-security-gate-") as directory:
        store = CampaignStore(Path(directory) / "isolated_campaigns.sqlite3")
        manager = SessionManager(campaign_store=store)
        app = create_app(session_manager=manager, ollama_adapter=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://isolated-testserver",
        ) as client:
            created = await client.post("/api/game/campaigns", json={})
            if created.status_code != 200:
                return {
                    "status": "INCONCLUSIVE",
                    "reason": "temporary_fixture_creation_failed",
                    "fixture_status": created.status_code,
                    "release_ready": False,
                }
            campaign_id = created.json()["campaign_id"]
            listing = await client.get("/api/game/campaigns")
            detail = await client.get(f"/api/game/campaigns/{campaign_id}")
            deletion = await client.delete(f"/api/game/campaigns/{campaign_id}")
            exposed = any(response.status_code == 200 for response in (
                listing, detail, deletion,
            ))
            return {
                "status": "FAIL" if exposed else "PASS",
                "scope": "temporary_in_memory_http_transport_temporary_sqlite",
                "anonymous_list_http": listing.status_code,
                "anonymous_read_http": detail.status_code,
                "anonymous_delete_http": deletion.status_code,
                "release_ready": not exposed,
            }


if __name__ == "__main__":
    result = asyncio.run(probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["release_ready"] else 1)
