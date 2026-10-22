import hashlib
import tempfile
import unittest
from pathlib import Path
from external_sources import verify_sources

class ExternalSourceVerificationTests(unittest.TestCase):
    def test_exact_bytes_pass_but_changed_bytes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            data=b'%PDF-1.7\nsynthetic test material only\n'
            path=Path(directory)/'sample.pdf';path.write_bytes(data)
            manifest=[{'filename':'sample.pdf','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]
            self.assertEqual(verify_sources(directory,manifest),1)
            path.write_bytes(data.replace(b'only',b'fake'))
            with self.assertRaises(ValueError):verify_sources(directory,manifest)
    def test_missing_book_fails_instead_of_skipping(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):verify_sources(directory,[{'filename':'missing.pdf','bytes':0,'sha256':'0'*64}])
    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):verify_sources('.', [{'filename':'../escape.pdf'}])

if __name__=='__main__':unittest.main()
