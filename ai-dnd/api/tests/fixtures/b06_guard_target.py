"""Synthetic target modules for the guarded B06 launcher; never import the game."""
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


class AsyncioTarget(unittest.TestCase):
    def test_internal_event_loop_works_but_service_connections_are_blocked(self):
        import asyncio

        async def value():
            await asyncio.sleep(0)
            return 7

        self.assertEqual(asyncio.run(value()), 7)
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b"ok")
            self.assertEqual(right.recv(2), b"ok")
        with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
            socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
            socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        unix_socket, peer = socket.socketpair()
        with unix_socket, peer:
            with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
                unix_socket.connect(str(Path(os.environ["AI_DND_GUARD_RUN_ROOT"]) / "no-service.sock"))
            with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
                unix_socket.connect_ex(str(Path(os.environ["AI_DND_GUARD_RUN_ROOT"]) / "no-service.sock"))
            with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
                unix_socket.bind(str(Path(os.environ["AI_DND_GUARD_RUN_ROOT"]) / "no-listener.sock"))
            with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
                unix_socket.sendto(b"synthetic", str(Path(os.environ["AI_DND_GUARD_RUN_ROOT"]) / "no-service.sock"))
            with self.assertRaisesRegex(PermissionError, "B06 network access blocked"):
                unix_socket.sendmsg([b"synthetic"])


class GuardedTarget(unittest.TestCase):
    def test_read_only_sqlite_uri_is_limited_to_owned_synthetic_database(self):
        import _sqlite3

        run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"])
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "synthetic 100% with spaces.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE synthetic(value INTEGER)")
            connection.execute("INSERT INTO synthetic VALUES (7)")
            connection.commit()
            connection.close()
            uri = database.as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
            self.assertEqual(connection.execute("SELECT value FROM synthetic").fetchone(), (7,))
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO synthetic VALUES (8)")
            connection.close()
            for invalid in (uri.replace("mode=ro", "mode=rw"),
                            uri + "&cache=shared", uri + "&mode=ro",
                            "file://remote/tmp/no-db?mode=ro",
                            "file:///tmp/%ZZ?mode=ro", "file:///tmp/%00?mode=ro",
                            "file::memory:?cache=shared", uri + "#fragment"):
                with self.subTest(uri=invalid), self.assertRaisesRegex(PermissionError, "B06 SQLite URI"):
                    sqlite3.connect(invalid, uri=True)
            with self.assertRaisesRegex(PermissionError, "B06 SQLite URI"):
                sqlite3.connect(uri)
            with self.assertRaisesRegex(PermissionError, "B06 SQLite URI"):
                _sqlite3.connect(uri, uri=True)
            with self.assertRaisesRegex(PermissionError, "B06 SQLite URI"):
                sqlite3.Connection(uri, uri=True)
            with self.assertRaisesRegex(PermissionError, "B06 credentials or campaign database path"):
                sqlite3.connect((run_root / "db" / "personal.sqlite3").as_uri() + "?mode=ro", uri=True)
            with self.assertRaisesRegex(PermissionError, "B06 credentials or campaign database path"):
                sqlite3.connect((Path(directory) / ".env").as_uri() + "?mode=ro", uri=True)
        link = run_root / "tmp" / "uri-outside-temp.sqlite3"
        link.symlink_to(run_root / "db" / "personal.sqlite3")
        with self.assertRaisesRegex(PermissionError, "B06 credentials or campaign database path"):
            sqlite3.connect(link.as_uri() + "?mode=ro", uri=True)

    def test_fresh_temporary_database_is_allowed_but_other_database_is_denied(self):
        run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"])
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "synthetic-checkpoint.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE synthetic(value INTEGER)")
                connection.execute("INSERT INTO synthetic VALUES (7)")
                self.assertEqual(connection.execute("SELECT value FROM synthetic").fetchone(), (7,))
            connection.close()
            with self.assertRaisesRegex(PermissionError, "B06 credentials or campaign database path"):
                (Path(directory) / ".env").write_text("synthetic-only", encoding="utf-8")
        link = run_root / "tmp" / "outside-temp.sqlite3"
        link.symlink_to(run_root / "db" / "personal.sqlite3")
        with self.assertRaisesRegex(PermissionError, "B06 credentials or campaign database path"):
            sqlite3.connect(link)
        with self.assertRaisesRegex(PermissionError, "B06 credentials or campaign database path"):
            sqlite3.connect(run_root / "db" / "personal.sqlite3")

    def test_guard_blocks_synthetic_private_path_and_network(self):
        run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"])
        started = run_root / "target.started"
        started.write_text("started", encoding="utf-8")
        self.assertNotIn("AI_DND_SECRET_PROBE", os.environ)
        self.assertEqual(Path(os.environ["HOME"]).resolve(), run_root / "home")
        self.assertEqual(Path(os.environ["AI_DND_CAMPAIGN_DB"]),
                         run_root / "db" / "campaigns.sqlite3")
        self.assertEqual(os.environ["AI_DND_DISABLE_DEFAULT_APP"], "1")
        self.assertNotIn("OLLAMA_HOST", os.environ)
        self.assertNotIn("SESSION_SECRET", os.environ)
        denied = Path(os.environ["AI_DND_GUARD_DENIED_PATH"])
        with self.assertRaises(PermissionError):
            denied.read_text(encoding="utf-8")
        with self.assertRaises(PermissionError):
            os.remove(Path(__file__).resolve().parents[3] / ".b06-never-delete-sentinel")
        with self.assertRaises(PermissionError):
            socket.socket()
        with self.assertRaises(PermissionError):
            subprocess.Popen([sys.executable, "-c", "raise SystemExit(99)"])
        with sqlite3.connect(":memory:") as database:
            database.execute("select 1")

    def test_only_runner_owned_synthetic_campaign_database_is_allowed(self):
        run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"])
        allowed = Path(os.environ["AI_DND_CAMPAIGN_DB"])
        self.assertEqual(allowed, run_root / "db" / "campaigns.sqlite3")
        with sqlite3.connect(allowed) as database:
            database.execute("CREATE TABLE synthetic_probe (value TEXT)")
            database.execute("INSERT INTO synthetic_probe VALUES ('owned')")
            self.assertEqual(database.execute(
                "SELECT value FROM synthetic_probe").fetchone(), ("owned",))

        personal = run_root / "db" / "personal.sqlite3"
        with self.assertRaises(PermissionError):
            sqlite3.connect(personal)
        external = run_root.parent / "external-campaigns.sqlite3"
        with self.assertRaises(PermissionError):
            sqlite3.connect(external)


