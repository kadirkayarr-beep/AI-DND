"""Python-level guard used only by the guarded B06 test launcher."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
import threading
from urllib.parse import unquote, urlsplit

GUARD_ID = "ai-dnd-b06-linux-guard-v1"
GUARD_SHA256 = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
if os.environ.get("AI_DND_GUARD_EXPECTED_SHA256") != GUARD_SHA256:
    raise RuntimeError("B06 guard digest mismatch")

_allowed = tuple(Path(item).resolve() for item in json.loads(
    os.environ["AI_DND_GUARD_ALLOWED_ROOTS"]))
_run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"]).resolve()
_synthetic_temp_root = (_run_root / "tmp").resolve()
_runner_database = (_run_root / "db" / "campaigns.sqlite3").resolve()
_runner_database_files = {
    _runner_database,
    *(Path(str(_runner_database) + suffix) for suffix in ("-journal", "-wal", "-shm")),
}
_denied = Path(os.environ["AI_DND_GUARD_DENIED_PATH"]).resolve()
_write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_sqlite_authorization = threading.local()
_original_sqlite_connect = sqlite3.connect


def _within(path, root):
    try:
        Path(path).resolve().relative_to(root)
        return True
    except (ValueError, OSError, TypeError):
        return False


def _check_path(value, write=False, dir_fd=None):
    if isinstance(value, int) or value is None:
        return
    path = Path(os.fsdecode(value))
    if not path.is_absolute():
        cwd_fd = getattr(os, "AT_FDCWD", -100)
        if dir_fd not in (None, -1, cwd_fd):
            if type(dir_fd) is not int or dir_fd < 0:
                raise PermissionError("B06 invalid relative directory descriptor")
            try:
                base = Path(f"/proc/self/fd/{dir_fd}").resolve(strict=True)
                if not base.is_dir():
                    raise PermissionError("B06 relative directory descriptor is not a directory")
            except OSError as exc:
                raise PermissionError("B06 invalid relative directory descriptor") from exc
            path = base / path
        else:
            path = Path.cwd() / path
    path = path.resolve()
    if path == _denied or _within(path, _denied):
        raise PermissionError("B06 synthetic forbidden path")
    parts = {part.casefold() for part in path.parts}
    if parts.intersection({".git", ".agents", ".local", "saves", "attached_assets",
                           "generated-artifacts", "evidence", "evidence-runs"}):
        raise PermissionError("B06 protected path")
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        raise PermissionError("B06 credentials or campaign database path")
    if (path.suffix.casefold() in {
                ".db", ".sqlite", ".sqlite3", ".sqlite3-journal",
                ".sqlite3-wal", ".sqlite3-shm", "-wal", "-shm"
            } and path not in _runner_database_files
            and not _within(path, _synthetic_temp_root)):
        raise PermissionError("B06 credentials or campaign database path")
    if not any(_within(path, root) for root in _allowed):
        raise PermissionError(f"B06 path outside allowlist: {path}")
    if write and not _within(path, _run_root):
        raise PermissionError("B06 writes limited to synthetic run root")


def _guarded_sqlite_connect(database, *args, **kwargs):
    if not isinstance(database, str) or not database.startswith("file:"):
        return _original_sqlite_connect(database, *args, **kwargs)
    uri_enabled = kwargs.get("uri", args[6] if len(args) > 6 else False)
    try:
        parsed = urlsplit(database)
        if (uri_enabled is not True or not database.startswith("file:///")
                or parsed.scheme != "file" or parsed.netloc or parsed.fragment
                or parsed.query != "mode=ro" or re.search(r"%(?![0-9a-fA-F]{2})", database)):
            raise ValueError("unsupported SQLite URI")
        decoded = unquote(parsed.path, encoding="utf-8", errors="strict")
        if "\x00" in decoded or not Path(decoded).is_absolute():
            raise ValueError("invalid SQLite URI path")
        path = Path(decoded).resolve()
    except (ValueError, UnicodeError) as error:
        raise PermissionError("B06 SQLite URI is not an approved read-only local URI") from error
    _check_path(path, write=True)
    canonical_uri = path.as_uri() + "?mode=ro"
    previous = getattr(_sqlite_authorization, "uri", None)
    _sqlite_authorization.uri = canonical_uri
    try:
        return _original_sqlite_connect(canonical_uri, *args, **kwargs)
    finally:
        _sqlite_authorization.uri = previous


def _audit(event, args):
    if event == "open":
        path = args[0] if args else None
        mode = args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        write = bool(flags & _write_flags) or (isinstance(mode, str) and any(ch in mode for ch in "wax+"))
        _check_path(path, write)
    elif event in ("os.listdir", "os.scandir"):
        _check_path(args[0] if args else None)
    elif event == "sqlite3.connect":
        database = args[0] if args else None
        if isinstance(database, str) and database.startswith("file:"):
            if database != getattr(_sqlite_authorization, "uri", None):
                raise PermissionError("B06 SQLite URI was not authorized by the guarded connector")
        elif database != ":memory:":
            _check_path(database, write=True)
    elif event == "os.mkdir":
        _check_path(args[0] if args else None, write=True,
                    dir_fd=args[2] if len(args) > 2 else None)
    elif event in {"os.remove", "os.rmdir"}:
        _check_path(args[0] if args else None, write=True,
                    dir_fd=args[1] if len(args) > 1 else None)
    elif event in {"os.chmod", "os.chown", "os.utime"}:
        fd_index = {"os.chmod": 2, "os.chown": 3, "os.utime": 3}[event]
        _check_path(args[0] if args else None, write=True,
                    dir_fd=args[fd_index] if len(args) > fd_index else None)
    elif event == "os.truncate":
        _check_path(args[0] if args else None, write=True)
    elif event in {"os.rename", "os.replace"}:
        _check_path(args[0] if args else None, write=True,
                    dir_fd=args[2] if len(args) > 2 else None)
        _check_path(args[1] if len(args) > 1 else None, write=True,
                    dir_fd=args[3] if len(args) > 3 else None)
    elif event == "os.link":
        _check_path(args[0] if args else None,
                    dir_fd=args[2] if len(args) > 2 else None)
        _check_path(args[1] if len(args) > 1 else None, write=True,
                    dir_fd=args[3] if len(args) > 3 else None)
    elif event == "os.symlink":
        _check_path(args[1] if len(args) > 1 else None, write=True,
                    dir_fd=args[2] if len(args) > 2 else None)
    elif event in {"os.fchmod", "os.ftruncate"}:
        raise PermissionError("B06 descriptor mutation blocked")
    elif event == "socket.__new__":
        # asyncio uses an anonymous local stream pair as its wake-up pipe.
        # No address-bearing operation is permitted, even for Unix sockets.
        if len(args) < 3 or args[1:3] != (socket.AF_UNIX, socket.SOCK_STREAM):
            raise PermissionError("B06 network access blocked")
    elif event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                   "socket.sendto", "socket.sendmsg"}:
        raise PermissionError("B06 network access blocked")
    elif event in {"subprocess.Popen", "os.system", "os.fork", "os.forkpty",
                   "os.posix_spawn", "os.exec", "os.spawn"}:
        raise PermissionError("B06 child process creation blocked")
    elif event in {"ctypes.dlopen", "ctypes.dlsym"}:
        raise PermissionError("B06 native loading blocked")


sys.addaudithook(_audit)
sqlite3.connect = _guarded_sqlite_connect
