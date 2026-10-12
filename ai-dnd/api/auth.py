"""Server-verified player identity.

The OIDC verifier below is a fail-closed skeleton. It does not complete Replit
login. Production status stays blocked until that issuer, audience, client, and
callback are verified outside this process.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


OIDC_PRODUCTION_STATUS = "BLOCKED: Replit verification required"
SESSION_COOKIE = "ai_dnd_session"
REQUEST_MARKER = "X-AI-DND-Request"
_OIDC_ENV = (
    "AI_DND_OIDC_ISSUER",
    "AI_DND_OIDC_AUDIENCE",
    "AI_DND_OIDC_CLIENT_ID",
    "AI_DND_OIDC_CLIENT_SECRET",
    "AI_DND_OIDC_JWKS",
)


class AuthenticationError(Exception):
    """No server-verified principal is available."""


@dataclass(frozen=True)
class Principal:
    """Identity pair verified by server-side code, not by the client."""

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        _require_identity_part(self.issuer, "issuer")
        _require_identity_part(self.subject, "subject")


class Authenticator(Protocol):
    """Future OIDC verification plugs in here. It must not read the request."""

    def authenticate(self) -> Principal:
        """Return a principal this server has already verified."""


class FailClosedAuthenticator:
    """Default authenticator. Configuration without a verifier stays closed."""

    def authenticate(self) -> Principal:
        raise AuthenticationError("No server authenticator is configured.")


class FixedAuthenticator:
    """Return one principal the server already chose. The request is ignored.

    This is not OIDC and contains no production user. Tests supply the principal.
    """

    def __init__(self, principal: Principal):
        if type(principal) is not Principal:
            raise AuthenticationError("Authenticator did not return a verified principal.")
        self._principal = principal

    def authenticate(self) -> Principal:
        return self._principal


@dataclass(frozen=True)
class OidcSettings:
    """Server configuration. None of these values are a player id."""

    issuer: str
    audience: str
    client_id: str
    client_secret: str
    jwks: dict[str, Any]


class OidcAuthenticator:
    """Verify a server-presented token. Client identity headers are not read."""

    def __init__(self, settings: OidcSettings):
        if type(settings) is not OidcSettings:
            raise AuthenticationError("OIDC verifier is not configured.")
        self._settings = settings

    def authenticate(self, token: str | None = None, *, now: float | None = None) -> Principal:
        if type(token) is not str or token == "":
            raise AuthenticationError("Authentication failed.")
        return verify_oidc_token(token, self._settings, now=now)


def oidc_settings_from_environ(environ: Mapping[str, str] | None = None) -> OidcSettings | None:
    """Return settings only when issuer, audience, client, secret, and JWKS exist."""
    source = os.environ if environ is None else environ
    values = [source.get(name, "") for name in _OIDC_ENV]
    if any(type(value) is not str or value.strip() == "" for value in values):
        return None
    issuer, audience, client_id, client_secret, jwks_text = values
    try:
        jwks = json.loads(jwks_text)
    except json.JSONDecodeError:
        return None
    if type(jwks) is not dict or type(jwks.get("keys")) is not list or not jwks["keys"]:
        return None
    return OidcSettings(issuer, audience, client_id, client_secret, jwks)


def loopback_allowed(environ: Mapping[str, str] | None = None, listen_host: str | None = None) -> bool:
    """Loopback stays closed.

    The listen address is not visible to the authenticator. An environment
    string of 127.0.0.1 can disagree with a public bind, so this mode does
    not install a fixed player.
    """
    del environ, listen_host
    return False


def select_authenticator(
    environ: Mapping[str, str] | None = None,
    listen_host: str | None = None,
) -> FailClosedAuthenticator | FixedAuthenticator | OidcAuthenticator:
    """Choose the server verifier. Incomplete OIDC and loopback stay closed.

    ``AI_DND_AUTH_MODE=clerk`` uses the Clerk bearer verifier or fails closed.
    It never installs ``FixedAuthenticator``. An unknown mode fails closed
    instead of falling through to OIDC. ``FixedAuthenticator`` remains an
    explicit test injection at ``create_app``.
    """
    source = os.environ if environ is None else environ
    del listen_host
    mode = source.get("AI_DND_AUTH_MODE")
    if mode == "loopback":
        return FailClosedAuthenticator()
    if mode == "clerk":
        from api.clerk_auth import clerk_authenticator_from_environ

        try:
            return clerk_authenticator_from_environ(source)
        except AuthenticationError:
            return FailClosedAuthenticator()
    if mode not in (None, "", "oidc"):
        return FailClosedAuthenticator()
    settings = oidc_settings_from_environ(source)
    if settings is None:
        return FailClosedAuthenticator()
    return OidcAuthenticator(settings)


def verify_oidc_token(
    token: str,
    settings: OidcSettings,
    *,
    now: float | None = None,
) -> Principal:
    """Check signature, issuer, audience, and expiry. Unknown algorithms fail closed."""
    parts = token.split(".")
    if len(parts) != 3 or any(part == "" for part in parts):
        raise AuthenticationError("Authentication failed.")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError):
        raise AuthenticationError("Authentication failed.") from None
    if type(header) is not dict or type(payload) is not dict:
        raise AuthenticationError("Authentication failed.")
    if header.get("alg") != "HS256":
        raise AuthenticationError("Authentication failed.")
    secret = _hmac_secret(settings.jwks, header.get("kid"))
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    try:
        presented = _b64url_decode(parts[2])
    except ValueError:
        raise AuthenticationError("Authentication failed.") from None
    if not hmac.compare_digest(expected, presented):
        raise AuthenticationError("Authentication failed.")
    if payload.get("iss") != settings.issuer:
        raise AuthenticationError("Authentication failed.")
    audience = payload.get("aud")
    audiences = audience if type(audience) is list else [audience]
    if settings.audience not in audiences:
        raise AuthenticationError("Authentication failed.")
    expiry = payload.get("exp")
    current = time.time() if now is None else now
    if type(expiry) is not int or expiry <= current:
        raise AuthenticationError("Authentication failed.")
    subject = payload.get("sub")
    try:
        return Principal(settings.issuer, subject)
    except (AuthenticationError, ValueError):
        raise AuthenticationError("Authentication failed.") from None


def session_cookie_parameters(secure: bool) -> dict[str, Any]:
    """HttpOnly session cookie. Secure follows HTTPS; SameSite stays Lax."""
    return {
        "key": SESSION_COOKIE,
        "httponly": True,
        "secure": bool(secure),
        "samesite": "lax",
        "path": "/",
    }


def request_marker_present(headers: Mapping[str, str]) -> bool:
    """Non-secret request marker. It is not an identity or an API key."""
    for name, value in headers.items():
        if name.lower() == REQUEST_MARKER.lower():
            return value == "1"
    return False


def clear_session_cookie(response: Any, *, secure: bool) -> None:
    """Remove the session cookie without writing a player id."""
    response.delete_cookie(**session_cookie_parameters(secure))


_CURRENT_PRINCIPAL: ContextVar[Principal | None] = ContextVar(
    "ai_dnd_principal",
    default=None,
)


def bind_principal(principal: Principal) -> Token[Principal | None]:
    """Bind a verified principal to this request context. It is not process-global."""
    if type(principal) is not Principal:
        raise AuthenticationError("Authenticator did not return a verified principal.")
    return _CURRENT_PRINCIPAL.set(principal)


def reset_principal(token: Token[Principal | None]) -> None:
    _CURRENT_PRINCIPAL.reset(token)


def current_principal() -> Principal | None:
    return _CURRENT_PRINCIPAL.get()


def authenticate(
    authenticator: Authenticator | FailClosedAuthenticator | FixedAuthenticator | OidcAuthenticator | None,
    untrusted: Any = None,
) -> Principal:
    """Resolve a principal from the server authenticator only.

    `untrusted` exists so an HTTP request can be passed through without
    becoming a source of identity. Headers and body fields are ignored.
    """
    del untrusted
    if authenticator is None or type(authenticator) is OidcAuthenticator:
        raise AuthenticationError("No server authenticator is configured.")
    try:
        principal = authenticator.authenticate()
    except AuthenticationError:
        raise
    except Exception:
        raise AuthenticationError("Authentication failed.") from None
    if type(principal) is not Principal:
        raise AuthenticationError("Authenticator did not return a verified principal.")
    return principal


def _hmac_secret(jwks: dict[str, Any], kid: object) -> bytes:
    if type(kid) is not str or kid == "":
        raise AuthenticationError("Authentication failed.")
    for key in jwks.get("keys", []):
        if type(key) is not dict or key.get("kid") != kid:
            continue
        if key.get("kty") != "oct" or key.get("alg") not in (None, "HS256"):
            raise AuthenticationError("Authentication failed.")
        encoded = key.get("k")
        if type(encoded) is not str or encoded == "":
            raise AuthenticationError("Authentication failed.")
        try:
            secret = _b64url_decode(encoded)
        except ValueError:
            raise AuthenticationError("Authentication failed.") from None
        if secret == b"":
            raise AuthenticationError("Authentication failed.")
        return secret
    raise AuthenticationError("Authentication failed.")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception:
        raise ValueError("Invalid base64url value.") from None


def _require_identity_part(value: object, field: str) -> None:
    if type(value) is not str or value == "" or value.strip() != value:
        raise ValueError(f"Principal {field} is invalid.")
    if len(value) > 512 or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"Principal {field} is invalid.")
