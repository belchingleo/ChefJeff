"""The operator archive is reproducible and cannot sweep in credentials or downloads."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
from scripts.package_research_admin import FILES,ROOT,package


class AdminPackageTests(unittest.TestCase):
    def test_two_builds_are_identical_and_only_allowlisted_files_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'ops/research_admin').mkdir(parents=True);(root/'docs').mkdir()
            for name in FILES:shutil.copyfile(ROOT/'ops/research_admin'/name,root/'ops/research_admin'/name)
            shutil.copyfile(ROOT/'docs/research-admin.md',root/'docs/research-admin.md')
            (root/'ops/research_admin/auth.json').write_text('synthetic-private-marker')
            (root/'ops/research_admin/records.cjresearch.zip').write_text('synthetic-record-marker')
            one,manifest=package(root,root/'one.zip');two,_=package(root,root/'two.zip')
            self.assertEqual(hashlib.sha256(one.read_bytes()).digest(),hashlib.sha256(two.read_bytes()).digest())
            with zipfile.ZipFile(one) as archive:
                self.assertEqual(set(archive.namelist()),{'chefjeff-admin-v2/'+name for name in (*FILES,'README.md','manifest.json')})
                self.assertFalse(json.loads(archive.read('chefjeff-admin-v2/manifest.json'))['production_data_included'])
                for name,expected in manifest['files'].items():self.assertEqual(hashlib.sha256(archive.read('chefjeff-admin-v2/'+name)).hexdigest(),expected)
            path=root/'ops/research_admin/admin_server.py';path.unlink();path.symlink_to(ROOT/'ops/research_admin/admin_server.py')
            with self.assertRaises(ValueError):package(root,root/'linked.zip')
