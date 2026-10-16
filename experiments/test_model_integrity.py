"""Regression checks for stale snapshot pointers after a successful download."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import model_integrity as integrity


class CachedCheckpointRecovery(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name)
        self.snapshot = self.cache / 'models--BAAI--bge-m3' / 'snapshots' / integrity.MODEL_REVISION
        self.snapshot.mkdir(parents=True)
        self.weights = self.snapshot / 'pytorch_model.bin'
        self.complete = b'complete verified checkpoint fixture'
        self.digest = hashlib.sha256(self.complete).hexdigest()
        for name, value in [('WEIGHTS_SIZE', len(self.complete)), ('WEIGHTS_SHA256', self.digest)]:
            replacement = patch.object(integrity, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def cache_blob(self, content):
        blob = self.cache / 'blobs' / integrity.XET_HASH[:2] / integrity.XET_HASH
        blob.parent.mkdir(parents=True)
        blob.write_bytes(content)

    def test_complete_cached_blob_replaces_stale_partial_snapshot(self):
        self.weights.write_bytes(b'partial')
        self.cache_blob(self.complete)
        self.assertTrue(integrity.recover_cached_weights(self.snapshot, self.cache))
        self.assertEqual(self.weights.read_bytes(), self.complete)
        self.assertEqual(integrity.verify_checkpoint({'revision': integrity.MODEL_REVISION, 'snapshot_path': str(self.snapshot)}), self.digest)

    def test_same_size_corrupt_blob_is_rejected_without_replacing_partial(self):
        self.weights.write_bytes(b'partial')
        self.cache_blob(b'x' * len(self.complete))
        self.assertFalse(integrity.recover_cached_weights(self.snapshot, self.cache))
        self.assertEqual(self.weights.read_bytes(), b'partial')

    def test_already_valid_snapshot_needs_no_cached_blob(self):
        self.weights.write_bytes(self.complete)
        self.assertTrue(integrity.recover_cached_weights(self.snapshot, self.cache))


if __name__ == '__main__':
    unittest.main()
