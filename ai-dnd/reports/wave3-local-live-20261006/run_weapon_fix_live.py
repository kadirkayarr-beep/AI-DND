"""Live revalidation of weapon_not_held fix. Records as f74 + working changes."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8008"
VAL = Path(__file__).resolve().parent
LOGS = (VAL / "api_fix.out.log", VAL / "api_fix.err.log")
START = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}
BUDGET_CAP = 4


def sizes() -> dict[str, int]:
    return {str(p): (p.stat().st_size if p.exists() else 0) for p in LOGS}


def calls(before: dict[str, int]) -> int:
    chunks = []
    for path in LOGS:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        chunks.append(text[before.get(str(path), 0) :])
    new = "\n".join(chunks)
    matches = re.findall(r"model_calls=(\d+)", new)
    started = len(re.findall(r"Ollama chat request started", new))
    return int(matches[-1]) if matches else started


def main() -> None:
    budget_used = 0
    rows: list[dict] = []
    with httpx.Client(timeout=300.0) as client:
        health = client.get(f"{BASE}/api/game/health").json()
        created = client.post(
            f"{BASE}/api/game/campaigns",
            json={
                "name": f"weapon fix live {uuid.uuid4().hex[:6]}",
                "campaign_start": START,
            },
        )
        created.raise_for_status()
        body = created.json()
        sid = body["session_id"]

        def turn(message: str, mode: str, target_id: str | None = None, label: str = "") -> dict:
            nonlocal budget_used
            before = sizes()
            payload = {
                "message": message,
                "interaction_mode": mode,
                "action_id": str(uuid.uuid4()),
            }
            if target_id is not None:
                payload["target_id"] = target_id
            resp = client.post(f"{BASE}/api/game/sessions/{sid}/turn", json=payload)
            count = calls(before)
            if count > 0:
                budget_used += 1
            data = resp.json()
            after = data.get("state")
            if resp.status_code == 200 and not isinstance(after, dict):
                after = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            row = {
                "label": label,
                "message": message,
                "mode": mode,
                "target": target_id,
                "http": resp.status_code,
                "calls": count,
                "budget_used": budget_used,
                "detail": data.get("detail"),
                "narration": (data.get("narration") or "")[:220],
                "combat": bool(((after or {}).get("combat") or {}).get("active"))
                if isinstance(after, dict)
                else False,
                "conversation": (after or {}).get("conversation")
                if isinstance(after, dict)
                else None,
                "inventory": (after or {}).get("inventory") if isinstance(after, dict) else None,
                "combat_result": data.get("combat_result"),
            }
            rows.append(row)
            if budget_used > BUDGET_CAP:
                raise RuntimeError(f"budget exceeded: {budget_used}")
            return row

        turn("Etrafıma bakıyorum.", "ask_dm", label="look")
        inv = turn("Envanterimde neler var?", "ask_dm", label="inventory")
        state = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
        npcs = state.get("npcs") or []
        if not npcs:
            raise RuntimeError("No NPCs after look")
        primary = npcs[0]
        turn(
            f"{primary.get('name', 'kişi')} kişisine yaklaşıyorum.",
            "do",
            primary["id"],
            label="approach",
        )
        named = turn(
            "Ona kılıcımla saldırıyorum.",
            "do",
            primary["id"],
            label="named_attack_no_draw",
        )

        # Separate campaign for pronoun attack after inventory materialize
        created2 = client.post(
            f"{BASE}/api/game/campaigns",
            json={
                "name": f"weapon fix pronoun {uuid.uuid4().hex[:6]}",
                "campaign_start": START,
            },
        ).json()
        sid2 = created2["session_id"]
        pronoun_rows: list[dict] = []

        def turn2(message: str, mode: str, target_id: str | None = None, label: str = "") -> dict:
            nonlocal budget_used
            before = sizes()
            payload = {
                "message": message,
                "interaction_mode": mode,
                "action_id": str(uuid.uuid4()),
            }
            if target_id is not None:
                payload["target_id"] = target_id
            resp = client.post(f"{BASE}/api/game/sessions/{sid2}/turn", json=payload)
            count = calls(before)
            if count > 0:
                budget_used += 1
            data = resp.json()
            after = data.get("state")
            if resp.status_code == 200 and not isinstance(after, dict):
                after = client.get(f"{BASE}/api/game/sessions/{sid2}/state").json()
            row = {
                "label": label,
                "message": message,
                "mode": mode,
                "target": target_id,
                "http": resp.status_code,
                "calls": count,
                "budget_used": budget_used,
                "detail": data.get("detail"),
                "narration": (data.get("narration") or "")[:220],
                "combat": bool(((after or {}).get("combat") or {}).get("active"))
                if isinstance(after, dict)
                else False,
                "conversation": (after or {}).get("conversation")
                if isinstance(after, dict)
                else None,
                "inventory": (after or {}).get("inventory") if isinstance(after, dict) else None,
            }
            pronoun_rows.append(row)
            if budget_used > BUDGET_CAP:
                raise RuntimeError(f"budget exceeded: {budget_used}")
            return row

        turn2("Etrafıma bakıyorum.", "ask_dm", label="look2")
        turn2("Envanterimde neler var?", "ask_dm", label="inventory2")
        state2 = client.get(f"{BASE}/api/game/sessions/{sid2}/state").json()
        npc2 = (state2.get("npcs") or [None])[0]
        if not npc2:
            raise RuntimeError("No NPCs in pronoun campaign")
        turn2(
            f"{npc2.get('name', 'kişi')} kişisine yaklaşıyorum.",
            "do",
            npc2["id"],
            label="approach2",
        )
        pronoun = turn2(
            "Ona saldırıyorum.",
            "do",
            npc2["id"],
            label="pronoun_attack_no_draw",
        )

        # Unequipped control on third campaign: unequip via /item then attack
        created3 = client.post(
            f"{BASE}/api/game/campaigns",
            json={
                "name": f"weapon fix unequip {uuid.uuid4().hex[:6]}",
                "campaign_start": START,
            },
        ).json()
        sid3 = created3["session_id"]

        def turn3(message: str, mode: str, target_id: str | None = None, label: str = "") -> dict:
            nonlocal budget_used
            before = sizes()
            payload = {
                "message": message,
                "interaction_mode": mode,
                "action_id": str(uuid.uuid4()),
            }
            if target_id is not None:
                payload["target_id"] = target_id
            resp = client.post(f"{BASE}/api/game/sessions/{sid3}/turn", json=payload)
            count = calls(before)
            if count > 0:
                budget_used += 1
            data = resp.json()
            after = data.get("state")
            if resp.status_code == 200 and not isinstance(after, dict):
                after = client.get(f"{BASE}/api/game/sessions/{sid3}/state").json()
            return {
                "label": label,
                "message": message,
                "http": resp.status_code,
                "calls": count,
                "budget_used": budget_used,
                "detail": data.get("detail"),
                "combat": bool(((after or {}).get("combat") or {}).get("active"))
                if isinstance(after, dict)
                else False,
                "inventory": (after or {}).get("inventory") if isinstance(after, dict) else None,
                "narration": (data.get("narration") or "")[:220],
            }

        turn3("Etrafıma bakıyorum.", "ask_dm", label="look3")
        turn3("/item list", "do", label="item_list")
        state3 = client.get(f"{BASE}/api/game/sessions/{sid3}/state").json()
        unequip = turn3("/item unequip main_hand", "do", label="unequip")
        npc3 = (state3.get("npcs") or [None])[0]
        # refresh npcs after looks
        state3 = client.get(f"{BASE}/api/game/sessions/{sid3}/state").json()
        npc3 = (state3.get("npcs") or [None])[0]
        if npc3:
            turn3(
                f"{npc3.get('name', 'kişi')} kişisine yaklaşıyorum.",
                "do",
                npc3["id"],
                label="approach3",
            )
            unheld = turn3(
                "Ona kılıcımla saldırıyorum.",
                "do",
                npc3["id"],
                label="unheld_named_attack",
            )
        else:
            unheld = {"http": None, "detail": "no npc", "combat": False}

        out = {
            "source": "f74 + working tree weapon_not_held fix",
            "not_clean_f74": True,
            "health": health,
            "budget_used_model_requiring_turns": budget_used,
            "budget_cap": BUDGET_CAP,
            "named_campaign": sid,
            "pronoun_campaign": sid2,
            "unequip_campaign": sid3,
            "inventory_after_materialize": inv.get("inventory"),
            "named_attack_no_draw": {
                "status": (
                    "PASS"
                    if named["http"] == 200
                    and named["combat"] is True
                    and (named.get("conversation") or {}).get("active") is False
                    else "FAIL"
                ),
                **{k: named[k] for k in ("http", "combat", "conversation", "detail", "calls", "narration", "inventory")},
            },
            "pronoun_attack_no_draw": {
                "status": (
                    "PASS"
                    if pronoun["http"] == 200
                    and pronoun["combat"] is True
                    and (pronoun.get("conversation") or {}).get("active") is False
                    else "FAIL"
                ),
                **{
                    k: pronoun[k]
                    for k in ("http", "combat", "conversation", "detail", "calls", "narration", "inventory")
                },
            },
            "unheld_still_rejected": {
                "status": (
                    "PASS"
                    if unheld.get("http") == 400
                    and isinstance(unheld.get("detail"), dict)
                    and unheld["detail"].get("code") == "weapon_not_held"
                    and unheld.get("combat") is False
                    else "FAIL"
                ),
                "unequip": unequip,
                "attack": unheld,
            },
            "turns_named": rows,
            "turns_pronoun": pronoun_rows,
            "prior_failing_evidence_preserved": str(VAL / "evidence.json"),
        }
        (VAL / "evidence_weapon_fix_live.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "named": out["named_attack_no_draw"]["status"],
                    "pronoun": out["pronoun_attack_no_draw"]["status"],
                    "unheld": out["unheld_still_rejected"]["status"],
                    "budget_used": budget_used,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
