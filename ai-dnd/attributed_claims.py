"""Attributed claim presentation (W03; design Rev2 section 5.5).

An NPC's words stay the NPC's words. This module never rewrites `speaker_text`; it only decides whether a SEPARATE narrator
note may recall a state the player already knows. A fact the player does not know (a lock behind the scenes) is not revealed
under the label "correction", and nothing here creates a new NPC line or a player action.
"""
from __future__ import annotations


def present_claim(claim: dict, knowledge: dict) -> dict:
    """`claim`: {speaker_text, source_event_id, subject: {name, locked}}; `knowledge`: {lock_known_to_player: bool}."""
    if not isinstance(claim, dict) or not isinstance(claim.get("speaker_text"), str):
        raise ValueError("A claim needs the speaker's own text.")
    subject = claim.get("subject") if isinstance(claim.get("subject"), dict) else {}
    note = None
    if subject.get("locked") is True and isinstance(knowledge, dict) and knowledge.get("lock_known_to_player") is True:
        name = str(subject.get("name") or "Orası")
        note = f"{name} kapısının kilitli olduğunu zaten biliyorsun."
    return {"speaker_text": claim["speaker_text"], "narrator_note": note,
            "narrator_note_speaker": "narrator" if note else None, "source_event_id": claim.get("source_event_id")}
