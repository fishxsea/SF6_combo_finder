"""Dark-surface readability and theme preference recovery checks."""
from pathlib import Path
import tempfile
import unittest

from sf_combo_finder.tui_themes import DEFAULT_THEME, PALETTES, load_theme, save_theme


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in channels]
    return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


class ThemeTests(unittest.TestCase):
    def test_every_surface_is_dark_and_body_text_is_readable(self):
        for name, palette in PALETTES.items():
            colors = palette.variables()
            for role in ('cf-background', 'cf-surface', 'cf-focus', 'cf-selection', 'cf-hover', 'cf-header'):
                with self.subTest(theme=name, role=role):
                    background = luminance(colors[role])
                    self.assertLess(background, 0.1)
                    contrast = (luminance(palette.foreground) + 0.05) / (background + 0.05)
                    self.assertGreaterEqual(contrast, 4.5)

    def test_saved_theme_round_trip_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.json'
            self.assertEqual(load_theme(path), DEFAULT_THEME)
            for name in PALETTES:
                save_theme(name, path)
                self.assertEqual(load_theme(path), name)
            for contents in ('invalid JSON', 'null', '[]', '{}', '{"theme": []}', '{"theme": "light"}'):
                path.write_text(contents)
                self.assertEqual(load_theme(path), DEFAULT_THEME)
            with self.assertRaises(ValueError):
                save_theme('light', path)


if __name__ == '__main__':
    unittest.main()
