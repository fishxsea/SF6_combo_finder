from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sf_combo_finder.combo_finder import ComboFinder, main
from sf_combo_finder.combo_library import combo_identity
from sf_combo_finder.tui_themes import load_controller, load_theme, save_controller, save_theme


class ControllerTests(unittest.TestCase):
    def test_playstation_mapping_directions_and_overdrive(self):
        finder = ComboFinder('ryu', controller='playstation')
        self.assertEqual(finder.format_input('LP MP HP LK MK HK'), '□ △ R1 × ○ R2')
        self.assertEqual(finder.format_input('236LP'), '↓↘→□')
        self.assertEqual(finder.format_input('214PP'), '↓↙←(□+△/□+R1/△+R1)')
        self.assertEqual(finder.format_input('214KK'), '↓↙←(×+○/×+R2/○+R2)')
        self.assertEqual(finder.format_input('5MP > 2HK'), '△ > ↓R2')
        for button, symbol, rgb in [('LP', '□', '255;105;180'), ('MP', '△', '0;208;132'),
                                    ('LK', '×', '0;128;255'), ('MK', '○', '255;59;48')]:
            self.assertEqual(finder.format_input(button, color=True), f'\033[38;2;{rgb}m{symbol}\033[0m')

    def test_display_override_preserves_route_and_favorite_identity(self):
        finder = ComboFinder('ryu', documented_only=True)
        combo = next(finder.iter_combos())
        original = deepcopy(combo)
        key = combo_identity(combo)
        self.assertEqual(finder.format_combo(combo, controller='playstation'), '△ > × > R2')
        self.assertEqual(finder.format_combo(combo, controller='xbox'), 'Y > A > RT')
        self.assertEqual(finder.format_combo(combo, mapped=False, controller='playstation'), '5MP > 5LK > 5HK')
        self.assertEqual(combo, original)
        self.assertEqual(combo_identity(combo), key)

    def test_profiles_fallback_for_older_data_files_and_validate_controller(self):
        data = deepcopy(ComboFinder('ryu').data)
        del data['notation']['controllers']
        finder = ComboFinder('ryu', data=data, controller='playstation')
        self.assertEqual(finder.format_input('LP'), '□')
        data['notation']['buttons']['LP'] = 'B'
        xbox = ComboFinder('ryu', data=data)
        self.assertEqual(xbox.format_input('LP'), 'B')
        with self.assertRaises(ValueError):
            ComboFinder('ryu', controller='unknown')

    def test_controller_and_theme_preferences_preserve_each_other(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.json'
            self.assertEqual(load_controller(path), 'xbox')
            save_theme('forest', path)
            save_controller('playstation', path)
            self.assertEqual(load_theme(path), 'forest')
            save_theme('slate', path)
            self.assertEqual(load_controller(path), 'playstation')
            for contents in ('broken', 'null', '[]', '{}', '{"controller": []}'):
                path.write_text(contents)
                self.assertEqual(load_controller(path), 'xbox')
            with self.assertRaises(ValueError):
                save_controller('unknown', path)

    def test_cli_playstation_json_and_plain_output(self):
        def run(*flags):
            output = io.StringIO()
            args = ['combo_finder.py', 'ryu', '--documented-only', '--controller', 'playstation', '--color', 'never']
            with patch('sys.argv', args + list(flags)), redirect_stdout(output):
                main()
            return output.getvalue()
        self.assertIn('△ > × > R2', run())
        first = json.loads(run('--json'))[0]
        self.assertEqual(first['mapped_inputs'], ['△', '×', 'R2'])


if __name__ == '__main__':
    unittest.main()
