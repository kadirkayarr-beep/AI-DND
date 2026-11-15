"""D-126 (ORTA-12): a failed temporary write while loading a sound save leaves no file and is not called corruption."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import game
from api.persistence.campaign_models import CampaignCorruptError, CampaignStorageError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload


class RestoreTemporaryFileTests(unittest.TestCase):
    def setUp(self):
        self.payload = serialize_campaign_payload(game.create_session(seed=7))
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = scratch.name
        tempdir_patch = patch.object(tempfile, "tempdir", self.scratch)
        tempdir_patch.start()
        self.addCleanup(tempdir_patch.stop)

    def test_a_sound_save_restores_and_leaves_no_temporary_file(self):
        restore_campaign_session(game.create_session(seed=8), self.payload)
        self.assertEqual(os.listdir(self.scratch), [])

    def test_a_disk_failure_mid_write_removes_the_partial_file_and_is_a_storage_error(self):
        real_dump = json.dump

        def half_write(obj, handle, **kwargs):
            handle.write('{"version": ')
            handle.flush()
            raise OSError(28, "No space left on device")

        with patch("json.dump", side_effect=half_write):
            with self.assertRaises(CampaignStorageError):
                restore_campaign_session(game.create_session(seed=8), self.payload)
        self.assertIs(json.dump, real_dump)
        self.assertEqual(os.listdir(self.scratch), [])

    def test_a_temporary_file_that_cannot_be_created_is_a_storage_error(self):
        with patch("tempfile.NamedTemporaryFile", side_effect=OSError(13, "Permission denied")):
            with self.assertRaises(CampaignStorageError):
                restore_campaign_session(game.create_session(seed=8), self.payload)

    def test_an_engine_load_failure_is_still_corruption_and_leaves_no_file(self):
        session = game.create_session(seed=8)
        with patch.object(session, "load_game", side_effect=ValueError("bad engine save")):
            with self.assertRaises(CampaignCorruptError):
                restore_campaign_session(session, self.payload)
        self.assertEqual(os.listdir(self.scratch), [])


if __name__ == "__main__":
    unittest.main()
