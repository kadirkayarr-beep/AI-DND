"""Bounded Clerk JWKS cache. Not connected to FastAPI routes.

The issuer is server configuration. The only fetch URL is that issuer's
origin plus ``/.well-known/jwks.json``. Token headers, including ``jku``,
``jwk``, and ``x5u``, are never a key location. Development and production
each need their own cache; this module does not accept a client-selected
issuer or a list of issuers.

Cache and outage behavior:

- A successful document is trusted only until ``cache_ttl_seconds``. After
  that instant the old keys are not used.
- While the cache is inside its lifetime, a provider outage does not cause a
  fetch. Verification keeps using the keys already bound to this issuer and
  environment.
- When the lifetime has ended, one refresh is attempted. If it fails, the
  expired keys are dropped and authentication fails. The next attempt waits
  until ``refresh_interval_seconds``. No anonymous principal is created.
- An unknown ``kid`` during a fresh cache triggers at most one refresh per
  refresh interval, and each lookup performs at most one HTTP request. There
  is no retry loop.
- A bad rotation response does not delete keys that are still inside their
  lifetime. A bad response after expiry does not revive them.
- An invalid signature does not refresh. The caller must not call ``key_for``
  again for that failure.
- Concurrent lookups share one in-flight refresh.

``refresh_interval_seconds`` must be less than or equal to the cache lifetime,
so an expired cache is allowed to refresh instead of staying dark until a
longer backoff ends.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, RSAPublicNumbers

from api.auth import AuthenticationError


JWKS_PATH = "/.well-known/jwks.json"
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_REFRESH_INTERVAL_SECONDS = 60
DEFAULT_CONNECT_TIMEOUT_SECONDS = 2.0
DEFAULT_READ_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_RESPONSE_BYTES = 32_768
DEFAULT_MAX_KEYS = 8
MAX_CACHE_TTL_SECONDS = 3600
MAX_RESPONSE_BYTES = 65_536
MAX_KEYS = 8
_MAX_RSA_BITS = 4096
_HEADER_LIMIT = 8192
_ENVIRONMENTS = frozenset({"development", "production"})
_JWK_FIELDS = frozenset({"kty", "kid", "use", "key_ops", "alg", "n", "e"})
_BLOCKED_SUFFIXES = (".local", ".localhost", ".localdomain", ".internal", ".arpa")
_HOST_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_MAPPING_FORBIDDEN = frozenset({
    "secret_key",
    "api_url",
    "issuers",
    "public_keys",
    "jku",
    "jwk",
    "x5u",
    "x5c",
})


class JwksTransportError(Exception):
    """The injected transport could not complete one JWKS read."""


@dataclass(frozen=True)
class JwksRequest:
    """One pinned HTTPS GET. The URL is derived by the cache, not by a token."""

    url: str
    hostname: str
    pinned_ip: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_bytes: int


@dataclass(frozen=True)
class JwksResponse:
    """A single response. A redirect location is recorded and never requested."""

    status_code: int
    body: bytes
    location: str | None = None


class JwksTransport(Protocol):
    """Fetch the cache's exact URL. Implementations must not follow redirects."""

    def fetch(self, request: JwksRequest) -> JwksResponse:
        """Return one response or raise ``JwksTransportError``."""


