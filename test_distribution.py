"""Distribution checks: user storage, existing saves, and bundled resources."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sf_combo_finder import app_paths
from sf_combo_finder.combo_finder import DATA_PATH
from sf_combo_finder.combo_library import ComboLibrary
from sf_combo_finder.tui_themes import load_controller, load_theme, save_controller, save_theme


class DistributionTests(unittest.TestCase):
    def test_user_storage_on_each_platform_and_override(self):
        home = Path('/test-user')
        with patch.object(Path, 'home', return_value=home), patch.dict(os.environ, {}, clear=True):
            for platform, expected in [
                ('win32', home / 'AppData/Local/SF Combo Finder'),
                ('darwin', home / 'Library/Application Support/SF Combo Finder'),
                ('linux', home / '.local/share/sf-combo-finder'),
            ]:
                with patch.object(app_paths.sys, 'platform', platform):
                    self.assertEqual(app_paths.user_data_dir(), expected)
            with patch.object(app_paths.sys, 'platform', 'linux'), patch.dict(os.environ, {'XDG_DATA_HOME': '/custom'}):
                self.assertEqual(app_paths.user_data_dir(), Path('/custom/sf-combo-finder'))
            with patch.object(app_paths.sys, 'platform', 'win32'), patch.dict(os.environ, {'LOCALAPPDATA': '/custom'}):
                self.assertEqual(app_paths.user_data_dir(), Path('/custom/SF Combo Finder'))
            with patch.dict(os.environ, {'SF_COMBO_FINDER_HOME': '/override'}):
                self.assertEqual(app_paths.user_data_dir(), Path('/override'))

    def test_saves_create_storage_and_preserve_other_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Path(directory) / 'new' / 'nested' / 'preferences.json'
            save_controller('playstation', preferences)
            save_theme('forest', preferences)
            self.assertEqual(load_controller(preferences), 'playstation')
            self.assertEqual(load_theme(preferences), 'forest')
            library_path = Path(directory) / 'another' / 'library.json'
            combo = {'character': 'ryu', 'inputs': ['2LP', '5LP']}
            ComboLibrary(library_path).toggle(combo, 'starred')
            self.assertEqual(ComboLibrary(library_path).marks(combo), (True, False))

    def test_legacy_checkout_files_are_read_only_when_default_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            package = checkout / 'sf_combo_finder'
            package.mkdir()
            (checkout / 'pyproject.toml').touch()
            old = checkout / '.tui_preferences.json'
            old.write_text('{"theme":"forest"}')
            new = checkout / 'user' / old.name
            with patch.object(app_paths, '__file__', str(package / 'app_paths.py')), \
                    patch.dict(os.environ, {}, clear=True), \
                    patch.object(app_paths.sys, 'frozen', False, create=True):
                self.assertEqual(json.loads(app_paths.read_personal_file(new, new))['theme'], 'forest')
                with self.assertRaises(FileNotFoundError):
                    app_paths.read_personal_file(checkout / 'explicit.json', new)
                new.parent.mkdir()
                new.write_text('{"theme":"slate"}')
                self.assertEqual(json.loads(app_paths.read_personal_file(new, new))['theme'], 'slate')
                new.unlink()
                with patch.object(app_paths.sys, 'frozen', True):
                    with self.assertRaises(FileNotFoundError):
                        app_paths.read_personal_file(new, new)

    def test_roster_and_attribution_are_bundled_together(self):
        data = json.loads(DATA_PATH.read_text(encoding='utf-8'))
        self.assertIn('ryu', data['characters'])
        notice = DATA_PATH.with_name('DATA_NOTICE.md')
        root_notice = Path(__file__).parent / 'DATA_NOTICE.md'
        self.assertEqual(notice.read_text(), root_notice.read_text())
