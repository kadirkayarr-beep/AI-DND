---
name: Journal NPC reference boundary
description: Native producers must make an event-bound NPC discoverable in the same canonical turn.
---

Any native producer emitting a player-known, NPC-bound interaction event must
also expose the correct NPC identity to the journal's canonical encounter
projection in that turn. Item IDs and operation names are not NPC identities.

**Why:** An engine-only native transfer can succeed while the full API autosave
fails closed: the journal refuses events referencing NPCs the player has not
canonically encountered. Unit-only producer tests cannot establish HTTP readiness.

**How to apply:** Exercise the existing complete turn and journal/receipt/save
path for new native interaction producers. Preserve journal validation rather
than allowing unknown NPC references to make a feature appear to work.
