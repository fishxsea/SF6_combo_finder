import unittest
from types import SimpleNamespace

from sf_combo_finder.tui_search import SearchSettings, sort_combo_rows, combo_startup
from sf_combo_finder.combo_finder import ComboFinder


class ComboSortingTests(unittest.TestCase):
    def test_startup_uses_first_attack_and_target_combo_opening_normal(self):
        finder = ComboFinder('aki')
        self.assertEqual(combo_startup(finder, {'moves': ['drive_rush', '5lp']}), 5)
        self.assertEqual(combo_startup(finder, {'moves': ['sinister_slide', 'heel_strike']}), 11)
        finder.moves['hundun']['startup'] = 30
        self.assertEqual(combo_startup(finder, {'moves': ['hundun']}), 5)
        self.assertIsNone(combo_startup(finder, {'moves': ['drive_rush']}))
        finder.moves['unknown_attack'] = dict(finder.moves['heavy_serpent_lash'],
                                             startup=None, damage=[], damage_unknown=True)
        self.assertIsNone(combo_startup(finder, {'moves': ['unknown_attack', '5lp']}))

    def test_startup_orders_numerically_with_unknown_last_in_both_directions(self):
        finder = ComboFinder('aki')
        finder.moves['unknown_attack'] = dict(finder.moves['heavy_serpent_lash'], startup=None)
        rows = [(finder, dict(id=label, moves=[move], difficulty={'score': score},
                             length=3, damage={'raw_total': 1000}))
                for label, move, score in [('slow', 'heavy_serpent_lash', 0),
                                           ('fast', '5lp', 99), ('tie', '5lp', 1),
                                           ('unknown', 'unknown_attack', 0)]]
        original = list(rows)
        for descending, expected in [(False, ['tie', 'fast', 'slow', 'unknown']),
                                     (True, ['slow', 'fast', 'tie', 'unknown'])]:
            sorted_rows = sort_combo_rows(rows, 'startup', descending=descending)
            self.assertEqual([c['id'] for _, c in sorted_rows], expected)
        self.assertEqual(rows, original)
        self.assertEqual(sort_combo_rows([], 'startup'), [])

    def test_all_sort_fields_and_directions_use_numeric_values_and_display_names(self):
        fighters = {'z': {'display_name': 'Alpha'}, 'a': {'display_name': 'Zulu'}}
        alpha = SimpleNamespace(character='z', data={'characters': fighters})
        zulu = SimpleNamespace(character='a', data={'characters': fighters})
        rows = [
            (zulu, {'id': 'A', 'difficulty': {'score': 10}, 'length': 2, 'damage': {'raw_total': 100}}),
            (alpha, {'id': 'B', 'difficulty': {'score': 2}, 'length': 10, 'damage': {'raw_total': 900}}),
            (alpha, {'id': 'C', 'difficulty': {'score': 1}, 'length': 3, 'damage': {'raw_total': 2000}}),
        ]
        expected = {'character': ['C', 'B', 'A'], 'difficulty': ['C', 'B', 'A'],
                    'length': ['A', 'C', 'B'], 'damage': ['A', 'B', 'C']}
        for field, ids in expected.items():
            for descending in (False, True):
                with self.subTest(field=field, descending=descending):
                    sorted_rows = sort_combo_rows(rows, field, descending=descending)
                    self.assertEqual([combo['id'] for _, combo in sorted_rows],
                                     list(reversed(ids)) if descending else ids)
                    self.assertEqual([combo['id'] for _, combo in rows], ['A', 'B', 'C'])

    def test_sort_validation_empty_results_and_unsampled_default(self):
        self.assertEqual(sort_combo_rows([], 'damage'), [])
        with self.assertRaises(ValueError):
            sort_combo_rows([], 'invalid')
        self.assertIsNone(SearchSettings().sample_size)


if __name__ == '__main__':
    unittest.main()
