"""Frozen adventure templates. One contract, two implementations."""

from __future__ import annotations

from adventure.dungeon import HIDEOUT_ID
from adventure.models import empty_bindings, new_dynamic_quest

CAPTIVE_TARGET = f"{HIDEOUT_ID}:captive"

TEMPLATES = ("MISSING_PERSON", "BOUNTY")


def instantiate(template_id, *, quest_id, turn, opportunity_key, creation_evidence, bindings, rumor):
    if template_id == "MISSING_PERSON":
        return _missing_person(
            quest_id=quest_id,
            turn=turn,
            opportunity_key=opportunity_key,
            creation_evidence=creation_evidence,
            bindings=bindings,
            rumor=rumor,
        )
    if template_id == "BOUNTY":
        return _bounty(
            quest_id=quest_id,
            turn=turn,
            opportunity_key=opportunity_key,
            creation_evidence=creation_evidence,
            bindings=bindings,
            rumor=rumor,
        )
    raise ValueError("Bu macera şablonu yok.")


def _require_bindings(bindings, *keys):
    if not isinstance(bindings, dict):
        raise ValueError("Macera bağı geçersiz.")
    for key in keys:
        value = bindings.get(key)
        if key.endswith("_ids"):
            if not isinstance(value, list) or not value:
                raise ValueError("Macera bağı geçersiz.")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError("Macera bağı geçersiz.")


def _missing_person(*, quest_id, turn, opportunity_key, creation_evidence, bindings, rumor):
    _require_bindings(bindings, "source_npc_id", "target_npc_id", "location_ids")
    place = bindings["location_ids"][0]
    return new_dynamic_quest(
        quest_id=quest_id,
        title="Kayıp kişi",
        description=rumor,
        turn=turn,
        template_id="MISSING_PERSON",
        template_version=1,
        binding_version=1,
        opportunity_key=opportunity_key,
        creation_evidence=creation_evidence,
        giver_npc_id=bindings["source_npc_id"],
        bindings=bindings,
        threat_band="moderate",
        reward_plan={
            "success": {"xp": 80, "gold": 50, "item": "dagger"},
            "partial_success": {"xp": 40, "gold": 20},
            "failed": {"xp": 0, "gold": 0},
        },
        objectives=[
            _node("hook", "Söylentiyi dinle", "investigate", bindings["source_npc_id"], ["investigation", "persuasion", "social"]),
            _node("clue", "Bir iz bul", "discover_clue", place, ["investigation"], ("hook",), hidden=True),
            _node("site", "Son görülen yere git", "visit_location", place, ["investigation"], ("clue",), hidden=True),
            _node(
                "cell",
                "Tutsak odasına ulaş",
                "visit_location",
                CAPTIVE_TARGET,
                ["investigation"],
                ("site",),
                hidden=True,
            ),
            _node(
                "rescue",
                "Kayıp kişiyi güvenli yere ulaştır",
                "rescue_person",
                bindings["target_npc_id"],
                ["combat", "persuasion", "stealth", "rescue"],
                ("site", "cell"),
                hidden=True,
            ),
            _node(
                "threat",
                "Tehdidi dağıt",
                "defeat_entity",
                bindings["target_npc_id"],
                ["combat", "persuasion"],
                ("site",),
                hidden=True,
            ),
        ],
    )


def _bounty(*, quest_id, turn, opportunity_key, creation_evidence, bindings, rumor):
    _require_bindings(bindings, "source_npc_id", "target_npc_id", "location_ids")
    place = bindings["location_ids"][0]
    return new_dynamic_quest(
        quest_id=quest_id,
        title="Ödül avı",
        description=rumor,
        turn=turn,
        template_id="BOUNTY",
        template_version=1,
        binding_version=1,
        opportunity_key=opportunity_key,
        creation_evidence=creation_evidence,
        giver_npc_id=bindings["source_npc_id"],
        bindings=bindings,
        threat_band="low",
        reward_plan={
            "success": {"xp": 60, "gold": 80},
            "partial_success": {"xp": 20, "gold": 20},
            "failed": {"xp": 0, "gold": 0},
        },
        objectives=[
            _node("notice", "Hedefi öğren", "investigate", bindings["source_npc_id"], ["investigation"]),
            _node("mark", "Hedefin yerini doğrula", "visit_location", place, ["investigation"], ("notice",), hidden=True),
            _node(
                "resolve",
                "Hedefi etkisiz bırak ya da teslim olmaya ikna et",
                "defeat_entity",
                bindings["target_npc_id"],
                ["combat", "persuasion"],
                ("mark",),
                hidden=True,
            ),
        ],
    )


def _node(objective_id, description, kind, target, resolutions, prerequisites=(), hidden=False):
    return {
        "objective_id": objective_id,
        "description": description,
        "type": kind,
        "target": target,
        "required_count": 1,
        "progress": 0,
        "visibility": "hidden" if hidden else "known",
        "prerequisites": list(prerequisites),
        "resolution_kinds": list(resolutions),
        "graph_state": "HIDDEN" if hidden else "ACTIVE",
    }


def prepared_bindings(**values):
    bindings = empty_bindings()
    bindings.update(values)
    return bindings
