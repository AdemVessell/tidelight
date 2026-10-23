"""Download packaging controls using local fixtures; no network required."""
from pathlib import Path
import hashlib, tempfile, unittest
from unittest.mock import patch
import fetch_assets

class AssetTests(unittest.TestCase):
    def test_verified_asset_copies_to_other_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'existing'; source.write_bytes(b'tidelight')
            asset = {'bytes': 9, 'sha256': hashlib.sha256(b'tidelight').hexdigest(),
                'destinations': ['existing', 'new/asset'], 'url': 'https://invalid.example/never-requested'}
            with patch.object(fetch_assets, 'ROOT', root): fetch_assets.install(asset)
            self.assertEqual((root / 'new/asset').read_bytes(), b'tidelight')

    def test_changed_file_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'existing'; source.write_bytes(b'changed')
            asset = {'bytes': 9, 'sha256': hashlib.sha256(b'tidelight').hexdigest(),
                'destinations': ['existing'], 'url': 'https://invalid.example/never-requested'}
            with patch.object(fetch_assets, 'ROOT', root), self.assertRaises(ValueError): fetch_assets.install(asset)
            self.assertEqual(source.read_bytes(), b'changed')

    def test_checksum_failure_installs_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'download'; source.write_bytes(b'corrupt')
            asset = {'bytes': 7, 'sha256': hashlib.sha256(b'correct').hexdigest(),
                'destinations': ['new/asset'], 'url': source.as_uri()}
            with patch.object(fetch_assets, 'ROOT', root), patch.object(fetch_assets.shutil, 'which', return_value=None), self.assertRaises(ValueError):
                fetch_assets.install(asset)
            self.assertFalse((root / 'new/asset').exists())

if __name__ == '__main__': unittest.main()
