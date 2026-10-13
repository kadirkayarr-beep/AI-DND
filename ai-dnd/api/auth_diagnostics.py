"""Value-free, opt-in diagnostics for the isolated Clerk development API."""

from __future__ import annotations

from typing import Any


_SAFE_CATEGORIES = frozenset({
    "bearer_parse_rejected",
    "header_shape_rejected",
    "identity_header_rejected",
    "legacy_session_cookie_rejected",
    "authorization_header_missing",
    "authorization_header_multiple",
    "authorization_scheme_rejected",
    "bearer_format_rejected",
    "token_format_rejected",
    "token_header_rejected",
    "verifier_clock_rejected",
    "jwks_key_rejected",
    "signature_rejected",
    "issuer_rejected",
    "audience_rejected",
    "jwt_claims_rejected",
    "token_time_rejected",
    "authorized_party_rejected",
    "session_claim_rejected",
    "session_status_rejected",
    "subject_rejected",
    "verifier_internal_failure",
})


def enabled_for_request(flag: str | None, auth_mode: str | None, server: Any) -> bool:
    """Enable only for an explicitly opted-in Clerk request served on port 8017."""
    return (
        flag == "1"
        and auth_mode == "clerk"
        and isinstance(server, tuple)
        and len(server) > 1
        and server[1] == 8017
    )


def safe_failure_category(value: object) -> str:
    """Return a constant category only; never serialize exception details."""
    if type(value) is str and value in _SAFE_CATEGORIES:
        return value
    return "unclassified"
