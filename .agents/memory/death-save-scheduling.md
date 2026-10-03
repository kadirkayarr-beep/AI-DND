---
name: Death-save turn scheduling
description: Keep unconscious player initiative boundaries available for death saves and stable-state stopping.
---

An unconscious player must remain in the initiative order even when stable. Their scheduled slot is needed for an automatic death save or for the scheduler to stop at the stable boundary; this is separate from permission to take player actions.

**Why:** Skipping a stable player's slot advanced initiative through another enemy turn, so the scheduler could keep running and expose the player to another attack before returning control.

**How to apply:** When changing combat turn eligibility, distinguish a player action from a scheduler-only death-save or stable turn. Test the full path from an enemy turn through the unconscious player's next initiative slot.