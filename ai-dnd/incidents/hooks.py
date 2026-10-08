"""The two session doors into the incident owner.

``before_narration`` may spend the one emergence call when the arbiter allows
it. ``after_turn`` applies lifecycle and awareness from committed evidence and
never calls a model.
"""

from __future__ import annotations

import emergence_audit
from incidents import arbiter, attempts, awareness, commit, generator, npcs, profiles, props, rewards, sublocations, triggers
from incidents import envelope as envelope_owner

PENDING_ATTR = "_emergence_pending"


def _lore_state(session):
    return getattr(session, "lore_authority", None)


def _result(status=None, calls=0):
    return {"status": status, "model_calls": calls}


def before_narration(session, *, action_result, player_text, location_changed, propose=None):
    """Return ``{"status", "model_calls"}``. Status None means no attempt."""
    setattr(session, PENDING_ATTR, None)
    world = session.world_state
    npcs.bind_address(world, action_result, player_text)
    campaign_id = world.get("campaign_id")
    store = getattr(session, "emergence_store", None)
    if not isinstance(campaign_id, str) or store is None:
        return _result()
    if world.get("combat", {}).get("active"):
        return _result()
    calls = arbiter.calls_used()
    if calls is None:
        return _result()
    trigger = triggers.detect(
        world, action_result=action_result, player_text=player_text,
        location_changed=location_changed,
    )
    if trigger is None:
        return _result()
    lore_state = _lore_state(session)
    profile = profiles.resolve(world, trigger["location_id"])
    if propose is None and not profiles.generation_enabled(world):
        return _result()
    selection = triggers.select(
        world, campaign_id=campaign_id, trigger=trigger, profile=profile, lore_state=lore_state,
    )
    if selection is None:
        return _result()
    if arbiter.decide(calls_used=calls, narration_needed=True) != arbiter.PROPOSE:
        return _result("deferred")
    try:
        built = envelope_owner.build(
            world, campaign_id=campaign_id, trigger_id=selection.trigger_id,
            trigger_kind=trigger["kind"], location_id=trigger["location_id"],
            profile=profile, decisions=selection.decisions,
            faction_ids=profile.get("faction_ids", ()), lore_state=lore_state,
        )
    except envelope_owner.EnvelopeError:
        return _result()
    outcome = attempts.run(
        store, campaign_id=campaign_id, envelope=built, world=world,
        propose=propose or generator.propose, model_id=generator.MODEL_ID,
        player_text=player_text, lore_state=lore_state,
        audit=emergence_audit.ring_for(session),
    )
    if outcome.status != "ready":
        return _result(outcome.status, outcome.model_calls)
    row = outcome.row
    try:
        incident_id = commit.commit(world, built, outcome.gate_result.normalized, lore_state=lore_state)
    except commit.StaleCommit:
        store.update(campaign_id, row["trigger_id"], row["owner_token"], attempts.OPEN,
                     {"status": "stale", "rejection_reason": "canon_stamp"})
        return _result("stale", outcome.model_calls)
    except ValueError:
        store.update(campaign_id, row["trigger_id"], row["owner_token"], attempts.OPEN,
                     {"status": "rejected", "rejection_reason": "record",
                      "gate_outcome": outcome.gate_result.outcome})
        return _result("rejected", outcome.model_calls)
    pending = dict(outcome.pending_finish, incident_id=incident_id)
    if store.finish_accepted(pending) is None:
        setattr(session, PENDING_ATTR, pending)
    return _result("accepted", outcome.model_calls)


def take_pending(session):
    """Hand the accepted attempt to autosave once, if its incident is still canon."""
    pending = getattr(session, PENDING_ATTR, None)
    setattr(session, PENDING_ATTR, None)
    if not isinstance(pending, dict):
        return None
    if pending.get("incident_id") not in session.world_state.get("incidents", {}):
        return None
    return pending


def after_turn(session, before_world, action_result):
    world = session.world_state
    if not world.get("incidents"):
        return
    commit.advance(world, before_location=before_world.get("location"))
    awareness.reveal_from_check(world, action_result)
    promoted = npcs.apply_action(world, action_result, session=session)
    if isinstance(promoted, dict) and not isinstance(action_result.get("npc_id"), str):
        action_result["npc_id"] = promoted.get("id")
    props.apply_action(world, action_result, session=session)
    sublocations.apply_action(world, action_result)
    rewards.apply_action(world, action_result)
    npc_id = action_result.get("npc_id")
    delta = action_result.get("relationship_delta")
    if isinstance(npc_id, str) and type(delta) is int:
        import relationships
        reason = action_result.get("relationship_reason") or f"{record_reason(action_result)}:{npc_id}"
        relationships.note(world, npc_id, delta, reason)


def record_reason(action_result):
    return str(action_result.get("action") or "incident")
