"""Public helpers for restoring saved campaigns without changing the engine."""

from __future__ import annotations

from typing import Any

from api.persistence.campaign_models import StoredCampaign
from api.persistence.campaign_validation import restore_campaign_session


def restore_stored_campaign(session: Any, campaign: StoredCampaign) -> None:
    restore_campaign_session(session, campaign.payload)