"""Python-authored, non-economic local shop creation through existing owners."""

import living_world


def resolve_explicit_request(session):
    """Called only after the engine's explicit-request and capacity gates."""
    world = session.world_state
    location = world.get("location")
    proposal = {
        "name": "Yerel Dükkân",
        "description": "Küçük, sade bir yerel dükkân.",
        "shopkeeper": {
            "name": living_world.stable_local_name(world, location, "Shopkeeper"),
            "personality": "Sakin ve dikkatli.",
            "appearance": "Sade giysili bir dükkâncı.",
        },
    }
    created = session.create_shop_from_proposal(proposal)
    if not created:
        return {
            "action": "shop_setup", "status": "proposal_rejected",
            "success": False, "state_changes": [],
            "direct_response": "Burada yeni bir dükkân ve dükkâncı oluşturulamıyor.",
        }
    return {
        "action": "shop_setup", "status": "created", "success": True,
        "shop_id": created["shop"]["id"],
        "shopkeeper_id": created["shopkeeper"]["id"],
        "state_changes": ["world.shops", "world.npcs"],
        "direct_response": "Burada küçük bir yerel dükkân var; başında bir dükkâncı duruyor.",
    }
