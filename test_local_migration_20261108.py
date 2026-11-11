"""Migration checks on tiny temporary databases and synthetic configuration."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from migrate_local_paths_20261108 import copy_database, migrate


class LocalMigrationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.source = self.project / 'KI.matrix.sqlite3'
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT)')
            db.executemany('INSERT INTO observations(payload) VALUES(?)', [('one',), ('two',)])

    def test_copy_preserves_source_and_actual_rows(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        target = self.root / 'copy.sqlite3'
        self.assertEqual(copy_database(self.source, target), {'observations': 2})
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT payload FROM observations ORDER BY id').fetchall(), [('one',), ('two',)])

    def test_existing_target_is_not_overwritten(self):
        target = self.root / 'existing.sqlite3'
        target.write_bytes(b'preserve me')
        with self.assertRaises(ValueError):
            copy_database(self.source, target)
        self.assertEqual(target.read_bytes(), b'preserve me')

    def test_plan_does_not_create_destination_or_read_keys(self):
        target = self.root / 'new-place'
        result = migrate(self.project, target)
        self.assertEqual(result['status'], 'PLAN')
        self.assertFalse(target.exists())
        self.assertFalse((self.project / '.ki2-local-paths.json').exists())

    def test_inside_project_and_existing_profile_are_rejected(self):
        with self.assertRaises(ValueError):
            migrate(self.project, self.project / 'data')
        profile = self.project / '.ki2-local-paths.json'
        profile.write_text('preserve me', encoding='utf-8')
        with self.assertRaises(ValueError):
            migrate(self.project, self.root / 'elsewhere')
        self.assertEqual(profile.read_text(encoding='utf-8'), 'preserve me')

    def synthetic_config(self):
        home = self.root / 'home'
        home.mkdir()
        folder = self.project / '.streamlit'
        folder.mkdir()
        secrets = folder / 'secrets.toml'
        secrets.write_text('OPENAI_API_KEY="synthetic-openai"\nTAVILY_API_KEY="synthetic-tavily"', encoding='utf-8')
        (self.project / '.env').write_text('SYNTHETIC=fixture\n', encoding='utf-8')
        return home, secrets

    @unittest.skipUnless(os.name == 'nt', 'Local migration is Windows-only')
    def test_activation_moves_config_preserves_database_and_keys(self):
        home, secrets = self.synthetic_config()
        original = secrets.read_bytes()
        target = self.root / 'active'
        with patch.dict(os.environ, {}, clear=True), patch('pathlib.Path.home', return_value=home), \
             patch('migrate_local_paths_20261108.private_directory'):
            result = migrate(self.project, target, apply=True)
        self.assertEqual(result['status'], 'ACTIVATED_LOCAL_ONLY')
        self.assertTrue(self.source.exists())
        self.assertTrue((self.project / '.ki2-local-paths.json').is_file())
        self.assertFalse(secrets.exists())
        self.assertFalse((self.project / '.env').exists())
        self.assertEqual((target / 'config' / 'secrets.toml').read_bytes(), original)
        self.assertEqual((target / 'config' / 'previous-project-secrets.toml').read_bytes(), original)

    @unittest.skipUnless(os.name == 'nt', 'Local migration is Windows-only')
    def test_failed_removal_restores_original_config_and_disables_profile(self):
        home, secrets = self.synthetic_config()
        original = secrets.read_bytes()
        unlink = Path.unlink
        def deny_env(path, *args, **kwargs):
            if path == self.project / '.env':
                raise PermissionError('Synthetic failure')
            return unlink(path, *args, **kwargs)
        with patch.dict(os.environ, {}, clear=True), patch('pathlib.Path.home', return_value=home), \
             patch('migrate_local_paths_20261108.private_directory'), patch.object(Path, 'unlink', deny_env):
            with self.assertRaises(PermissionError):
                migrate(self.project, self.root / 'failed', apply=True)
        self.assertFalse((self.project / '.ki2-local-paths.json').exists())
        self.assertEqual(secrets.read_bytes(), original)
        self.assertTrue((self.project / '.env').exists())
        self.assertTrue(self.source.exists())


if __name__ == '__main__':
    unittest.main()
