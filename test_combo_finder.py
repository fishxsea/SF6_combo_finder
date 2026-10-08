import json
import io
import random
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from sf_combo_finder.combo_finder import ComboFinder, main


class ComboFinderTests(unittest.TestCase):
    def test_controller_notation(self):
        finder = ComboFinder('aki', 1, 1)
        self.assertEqual(finder.format_input('236LP'), '↓↘→X')
        self.assertEqual(finder.format_input('2HK'), '↓RT')
        self.assertEqual(finder.format_input('5MP > j.2HP'), 'Y > j.↓RB')
        self.assertEqual(finder.format_input('4LP+LK'), '←X+A')
        self.assertEqual(finder.format_input('Nightshade Pulse > 6HP'), 'Nightshade Pulse > →RB')
        self.assertEqual(finder.format_input('236P'), '↓↘→(X/Y/RB)')
        self.assertEqual(finder.format_input('214KK'), '↓↙←(A+B/A+RT/B+RT)')
        finder.button_mapping['LP'] = 'B'
        finder.direction_mapping['2']['symbol'] = 'DOWN'
        self.assertEqual(finder.format_input('2LP'), 'DOWNB')
        combo = next(c for c in finder.iter_combos() if c['moves'] == ['2lp'])
        self.assertEqual(combo['mapped_inputs'], ['DOWNB'])
        self.assertEqual(finder.format_combo(combo), 'DOWNB')
        self.assertEqual(finder.format_combo(combo, mapped=False), '2LP')

    def test_xbox_button_colors(self):
        finder = ComboFinder('aki')
        for button, label, code in [('LP', 'X', '0;128;255'), ('MP', 'Y', '255;214;0'),
                                    ('LK', 'A', '50;205;50'), ('MK', 'B', '255;59;48')]:
            self.assertEqual(finder.format_input(button, color=True),
                             f'\033[38;2;{code}m{label}\033[0m')
        self.assertEqual(finder.format_input('2HK', color=True), '↓\033[38;2;255;255;255mRT\033[0m')

    def test_links_and_knockdown(self):
        finder = ComboFinder('aki', 2, 2, includes_specials=False)
        routes = {tuple(c['moves']) for c in finder.iter_combos()}
        self.assertIn(('5mk', '5mp'), routes)  # +6 into six-frame startup
        self.assertNotIn(('5mp', '5mk'), routes)
        self.assertFalse(any(route[0] == '2hp' for route in routes))

    def test_counter_bonus_only_on_opener(self):
        finder = ComboFinder('aki', 2, 2, includes_specials=False, hit_type='counter')
        routes = {tuple(c['moves']) for c in finder.iter_combos()}
        self.assertIn(('5hk', '5mp'), routes)
        move, _ = finder._resolve(finder.moves['5hk'], False, False)
        self.assertEqual(move['hit']['advantage'], 4)

    def test_meter_and_followup_restrictions(self):
        finder = ComboFinder('aki', 2, 3, drive_meter=0, super_meter=0)
        for combo in finder.iter_combos():
            for index, key in enumerate(combo['moves']):
                move = finder.moves[key]
                self.assertNotEqual(move['category'], 'od_special')
                self.assertNotEqual(move['category'], 'super')
                if move.get('requires'):
                    self.assertGreater(index, 0)
                    self.assertIn(combo['moves'][index - 1], move['requires'])
        # Its SA3 cancel requires the non-hitgrab version, which this search
        # cannot establish for a grounded opponent.
        self.assertIsNone(finder._transition('od_cruel_fate', finder.moves['od_cruel_fate'],
                                            'sa3', finder.moves['sa3']))
        self.assertIsNone(finder._transition('od_cruel_fate', finder.moves['od_cruel_fate'],
                                             'sa1', finder.moves['sa1']))

    def test_poison_detonation_and_target_length(self):
        finder = ComboFinder('aki', 2, 2)
        move, poisoned = finder._resolve(finder.moves['heavy_serpent_lash'], True, False)
        self.assertEqual(move['hit']['state'], 'crumple')
        self.assertFalse(poisoned)
        routes = list(finder.iter_combos())
        self.assertTrue(any(c['moves'] == ['hundun'] and c['length'] == 2 for c in routes))

    def test_cancel_permission_is_not_enough_to_combo(self):
        finder = ComboFinder('aki', 2, 2)
        routes = {tuple(c['moves']) for c in finder.iter_combos()}
        self.assertIn(('2lp', 'heavy_serpent_lash'), routes)
        self.assertIn(('5mp', 'od_serpent_lash'), routes)
        for slow_move in ('od_serpent_lash', 'light_cruel_fate', 'medium_cruel_fate',
                          'heavy_cruel_fate', 'od_cruel_fate', 'nightshade_pulse'):
            self.assertNotIn(('2lp', slow_move), routes)
        self.assertNotIn(('5hk', 'heavy_cruel_fate'), routes)
        punish = ComboFinder('aki', 2, 2, hit_type='punish_counter')
        self.assertIn(('5hk', 'heavy_cruel_fate'),
                      {tuple(c['moves']) for c in punish.iter_combos()})
        unknown = deepcopy(finder.moves['2lp'])
        unknown.pop('recovery_on_hit')
        self.assertIsNone(finder._transition('2lp', unknown, 'heavy_serpent_lash',
                                            finder.moves['heavy_serpent_lash']))

    def test_target_combos_and_explicit_chains(self):
        finder = ComboFinder('aki', 2, 3, includes_specials=False)
        routes = {tuple(c['moves']) for c in finder.iter_combos()}
        self.assertNotIn(('5lp', '5lp'), routes)
        self.assertNotIn(('5lp', 'hundun'), routes)
        self.assertIn(('2lk', 'hundun'), routes)
        self.assertIn(('2lp', 'hundun'), routes)
        self.assertIn(('5lp', '2lk'), routes)
        self.assertNotIn(('5lk', '2lk'), routes)
        # The second LP is the 8-frame target attack, not another 5-frame jab.
        target = next(c for c in finder.iter_combos() if c['moves'] == ['hundun'])
        self.assertEqual(target['length'], 2)
        with_specials = ComboFinder('aki', 2, 3)
        special_routes = {tuple(c['moves']) for c in with_specials.iter_combos()}
        self.assertIn(('hundun', 'nightshade_pulse'), special_routes)
        self.assertNotIn(('hundun', 'od_serpent_lash'), special_routes)

    def test_move_specific_counter_data_and_multihit(self):
        finder = ComboFinder('aki', hit_type='punish_counter')
        kick, _ = finder._resolve(finder.moves['5hk'], False, True)
        self.assertEqual(kick['hit']['advantage'], 12)
        target, _ = finder._resolve(finder.moves['hundun'], False, True)
        self.assertEqual(target['hit']['advantage'], 1)
        double, _ = finder._resolve(finder.moves['6hk'], False, True)
        self.assertEqual(double['hit']['advantage'], 4)
        jab, _ = finder._resolve(finder.moves['2lp'], False, True)
        self.assertEqual(jab['hit']['advantage'], 8)

    def test_unknown_followup_timing_is_excluded(self):
        finder = ComboFinder('aki')
        pulse, _ = finder._resolve(finder.moves['nightshade_pulse'], False, True)
        self.assertIsNone(finder._transition('nightshade_pulse', pulse, 'nightshade_chaser',
                                            finder.moves['nightshade_chaser']))
        # Knockdown advantage is wake-up timing, not a grounded link window.
        lash, _ = finder._resolve(finder.moves['heavy_serpent_lash'], False, True)
        self.assertIsNone(finder._transition('heavy_serpent_lash', lash, 'sa1', finder.moves['sa1']))

    def test_long_light_strings_are_not_inferred_from_pairs(self):
        # Reported false positive: 214HK > 2LP > 2LK > 2LK > LP > LP.
        # Hun Dun is two inputs, so this is a six-input route.
        bad_route = ['heavy_cruel_fate', '2lp', '2lk', '2lk', 'hundun']
        finder = ComboFinder('aki', 2, 6, drive_meter=0, super_meter=0)
        routes = {tuple(c['moves']) for c in finder.iter_combos()}
        self.assertNotIn(tuple(bad_route), routes)
        self.assertNotIn(('2lp', '2lk', '2lk'), routes)
        self.assertNotIn(('2lp', '2lp', '2lp', '2lp'), routes)
        self.assertIn(('heavy_cruel_fate', '2lp', '2lp', '5lk', 'heavy_serpent_lash'), routes)
        self.assertIn(('2lp', 'hundun', 'heavy_serpent_lash'), routes)
        # The filter uses data-backed patterns, not a hard-coded three-hit cap.
        finder.supported_light_sequences.append(['2lp', '2lk', '2lk', 'hundun'])
        self.assertTrue(finder._light_sequence_supported(bad_route))
        exploring = ComboFinder('aki', 6, 6, drive_meter=0, super_meter=0,
                                explore_light_chains=True)
        found = next(c for c in exploring.iter_combos() if c['moves'] == bad_route)
        self.assertTrue(any('Exploration:' in note for note in found['notes']))

    def test_super_cancel_levels(self):
        finder = ComboFinder('aki')
        # Synthetic timed specials isolate level restrictions from A.K.I.'s
        # individual special moves, whose conditional/juggle timing is absent.
        special = deepcopy(finder.moves['5mp'])
        special['category'] = 'special'
        special['cancel'] = {'super': True}
        for level in (1, 2, 3):
            transition = finder._transition('example', special, f'sa{level}', finder.moves[f'sa{level}'])
            self.assertEqual(transition is not None, level == 3)
        special['category'] = 'od_special'
        for level in (1, 2, 3):
            transition = finder._transition('example', special, f'sa{level}', finder.moves[f'sa{level}'])
            self.assertEqual(transition is not None, level in (2, 3))

    def test_other_character_and_validation(self):
        finder = ComboFinder('aki')
        data = finder.data.copy()
        data['characters'] = {'example': data['characters']['aki']}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'characters.json'
            path.write_text(json.dumps(data))
            other = ComboFinder('EXAMPLE', 2, 2, data_path=path)
            self.assertTrue(list(other.iter_combos()))
        with self.assertRaises(ValueError):
            ComboFinder('missing')
        with self.assertRaises(ValueError):
            ComboFinder('aki', 5, 2)
        with self.assertRaises(ValueError):
            ComboFinder('aki', max_difficulty='unknown')

    def test_difficulty_link_windows_respect_counter_state(self):
        route = ['5mk', '5mp', 'heavy_serpent_lash']
        ratings = []
        for hit_type in ('normal', 'counter'):
            finder = ComboFinder('aki', 3, 3, hit_type=hit_type)
            combo = next(c for c in finder.iter_combos() if c['moves'] == route)
            ratings.append(combo['difficulty'])
        self.assertEqual(ratings[0]['link_windows'][0]['nominal_frames'], 1)
        self.assertEqual(ratings[1]['link_windows'][0]['nominal_frames'], 3)
        self.assertGreater(ratings[0]['score'], ratings[1]['score'])
        self.assertTrue(ratings[0]['estimated'])
        self.assertTrue(any('buffer' in caveat for caveat in ratings[0]['caveats']))

    def test_difficulty_motion_and_target_input_count(self):
        finder = ComboFinder('aki', 1, 3)
        combos = {tuple(c['moves']): c for c in finder.iter_combos()}
        single = combos[('heavy_serpent_lash',)]['difficulty']
        double = combos[('sa3',)]['difficulty']
        od = combos[('od_serpent_lash',)]['difficulty']
        self.assertGreater(double['components']['motions'], single['components']['motions'])
        self.assertEqual(od['components']['simultaneous_buttons'], 1)
        target = combos[('hundun', 'heavy_serpent_lash')]['difficulty']
        self.assertEqual(target['components']['length'], 1)  # Three inputs, two move entries.
        self.assertEqual(target['link_windows'], [])
        self.assertTrue(any('cancel input windows' in caveat for caveat in target['caveats']))

    def test_difficulty_filter_is_inclusive_and_does_not_change_validity(self):
        unfiltered = list(ComboFinder('aki', 2, 4).iter_combos())
        limits = {'easy': 3, 'medium': 7, 'hard': float('inf')}
        for label, limit in limits.items():
            filtered = list(ComboFinder('aki', 2, 4, max_difficulty=label).iter_combos())
            self.assertEqual(filtered, [c for c in unfiltered if c['difficulty']['score'] <= limit])
        self.assertTrue(any(c['difficulty']['label'] == 'medium' for c in unfiltered))
        self.assertTrue(all(c['status'] == 'candidate' for c in unfiltered))

    def test_difficulty_cli_labels_combos_and_adds_metadata(self):
        args = ['combo_finder.py', 'aki', '--min-length', '2', '--max-length', '2',
                '--color', 'never', '--max-difficulty', 'easy']

        def run(*flags):
            output = io.StringIO()
            with patch('sys.argv', args + list(flags)), redirect_stdout(output):
                main()
            return output.getvalue()

        combos = ComboFinder('aki', 2, 2, max_difficulty='easy').get_combo()
        finder = ComboFinder('aki')
        expected = []
        for combo in combos:
            bracket = (f"[{combo['difficulty']['label']} | len={combo['length']} | "
                       f"raw dmg={combo['damage']['raw_total']}]")
            if combo['evidence']['kind'] == 'published_recipe':
                bracket = bracket[:-1] + f" | {combo['evidence']['source_label']}]"
            expected.append(f'{bracket:<36} {finder.format_combo(combo)}')
        self.assertEqual(run().splitlines(), expected)
        self.assertIn('Estimated difficulty: easy', run('-v'))
        self.assertIn('Score breakdown:', run('-v'))
        records = json.loads(run('--json'))
        self.assertEqual(records, combos)

    def test_difficulty_sort_prioritizes_score_over_length(self):
        finder = ComboFinder('aki', 2, 4)
        generated = list(finder.iter_combos())
        combos = finder.get_combo()
        keys = [(c['difficulty']['score'], c['length']) for c in combos]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual({tuple(c['moves']) for c in combos},
                         {tuple(c['moves']) for c in generated})
        # A longer easy route must precede a shorter, harder one.
        self.assertTrue(any(a['length'] > b['length'] and
                            a['difficulty']['score'] < b['difficulty']['score']
                            for a, b in zip(combos, combos[1:])))
        self.assertIs(finder.found_combos, combos)

    def test_random_cli_samples_filtered_routes_without_replacement(self):
        base = ['combo_finder.py', 'aki', '--min-length', '2', '--max-length', '3',
                '--max-difficulty', 'easy', '--color', 'never']

        def run(*flags):
            output = io.StringIO()
            with patch('sys.argv', base + list(flags)), redirect_stdout(output), \
                    patch('sf_combo_finder.combo_finder.random.sample', side_effect=random.Random(42).sample):
                main()
            return output.getvalue()

        records = json.loads(run('--random', '5', '--json'))
        self.assertEqual(len(records), 5)
        self.assertEqual(len({tuple(c['moves']) for c in records}), 5)
        available = ComboFinder('aki', 2, 3, max_difficulty='easy').get_combo()
        self.assertTrue(all(c in available for c in records))
        keys = [(c['difficulty']['score'], c['length']) for c in records]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(run('--random', '5').splitlines()), 5)
        self.assertIn('5 candidates.', run('--random', '5', '-v'))
        self.assertEqual(json.loads(run('--random', '10000', '--json')), available)
        self.assertEqual(json.loads(run('--min-length', '20', '--max-length', '20',
                                        '--random', '5', '--json')), [])

    def test_random_cli_limit_applies_across_characters(self):
        finder = ComboFinder('aki')
        data = deepcopy(finder.data)
        data['characters']['example'] = deepcopy(data['characters']['aki'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'characters.json'
            path.write_text(json.dumps(data))
            output = io.StringIO()
            with patch('sys.argv', ['combo_finder.py', 'all', '--data', str(path),
                                    '--min-length', '2', '--max-length', '2',
                                    '--random', '5', '--json']), redirect_stdout(output):
                main()
            self.assertEqual(len(json.loads(output.getvalue())), 5)

    def test_random_cli_rejects_nonpositive_counts(self):
        for count in ('0', '-1'):
            error = io.StringIO()
            with patch('sys.argv', ['combo_finder.py', '--random', count]), redirect_stdout(io.StringIO()), \
                    redirect_stderr(error), self.assertRaises(SystemExit) as raised:
                main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn('--random must be a positive integer', error.getvalue())

    def test_raw_damage_counts_all_hits_and_resolved_poison(self):
        finder = ComboFinder('aki', 1, 3)
        combos = {tuple(c['moves']): c for c in finder.iter_combos()}
        self.assertEqual(combos[('hundun',)]['damage']['raw_total'], 600)
        lash = finder.moves['heavy_serpent_lash']['damage'][0]
        self.assertEqual(combos[('hundun', 'heavy_serpent_lash')]['damage']['raw_total'], 600 + lash)
        self.assertFalse(combos[('hundun',)]['damage']['scaling_applied'])
        poisoned = ComboFinder('aki', 2, 2, opponent_poisoned=True)
        route = next(c for c in poisoned.iter_combos() if c['moves'] == ['2lp', 'heavy_serpent_lash'])
        self.assertEqual(route['damage']['raw_total'], 300 + 800)
        # Check an earlier move applying poison before the later detonation.
        normal = next(c for c in finder.iter_combos() if c['moves'] == ['od_serpent_lash', '2lp', 'heavy_serpent_lash'])
        self.assertEqual(normal['damage']['raw_total'],
                         sum(finder.moves['od_serpent_lash']['damage']) + 300 + 800)

    def test_no_jumping_excludes_jump_starters_and_preserves_ground_routes(self):
        finder = ComboFinder('aki', 2, 3)
        unfiltered = list(finder.iter_combos())
        grounded = list(ComboFinder('aki', 2, 3, no_jumping=True).iter_combos())
        expected = [c for c in unfiltered if all(finder.moves[key]['category'] != 'jump_normal'
                                                for key in c['moves'])]
        self.assertEqual(grounded, expected)
        self.assertLess(len(grounded), len(unfiltered))
        self.assertTrue(grounded)
        output = io.StringIO()
        with patch('sys.argv', ['combo_finder.py', 'aki', '--min-length', '2', '--max-length', '3',
                                '--no-jumping', '--no-specials', '--random', '5', '--json']), \
                redirect_stdout(output):
            main()
        records = json.loads(output.getvalue())
        self.assertEqual(len(records), 5)
        # Published routes may include Drive Rush system movement between
        # normals; --no-specials excludes specials/supers, not those actions.
        self.assertTrue(all(finder.moves[key]['category'] in ('normal', 'unique', 'target_combo', 'system')
                            for c in records for key in c['moves']))

    def test_od_pulse_has_sourced_followups_without_extra_od_cost(self):
        finder = ComboFinder('aki', 3, 8, documented_only=True)
        combos = list(finder.iter_combos())
        route = next(c for c in combos if c['moves'] == ['od_nightshade_pulse', 'od_nightshade_chaser', 'sa2'])
        self.assertEqual(route['drive_spent'], 2)
        self.assertEqual(route['super_spent'], 2)
        self.assertEqual(route['inputs'], ['214PP', '6HP', '214214P'])
        self.assertEqual(route['damage']['raw_total'], 700 + 800 + 2600)
        self.assertEqual(route['evidence']['kind'], 'published_recipe')
        self.assertTrue(route['evidence']['complete'])
        self.assertTrue(route['evidence']['sources'])
        self.assertEqual(finder._cost(finder.moves['od_nightshade_chaser_burst']), (0, 0))
        self.assertIn('od_nightshade_chaser_burst', finder.moves)

    def test_published_routes_respect_prefix_meter_budget(self):
        finder = ComboFinder('aki', 3, 8, documented_only=True)
        route = ['od_nightshade_pulse', 'drive_rush', '5mp', 'medium_serpent_lash',
                 'drive_rush', '5hk', 'od_cruel_fate', 'sa3']
        combo = next(c for c in finder.iter_combos() if c['moves'] == route)
        self.assertEqual(combo['drive_spent'], 6)
        self.assertEqual(combo['super_spent'], 3)
        self.assertEqual(combo['length'], 8)
        limited = list(ComboFinder('aki', 3, 8, drive_meter=2, documented_only=True).iter_combos())
        self.assertFalse(any('drive_rush' in c['moves'] and c['moves'][0] == 'od_nightshade_pulse'
                             for c in limited))
        zero = list(ComboFinder('aki', 2, 8, drive_meter=0, super_meter=0, documented_only=True).iter_combos())
        self.assertTrue(zero)
        self.assertTrue(all(c['drive_spent'] == c['super_spent'] == 0 for c in zero))
        self.assertFalse(any(c['moves'][-1] in ('drive_rush', 'drive_rush_cancel', 'sinister_slide', 'walk_forward')
                             for c in finder.iter_combos()))

    def test_published_stance_and_corner_routes_need_their_conditions(self):
        midscreen = ComboFinder('aki', 2, 12, opponent_poisoned=True, documented_only=True)
        self.assertTrue(any('walk_forward' in c['moves'] for c in midscreen.iter_combos()))
        self.assertTrue(all(c['conditions']['position'] != 'corner' for c in midscreen.iter_combos()))
        corner = ComboFinder('aki', 2, 12, opponent_poisoned=True, position='corner', documented_only=True)
        self.assertTrue(any('venomous_fang' in c['moves'] for c in corner.iter_combos()))
        self.assertTrue(all(c['conditions']['position'] != 'midscreen' for c in corner.iter_combos()))
        self.assertFalse(any(c['evidence']['recipe_id'] == 'hk_poison_corner_conversion'
                             for c in ComboFinder('aki', 2, 12, position='corner', documented_only=True).iter_combos()))
        counter = ComboFinder('aki', 2, 8, hit_type='counter', documented_only=True)
        self.assertTrue(any(c['moves'] == ['5mp', 'hundun', 'heavy_serpent_lash'] for c in counter.iter_combos()))
        self.assertTrue(all(c['conditions']['hit_type'] == 'counter' for c in counter.iter_combos()))

    def test_airborne_openers_use_only_matching_published_routes(self):
        finder = ComboFinder('aki', 2, 5, opponent_state='airborne')
        combos = list(finder.iter_combos())
        self.assertTrue(combos)
        self.assertTrue(all(c['evidence']['kind'] == 'published_recipe' for c in combos))
        self.assertTrue(all(c['conditions']['opponent_state'] == 'airborne' for c in combos))
        self.assertEqual(list(ComboFinder('aki', 2, 5, opponent_state='airborne', no_jumping=True).iter_combos()), [])
        poison = ComboFinder('aki', 2, 5, opponent_state='airborne', no_jumping=True, opponent_poisoned=True)
        self.assertTrue(any(c['moves'] == ['heavy_serpent_lash', 'medium_serpent_lash'] for c in poison.iter_combos()))

    def test_published_routes_are_not_spliced_and_timing_duplicates_are_removed(self):
        finder = ComboFinder('aki', 2, 8)
        combos = list(finder.iter_combos())
        self.assertEqual(len(combos), len({tuple(c['moves']) for c in combos}))
        published = next(c for c in combos if c['moves'] == ['2lp', '2lp', 'heavy_serpent_lash'])
        self.assertEqual(published['evidence']['kind'], 'published_recipe')
        # An otherwise linkable attack cannot be appended to a recipe ending.
        documented = list(ComboFinder('aki', 2, 8, documented_only=True).iter_combos())
        self.assertFalse(any(c['moves'] == ['5hk', 'sinister_slide', 'heel_strike', '2lp', '2lk']
                             for c in documented))
        self.assertTrue(any('sinister_slide' in c['moves'] for c in documented))

    def test_new_recipe_cli_flags_and_condition_labels(self):
        args = ['combo_finder.py', 'aki', '--min-length', '3', '--max-length', '8',
                '--documented-only', '--no-jumping', '--color', 'never']
        output = io.StringIO()
        with patch('sys.argv', args + ['--json']), redirect_stdout(output):
            main()
        records = json.loads(output.getvalue())
        self.assertTrue(any(c['moves'][0] == 'od_nightshade_pulse' for c in records))
        self.assertTrue(all(c['evidence']['kind'] == 'published_recipe' for c in records))
        output = io.StringIO()
        with patch('sys.argv', args + ['--position', 'any', '--opponent-poisoned', '--random', '3']), redirect_stdout(output):
            main()
        self.assertEqual(len(output.getvalue().splitlines()), 3)
        self.assertTrue(all('midscreen]' in line or 'corner]' in line or
                            'Community guide]' in line for line in output.getvalue().splitlines()))

    def test_invalid_recipe_references_fail_clearly(self):
        finder = ComboFinder('aki')
        data = deepcopy(finder.data)
        data['characters']['aki']['documented_combos'][0]['moves'][0] = 'missing_move'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'characters.json'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Unknown move missing_move'):
                ComboFinder('aki', data_path=path)


if __name__ == '__main__':
    unittest.main()