class SlowTarget(unittest.TestCase):
    def test_timeout_fixture(self):
        time.sleep(30)


class FailingTarget(unittest.TestCase):
    def test_failure_is_forwarded(self):
        self.fail("synthetic failing target")


class EmptyTarget(unittest.TestCase):
    pass


class DirFdTarget(unittest.TestCase):
    def test_nested_temporary_directory_is_created_and_cleaned(self):
        run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"])
        parent = run_root / "nested-cleanup"
        parent.mkdir()
        with tempfile.TemporaryDirectory(prefix="nested-", dir=parent) as temporary:
            parent_fd = os.open(temporary, os.O_RDONLY)
            try:
                os.mkdir("dirfd-created", dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
            nested = Path(temporary) / "dirfd-created" / "one" / "two"
            nested.mkdir(parents=True)
            (nested / "synthetic.txt").write_text("temporary", encoding="utf-8")
        self.assertEqual(list(parent.iterdir()), [])

    def test_dir_fd_delete_outside_run_root_is_denied(self):
        run_root = Path(os.environ["AI_DND_GUARD_RUN_ROOT"])
        outside = Path(os.environ["AI_DND_GUARD_OUTSIDE_SENTINEL"])
        fd = os.open(outside.parent, os.O_RDONLY)
        previous_cwd = os.getcwd()
        try:
            os.chdir(run_root)
            with self.assertRaises(PermissionError):
                os.unlink(outside.name, dir_fd=fd)
        finally:
            os.chdir(previous_cwd)
            os.close(fd)
