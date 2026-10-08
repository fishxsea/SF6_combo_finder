"""Integration checks for provenance, recipe integrity, and imported action costs."""
from copy import deepcopy
import io
import json
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from sf_combo_finder.combo_finder import ComboFinder, DATA_PATH, main
from import_documented import apply_documented_routes
from sf_combo_finder.tui_search import sort_combo_rows


class DocumentedRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_PATH.read_text(encoding='utf-8'))

    def test_every_character_has_source_labelled_default_results(self):
        for character in self.data['characters']:
            with self.subTest(character=character):
                finder = ComboFinder(character, data=self.data, documented_only=True)
                routes = list(finder.iter_combos())
                self.assertTrue(routes)
                for route in routes:
                    self.assertEqual(route['evidence']['kind'], 'published_recipe')
                    self.assertTrue(route['evidence']['sources'])
                    self.assertIn(route['evidence']['source_kind'],
                                  ('community_guide', 'capcom_trial_transcription'))
                self.assertFalse(self.data['characters'][character]['documented_coverage']['official_trials_complete'])

    def test_trial_and_community_provenance_are_distinct(self):
        routes = list(ComboFinder('ryu', data=self.data, documented_only=True).iter_combos())
        self.assertEqual({r['evidence']['source_kind'] for r in routes},
                         {'community_guide', 'capcom_trial_transcription'})
        trial = next(r for r in routes if r['evidence']['recipe_id'] == 'prima_trials_ryu_basic_1')
        self.assertTrue(trial['evidence']['complete'])
        self.assertEqual(trial['inputs'], ['5MP', '5LK', '5HK'])
        self.assertEqual(trial['length'], 3)
        self.assertEqual(trial['damage']['raw_total'], 1800)

    def test_followup_has_single_input_correct_damage_and_no_extra_od_cost(self):
        finder = ComboFinder('marisa', 4, 4, data=self.data, documented_only=True)
        route = next(r for r in finder.iter_combos()
                     if r['inputs'] == ['5MP', '5MP', '214MP', '6P'])
        self.assertEqual(route['length'], 4)
        self.assertEqual(route['drive_spent'], 0)
        self.assertEqual(route['damage']['raw_total'], sum(sum(finder.moves[k]['damage']) for k in route['moves']))
        followup = finder.moves[route['moves'][-1]]
        self.assertEqual(followup['requires'], [route['moves'][-2]])
        self.assertFalse(finder._eligible(followup))

    def test_drive_rush_cancel_cost_blocks_prefix_and_raw_rush_costs_one(self):
        for budget in (0, 2):
            routes = list(ComboFinder('ryu', data=self.data, documented_only=True,
                                     drive_meter=budget).iter_combos())
            self.assertFalse(any('DRC(MP+MK)' in r['inputs'] for r in routes))
        routes = list(ComboFinder('ryu', data=self.data, documented_only=True,
                                 drive_meter=3).iter_combos())
        self.assertTrue(any('DRC(MP+MK)' in r['inputs'] and r['drive_spent']==3 for r in routes))
        routes = list(ComboFinder('guile', data=self.data, documented_only=True,
                                 drive_meter=1).iter_combos())
        self.assertTrue(any(r['inputs'][0]=='DR(MP+MK,66)' and r['drive_spent']==1 for r in routes))

    def test_unknown_damage_is_not_zero_or_a_partial_sum_and_sorts_last(self):
        finder = ComboFinder('yasmine', data=self.data, documented_only=True)
        routes = list(finder.iter_combos())
        unknown = next(r for r in routes if r['inputs']==['2MP', '236HP', '6P'])
        self.assertIsNone(unknown['damage']['raw_total'])
        known = next(r for r in routes if r['damage']['raw_total'] is not None)
        for descending in (False, True):
            rows = sort_combo_rows([(finder, unknown), (finder, known)], 'damage', descending=descending)
            self.assertIs(rows[-1][1], unknown)
        output = io.StringIO()
        with patch('sys.argv', ['combo_finder.py', 'yasmine', '--documented-only', '--color', 'never']), redirect_stdout(output):
            main()
        self.assertIn('raw dmg=unknown', output.getvalue())
        self.assertIn('Community guide', output.getvalue())

    def test_air_specials_are_excluded_by_no_jumping(self):
        base = ComboFinder('mai', data=self.data, documented_only=True)
        self.assertTrue(any('8214P' in r['inputs'] for r in base.iter_combos()))
        restricted = ComboFinder('mai', data=self.data, documented_only=True, no_jumping=True)
        self.assertFalse(any(any(i.startswith('8') for i in r['inputs']) for r in restricted.iter_combos()))

    def test_import_is_idempotent_and_recipe_copies_cannot_enter_generation(self):
        data = deepcopy(self.data)
        apply_documented_routes(data)
        self.assertEqual(data, self.data)
        for character in data['characters']:
            finder = ComboFinder(character, data=data)
            for key, move in finder.moves.items():
                if move.get('documented_import'):
                    self.assertFalse(finder._eligible(move), key)


if __name__ == '__main__':
    unittest.main()
