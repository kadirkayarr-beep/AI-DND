"""Direct unit tests for incidents.threads: an id-only, depth-capped thread index."""

import unittest

from incidents import threads


def _world(*incident_ids):
    return {"incidents": {incident_id: {} for incident_id in incident_ids}}


class ValidateTests(unittest.TestCase):
    def test_good_rows_pass_and_bad_rows_fail(self):
        good = [{"thread_id": "t1", "incident_ids": ["a", "b"], "depth": 2}]
        self.assertEqual(threads.validate(good), good)
        bad = [
            "x",
            [{"thread_id": "t1", "incident_ids": [], "depth": 0}],
            [{"thread_id": "t1", "incident_ids": ["a"], "depth": 2}],
            [{"thread_id": "t1", "incident_ids": ["a", "a"], "depth": 2}],
            [{"thread_id": "t1", "incident_ids": ["a"], "depth": 1, "extra": 1}],
            [good[0], good[0]],
            [{"thread_id": f"t{n}", "incident_ids": ["a"], "depth": 1} for n in range(threads.MAX_THREADS + 1)],
        ]
        for raw in bad:
            with self.subTest(raw=str(raw)[:60]), self.assertRaises(ValueError):
                threads.validate(raw)

    def test_read_missing_is_empty(self):
        self.assertEqual(threads.read({}), [])
        self.assertEqual(threads.ensure({}), [])


class AttachTests(unittest.TestCase):
    def test_root_incident_starts_a_thread_and_is_stamped(self):
        world = _world("a")
        thread_id = threads.attach(world, "a")
        self.assertTrue(thread_id.startswith("thr."))
        self.assertEqual(world["incidents"]["a"]["thread_id"], thread_id)
        self.assertEqual(threads.attach(world, "a"), thread_id)

    def test_child_joins_its_parent_until_the_depth_cap(self):
        world = _world("a", "b", "c", "d", "e")
        root = threads.attach(world, "a")
        parent = "a"
        for child in ("b", "c", "d"):
            self.assertEqual(threads.attach(world, child, parent), root)
            parent = child
        self.assertEqual(world["incident_threads"][0]["depth"], threads.MAX_DEPTH)
        self.assertNotEqual(threads.attach(world, "e", "d"), root)

    def test_bad_ids_and_full_index_attach_nothing(self):
        self.assertIsNone(threads.attach({}, ""))
        self.assertIsNone(threads.attach({}, None))
        world = {}
        for number in range(threads.MAX_THREADS):
            threads.attach(world, f"inc.{number}")
        self.assertIsNone(threads.attach(world, "one.too.many"))


if __name__ == "__main__":
    unittest.main()
