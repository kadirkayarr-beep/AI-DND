"""Public helpers for restoring saved campaigns without changing the engine."""

from __future__ import annotations

from typing import Any

from api.persistence.campaign_models import StoredCampaign
from api.persistence.campaign_validation import restore_campaign_session


def restore_stored_campaign(
    session: Any,
    campaign: StoredCampaign,
) -> dict[str, Any]:
    journal = restore_campaign_session(session, campaign.payload)
    session._campaign_persistence_version = (
        campaign.metadata["campaign_id"], campaign.metadata["revision"]
    )
    return journal