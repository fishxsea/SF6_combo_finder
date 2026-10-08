import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from sf_combo_finder.combo_finder import main
from sf_combo_finder.combo_library import ComboLibrary, combo_identity
from sf_combo_finder.tui_search import SearchSettings, search_combos


class ComboLibraryTests(unittest.TestCase):
    def test_identity_ignores_source_representation_and_preserves_exact_route(self):
        a = {'character': 'ryu', 'inputs': ['5MP > LK > HK'], 'moves': ['target'], 'hit_type': 'normal'}
        b = {'character': 'RYU', 'inputs': ['MP', '5LK', '5HK'], 'moves': ['different'], 'hit_type': 'counter'}
        self.assertEqual(combo_identity(a), combo_identity(b))
        self.assertNotEqual(combo_identity(a), combo_identity(dict(b, character='ken')))
        self.assertNotEqual(combo_identity(a), combo_identity(dict(b, inputs=['5MP', '5LK'])))
        self.assertNotEqual(combo_identity(a), combo_identity(dict(b, inputs=b['inputs']+['623HP'])))

    def test_persistence_independent_marks_restore_and_multiple_instances(self):
        combo = {'character': 'ryu', 'inputs': ['5MP', '2MP', '623HP']}
        other = {'character': 'ken', 'inputs': ['5MP', '2MP', '623HP']}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.json'
            a, b = ComboLibrary(path), ComboLibrary(path)
            self.assertTrue(a.toggle(combo, 'starred'))
            b.toggle(other, 'hidden')
            self.assertTrue(a.toggle(combo, 'hidden'))
            loaded = ComboLibrary(path)
            self.assertEqual(loaded.marks(combo), (True, True))
            self.assertEqual(loaded.marks(other), (False, True))
            self.assertFalse(loaded.matches(combo, starred_only=True))
            self.assertTrue(loaded.matches(combo, starred_only=True, hidden_only=True))
            self.assertFalse(loaded.toggle(combo, 'hidden'))
            self.assertEqual(ComboLibrary(path).marks(combo), (True, False))
            loaded.toggle(combo, 'starred')
            self.assertNotIn(combo_identity(combo), ComboLibrary(path).entries)

    def test_corrupt_library_is_not_overwritten_and_failed_save_does_not_change_marks(self):
        combo = {'character': 'ryu', 'inputs': ['5MP', '2MP']}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.json'
            library = ComboLibrary(path)
            path.write_text('broken json')
            with self.assertRaises(ValueError):
                library.toggle(combo, 'hidden')
            self.assertEqual(path.read_text(), 'broken json')
            self.assertEqual(library.marks(combo), (False, False))
            path.unlink()
            with patch('sf_combo_finder.combo_library.tempfile.NamedTemporaryFile', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    library.toggle(combo, 'starred')
            self.assertEqual(library.marks(combo), (False, False))

    def test_search_filters_before_sampling_and_combines_starred_hidden_views(self):
        library = ComboLibrary(None)
        settings = SearchSettings(character='ryu', documented_only=True)
        baseline = search_combos(settings, library=library)
        combo = baseline.rows[0][1]
        library.toggle(combo, 'starred')
        library.toggle(combo, 'hidden')
        key = combo_identity(combo)
        visible = search_combos(settings, library=library)
        self.assertFalse(any(combo_identity(c)==key for _, c in visible.rows))
        revealed = search_combos(replace(settings, show_hidden=True), library=library)
        self.assertEqual(revealed.total, baseline.total)
        favorites = search_combos(replace(settings, starred_only=True), library=library)
        self.assertEqual(favorites.total, 0)
        hidden = search_combos(replace(settings, hidden_only=True, starred_only=True), library=library)
        self.assertTrue(hidden.rows)
        self.assertTrue(all(combo_identity(c)==key for _, c in hidden.rows))
        sample = search_combos(replace(settings, hidden_only=True, starred_only=True, sample_size=100),
                               library=library, rng=random.Random(10))
        self.assertEqual(sample.total, hidden.total)
        self.assertEqual([c for _, c in sample.rows], [c for _, c in hidden.rows])
        library.toggle(combo, 'hidden')
        self.assertEqual(search_combos(settings, library=library).total, baseline.total)

    def test_cli_uses_saved_library_and_flags_before_random_selection(self):
        settings = SearchSettings(character='ryu', documented_only=True)
        combo = search_combos(settings, library=ComboLibrary(None)).rows[0][1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.json'
            library = ComboLibrary(path)
            library.toggle(combo, 'starred')
            library.toggle(combo, 'hidden')
            def run(*flags):
                output = io.StringIO()
                args = ['combo_finder.py', 'ryu', '--documented-only', '--library', str(path), '--json']
                with patch('sys.argv', args + list(flags)), redirect_stdout(output):
                    main()
                return json.loads(output.getvalue())
            self.assertEqual(run('--starred-only'), [])
            restored_view = run('--starred-only', '--show-hidden', '--random', '5')
            self.assertTrue(restored_view)
            self.assertTrue(all(combo_identity(c)==combo_identity(combo) for c in restored_view))
            self.assertEqual(run('--hidden-only'), run('--hidden-only', '--starred-only'))


if __name__ == '__main__':
    unittest.main()
