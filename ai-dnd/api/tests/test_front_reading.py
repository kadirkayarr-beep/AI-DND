"""The shared front-reading test helpers (G2.1: D-410, D-421, D-428). Offline; no model, no campaign."""

import contextlib
import os
import unittest
from unittest.mock import patch

import front_proposal
from api.tests import front_reading, test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech


class CallKindTests(unittest.TestCase):
    def test_the_front_reading_is_told_before_the_classifier_it_also_carries(self):
        schema = {"properties": {"intent": {}, "front": {}}}
        self.assertEqual(front_reading.call_kind(schema), "front")
        self.assertEqual(front_reading.call_kind({"properties": {"arrival": {}, "narration": {}}}), "arrival")
        self.assertEqual(front_reading.call_kind({"properties": {"spoken_text": {}}}), "speech")
        self.assertIsNone(front_reading.call_kind({"properties": {}}))

    def test_a_schema_that_is_no_mapping_is_no_kind_and_the_helpers_agree(self):
        # D-421 (9): format='json' is a string; no helper may fail on it
        self.assertEqual(front_reading.call_kinds(["json", None, {"properties": {"front": {}}}]),
                         ["other", "other", "front"])
        self.assertEqual(speech.call_kinds(["json"]), ["other"])
        self.assertIs(speech.call_kinds, front_reading.call_kinds)
        self.assertIs(test_campaign_api.call_kind, front_reading.call_kind)

    def test_the_line_reads_first_only_with_the_flag_on(self):
        for flag, expected in (("1", ["front", "speech"]), ("", ["speech"])):
            with self.subTest(flag=flag), patch.dict(os.environ, {front_proposal.FLAG: flag}):
                self.assertEqual(front_reading.with_reading("speech"), expected)
        self.assertIs(test_campaign_api.read_first, front_reading.with_reading)
        self.assertIs(speech.with_reading, front_reading.with_reading)


class LoudFakeTests(unittest.TestCase):
    def test_a_fake_model_asked_for_the_reading_fails_loudly_and_by_name(self):
        # D-410 (1): the engine swallows the failure of a reading; the fake says what is missing
        client = test_campaign_api.FakeOllamaClient()
        with self.assertRaises(front_reading.UnscriptedReadingError) as caught:
            client.chat(format={"type": "object", "properties": {"front": {}, "intent": {}}})
        self.assertIn("FakeOllamaClient", str(caught.exception))
        with self.assertRaises(AssertionError) as other:
            client.chat(format={"type": "object", "properties": {"narration": {}}})
        self.assertNotIsInstance(other.exception, front_reading.UnscriptedReadingError)

    def test_a_plain_talk_client_refuses_what_it_would_drop(self):
        # D-421 (8): operation, conversation and stage_direction were silently thrown away
        for extra in ({"operation": "buy"}, {"conversation": {}}, {"stage_direction": "x"}):
            with self.subTest(extra=extra), self.assertRaises(TypeError):
                speech.plain_talk_client("Merhaba.", **extra)


class ForbidUnscriptedTests(unittest.TestCase):
    @staticmethod
    def run_case(asks_for_a_reading):
        class Case(unittest.TestCase):
            def test_it(self):
                front_reading.forbid_unscripted(self)
                if asks_for_a_reading:
                    with contextlib.suppress(AssertionError):  # the engine swallows a failed reading; the test must still fail
                        test_campaign_api.FakeOllamaClient().chat(format={"properties": {"front": {}}})
        result = unittest.TestResult()
        Case("test_it").run(result)
        return result

    def test_a_test_whose_fake_was_asked_for_an_unscripted_reading_fails_even_if_the_engine_swallowed_it(self):
        self.assertEqual(len(self.run_case(True).failures), 1)

    def test_a_test_that_asked_for_none_passes(self):
        self.assertTrue(self.run_case(False).wasSuccessful())


class RouteWatchTests(unittest.TestCase):
    def test_only_a_reading_that_fell_back_or_was_skipped_counts_as_unusable(self):
        watch = front_reading.RouteWatch(self)
        watch.routes.extend(["front:speak_to", "fallback:failed", "skipped:fight", "front:work"])
        self.assertEqual(watch.unusable(), ["fallback:failed", "skipped:fight"])
        self.assertEqual(watch.fell_back(), ["fallback:failed"])
        watch.reset()
        self.assertEqual(watch.unusable(), [])


if __name__ == "__main__":
    unittest.main()