class ClerkJwksCache:
    """RSA signing keys for one Clerk issuer and one environment."""

    def __init__(
        self,
        *,
        issuer: str,
        environment: str,
        transport: JwksTransport,
        resolver: Callable[[str], tuple[str, ...]] | None = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_keys: int = DEFAULT_MAX_KEYS,
    ) -> None:
        self._issuer = _require_jwks_issuer(issuer)
        self._environment = _require_environment(environment)
        if not hasattr(transport, "fetch"):
            raise AuthenticationError("Clerk verifier is not configured.")
        self._transport = transport
        self._resolver = resolve_hostname if resolver is None else resolver
        self._ttl = _require_ttl(cache_ttl_seconds)
        self._interval = _require_interval(refresh_interval_seconds, self._ttl)
        self._connect_timeout = _require_timeout(connect_timeout_seconds)
        self._read_timeout = _require_timeout(read_timeout_seconds)
        self._max_bytes = _require_max_bytes(max_response_bytes)
        self._max_keys = _require_max_keys(max_keys)
        self._keys: dict[str, RSAPublicKey] = {}
        self._expires_at = 0.0
        self._next_fetch_at = 0.0
        self._refreshing = False
        self._lock = threading.Lock()
        self._refresh_done = threading.Condition(self._lock)

    @classmethod
    def from_mapping(
        cls,
        config: Mapping[str, object],
        *,
        transport: JwksTransport,
        resolver: Callable[[str], tuple[str, ...]] | None = None,
    ) -> ClerkJwksCache:
        """Build a cache from server config. A mismatched JWKS URL fails closed."""
        if any(name in config for name in _MAPPING_FORBIDDEN):
            raise AuthenticationError("Clerk verifier is not configured.")
        try:
            issuer = config["issuer"]
            environment = config["environment"]
        except KeyError:
            raise AuthenticationError("Clerk verifier is not configured.") from None
        if type(issuer) is not str:
            raise AuthenticationError("Clerk verifier is not configured.")
        derived = jwks_url_for(issuer)
        if "jwks_url" in config and config["jwks_url"] != derived:
            raise AuthenticationError("Clerk verifier is not configured.")
        ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)
        interval = config.get("refresh_interval_seconds", DEFAULT_REFRESH_INTERVAL_SECONDS)
        connect = config.get("connect_timeout_seconds", DEFAULT_CONNECT_TIMEOUT_SECONDS)
        read = config.get("read_timeout_seconds", DEFAULT_READ_TIMEOUT_SECONDS)
        max_bytes = config.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)
        max_keys = config.get("max_keys", DEFAULT_MAX_KEYS)
        if type(ttl) is not int or type(interval) is not int or type(max_bytes) is not int or type(max_keys) is not int:
            raise AuthenticationError("Clerk verifier is not configured.")
        if type(connect) not in (int, float) or type(read) not in (int, float):
            raise AuthenticationError("Clerk verifier is not configured.")
        return cls(
            issuer=issuer,
            environment=environment if type(environment) is str else "",
            transport=transport,
            resolver=resolver,
            cache_ttl_seconds=ttl,
            refresh_interval_seconds=interval,
            connect_timeout_seconds=float(connect),
            read_timeout_seconds=float(read),
            max_response_bytes=max_bytes,
            max_keys=max_keys,
        )

    @property
    def issuer(self) -> str:
        return self._issuer

    @property
    def environment(self) -> str:
        return self._environment

    @property
    def jwks_url(self) -> str:
        return jwks_url_for(self._issuer)

    def key_for(self, kid: str, *, now: float) -> RSAPublicKey:
        """Return the RSA key for ``kid`` or fail closed. At most one fetch."""
        if type(now) is not int and type(now) is not float:
            raise AuthenticationError("Authentication failed.")
        if now != now or now in (float("inf"), float("-inf")):
            raise AuthenticationError("Authentication failed.")
        while True:
            with self._lock:
                if self._is_fresh(now):
                    found = self._keys.get(kid)
                    if found is not None:
                        return found
                if self._refreshing:
                    if not self._wait_locked():
                        raise AuthenticationError("Authentication failed.")
                    continue
                if now < self._next_fetch_at:
                    raise AuthenticationError("Authentication failed.")
                was_fresh = self._is_fresh(now)
                self._next_fetch_at = now + self._interval
                self._refreshing = True
                break
        keys: dict[str, RSAPublicKey] | None = None
        unexpected: BaseException | None = None
        try:
            keys = self._retrieve()
        except (AuthenticationError, JwksTransportError, TimeoutError, OSError, ValueError):
            keys = None
        except BaseException as exc:
            unexpected = exc
            keys = None
        with self._lock:
            try:
                if keys is None:
                    if not was_fresh:
                        self._keys = {}
                        self._expires_at = now
                else:
                    self._keys = keys
                    self._expires_at = now + self._ttl
            finally:
                self._refreshing = False
                self._refresh_done.notify_all()
        if unexpected is not None:
            raise unexpected
        if keys is None or not self._is_fresh(now) or kid not in keys:
            raise AuthenticationError("Authentication failed.")
        return keys[kid]

    def _wait_locked(self) -> bool:
        deadline = time.monotonic() + self._connect_timeout + self._read_timeout + 1.0
        while self._refreshing:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._refresh_done.wait(remaining)
        return True

    def _is_fresh(self, now: float) -> bool:
        return bool(self._keys) and now < self._expires_at

    def _retrieve(self) -> dict[str, RSAPublicKey]:
        hostname = urlsplit(self._issuer).hostname or ""
        try:
            answers = self._resolver(hostname)
        except AuthenticationError:
            raise
        except (OSError, TimeoutError, ValueError):
            raise AuthenticationError("Authentication failed.") from None
        if type(answers) is not tuple:
            raise AuthenticationError("Authentication failed.")
        pinned = pinned_public_ip(answers)
        response = self._transport.fetch(JwksRequest(
            url=self.jwks_url,
            hostname=hostname,
            pinned_ip=pinned,
            connect_timeout_seconds=self._connect_timeout,
            read_timeout_seconds=self._read_timeout,
            max_bytes=self._max_bytes,
        ))
        if type(response) is not JwksResponse or response.status_code != 200 or response.location is not None:
            raise AuthenticationError("Authentication failed.")
        if type(response.body) is not bytes or len(response.body) > self._max_bytes:
            raise AuthenticationError("Authentication failed.")
        return keys_from_jwks(response.body, max_keys=self._max_keys)


