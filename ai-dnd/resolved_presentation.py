"""Read-only narration of resolved outcomes; no mechanics or world writes."""


def lore_rejected_action(result, lore_context=None):
    if not isinstance(result, dict):
        return None
    # Reject unsupported decoration, not an already committed physical result.
    # These texts originate in the Python action owner, never model proposals.
    if result.get("action") in {"enter", "travel", "grounded_action", "open", "close", "leave"}:
        direct = result.get("direct_response")
        if isinstance(direct, str) and direct.strip():
            return direct
    if (result.get("action") == "explore" and result.get("status") == "observed"
            and result.get("success") is True):
        direct = result.get("direct_response")
        if isinstance(direct, str) and direct.strip():
            return direct
    if result.get("action") == "shop_setup" and result.get("status") == "created":
        return result.get("direct_response")
    if result.get("action") != "skill_check":
        return None
    if result.get("skill") not in {"Investigation", "Perception"}:
        return None
    findings = result.get("inspection")
    if isinstance(findings, dict) and isinstance(findings.get("text"), str):
        # LR00-P2: the concrete, target-bound finding is the resolved outcome.
        return findings["text"]
    success = result.get("outcome") in {"success", "critical_success"}
    if success:
        sections = lore_context.get("sections", {}) if isinstance(lore_context, dict) else {}
        facts = [fact for key in ("official_forgotten_realms_lore", "campaign_canon", "player_known_lore")
                 for fact in sections.get(key, []) if isinstance(fact, dict)]
        if any(fact.get("subject_id") == "fr:city:neverwinter"
               and fact.get("predicate") == "current_status"
               and fact.get("object_id_or_value") == "rebuilding" for fact in facts):
            return ("İncelemen başarılı: Neverwinter'ın her yanında yeniden inşa izleri var; "
                    "bunun ötesinde yeni bir şey göze çarpmıyor.")
        return "İncelemen başarılı: gözden kaçan bir şey yok, ama yeni bir ipucu da çıkmıyor."
    return "İncelemen sonuç vermedi; bu bakışla yeni bir ayrıntı seçilmiyor."


def bounded_rebuilding_check(result, player_input, lore_context):
    """Only this lore investigation needs a bounded, resolved evidence answer."""
    import living_world
    text = living_world.normalize_text(player_input)
    if (isinstance(result, dict) and result.get("action") == "skill_check"
            and result.get("skill") == "Investigation" and "neverwinter" in text
            and ("rebuild" in text or "yeniden insa" in text)):
        return lore_rejected_action(result, lore_context)
    return None
