"""Frozen adventure templates. One contract, two implementations."""

from __future__ import annotations

from adventure.dungeon import HIDEOUT_ID
from adventure.models import empty_bindings, new_dynamic_quest

CAPTIVE_TARGET = f"{HIDEOUT_ID}:captive"

TEMPLATES = (
    "MISSING_PERSON", "BOUNTY", "RECOVERY", "DELIVERY", "MONSTER_HUNT",
    "FACTION_CONFLICT", "SOCIAL_INTRIGUE", "DUNGEON_DELVE", "URBAN_INVESTIGATION",
    "ESCORT",
)


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
    builders = {
        "BOUNTY": _bounty,
        "RECOVERY": _recovery,
        "DELIVERY": _delivery,
        "MONSTER_HUNT": _monster_hunt,
        "FACTION_CONFLICT": _faction_conflict,
        "SOCIAL_INTRIGUE": _social_intrigue,
        "DUNGEON_DELVE": _dungeon_delve,
        "URBAN_INVESTIGATION": _urban_investigation,
        "ESCORT": _escort,
    }
    builder = builders.get(template_id)
    if builder is None:
        raise ValueError("Bu macera şablonu yok.")
    return builder(
        quest_id=quest_id,
        turn=turn,
        opportunity_key=opportunity_key,
        creation_evidence=creation_evidence,
        bindings=bindings,
        rumor=rumor,
    )


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


def _simple(title, template_id, threat, plan, objectives, *, quest_id, turn, opportunity_key, creation_evidence, bindings, rumor):
    _require_bindings(bindings, "source_npc_id", "target_npc_id", "location_ids")
    return new_dynamic_quest(
        quest_id=quest_id,
        title=title,
        description=rumor,
        turn=turn,
        template_id=template_id,
        template_version=1,
        binding_version=1,
        opportunity_key=opportunity_key,
        creation_evidence=creation_evidence,
        giver_npc_id=bindings["source_npc_id"],
        bindings=bindings,
        threat_band=threat,
        reward_plan=plan,
        objectives=objectives,
    )


def _recovery(**kwargs):
    place = kwargs["bindings"]["location_ids"][0]
    return _simple(
        "Kayıp eşya", "RECOVERY", "low",
        {"success": {"xp": 50, "gold": 30, "item": "dagger"}, "partial_success": {"xp": 20, "gold": 10}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("ask", "Sahibini dinle", "investigate", kwargs["bindings"]["source_npc_id"], ["investigation", "social"]),
            _node("scene", "Kaybolduğu yere git", "visit_location", place, ["investigation"], ("ask",), hidden=True),
            _node("clue", "Bir iz bul", "discover_clue", place, ["investigation"], ("scene",), hidden=True),
            _node("item", "Kılıcı geri al", "acquire_item", "Kılıç", ["investigation", "item_use"], ("clue",), hidden=True),
            _node("favor", "Ek bir tanığı ara", "investigate", kwargs["bindings"]["target_npc_id"], ["social"], ("ask",), hidden=True, optional=True),
        ],
        **kwargs,
    )


def _delivery(**kwargs):
    place = kwargs["bindings"]["location_ids"][0]
    return _simple(
        "Teslimat", "DELIVERY", "low",
        {"success": {"xp": 40, "gold": 25}, "partial_success": {"xp": 15, "gold": 5}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("take", "Paketi al", "investigate", kwargs["bindings"]["source_npc_id"], ["social"]),
            _node("road", "Varış yerine git", "visit_location", place, ["investigation"], ("take",), hidden=True),
            _node("hand", "Teslim et", "investigate", kwargs["bindings"]["target_npc_id"], ["social"], ("road",), hidden=True),
        ],
        **kwargs,
    )


def _monster_hunt(**kwargs):
    place = kwargs["bindings"]["location_ids"][0]
    return _simple(
        "Canavar avı", "MONSTER_HUNT", "moderate",
        {"success": {"xp": 90, "gold": 40}, "partial_success": {"xp": 30, "gold": 10}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("track", "İzi sür", "visit_location", place, ["investigation"]),
            _node("fight", "Tehdidi durdur", "defeat_entity", kwargs["bindings"]["target_npc_id"], ["combat"], ("track",), hidden=True),
        ],
        **kwargs,
    )


