"""Direct unit tests for incidents.versions: an accepted incident keeps the contract that made it."""

import unittest

from incidents import versions


class _Failed(Exception):
    pass


def _fail():
    raise _Failed()


class VersionsTests(unittest.TestCase):
    def test_current_tuple_is_the_supported_reader(self):
        record = dict(versions.current(), premise="p")
        self.assertIn(versions.version_tuple(record, _fail), versions.SUPPORTED)

    def test_load_returns_an_independent_copy(self):
        record = dict(versions.current(), details={"facts": {}})
        loaded = versions.load_record(record, _fail)
        self.assertEqual(loaded, record)
        loaded["details"]["facts"]["x"] = 1
        self.assertEqual(record["details"]["facts"], {})

    def test_missing_zero_or_non_int_versions_fail(self):
        for bad in (None, 0, -1, "1", 1.0, True):
            record = dict(versions.current(), gate_policy_version=bad)
            with self.subTest(bad=bad), self.assertRaises(_Failed):
                versions.load_record(record, _fail)
        with self.assertRaises(_Failed):
            versions.load_record("not a record", _fail)

    def test_unknown_tuple_fails(self):
        record = dict(versions.current(), envelope_version=99)
        with self.assertRaises(_Failed):
            versions.load_record(record, _fail)


if __name__ == "__main__":
    unittest.main()
