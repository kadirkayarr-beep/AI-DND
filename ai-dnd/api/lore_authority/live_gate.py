"""Live model verification stays closed unless a later owner authorizes it."""

from __future__ import annotations

import os


def live_verification_status() -> str:
    if os.environ.get("AI_DND_PHASE8_LIVE_AUTHORIZED") == "1":
        return "AUTHORIZED"
    return "NOT_RUN"