def jwks_url_for(issuer: str) -> str:
    """Return the one approved JWKS URL for an already shaped issuer."""
    confirmed = _require_jwks_issuer(issuer)
    return confirmed + JWKS_PATH


def pinned_public_ip(answers: tuple[str, ...]) -> str:
    """Return the first address only when every answer is a global IP."""
    if type(answers) is not tuple or len(answers) == 0:
        raise AuthenticationError("Authentication failed.")
    pinned = ""
    for answer in answers:
        if type(answer) is not str or not _is_global_ip(answer):
            raise AuthenticationError("Authentication failed.")
        if pinned == "":
            pinned = _canonical_ip(answer)
    return pinned


def resolve_hostname(hostname: str) -> tuple[str, ...]:
    """Resolve one configured hostname. Private answers fail closed."""
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise AuthenticationError("Authentication failed.") from None
    return tuple(str(info[4][0]) for info in infos)


def keys_from_jwks(body: bytes, *, max_keys: int) -> dict[str, RSAPublicKey]:
    """Parse one JWKS body into RSA-2048-or-larger RS256 public keys."""
    if body.startswith(b"\xef\xbb\xbf") or len(body) == 0:
        raise AuthenticationError("Authentication failed.")
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise AuthenticationError("Authentication failed.") from None
    if type(document) is not dict:
        raise AuthenticationError("Authentication failed.")
    entries = document.get("keys")
    if type(entries) is not list or len(entries) == 0 or len(entries) > max_keys:
        raise AuthenticationError("Authentication failed.")
    loaded: dict[str, RSAPublicKey] = {}
    for entry in entries:
        kid, key = _public_rsa_jwk(entry)
        if kid in loaded:
            raise AuthenticationError("Authentication failed.")
        loaded[kid] = key
    return loaded


