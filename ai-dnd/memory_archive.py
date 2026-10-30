"""Memory compaction and bounded retrieval with kept sources (W08).

Active short context, summaries and a source-traced archive are separate things:

* `compact_memory` keeps the newest `active_limit` entries per NPC plus every high-importance entry in the active context
  and moves the rest to an archive. An archived record keeps the ORIGINAL entry whole, resolvable by a stable source id.
  Its summary is labelled `summary_authority: "summary"`; nothing here (and no model) decides that a summary is an event.
  The input is never mutated, and the commitment ledger in `npc_statements` is not touched, so a closed promise keeps its reason.
* `retrieve_memory` answers from active + archive within a token budget. Names with Turkish case suffixes, an explicit last
  referent for pronouns and explicit aliases select the NPC; a secret entry is returned only to an observer in its `known_to`.

Measured numbers are reported separately in `metrics` (bytes, estimated context tokens, elapsed time); no vector store.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from typing import Any

_PRONOUNS = frozenset({"o", "ona", "onu", "onun", "ondan", "onunla", "onda"})


def source_id_of(npc_id: str, entry: dict[str, Any]) -> str:
    """Stable id of one memory entry: owner, turn and a hash of its text."""
    digest = hashlib.sha1(str(entry.get("text", "")).encode("utf-8")).hexdigest()[:8]
    return f"mem:{npc_id}:{_turn(entry)}:{digest}"


def _turn(entry: dict[str, Any]) -> int:
    value = entry.get("turn_index")
    return value if type(value) is int else 0


def _authority(entry: dict[str, Any]) -> str:
    return "player_note" if entry.get("source") == "player_note" else str(entry.get("source") or "player_utterance")


def _tokens(text: str) -> int:
    return len(text.encode("utf-8")) // 2 + 4  # conservative UTF-8 estimate, not a tokenizer count


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def compact_memory(memory: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Return {"active": memory', "archive": [records], "metrics": {...}}; `memory` itself is left untouched."""
    started = time.perf_counter()
    limit = max(0, int(policy.get("active_limit", 20)))
    keep_high = policy.get("keep_importance", "high") == "high"
    active = copy.deepcopy(memory)
    archive: list[dict[str, Any]] = []
    entries_before = entries_active = 0
    for npc_id, entries in list(active.get("npc_interactions", {}).items()):
        entries_before += len(entries)
        ordered = sorted(enumerate(entries), key=lambda pair: (_turn(pair[1]), pair[0]))
        newest = {index for index, _ in ordered[-limit:]} if limit else set()
        kept = []
        for index, entry in enumerate(entries):
            if index in newest or (keep_high and entry.get("importance") == "high"):
                kept.append(entry)
                continue
            archive.append({
                "source_id": source_id_of(npc_id, entry), "npc_id": npc_id, "entry": copy.deepcopy(entry),
                "authority": _authority(entry), "visibility": copy.deepcopy(entry.get("visibility") or {}),
                # a secret's text never leaks through its summary
                "summary": "[gizli kayıt]" if (entry.get("visibility") or {}).get("secret") else str(entry.get("text", ""))[:80],
                "summary_authority": "summary",
            })
        active["npc_interactions"][npc_id] = kept
        entries_active += len(kept)
    metrics = {
        "entries_before": entries_before, "entries_active": entries_active, "entries_archived": len(archive),
        "bytes_before": _size(memory), "bytes_after": _size(active), "archive_bytes": _size(archive),
        "context_tokens": _tokens(json.dumps(active.get("npc_interactions", {}), ensure_ascii=False)),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    return {"active": active, "archive": archive, "metrics": metrics}


def resolve_source(compacted: dict[str, Any], source_id: str) -> dict[str, Any] | None:
    """Find the original entry for a source id in the active context or the archive."""
    for record in compacted.get("archive", []):
        if record["source_id"] == source_id:
            return {"source_id": source_id, "npc_id": record["npc_id"], "entry": record["entry"],
                    "authority": record["authority"], "where": "archive"}
    for npc_id, entries in compacted.get("active", {}).get("npc_interactions", {}).items():
        for entry in entries:
            if source_id_of(npc_id, entry) == source_id:
                return {"source_id": source_id, "npc_id": npc_id, "entry": entry,
                        "authority": _authority(entry), "where": "active"}
    return None


def _fold(text: str) -> str:
    return str(text).replace("İ", "i").replace("I", "ı").casefold()


def _resolve_npc(query: dict[str, Any], knowledge: dict[str, Any], names: dict[str, str]) -> str | None:
    if isinstance(query.get("npc_id"), str):
        return query["npc_id"]
    words = re.findall(r"[a-zçğıöşü]+", _fold(query.get("text", "")))
    folded_text = " ".join(words)
    for npc_id, name in names.items():
        # a name may carry Turkish case suffixes ("Aylin'e" -> words "aylin", "e")
        if name and re.search(rf"(?<![a-zçğıöşü]){re.escape(_fold(name))}", folded_text):
            return npc_id
    for npc_id, aliases in (knowledge.get("aliases") or {}).items():
        for alias in aliases:
            if re.search(rf"(?<![a-zçğıöşü]){re.escape(_fold(alias))}", folded_text):
                return npc_id
    if any(word in _PRONOUNS for word in words) and isinstance(knowledge.get("last_npc_id"), str):
        return knowledge["last_npc_id"]
    return None


def _may_know(visibility: dict[str, Any], observer_id: str, npc_id: str) -> bool:
    if not visibility or not visibility.get("secret"):
        return True
    return observer_id in (visibility.get("known_to") or []) or observer_id == npc_id


def retrieve_memory(query: dict[str, Any], knowledge: dict[str, Any], budget_tokens: int,
                    compacted: dict[str, Any] | None = None, memory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Select the observer-visible entries of the addressed NPC, high importance first then recent, within `budget_tokens`."""
    source = compacted if compacted is not None else compact_memory(memory or {"npc_interactions": {}}, {"active_limit": 10**6})
    active = source.get("active", {})
    names = {npc_id: str(record.get("name", ""))
             for npc_id, record in (active.get("entity_memory", {}).get("npcs", {}) or {}).items()}
    npc_id = _resolve_npc(query, knowledge, names)
    observer_id = str(knowledge.get("observer_id", ""))
    candidates = []
    if npc_id is not None:
        for entry in active.get("npc_interactions", {}).get(npc_id, []):
            candidates.append((entry, "active"))
        for record in source.get("archive", []):
            if record["npc_id"] == npc_id:
                candidates.append((record["entry"], "archive"))
    visible = [(entry, where) for entry, where in candidates
               if _may_know(entry.get("visibility") or {}, observer_id, npc_id or "")]
    visible.sort(key=lambda pair: (0 if pair[0].get("importance") == "high" else 1, -_turn(pair[0])))
    items, used, dropped = [], 0, 0
    for entry, where in visible:
        cost = _tokens(str(entry.get("text", "")))
        if used + cost > budget_tokens:
            dropped += 1
            continue
        used += cost
        items.append({"source_id": source_id_of(npc_id or "", entry), "text": entry.get("text", ""), "where": where,
                      "authority": _authority(entry), "importance": entry.get("importance")})
    return {"npc_id": npc_id, "items": items, "used_tokens": used, "dropped": dropped,
            "withheld": len(candidates) - len(visible)}
