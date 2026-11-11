"""Path contracts, synthetic secrets and temporary databases only."""
import json
from pathlib import Path
import tempfile
import unittest
import ki2_paths as paths


class RuntimePathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.home = self.root / 'home'
        self.home.mkdir()

    def profile(self):
        data = {'version': 1, 'data_dir': str(self.root / 'data'),
                'log_dir': str(self.root / 'logs'), 'secrets_file': str(self.root / 'private.toml')}
        (self.project / paths.PROFILE).write_text(json.dumps(data), encoding='utf-8')
        return data

    def test_legacy_defaults_and_linux_ignore_windows_profile(self):
        for platform in ('nt', 'posix'):
            self.assertEqual(paths.default_database(self.project, {}, platform), self.project / 'KI.matrix.sqlite3')
        self.profile()
        self.assertEqual(paths.default_database(self.project, {}, 'posix'), self.project / 'KI.matrix.sqlite3')

    def test_windows_profile_and_explicit_environment_priority(self):
        data = self.profile()
        actual = paths.runtime_paths(self.project, {}, 'nt')
        self.assertEqual(actual['database'], Path(data['data_dir']) / 'KI.matrix.sqlite3')
        other = self.root / 'explicit'
        self.assertEqual(paths.default_database(self.project, {'KI2_DATA_DIR': str(other)}, 'nt'), other / 'KI.matrix.sqlite3')

    def test_key_priority_and_missing_keys_preserved(self):
        for base, text in ((self.home, 'OPENAI_API_KEY="home"\nTAVILY_API_KEY="home-tavily"'),
                           (self.project, 'OPENAI_API_KEY="project"')):
            (base / '.streamlit').mkdir()
            (base / '.streamlit' / 'secrets.toml').write_text(text, encoding='utf-8-sig')
        keys = paths.load_keys(('OPENAI_API_KEY', 'TAVILY_API_KEY', 'TELEGRAM_CHAT_ID'), self.project,
                               self.home, {'OPENAI_API_KEY': 'environment'}, 'nt')
        self.assertEqual(keys, {'OPENAI_API_KEY': 'environment', 'TAVILY_API_KEY': 'home-tavily', 'TELEGRAM_CHAT_ID': ''})

    def test_external_file_replaces_project_only_and_missing_file_fails(self):
        data = self.profile()
        (self.project / '.streamlit').mkdir()
        (self.project / '.streamlit' / 'secrets.toml').write_text('OPENAI_API_KEY="obsolete"', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Nie można odczytać'):
            paths.load_keys(('OPENAI_API_KEY',), self.project, self.home, {}, 'nt')
        Path(data['secrets_file']).write_text('OPENAI_API_KEY="external"', encoding='utf-8')
        self.assertEqual(paths.load_keys(('OPENAI_API_KEY',), self.project, self.home, {}, 'nt'), {'OPENAI_API_KEY': 'external'})

    def test_invalid_config_has_no_secret_in_exception_and_does_not_fall_back(self):
        profile = self.project / paths.PROFILE
        for content in ('not-json PRIVATE_VALUE', '{"version":99}', '{"version":1}'):
            profile.write_text(content, encoding='utf-8')
            with self.assertRaises(ValueError) as caught:
                paths.runtime_paths(self.project, {}, 'nt')
            self.assertNotIn('PRIVATE_VALUE', str(caught.exception))
        profile.unlink()
        with self.assertRaises(ValueError):
            paths.runtime_paths(self.project, {'KI2_DATA_DIR': 'relative-path'}, 'nt')

    def test_logs_follow_explicit_database_unless_log_directory_selected(self):
        db = self.root / 'custom.sqlite3'
        self.assertEqual(paths.process_log_paths(db, self.project, {}, 'nt'),
                         [self.root / 'custom.scanner.log', self.root / 'custom.panel.log'])
        data = self.profile()
        self.assertEqual(paths.process_log_paths(db, self.project, {}, 'nt')[0],
                         Path(data['log_dir']) / 'custom.scanner.log')


if __name__ == '__main__':
    unittest.main()
