"""Turn-local selection of actual witnessed engine deeds, never free speech authority."""
from __future__ import annotations

import hashlib
import json
import npc_statements
from collections.abc import Mapping

# Engine record kinds, not a vocabulary for recognizing player language.
_WITNESSED_KINDS = frozenset({"arson", "assault", "killing", "theft"})


def candidates(world: Mapping, npc: Mapping | None) -> list[dict[str, str]]:
    if not isinstance(npc, Mapping) or not isinstance(npc.get("id"), str):
        return []
    if npc.get("location") != world.get("location"):
        return []
    people = world.get("npcs", [])
    if not isinstance(people, list) or not any(
        isinstance(person, Mapping) and person.get("id") == npc["id"]
        and person.get("location") == world.get("location") for person in people
    ):
        return []
    flags = world.get("flags")
    deeds = flags.get("deeds") if isinstance(flags, Mapping) else None
    if not isinstance(deeds, list):
        return []
    rows = []
    for index in range(len(deeds) - 1, -1, -1):
        deed = deeds[index]
        if (not isinstance(deed, dict) or not isinstance(deed.get("kind"), str)
                or deed["kind"] not in _WITNESSED_KINDS):
            continue
        witnesses, text = deed.get("witnesses"), deed.get("text")
        if (not isinstance(witnesses, list) or npc["id"] not in witnesses
                or not isinstance(text, str) or not text.strip() or len(text) > 160):
            continue
        try:
            payload = json.dumps([npc["id"], index, deed], sort_keys=True,
                                 ensure_ascii=False, allow_nan=False)
            identity = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            continue
        rows.append({"source_id": "witness:" + identity, "text": text})
        if len(rows) == 8:
            break
    return rows


def answer(world: Mapping, npc: Mapping | None, player_input: str, proposal, *, about: str) -> str | None:
    """Return only the selected live source text. The proposal cannot supply answer prose."""
    if (about != "memory" or not isinstance(proposal, dict)
            or set(proposal) != {"scope", "source_id", "evidence_quote", "source_quote"}
            or proposal.get("scope") != "witnessed_deed"
            or proposal.get("evidence_quote") != player_input
            or not isinstance(proposal.get("source_id"), str)):
        return None
    for row in candidates(world, npc):
        if (row["source_id"] != proposal["source_id"]
                or proposal.get("source_quote") != row["text"]):
            continue
        source = npc_statements.fold(row["text"]).split()
        message = npc_statements.fold(player_input).split()
        if source and any(message[index:index + len(source)] == source
                          for index in range(len(message) - len(source) + 1)):
            return row["text"]
    return None


def schema(rows: list[dict[str, str]]) -> dict:
    return {"type": "object", "properties": {
        "scope": {"type": "string", "enum": ["witnessed_deed"]},
        "source_id": {"type": "string", "enum": [row["source_id"] for row in rows]},
        "source_quote": {"type": "string", "enum": [row["text"] for row in rows]},
        "evidence_quote": {"type": "string"}},
        "required": ["scope", "source_id", "evidence_quote", "source_quote"], "additionalProperties": False}


def guidance(rows: list[dict[str, str]]) -> str:
    return (
        "\nWITNESSED ENGINE DEEDS (read-only): " + json.dumps(rows, ensure_ascii=False)
        + "\nOyuncu kendi geçmiş eylemini hatırlamanı soruyorsa witness_recall önerebilirsin. "
        "scope=witnessed_deed, canlı listedeki source_id, aynı satırın tam text değerini source_quote "
        "ve mevcut oyuncu mesajının tamamını birebir evidence_quote olarak seç. Python yalnız kaynak "
        "metninin tamamı mevcut mesajda açıkça alıntılandığında o olayın sınırlı hatırlatılmasına izin verir. "
        "Genel veya serbestçe yeniden anlatılan olay güvenilir biçimde bağlanamıyorsa açıklama istenir; "
        "başka bir olayı cevap diye seçme. Aile bilgisi, oyuncunun sözleri veya NPC vaadi bu kaynakla "
        "doğrulanmaz. Bu öneri spoken_text, kişisel bellek, para veya mekanik alanlarına yetki vermez."
    )
