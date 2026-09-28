#!/usr/bin/env python3
"""Real HTTP-to-Qwen smoke for the FastAPI adapter; no parser/model mocks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import httpx


BASE_URL = os.environ.get("AI_DND_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_PREFIX = os.environ.get("AI_DND_API_PREFIX", "/api").rstrip("/")
MODEL_NAME = "qwen3:8b"


def api_path(suffix: str) -> str:
    return f"{API_PREFIX}/{suffix.lstrip('/')}"


def main() -> int:
    game_file = Path(__file__).resolve().parents[1] / "game.py"
    game_hash = hashlib.sha256(game_file.read_bytes()).hexdigest()
    issues: list[str] = []
    turns: list[dict[str, Any]] = []
    timeout = httpx.Timeout(120.0, connect=10.0)

    try:
        with httpx.Client(base_url=BASE_URL, timeout=timeout) as client:
            health_response = client.get(api_path("/health"))
            health_response.raise_for_status()
            health = health_response.json()
            if health.get("model") != MODEL_NAME:
                issues.append("API health reports an unexpected model")

            creation = client.post(api_path("/sessions"))
            creation.raise_for_status()
            session_id = creation.json()["session_id"]
            state = creation.json()["state"]

            steps = [
                ("travel_tavern", "tavernaya gidiyorum"),
                ("explore_tavern", "şöyle bi etrafa bakalım"),
                ("presence", "burda kimler var"),
            ]

            previous_location = state.get("location")
            for label, message in steps:
                response = client.post(
                    api_path(f"/sessions/{session_id}/turn"),
                    json={"message": message},
                )
                response.raise_for_status()
                turn = response.json()
                state = turn["state"]
                if turn.get("session_id") != session_id:
                    issues.append(f"{label}: response session id mismatch")
                if not isinstance(turn.get("narration"), str) or not turn["narration"].strip():
                    issues.append(f"{label}: empty narration")

                canonical_response = client.get(
                    api_path(f"/sessions/{session_id}/state")
                )
                canonical_response.raise_for_status()
                if canonical_response.json() != state:
                    issues.append(f"{label}: turn and state endpoint disagree")

                if label == "travel_tavern" and state.get("location") != "tavern":
                    issues.append("Tavern travel did not commit")
                if label == "explore_tavern" and state.get("location") != previous_location:
                    issues.append("Exploration changed location")
                if label == "location_query":
                    location = state.get("locations", {}).get(state.get("location"), {})
                    location_name = location.get("name", "")
                    if location_name and location_name.casefold() not in turn["narration"].casefold():
                        issues.append("Location narration contradicts canonical state")

                turns.append(
                    {
                        "label": label,
                        "status": response.status_code,
                        "location": state.get("location"),
                        "narration": turn["narration"],
                    }
                )
                previous_location = state.get("location")

                if label == "presence":
                    current_npcs = [
                        npc for npc in state.get("npcs", [])
                        if npc.get("location") == state.get("location")
                    ]
                    if current_npcs:
                        steps.append(("npc_greeting", "Merhaba, nasılsın?"))
                    steps.extend(
                        [
                            ("npc_identity", "senin adın ne?"),
                            ("location_query", "nerdeyim"),
                        ]
                    )

    except httpx.HTTPStatusError as error:
        response = error.response
        try:
            safe_detail = response.json().get("detail", "API request failed")
        except Exception:
            safe_detail = "API request failed"
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "game_sha256": game_hash,
                    "model": MODEL_NAME,
                    "http_status": response.status_code,
                    "detail": safe_detail,
                    "turns_run": len(turns),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "game_sha256": game_hash,
                    "model": MODEL_NAME,
                    "error_type": type(error).__name__,
                    "turns_run": len(turns),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "PASS" if not issues else "FAIL",
                "game_sha256": game_hash,
                "model": MODEL_NAME,
                "turns_run": len(turns),
                "issues": issues,
                "turns": turns,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())