def _faction_conflict(**kwargs):
    place = kwargs["bindings"]["location_ids"][0]
    return _simple(
        "Hizip gerilimi", "FACTION_CONFLICT", "moderate",
        {"success": {"xp": 70, "gold": 20}, "partial_success": {"xp": 25, "gold": 0}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("listen", "Tarafı dinle", "investigate", kwargs["bindings"]["source_npc_id"], ["social", "investigation"]),
            _node("meet", "Karşı tarafı bul", "visit_location", place, ["investigation"], ("listen",), hidden=True),
            _node("talk", "Görüşmeyi yürüt", "investigate", kwargs["bindings"]["target_npc_id"], ["persuasion", "social"], ("meet",), hidden=True),
        ],
        **kwargs,
    )


def _social_intrigue(**kwargs):
    return _simple(
        "Toplumsal entrika", "SOCIAL_INTRIGUE", "low",
        {"success": {"xp": 55, "gold": 15}, "partial_success": {"xp": 20, "gold": 0}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("hear", "Dedikoduyu dinle", "investigate", kwargs["bindings"]["source_npc_id"], ["social"]),
            _node("press", "İkinci kişiyi yokla", "investigate", kwargs["bindings"]["target_npc_id"], ["persuasion", "social"], ("hear",), hidden=True),
        ],
        **kwargs,
    )


def _dungeon_delve(**kwargs):
    return _simple(
        "Sığınak keşfi", "DUNGEON_DELVE", "high",
        {"success": {"xp": 100, "gold": 50}, "partial_success": {"xp": 40, "gold": 10}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("approach", "Sığınağı bul", "visit_location", kwargs["bindings"]["location_ids"][0], ["investigation"]),
            _node("cell", "İç odaya ulaş", "visit_location", CAPTIVE_TARGET, ["investigation"], ("approach",), hidden=True),
            _node("leave", "Tutsakı çıkar", "rescue_person", kwargs["bindings"]["target_npc_id"], ["rescue", "stealth"], ("cell",), hidden=True),
        ],
        **kwargs,
    )


def _urban_investigation(**kwargs):
    place = kwargs["bindings"]["location_ids"][0]
    return _simple(
        "Kent soruşturması", "URBAN_INVESTIGATION", "low",
        {"success": {"xp": 45, "gold": 20}, "partial_success": {"xp": 15, "gold": 0}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("ask", "Tanığı dinle", "investigate", kwargs["bindings"]["source_npc_id"], ["investigation", "social"]),
            _node("alley", "Sokağı ara", "visit_location", place, ["investigation"], ("ask",), hidden=True),
            _node("clue", "Gizli izi çöz", "discover_clue", place, ["investigation"], ("alley",), hidden=True),
        ],
        **kwargs,
    )


def _escort(**kwargs):
    place = kwargs["bindings"]["location_ids"][0]
    return _simple(
        "Refakat", "ESCORT", "low",
        {"success": {"xp": 50, "gold": 20}, "partial_success": {"xp": 20, "gold": 0}, "failed": {"xp": 0, "gold": 0}},
        [
            _node("meet", "Refakat edilecek kişiyi bul", "investigate", kwargs["bindings"]["target_npc_id"], ["social"]),
            _node("walk", "Varış yerine götür", "visit_location", place, ["investigation"], ("meet",), hidden=True),
            _node("arrive", "Güvenle teslim et", "rescue_person", kwargs["bindings"]["target_npc_id"], ["rescue", "social"], ("walk",), hidden=True),
        ],
        **kwargs,
    )


def _node(objective_id, description, kind, target, resolutions, prerequisites=(), hidden=False, optional=False):
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
        "optional": bool(optional),
    }


def prepared_bindings(**values):
    bindings = empty_bindings()
    bindings.update(values)
    return bindings
