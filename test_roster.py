from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sf_combo_finder.combo_finder import ComboFinder, DATA_PATH, main
from import_roster import SOURCE_DIR, convert_character, import_roster


class RosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_PATH.read_text(encoding='utf-8'))
        cls.levels = json.loads((SOURCE_DIR / 'sa-levels.json').read_text(encoding='utf-8'))

    def test_released_roster_has_data_not_placeholders(self):
        self.assertEqual(set(self.data['characters']), set(self.levels))
        self.assertEqual(len(self.data['characters']), 31)
        for key, character in self.data['characters'].items():
            with self.subTest(character=key):
                self.assertGreater(len(character['moves']), 30)
                finder = ComboFinder(key, 3, 5, data=self.data)
                self.assertIsNotNone(next(finder.iter_combos(), None))
                if key != 'aki':
                    source = json.loads((SOURCE_DIR / f'{key}.json').read_text(encoding='utf-8'))
                    originals = [m for m in character['moves'].values() if not m.get('documented_import')]
                    self.assertEqual(len(originals), len(source['moves']))
                    self.assertEqual({m['source_index'] for m in originals},
                                     set(range(len(source['moves']))))
                    self.assertEqual(character['data_source']['license'], 'CC-BY-SA-4.0')
                    self.assertFalse(character['combo_search']['coverage']['complete'])

    def test_import_is_reproducible_and_preserves_aki(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'characters.json'
            path.write_text(json.dumps(self.data))
            data = import_roster(data_path=path)
            self.assertEqual(data['characters']['aki'], self.data['characters']['aki'])
            self.assertEqual(data, self.data)

    def test_aki_is_rebuilt_from_its_character_file(self):
        snapshot = json.loads((SOURCE_DIR / 'aki.json').read_text(encoding='utf-8'))
        self.assertEqual(snapshot['id'], 'aki')
        self.assertEqual({key: value for key, value in snapshot.items() if key != 'id'},
                         self.data['characters']['aki'])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'characters.json'
            data = deepcopy(self.data)
            del data['characters']['aki']
            path.write_text(json.dumps(data), encoding='utf-8')
            rebuilt = import_roster(data_path=path)
            self.assertEqual(rebuilt, self.data)

    def test_aki_character_file_edits_are_imported(self):
        snapshot = json.loads((SOURCE_DIR / 'aki.json').read_text(encoding='utf-8'))
        snapshot['moves']['2lp'].setdefault('notes', []).append('Reviewed source-file edit.')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / 'characters.json'
            path.write_text(json.dumps(self.data), encoding='utf-8')
            sources = directory / 'sources'
            sources.mkdir()
            (sources / 'aki.json').write_text(json.dumps(snapshot), encoding='utf-8')
            (sources / 'sa-levels.json').write_text(json.dumps(self.levels), encoding='utf-8')
            rebuilt = import_roster(source_dir=sources, data_path=path)
            self.assertIn('Reviewed source-file edit.', rebuilt['characters']['aki']['moves']['2lp']['notes'])

    def test_charge_air_variants_and_command_grabs_are_excluded(self):
        for key in self.levels:
            if key == 'aki':
                continue
            finder = ComboFinder(key, data=self.data)
            for move in finder.moves.values():
                with self.subTest(character=key, move=move['name']):
                    if ('[' in move['input']['sf'] or 'throw' in move.get('properties', [])
                            or any('Air-only' in reason for reason in move['search_exclusions'])):
                        self.assertFalse(finder._eligible(move))
                    if move['category'] in ('special', 'od_special'):
                        self.assertNotEqual(move['hit']['state'], 'normal')
        mai = self.data['characters']['mai']['moves']
        self.assertTrue(any('Flame' in m['name'] and not m['search_eligible'] for m in mai.values()))

    def test_knockdown_pc_values_do_not_become_grounded_links(self):
        finder = ComboFinder('cammy', hit_type='punish_counter', data=self.data)
        move, _ = finder._resolve(finder.moves['5hk'], False, True)
        self.assertEqual(move['hit']['advantage'], 47)
        self.assertNotEqual(move['hit']['state'], 'normal')
        self.assertIsNone(finder._transition('5hk', move, '2lp', finder.moves['2lp']))

    def test_imported_cancel_delays_reduce_budget(self):
        finder = ComboFinder('juri', data=self.data)
        move = finder.moves['5mp']
        naive = move['hit']['advantage'] + move['active_frames'] - 1 + move['recovery_on_hit']
        self.assertLess(finder._cancel_budget(move), naive)
        delayed = dict(move, cancel=dict(move['cancel'], hitstun_budget=3))
        self.assertIsNone(finder._transition('5mp', delayed, '214lk', finder.moves['214lk']))

    def test_imported_long_light_strings_stay_bounded(self):
        for character in ('ryu', 'dhalsim', 'yasmine', 'zangief'):
            finder = ComboFinder(character, data=self.data)
            key = '1lk' if character == 'dhalsim' else '2lp'
            self.assertTrue(finder._is_light(key))
            self.assertFalse(finder._light_sequence_supported([key, key, key]))

    def test_jamie_baseline_uses_explicit_dl0_damage(self):
        move = self.data['characters']['jamie']['moves']['2lp']
        self.assertEqual(move['damage'], [225])
        self.assertIn('DL0', move['name'])
        self.assertTrue(move['search_eligible'])
        self.assertTrue(any('DL4' in m['name'] and not m['search_eligible']
                            for m in self.data['characters']['jamie']['moves'].values()))

    def test_yasmine_missing_values_are_not_fabricated(self):
        source = json.loads((SOURCE_DIR / 'yasmine.json').read_text(encoding='utf-8'))
        character = self.data['characters']['yasmine']
        for move in character['moves'].values():
            if source['moves'][move['source_index']]['startup'] is None:
                self.assertIsNone(move['startup'])
                self.assertFalse(move['search_eligible'])

    def test_source_attribution_is_in_results(self):
        combo = next(c for c in ComboFinder('ryu', data=self.data).iter_combos()
                     if c['evidence']['kind'] != 'published_recipe')
        self.assertEqual(combo['evidence']['license'], 'CC-BY-SA-4.0')
        self.assertIn('SuperCombo', combo['evidence']['provider'])
        self.assertTrue(combo['evidence']['sources'])

    def test_list_characters_text_and_json(self):
        for json_output in (False, True):
            output = StringIO()
            args = ['combo_finder.py', '--list-characters'] + (['--json'] if json_output else [])
            with patch('sys.argv', args), redirect_stdout(output):
                main()
            if json_output:
                roster = json.loads(output.getvalue())
                self.assertEqual(len(roster), 31)
                self.assertIn({'id': 'chunli', 'name': 'Chun-Li'}, roster)
            else:
                self.assertIn('Dee Jay', output.getvalue())
                self.assertIn('yasmine', output.getvalue())

    def test_shared_data_is_read_only_during_search(self):
        before = deepcopy(self.data)
        finder = ComboFinder('ryu', data=self.data)
        self.assertIs(finder.data, self.data)
        list(itertools.islice(finder.iter_combos(), 10))
        self.assertEqual(self.data, before)

    def test_ambiguous_duplicates_cannot_enter_generation(self):
        source = json.loads((SOURCE_DIR / 'ryu.json').read_text(encoding='utf-8'))
        normal = next(m for m in source['moves'] if (m.get('input') or {}).get('numpad') == '5MP')
        source['moves'] = [deepcopy(normal), deepcopy(normal)]
        converted = convert_character(source, self.levels['ryu'])
        self.assertEqual(len(converted['moves']), 2)
        self.assertTrue(all(not m['search_eligible'] for m in converted['moves'].values()))


if __name__ == '__main__':
    unittest.main()
