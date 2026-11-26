"""One place that turns a campaign storage error into the HTTP error the player sees."""

from __future__ import annotations

from fastapi import HTTPException

from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignError,
    CampaignIdConflictError,
    CampaignNotActiveError,
    CampaignNotFoundError,
    CampaignStaleError,
    CampaignStorageError,
)

# First match wins. A message of None means the error's own text.
_CAMPAIGN_ERRORS = (
    (CampaignStaleError, 409, "campaign_stale", None),
    (
        CampaignIdConflictError,
        409,
        "campaign_id_conflict",
        "A campaign with this identifier already exists.",
    ),
    (CampaignNotFoundError, 404, "campaign_not_found", "Bu macera kaydı bulunamadı."),
    (
        CampaignCorruptError,
        409,
        "campaign_unavailable",
        "Bu macera kaydı güvenli biçimde yüklenemedi.",
    ),
    (
        CampaignNotActiveError,
        409,
        "campaign_not_active",
        "Bu macera için açık bir oturum bulunamadı.",
    ),
    (
        CampaignStorageError,
        503,
        "campaign_storage_unavailable",
        "Macera kaydı şu anda güvenli biçimde saklanamıyor.",
    ),
)


def campaign_http_exception(error: CampaignError) -> HTTPException:
    """Return the HTTP error for a campaign error; an unlisted one is a plain 500."""
    for kind, status, code, message in _CAMPAIGN_ERRORS:
        if isinstance(error, kind):
            text = str(error) if message is None else message
            detail = {"code": code, "message": text}
            return HTTPException(status_code=status, detail=detail)
    return HTTPException(
        status_code=500,
        detail={"code": "campaign_error", "message": "Macera işlemi tamamlanamadı."},
    )
