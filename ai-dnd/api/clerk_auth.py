"""Fail-closed Clerk session-token verifier.

Static keys are injected by the caller. JWKS retrieval, caching, and rotation
live in ``api.clerk_jwks``. FastAPI uses ``ClerkAuthenticator`` only when
``AI_DND_AUTH_MODE=clerk`` or a test passes that object into ``create_app``.
The verifier never derives an issuer, a key URL, or a policy from the token.
Logout does not revoke a bearer token; see ``CLERK_LOGOUT_REVOCATION``.

PyJWT 2.15.1 checks ``iss`` only when ``decode(..., issuer=...)`` receives a
value. ``verify_iss=True`` with ``issuer=None`` returns without reading the
claim. This verifier always passes the configured issuer string, which PyJWT
compares with exact equality.

Clerk's current ``verifyJwt`` does not check ``iss``. Ownership here is the
configured issuer plus ``sub``, so a mismatched issuer is rejected.

Clerk's session-token reference says ``azp`` can be omitted when the browser
Origin is empty or null. Those sessions are rejected on purpose. The
authorized-party allowlist is mandatory, and a missing or unapproved ``azp``
is authentication failure.

Session tokens are also required to carry ``typ=JWT``, a ``kid`` for an
injected key, ``sid``, ``nbf``, and ``iat``. Clerk documents those header
fields and default claims. Unknown headers, including Clerk's ``oiat``, are
ignored. ``aud`` is not required unless an audience was configured. ``exp``
may be at most 24 hours after ``iat``; Clerk's default session token lasts
60 seconds, so a longer dashboard lifetime above that cap fails closed.

Clerk's default session claims include ``sts``. A missing ``sts`` stays
acceptable so older tokens still verify. ``sts=active`` is accepted.
``sts=pending`` means the session still has required tasks, so it is rejected.
Any other explicit status is rejected too. Issuer, signature, subject,
authorized party, audience, expiry, and clock rules are unchanged.

Clock comparisons follow PyJWT 2.15.1 (``exp <= now - leeway``,
``nbf > now + leeway``, ``iat > now + leeway``) against the supplied ``now``.
``PyJWT.decode`` itself always reads the wall clock, so those three checks
are applied after the signature and issuer checks.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Mapping
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt.exceptions import InvalidSignatureError, InvalidTokenError

from api.auth import AuthenticationError, Principal
from api.clerk_jwks import ClerkJwksCache, PinnedHttpsJwksTransport, jwks_url_for


CLERK_HTTP_INTEGRATION = "BLOCKED: Clerk bearer mode is wired and is not a production release"
CLERK_LOGOUT_REVOCATION = (
    "BLOCKED: logout clears only the legacy OIDC cookie. "
    "A verified Clerk bearer token remains valid until exp. "
    "This server does not revoke the Clerk session."
)
ALLOWED_ALGORITHM = "RS256"
DEFAULT_CLOCK_SKEW_SECONDS = 5
MAX_CLOCK_SKEW_SECONDS = 60
MAX_TOKEN_LIFETIME_SECONDS = 24 * 60 * 60
_MAX_TOKEN_CHARACTERS = 8192
_FORBIDDEN_HEADER_FIELDS = frozenset({"jku", "jwk", "x5u", "x5c", "crit"})
_NETWORK_CONFIG_FIELDS = frozenset({"jwks_url", "jwks", "secret_key", "api_url", "issuers"})


class ClerkSessionVerifier:
    """Verify one RS256 Clerk session token into an ``(issuer, subject)`` principal."""

    def __init__(
        self,
        *,
        issuer: str,
        authorized_parties: tuple[str, ...] | list[str],
        public_keys: Mapping[str, str] | None = None,
        jwks: ClerkJwksCache | None = None,
        environment: str | None = None,
        audience: str | None = None,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ) -> None:
        self._issuer = _require_https_issuer(issuer)
        self._authorized_parties = _require_parties(authorized_parties)
        self._keys = _require_key_source(
            self._issuer,
            public_keys=public_keys,
            jwks=jwks,
            environment=environment,
        )
        self._audience = _require_audience(audience)
        self._clock_skew_seconds = _require_skew(clock_skew_seconds)

    @classmethod
    def from_mapping(cls, config: Mapping[str, object]) -> ClerkSessionVerifier:
        """Build a verifier from an explicit mapping. Incomplete config fails closed."""
        if any(name in config for name in _NETWORK_CONFIG_FIELDS):
            raise AuthenticationError("Clerk verifier is not configured.")
        try:
            issuer = config["issuer"]
            parties = config["authorized_parties"]
            keys = config["public_keys"]
        except KeyError:
            raise AuthenticationError("Clerk verifier is not configured.") from None
        if type(parties) not in (tuple, list) or type(keys) is not dict:
            raise AuthenticationError("Clerk verifier is not configured.")
        audience = config.get("audience")
        skew = config.get("clock_skew_seconds", DEFAULT_CLOCK_SKEW_SECONDS)
        if audience is not None and type(audience) is not str:
            raise AuthenticationError("Clerk verifier is not configured.")
        if type(skew) is not int:
            raise AuthenticationError("Clerk verifier is not configured.")
        return cls(
            issuer=issuer if type(issuer) is str else "",
            authorized_parties=parties,
            public_keys=keys,
            audience=audience,
            clock_skew_seconds=skew,
        )

    def verify(self, token: str, *, now: float | None = None) -> Principal:
        """Return the verified principal. Every failure is authentication failure."""
        if type(token) is not str or token == "" or len(token) > _MAX_TOKEN_CHARACTERS:
            raise AuthenticationError("Authentication failed.")
        header = _untrusted_header(token)
        current = time.time() if now is None else now
        if type(current) is not int and type(current) is not float:
            raise AuthenticationError("Authentication failed.")
        if current != current or current in (float("inf"), float("-inf")):
            raise AuthenticationError("Authentication failed.")
        key = self._keys.key_for(header["kid"], now=float(current))
        options = {
            "verify_signature": True,
            "verify_exp": False,
            "verify_nbf": False,
            "verify_iat": False,
            "verify_aud": True,
            "verify_iss": True,
            "strict_aud": self._audience is not None,
            "require": ["iss", "sub", "exp", "iat", "nbf", "azp", "sid"],
        }
        try:
            if self._audience is None:
                claims = jwt.decode(
                    token,
                    key,
                    algorithms=[ALLOWED_ALGORITHM],
                    issuer=self._issuer,
                    options=options,
                )
            else:
                claims = jwt.decode(
                    token,
                    key,
                    algorithms=[ALLOWED_ALGORITHM],
                    issuer=self._issuer,
                    audience=self._audience,
                    options=options,
                )
        except InvalidSignatureError:
            raise AuthenticationError("Authentication failed.") from None
        except InvalidTokenError:
            raise AuthenticationError("Authentication failed.") from None
        if type(claims) is not dict:
            raise AuthenticationError("Authentication failed.")
        _require_session_claims(
            claims,
            issuer=self._issuer,
            authorized_parties=self._authorized_parties,
            audience=self._audience,
            now=float(current),
            clock_skew_seconds=self._clock_skew_seconds,
        )
        try:
            return Principal(self._issuer, claims["sub"])
        except (AuthenticationError, ValueError):
            raise AuthenticationError("Authentication failed.") from None


def _untrusted_header(token: str) -> dict[str, str]:
    parts = token.split(".")
    if len(parts) != 3 or any(part == "" for part in parts):
        raise AuthenticationError("Authentication failed.")
    try:
        header = json.loads(_b64url_decode(parts[0]))
    except (ValueError, json.JSONDecodeError):
        raise AuthenticationError("Authentication failed.") from None
    if type(header) is not dict:
        raise AuthenticationError("Authentication failed.")
    if any(name in header for name in _FORBIDDEN_HEADER_FIELDS):
        raise AuthenticationError("Authentication failed.")
    if header.get("alg") != ALLOWED_ALGORITHM or header.get("typ") != "JWT":
        raise AuthenticationError("Authentication failed.")
    kid = header.get("kid")
    if type(kid) is not str or kid == "" or kid.strip() != kid:
        raise AuthenticationError("Authentication failed.")
    return {"alg": ALLOWED_ALGORITHM, "typ": "JWT", "kid": kid}


def _require_session_claims(
    claims: dict[str, object],
    *,
    issuer: str,
    authorized_parties: tuple[str, ...],
    audience: str | None,
    now: float,
    clock_skew_seconds: int,
) -> None:
    if claims.get("iss") != issuer:
        raise AuthenticationError("Authentication failed.")
    for name in ("exp", "iat", "nbf"):
        if type(claims.get(name)) is not int:
            raise AuthenticationError("Authentication failed.")
    exp = claims["exp"]
    iat = claims["iat"]
    nbf = claims["nbf"]
    if type(exp) is not int or type(iat) is not int or type(nbf) is not int:
        raise AuthenticationError("Authentication failed.")
    if iat > exp or nbf > exp or exp - iat > MAX_TOKEN_LIFETIME_SECONDS:
        raise AuthenticationError("Authentication failed.")
    if exp <= (now - clock_skew_seconds):
        raise AuthenticationError("Authentication failed.")
    if nbf > (now + clock_skew_seconds) or iat > (now + clock_skew_seconds):
        raise AuthenticationError("Authentication failed.")
    azp = claims.get("azp")
    if type(azp) is not str or azp not in authorized_parties:
        raise AuthenticationError("Authentication failed.")
    sid = claims.get("sid")
    if type(sid) is not str or sid == "" or sid.strip() != sid or len(sid) > 512:
        raise AuthenticationError("Authentication failed.")
    _require_session_status(claims)
    if audience is None:
        if "aud" in claims and claims.get("aud") not in (None, ""):
            raise AuthenticationError("Authentication failed.")
        return
    if claims.get("aud") != audience:
        raise AuthenticationError("Authentication failed.")


def _require_session_status(claims: dict[str, object]) -> None:
    if "sts" not in claims:
        return
    if claims.get("sts") != "active":
        raise AuthenticationError("Authentication failed.")


class _StaticKeySource:
    """Stage 1 path. A missing kid fails without contacting a network."""

    def __init__(self, public_keys: dict[str, RSAPublicKey]) -> None:
        self._keys = public_keys

    def key_for(self, kid: str, *, now: float) -> RSAPublicKey:
        key = self._keys.get(kid)
        if key is None:
            raise AuthenticationError("Authentication failed.")
        return key


def _require_key_source(
    issuer: str,
    *,
    public_keys: Mapping[str, str] | None,
    jwks: ClerkJwksCache | None,
    environment: str | None,
) -> _StaticKeySource | ClerkJwksCache:
    if (public_keys is None) == (jwks is None):
        raise AuthenticationError("Clerk verifier is not configured.")
    if jwks is None:
        if environment is not None:
            raise AuthenticationError("Clerk verifier is not configured.")
        return _StaticKeySource(_require_keys(public_keys or {}))
    if not isinstance(jwks, ClerkJwksCache) or jwks.issuer != issuer or jwks.environment != environment:
        raise AuthenticationError("Clerk verifier is not configured.")
    return jwks


def _require_https_issuer(issuer: object) -> str:
    if type(issuer) is not str or issuer == "" or issuer.strip() != issuer:
        raise AuthenticationError("Clerk verifier is not configured.")
    if len(issuer) > 512 or any(ord(character) < 32 or ord(character) == 127 for character in issuer):
        raise AuthenticationError("Clerk verifier is not configured.")
    parts = urlsplit(issuer)
    if (
        parts.scheme != "https"
        or parts.hostname in (None, "")
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("",)
        or parts.query != ""
        or parts.fragment != ""
    ):
        raise AuthenticationError("Clerk verifier is not configured.")
    return issuer


def _require_parties(parties: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if type(parties) not in (tuple, list) or len(parties) == 0:
        raise AuthenticationError("Clerk verifier is not configured.")
    normalized: list[str] = []
    for party in parties:
        if type(party) is not str or party == "" or party.strip() != party or len(party) > 512:
            raise AuthenticationError("Clerk verifier is not configured.")
        if any(ord(character) < 32 or ord(character) == 127 for character in party):
            raise AuthenticationError("Clerk verifier is not configured.")
        parts = urlsplit(party)
        if (
            parts.scheme not in ("https", "http")
            or parts.hostname in (None, "")
            or parts.username is not None
            or parts.password is not None
            or parts.path not in ("",)
            or parts.query != ""
            or parts.fragment != ""
        ):
            raise AuthenticationError("Clerk verifier is not configured.")
        normalized.append(party)
    if len(set(normalized)) != len(normalized):
        raise AuthenticationError("Clerk verifier is not configured.")
    return tuple(normalized)


def _require_keys(public_keys: Mapping[str, str]) -> dict[str, RSAPublicKey]:
    if type(public_keys) is not dict or len(public_keys) == 0:
        raise AuthenticationError("Clerk verifier is not configured.")
    loaded: dict[str, RSAPublicKey] = {}
    for kid, pem in public_keys.items():
        if type(kid) is not str or kid == "" or kid.strip() != kid or len(kid) > 256:
            raise AuthenticationError("Clerk verifier is not configured.")
        if type(pem) is not str or pem.strip() == "":
            raise AuthenticationError("Clerk verifier is not configured.")
        try:
            key = load_pem_public_key(pem.encode("utf-8"))
        except (ValueError, TypeError):
            raise AuthenticationError("Clerk verifier is not configured.") from None
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise AuthenticationError("Clerk verifier is not configured.")
        loaded[kid] = key
    return loaded


def _require_audience(audience: str | None) -> str | None:
    if audience is None:
        return None
    if type(audience) is not str or audience == "" or audience.strip() != audience or len(audience) > 512:
        raise AuthenticationError("Clerk verifier is not configured.")
    if any(ord(character) < 32 or ord(character) == 127 for character in audience):
        raise AuthenticationError("Clerk verifier is not configured.")
    return audience


def _require_skew(clock_skew_seconds: object) -> int:
    if type(clock_skew_seconds) is not int:
        raise AuthenticationError("Clerk verifier is not configured.")
    if clock_skew_seconds < 0 or clock_skew_seconds > MAX_CLOCK_SKEW_SECONDS:
        raise AuthenticationError("Clerk verifier is not configured.")
    return clock_skew_seconds


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


_SESSION_COOKIE_NAME = "ai_dnd_session"
_IDENTITY_HEADERS = frozenset({b"x-replit-user-id"})
_BEARER_PREFIX = "Bearer "
_FORBIDDEN_CLERK_ENV = frozenset({
    "AI_DND_CLERK_SECRET_KEY",
    "AI_DND_CLERK_SECRET",
})


class ClerkAuthenticator:
    """Bearer-only Clerk session check for one configured issuer.

    Verification runs in a worker thread so JWKS I/O does not hold the ASGI
    event loop. The cache still permits one in-flight refresh, a finite TTL,
    and connect/read timeouts. Tokens longer than 8192 characters are rejected
    before signature checks. This object never reads ``bound_principal``,
    cookies, or client user ids as identity.

    Production cache bounds, unless operator settings replace them, are a
    300-second key lifetime, a 60-second refresh interval, 2-second connect
    and read timeouts, 32768 response bytes, and at most 8 keys.
    """

    def __init__(self, verifier: ClerkSessionVerifier) -> None:
        if type(verifier) is not ClerkSessionVerifier:
            raise AuthenticationError("Clerk verifier is not configured.")
        self._verifier = verifier

    @property
    def issuer(self) -> str:
        return self._verifier._issuer

    @property
    def environment(self) -> str:
        return self._verifier._keys.environment if isinstance(self._verifier._keys, ClerkJwksCache) else ""

    def authenticate(self) -> Principal:
        """No request is available. A missing bearer token is not a player."""
        raise AuthenticationError("Authentication failed.")

    def authenticate_asgi(
        self,
        headers: tuple[tuple[bytes, bytes], ...] | list[tuple[bytes, bytes]],
        cookies: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
    ) -> Principal:
        """Return the principal for one bearer token. Failures stay anonymous."""
        try:
            token = _bearer_token(headers, cookies)
            return self._verifier.verify(token)
        except AuthenticationError:
            raise
        except Exception:
            raise AuthenticationError("Authentication failed.") from None


def clerk_authenticator_from_environ(environ: Mapping[str, str]) -> ClerkAuthenticator:
    """Build a Clerk authenticator from server settings. Secrets are rejected."""
    if any(name in environ for name in _FORBIDDEN_CLERK_ENV):
        raise AuthenticationError("Clerk verifier is not configured.")
    try:
        issuer = environ["AI_DND_CLERK_ISSUER"]
        parties_text = environ["AI_DND_CLERK_AUTHORIZED_PARTIES"]
        environment = environ["AI_DND_CLERK_ENVIRONMENT"]
    except KeyError:
        raise AuthenticationError("Clerk verifier is not configured.") from None
    if type(issuer) is not str or type(parties_text) is not str or type(environment) is not str:
        raise AuthenticationError("Clerk verifier is not configured.")
    configured_url = environ.get("AI_DND_CLERK_JWKS_URL")
    if configured_url is not None and configured_url != jwks_url_for(issuer):
        raise AuthenticationError("Clerk verifier is not configured.")
    audience = environ.get("AI_DND_CLERK_AUDIENCE")
    if audience is not None and (type(audience) is not str or audience == ""):
        raise AuthenticationError("Clerk verifier is not configured.")
    cache_arguments: dict[str, object] = {
        "issuer": issuer,
        "environment": environment,
        "transport": PinnedHttpsJwksTransport(),
    }
    ttl = _optional_digits(environ, "AI_DND_CLERK_CACHE_TTL_SECONDS")
    interval = _optional_digits(environ, "AI_DND_CLERK_REFRESH_INTERVAL_SECONDS")
    if ttl is not None:
        cache_arguments["cache_ttl_seconds"] = ttl
    if interval is not None:
        cache_arguments["refresh_interval_seconds"] = interval
    verifier_arguments: dict[str, object] = {
        "issuer": issuer,
        "authorized_parties": _split_parties(parties_text),
        "jwks": ClerkJwksCache(**cache_arguments),  # type: ignore[arg-type]
        "environment": environment,
    }
    if audience is not None:
        verifier_arguments["audience"] = audience
    skew = _optional_digits(environ, "AI_DND_CLERK_CLOCK_SKEW_SECONDS")
    if skew is not None:
        verifier_arguments["clock_skew_seconds"] = skew
    return ClerkAuthenticator(ClerkSessionVerifier(**verifier_arguments))  # type: ignore[arg-type]


def _split_parties(value: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in value.split(","))
    if len(parts) == 0 or any(part == "" for part in parts):
        raise AuthenticationError("Clerk verifier is not configured.")
    return parts


def _optional_digits(environ: Mapping[str, str], name: str) -> int | None:
    if name not in environ:
        return None
    value = environ[name]
    if type(value) is not str or value == "" or not value.isdigit():
        raise AuthenticationError("Clerk verifier is not configured.")
    return int(value)


def _bearer_token(
    headers: tuple[tuple[bytes, bytes], ...] | list[tuple[bytes, bytes]],
    cookies: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> str:
    if type(headers) not in (tuple, list) or type(cookies) not in (tuple, list):
        raise AuthenticationError("Authentication failed.")
    authorizations: list[bytes] = []
    for item in headers:
        if type(item) is not tuple or len(item) != 2:
            raise AuthenticationError("Authentication failed.")
        name, value = item
        if type(name) is not bytes or type(value) is not bytes:
            raise AuthenticationError("Authentication failed.")
        lowered = name.lower()
        if lowered == b"authorization":
            authorizations.append(value)
        elif lowered in _IDENTITY_HEADERS:
            raise AuthenticationError("Authentication failed.")
        elif lowered == b"cookie" and _cookie_names_session(value):
            raise AuthenticationError("Authentication failed.")
    for item in cookies:
        if type(item) is not tuple or len(item) != 2 or type(item[0]) is not str:
            raise AuthenticationError("Authentication failed.")
        if item[0].lower() == _SESSION_COOKIE_NAME:
            raise AuthenticationError("Authentication failed.")
    if len(authorizations) != 1:
        raise AuthenticationError("Authentication failed.")
    raw = authorizations[0]
    if len(raw) > len(_BEARER_PREFIX) + _MAX_TOKEN_CHARACTERS:
        raise AuthenticationError("Authentication failed.")
    try:
        text = raw.decode("ascii")
    except UnicodeError:
        raise AuthenticationError("Authentication failed.") from None
    if not text.startswith(_BEARER_PREFIX) or " " in text[len(_BEARER_PREFIX):]:
        raise AuthenticationError("Authentication failed.")
    token = text[len(_BEARER_PREFIX):]
    if token == "" or len(token) > _MAX_TOKEN_CHARACTERS:
        raise AuthenticationError("Authentication failed.")
    if any(ord(character) < 33 or ord(character) == 127 for character in token):
        raise AuthenticationError("Authentication failed.")
    return token


def _cookie_names_session(value: bytes) -> bool:
    for part in value.split(b";"):
        piece = part.strip()
        if b"=" not in piece:
            continue
        name = piece.split(b"=", 1)[0].strip().lower()
        if name == _SESSION_COOKIE_NAME.encode("ascii"):
            return True
    return False
