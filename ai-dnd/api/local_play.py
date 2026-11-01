"""Owner-only local play: one fixed principal on a proven loopback server.

For the owner playing alone on this PC. Real Clerk stays the only login for
anything else, and nothing here replaces it.

Threat model
    Stopped: a LAN or internet peer (non-loopback peer, or a non-loopback local
    address), a hosted deployment that inherits the mode (Replit and production
    markers, and plain ``uvicorn --host 0.0.0.0`` never proves a bind), DNS
    rebinding (Host and Origin), a reverse proxy on this PC that adds forwarding
    headers or sends its own Host, a web page in the owner's browser (Origin,
    Sec-Fetch-Site, and the non-simple request marker on writes), and
    client-supplied identity (no request field selects the principal).
    Not stopped: another program or OS user on this PC, and a header-less raw
    TCP forwarder on it (netsh portproxy, ssh -R or -L, socat). Any local process
    can reach loopback, and a raw forwarder arrives as a loopback peer with the
    client's own headers, so this mode assumes the machine itself is trusted and
    that the owner has not opened such a forward to it.

Why an environment value is not enough
    ``AI_DND_AUTH_MODE=local`` only asks for this mode. It opens nothing without
    a socket address, and ``create_app`` never has one. ``main`` below binds the
    socket itself and passes the address the operating system reports.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import socket
import sys
from typing import Any, Mapping

from api.auth import (
    AuthenticationError,
    FailClosedAuthenticator,
    Principal,
    REQUEST_MARKER,
)


LOCAL_PLAY_MODE = "local"
LOCAL_PRINCIPAL = Principal("urn:ai-dnd:local-play", "owner")

_LOOPBACK_BINDS = ("127.0.0.1", "::1")
_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "[::1]"})
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOCAL_FETCH_SITES = frozenset({"same-origin", "none"})
_FORWARDING_HEADERS = frozenset({
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "cf-connecting-ip",
    "true-client-ip",
})


class LocalPlayRefused(Exception):
    """This process must not serve local play."""


def _is_production_configuration(environ: Mapping[str, str]) -> bool:
    if any(name == "REPL_ID" or name.startswith("REPLIT_") for name in environ):
        return True
    return (
        environ.get("NODE_ENV") == "production"
        or environ.get("AI_DND_CLERK_ENVIRONMENT") == "production"
    )


def _is_loopback_address(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def _is_loopback_authority(value: str) -> bool:
    """``name`` or ``name:port`` for an exact loopback name. Nothing else parses."""
    if value in _LOOPBACK_NAMES:
        return True
    name, separator, port = value.rpartition(":")
    return separator == ":" and port.isascii() and port.isdigit() and name in _LOOPBACK_NAMES


def _is_loopback_origin(value: str) -> bool:
    scheme, separator, authority = value.partition("://")
    return separator == "://" and scheme == "http" and _is_loopback_authority(authority)


class LocalPlayAuthenticator:
    """Return the fixed principal for a request that proves it is local."""

    def __init__(self, bound_host: str) -> None:
        if bound_host not in _LOOPBACK_BINDS:
            raise AuthenticationError("Local play requires a loopback bind.")
        self._bound_host = bound_host

    def authenticate(self) -> Principal:
        raise AuthenticationError("Local play needs the request to prove it is local.")

    def authenticate_asgi(self, scope: Mapping[str, Any]) -> Principal:
        try:
            self._require_local(scope)
        except (AttributeError, LookupError, TypeError, ValueError):
            raise AuthenticationError("Authentication failed.") from None
        return LOCAL_PRINCIPAL

    def _require_local(self, scope: Mapping[str, Any]) -> None:
        if scope["server"][0] != self._bound_host:
            raise AuthenticationError("Authentication failed.")
        if not _is_loopback_address(scope["client"][0]):
            raise AuthenticationError("Authentication failed.")
        headers = [
            (name.decode("latin-1").lower(), value.decode("latin-1"))
            for name, value in scope["headers"]
        ]
        hosts = [value for name, value in headers if name == "host"]
        if len(hosts) != 1 or not _is_loopback_authority(hosts[0]):
            raise AuthenticationError("Authentication failed.")
        marker = False
        for name, value in headers:
            if name in _FORWARDING_HEADERS:
                raise AuthenticationError("Authentication failed.")
            if name == "origin" and not _is_loopback_origin(value):
                raise AuthenticationError("Authentication failed.")
            if name == "sec-fetch-site" and value not in _LOCAL_FETCH_SITES:
                raise AuthenticationError("Authentication failed.")
            if name == REQUEST_MARKER.lower() and value == "1":
                marker = True
        if scope["method"] in _WRITE_METHODS and not marker:
            raise AuthenticationError("Authentication failed.")


def local_authenticator_from_environ(
    environ: Mapping[str, str],
    listen_host: str | None,
) -> LocalPlayAuthenticator | FailClosedAuthenticator:
    if (
        environ.get("AI_DND_AUTH_MODE") != LOCAL_PLAY_MODE
        or listen_host not in _LOOPBACK_BINDS
        or _is_production_configuration(environ)
    ):
        return FailClosedAuthenticator()
    return LocalPlayAuthenticator(listen_host)


def bind_loopback_socket(host: str, port: int) -> socket.socket:
    """Bind first, then believe the address the operating system reports."""
    if host not in _LOOPBACK_BINDS:
        raise LocalPlayRefused(f"Local play binds only to {' or '.join(_LOOPBACK_BINDS)}.")
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            # Ask for sole use of this address, so sharing it is a bind error.
            # A wildcard bind on the same port is another address; it still works.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, port))
        if listener.getsockname()[0] != host:
            raise LocalPlayRefused("The bound address is not the requested loopback address.")
    except BaseException:
        listener.close()
        raise
    return listener


def prepare_listener(
    environ: Mapping[str, str],
    host: str,
    port: int,
) -> tuple[socket.socket, LocalPlayAuthenticator]:
    if environ.get("AI_DND_AUTH_MODE") != LOCAL_PLAY_MODE:
        raise LocalPlayRefused("Set AI_DND_AUTH_MODE=local to start local play.")
    if _is_production_configuration(environ):
        raise LocalPlayRefused("Local play refuses a production configuration.")
    listener = bind_loopback_socket(host, port)
    authenticator = local_authenticator_from_environ(environ, listener.getsockname()[0])
    if type(authenticator) is not LocalPlayAuthenticator:
        listener.close()
        raise LocalPlayRefused("Local play could not prove a loopback listener.")
    return listener, authenticator


def uvicorn_settings() -> dict[str, Any]:
    """Keep the socket peer as the client: a proxy header must not rewrite it."""
    return {
        "proxy_headers": False,
        "forwarded_allow_ips": "",
        "server_header": False,
        "workers": 1,
        "reload": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve AI-DND for the owner on loopback.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    arguments = parser.parse_args(argv)
    try:
        listener, authenticator = prepare_listener(os.environ, arguments.host, arguments.port)
    except LocalPlayRefused as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 2

    import front_proposal

    front_proposal.default_on_for_local_play(os.environ)
    # The module-level app would build a second, closed application here.
    os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"
    import uvicorn

    from api.main import create_app
    from api.ollama_adapter import AuthenticatedOllamaAdapter

    # The loopback bind is proven above, so only here may a prompt go to a cloud model.
    application = create_app(
        authenticator=authenticator,
        ollama_adapter=AuthenticatedOllamaAdapter.from_environment(use_cloud=True),
    )
    config = uvicorn.Config(application, **uvicorn_settings())
    uvicorn.Server(config).run(sockets=[listener])
    return 0


if __name__ == "__main__":
    # Under -m this file is __main__. Call the importable module, whose class is
    # the one the API middleware recognises.
    from api.local_play import main as importable_main

    raise SystemExit(importable_main())