def parse_http_jwks_message(raw: bytes, max_bytes: int) -> JwksResponse:
    """Parse one buffered HTTP response. Redirects are not followed."""
    if len(raw) > _HEADER_LIMIT + max_bytes + 4:
        raise AuthenticationError("Authentication failed.")
    separator = raw.find(b"\r\n\r\n")
    if separator < 0 or separator > _HEADER_LIMIT:
        raise AuthenticationError("Authentication failed.")
    try:
        head = raw[:separator].decode("ascii")
    except UnicodeError:
        raise AuthenticationError("Authentication failed.") from None
    body = raw[separator + 4:]
    lines = head.split("\r\n")
    status_parts = lines[0].split(" ")
    if len(status_parts) < 2 or status_parts[0] not in ("HTTP/1.0", "HTTP/1.1") or not status_parts[1].isdigit():
        raise AuthenticationError("Authentication failed.")
    status = int(status_parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise AuthenticationError("Authentication failed.")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    if "transfer-encoding" in headers:
        raise AuthenticationError("Authentication failed.")
    location = headers.get("location")
    if status != 200:
        return JwksResponse(status_code=status, body=b"", location=location)
    if location is not None:
        raise AuthenticationError("Authentication failed.")
    content_type = headers.get("content-type")
    if content_type is not None and "application/json" not in content_type.lower():
        raise AuthenticationError("Authentication failed.")
    if "content-length" in headers:
        length_text = headers["content-length"]
        if not length_text.isdigit():
            raise AuthenticationError("Authentication failed.")
        length = int(length_text)
        if length > max_bytes or length != len(body):
            raise AuthenticationError("Authentication failed.")
    if len(body) > max_bytes:
        raise AuthenticationError("Authentication failed.")
    return JwksResponse(status_code=200, body=body, location=None)


class PinnedHttpsJwksTransport:
    """HTTPS GET that connects only to a cache-pinned global address.

    Certificate verification uses the default TLS context and the configured
    hostname as SNI. Redirects are returned to the cache and not requested.
    Environment proxies are not consulted because this client never uses them.
    """

    def __init__(self, opener: Callable[[str, str, float], object] | None = None) -> None:
        self._open = connect_pinned if opener is None else opener

    def fetch(self, request: JwksRequest) -> JwksResponse:
        if request.url != f"https://{request.hostname}{JWKS_PATH}":
            raise AuthenticationError("Authentication failed.")
        if not _is_global_ip(request.pinned_ip):
            raise AuthenticationError("Authentication failed.")
        try:
            stream = self._open(request.pinned_ip, request.hostname, request.connect_timeout_seconds)
            try:
                setter = getattr(stream, "settimeout", None)
                if setter is not None:
                    setter(request.read_timeout_seconds)
                stream.write(_http_request(request.hostname))
                raw = _read_bounded(stream, _HEADER_LIMIT + request.max_bytes + 4)
            finally:
                stream.close()
        except AuthenticationError:
            raise
        except (TimeoutError, OSError, ssl.SSLError) as exc:
            raise JwksTransportError("JWKS request failed.") from exc
        return parse_http_jwks_message(raw, request.max_bytes)


def connect_pinned(ip: str, hostname: str, timeout: float) -> ssl.SSLSocket:
    """Open one verified TLS socket to ``ip`` with SNI ``hostname``."""
    if not _is_global_ip(ip):
        raise AuthenticationError("Authentication failed.")
    context = ssl.create_default_context()
    sock = socket.create_connection((ip, 443), timeout=timeout)
    try:
        return context.wrap_socket(sock, server_hostname=hostname)
    except Exception:
        sock.close()
        raise


def _http_request(hostname: str) -> bytes:
    return (
        f"GET {JWKS_PATH} HTTP/1.1\r\n"
        f"Host: {hostname}\r\n"
        "Accept: application/json\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")


def _read_bounded(stream: object, limit: int) -> bytes:
    reader = getattr(stream, "read", None)
    if reader is None:
        raise JwksTransportError("JWKS request failed.")
    chunks: list[bytes] = []
    remaining = limit
    while remaining > 0:
        chunk = reader(remaining)
        if not isinstance(chunk, bytes):
            raise JwksTransportError("JWKS request failed.")
        if chunk == b"":
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _public_rsa_jwk(entry: object) -> tuple[str, RSAPublicKey]:
    if type(entry) is not dict or any(name not in _JWK_FIELDS for name in entry):
        raise AuthenticationError("Authentication failed.")
    if entry.get("kty") != "RSA" or entry.get("alg") != "RS256" or entry.get("use") != "sig":
        raise AuthenticationError("Authentication failed.")
    operations = entry.get("key_ops", ["verify"])
    if type(operations) is not list or operations != ["verify"]:
        raise AuthenticationError("Authentication failed.")
    kid = entry.get("kid")
    modulus = entry.get("n")
    exponent = entry.get("e")
    if type(kid) is not str or kid == "" or kid.strip() != kid or len(kid) > 256:
        raise AuthenticationError("Authentication failed.")
    if any(ord(character) < 32 or ord(character) == 127 for character in kid):
        raise AuthenticationError("Authentication failed.")
    if type(modulus) is not str or type(exponent) is not str:
        raise AuthenticationError("Authentication failed.")
    try:
        modulus_number = _unsigned(modulus)
        exponent_number = _unsigned(exponent)
        key = RSAPublicNumbers(exponent_number, modulus_number).public_key()
    except (ValueError, TypeError):
        raise AuthenticationError("Authentication failed.") from None
    if not isinstance(key, RSAPublicKey) or key.key_size < 2048 or key.key_size > _MAX_RSA_BITS:
        raise AuthenticationError("Authentication failed.")
    if exponent_number < 3 or exponent_number % 2 == 0 or exponent_number.bit_length() > 32:
        raise AuthenticationError("Authentication failed.")
    if modulus_number % 2 == 0:
        raise AuthenticationError("Authentication failed.")
    return kid, key


def _unsigned(value: str) -> int:
    raw = _b64url_decode(value)
    if raw == b"" or raw[:1] == b"\x00":
        raise ValueError("empty integer")
    return int.from_bytes(raw, "big")


def _b64url_decode(value: str) -> bytes:
    if value == "" or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ValueError("alphabet")
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _require_jwks_issuer(issuer: object) -> str:
    if type(issuer) is not str or issuer == "" or issuer.strip() != issuer or len(issuer) > 253 + len("https://"):
        raise AuthenticationError("Clerk verifier is not configured.")
    parts = urlsplit(issuer)
    hostname = parts.hostname
    if (
        parts.scheme != "https"
        or hostname in (None, "")
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("",)
        or parts.query != ""
        or parts.fragment != ""
        or parts.netloc != hostname
    ):
        raise AuthenticationError("Clerk verifier is not configured.")
    if hostname is None or not _public_hostname(hostname):
        raise AuthenticationError("Clerk verifier is not configured.")
    return issuer


def _public_hostname(hostname: str) -> bool:
    if hostname != hostname.lower() or not _HOST_RE.fullmatch(hostname):
        return False
    if hostname in ("localhost", "metadata", "metadata.google.internal", "metadata.goog"):
        return False
    if hostname.endswith(_BLOCKED_SUFFIXES):
        return False
    labels = hostname.split(".")
    if any(label.isdigit() for label in labels) and all(label.isdigit() for label in labels):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return False


def _require_environment(environment: object) -> str:
    if type(environment) is not str or environment not in _ENVIRONMENTS:
        raise AuthenticationError("Clerk verifier is not configured.")
    return environment


def _require_ttl(value: object) -> int:
    if type(value) is not int or value < 1 or value > MAX_CACHE_TTL_SECONDS:
        raise AuthenticationError("Clerk verifier is not configured.")
    return value


def _require_interval(value: object, ttl: int) -> int:
    if type(value) is not int or value < 1 or value > ttl:
        raise AuthenticationError("Clerk verifier is not configured.")
    return value


def _require_timeout(value: object) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise AuthenticationError("Clerk verifier is not configured.")
    if value != value or value in (float("inf"), float("-inf")) or value < 0.1 or value > 10:
        raise AuthenticationError("Clerk verifier is not configured.")
    return float(value)


def _require_max_bytes(value: object) -> int:
    if type(value) is not int or value < 1024 or value > MAX_RESPONSE_BYTES:
        raise AuthenticationError("Clerk verifier is not configured.")
    return value


def _require_max_keys(value: object) -> int:
    if type(value) is not int or value < 1 or value > MAX_KEYS:
        raise AuthenticationError("Clerk verifier is not configured.")
    return value


def _is_global_ip(value: str) -> bool:
    try:
        _canonical_ip(value)
    except ValueError:
        return False
    return True


def _canonical_ip(value: str) -> str:
    parsed = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    if not parsed.is_global:
        raise ValueError("not global")
    return str(parsed)
