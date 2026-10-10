"""Read-only narration of resolved outcomes; no mechanics or world writes."""


def lore_rejected_action(result, lore_context=None):
    if not isinstance(result, dict):
        return None
    if result.get("action") == "shop_setup" and result.get("status") == "created":
        return result.get("direct_response")
    if result.get("action") != "skill_check":
        return None
    if result.get("skill") not in {"Investigation", "Perception"}:
        return None
    success = result.get("outcome") in {"success", "critical_success"}
    if success:
        sections = lore_context.get("sections", {}) if isinstance(lore_context, dict) else {}
        facts = [fact for key in ("official_forgotten_realms_lore", "campaign_canon", "player_known_lore")
                 for fact in sections.get(key, []) if isinstance(fact, dict)]
        if any(fact.get("subject_id") == "fr:city:neverwinter"
               and fact.get("predicate") == "current_status"
               and fact.get("object_id_or_value") == "rebuilding" for fact in facts):
            return "İncelemen başarılı oldu. Neverwinter yeniden inşa ediliyor; bunun ötesinde doğrulanmış yeni bir bilgi yok."
        return "İncelemen başarılı oldu; bunun ötesinde doğrulanmış yeni bir bilgi yok."
    return "İncelemen bu kez sonuç vermedi; yeni bir bilgiye ulaşamadın."


def bounded_rebuilding_check(result, player_input, lore_context):
    """Only this lore investigation needs a bounded, resolved evidence answer."""
    import living_world
    text = living_world.normalize_text(player_input)
    if (isinstance(result, dict) and result.get("action") == "skill_check"
            and result.get("skill") == "Investigation" and "neverwinter" in text
            and ("rebuild" in text or "yeniden insa" in text)):
        return lore_rejected_action(result, lore_context)
    return None
