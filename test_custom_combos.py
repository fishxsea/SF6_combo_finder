import asyncio
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sf_combo_finder.combo_finder import DATA_PATH
from sf_combo_finder.combo_library import ComboLibrary
from sf_combo_finder.custom_combos import CustomCombos, normalize_inputs
from sf_combo_finder.tui_search import SearchSettings, sort_combo_rows

HAS_TEXTUAL = importlib.util.find_spec('textual') is not None
if HAS_TEXTUAL:
    from sf_combo_finder.combo_tui import ComboFinderApp
    from sf_combo_finder.tui_custom_combos import CustomCombosScreen
    from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static, TextArea


class CustomComboStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_PATH.read_text(encoding='utf-8'))

    def test_save_edit_delete_and_other_instances_preserve_sf_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'custom_combos.json'
            first, second = CustomCombos(path), CustomCombos(path)
            aki = first.save('AKI', 'My route', ['2lp', 'LP > 236HP'])
            ryu = second.save('ryu', 'Other route', ['2MP', '623HP'])
            first.save('aki', 'Extended', ['2LP', '5LP', '236HP', '236236P'], entry_id=aki['id'])
            loaded = CustomCombos(path)
            self.assertEqual(len(loaded.entries), 2)
            self.assertEqual(loaded.entries[0]['inputs'], ['2LP', '5LP', '236HP', '236236P'])
            second.delete(ryu['id'])
            self.assertEqual(CustomCombos(path).entries, loaded.entries[:1])

    def test_invalid_or_failed_saves_preserve_existing_file_and_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.json'
            store = CustomCombos(path)
            store.save('aki', 'Saved', ['2LP'])
            before, entries = path.read_bytes(), deepcopy(store.entries)
            for inputs in ([], [''], ['2LP > ']):
                with self.assertRaises(ValueError):
                    store.save('aki', '', inputs)
            with patch('sf_combo_finder.custom_combos.tempfile.NamedTemporaryFile', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.save('aki', '', ['5HP'])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.entries, entries)
            path.write_text('broken json', encoding='utf-8')
            with self.assertRaises(ValueError):
                store.save('aki', '', ['5HP'])
            self.assertEqual(path.read_text(), 'broken json')

    def test_custom_rows_filter_without_mutating_or_inventing_measured_stats(self):
        store, library = CustomCombos(None), ComboLibrary(None)
        store.save('aki', 'Grounded', ['2LP', '5LP', '236HP'])
        store.save('aki', 'Jump', ['j.HP', '5HP', '236HP'])
        store.save('ryu', 'Other fighter', ['2MP', '5MP', '623HP'])
        before = deepcopy(self.data)
        settings = SearchSettings(character='aki', show_custom=True)
        rows = store.rows(self.data, settings, library)
        self.assertEqual(len(rows), 2)
        for _, combo in rows:
            self.assertEqual(combo['evidence']['kind'], 'custom')
            self.assertEqual(combo['difficulty']['label'], 'custom')
            self.assertFalse(combo['difficulty']['estimated'])
            self.assertIsNone(combo['damage']['raw_total'])
        self.assertEqual(len(store.rows(self.data, SearchSettings(character='aki', show_custom=True,
                                                                  no_jumping=True), library)), 1)
        self.assertEqual(store.rows(self.data, SearchSettings(character='aki'), library), [])
        self.assertEqual(len(store.rows(self.data, SearchSettings(character='aki', show_custom=True,
                                                                 documented_only=True), library)), 2)
        library.toggle(rows[0][1], 'hidden')
        self.assertEqual(len(store.rows(self.data, settings, library)), 1)
        self.assertEqual(self.data, before)
        for field in ('character', 'difficulty', 'length', 'damage', 'startup'):
            for descending in (False, True):
                self.assertEqual(len(sort_combo_rows(rows, field, descending=descending)), 2)

    def test_custom_only_ignores_length_limits_but_including_custom_combos_keeps_them(self):
        store, library = CustomCombos(None), ComboLibrary(None)
        store.save('aki', 'Long route', ['2LP', '5LP', '5LP', '236HP', '5LP', '5LP', '214HP'])
        store.save('aki', 'Short route', ['2LP'])
        store.save('aki', 'In range', ['2LP', '5LP', '236HP'])
        settings = SearchSettings(character='aki', custom_only=True)
        self.assertEqual({combo['custom_name'] for _, combo in store.rows(self.data, settings, library)},
                         {'Long route', 'Short route', 'In range'})
        mixed = replace(settings, custom_only=False, show_custom=True)
        self.assertEqual([combo['custom_name'] for _, combo in store.rows(self.data, mixed, library)],
                         ['In range'])

    def test_notes_persist_and_old_combos_without_notes_can_be_edited(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.json'
            legacy = dict(id='legacy', character='aki', name='Corner route', inputs=['2LP'])
            path.write_text(json.dumps({'version': 1, 'combos': [legacy]}), encoding='utf-8')
            store = CustomCombos(path)
            settings = SearchSettings(character='aki', custom_only=True)
            self.assertEqual(store.rows(self.data, settings, ComboLibrary(None))[0][1]['custom_description'], '')
            notes = 'Needs poison in the corner.\nDelay the last hit. [Tip] → create space.'
            store.save('aki', 'Corner route', ['2LP'], entry_id='legacy', description=notes)
            restored = CustomCombos(path)
            self.assertEqual(restored.entries[0]['description'], notes)
            self.assertEqual(restored.rows(self.data, settings, ComboLibrary(None))[0][1]['custom_description'], notes)
            restored.save('aki', 'Renamed', ['2LP'], entry_id='legacy')
            self.assertEqual(CustomCombos(path).entries[0]['description'], notes)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                restored.save('aki', 'Renamed', ['2LP'], entry_id='legacy', description=['invalid'])
            self.assertEqual(path.read_bytes(), before)
            restored.save('aki', 'Renamed', ['2LP'], entry_id='legacy', description='')
            self.assertEqual(CustomCombos(path).entries[0]['description'], '')


@unittest.skipUnless(HAS_TEXTUAL, 'Textual required')
class CustomComboInteractionTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self, path=None, **kwargs):
        return ComboFinderApp(preferences_path=None, library_path=None,
                              custom_combos_path=path, **kwargs)

    async def click(self, app, pilot, selector):
        # Editing a combo animates a scroll to its name. Let that finish before
        # scrolling to the next target so it cannot move during the click.
        await pilot.wait_for_scheduled_animations()
        app.screen.query_one(selector).scroll_visible(animate=False)
        await pilot.pause()
        self.assertTrue(await pilot.click(selector))

    async def test_notes_can_be_added_edited_displayed_and_carried_into_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.json'
            saved = CustomCombos(path).save('aki', 'Corner route', ['2LP', '5LP', '236HP'])
            app = self.make_app(path, settings=SearchSettings(character='aki'))
            async with app.run_test(size=(140, 80)) as pilot:
                await self.click(app, pilot, '#custom-combos')
                await self.click(app, pilot, '#custom-edit')
                editor = app.screen.query_one('#custom-notes', TextArea)
                self.assertEqual(editor.text, '')
                editor.load_text('Needs poison.')
                editor.focus()
                await pilot.press('end', 'enter', *list('Delay the last hit. [Tip]'))
                notes = 'Needs poison.\nDelay the last hit. [Tip]'
                self.assertEqual(editor.text, notes)
                self.assertIsNone(app.search_worker)
                await pilot.press('ctrl+s')
                await pilot.pause()
                self.assertEqual(CustomCombos(path).entries[0]['description'], notes)
                self.assertEqual(CustomCombos(path).entries[0]['id'], saved['id'])
                await self.click(app, pilot, '#custom-close')
                await pilot.pause()
                self.assertIn(notes, str(app.query_one('#detail-text', Static).render()))
                await pilot.click('#extend-combo')
                self.assertEqual(app.screen.query_one('#custom-notes', TextArea).text, notes)
                await self.click(app, pilot, '#custom-new')
                self.assertEqual(app.screen.query_one('#custom-notes', TextArea).text, '')
                app.screen.query_one('#custom-preset', Select).value = '0'
                await pilot.pause()
                self.assertEqual(app.screen.query_one('#custom-notes', TextArea).text, notes)
                await self.click(app, pilot, '#custom-close')
            restored = self.make_app(path, settings=SearchSettings(character='aki'))
            async with restored.run_test(size=(100, 32)) as pilot:
                restored.query_one('#custom-only', Checkbox).value = True
                await pilot.pause()
                self.assertIn(notes, str(restored.query_one('#detail-text', Static).render()))
                await pilot.press('ctrl+b')
                await self.click(restored, pilot, '#custom-combos')
                await self.click(restored, pilot, '#custom-edit')
                editor = restored.screen.query_one('#custom-notes', TextArea)
                self.assertEqual(editor.text, notes)
                editor.load_text('')
                await self.click(restored, pilot, '#custom-save')
                await self.click(restored, pilot, '#custom-close')
                await pilot.pause()
                self.assertNotIn('NOTES / EXPLANATION', str(restored.query_one('#detail-text', Static).render()))
                self.assertEqual(CustomCombos(path).entries[0]['description'], '')

    async def test_custom_only_without_search_respects_filters_sampling_and_marks(self):
        app = self.make_app(settings=SearchSettings(character='ryu', min_length=2, max_length=3))
        app.custom_combos.save('ryu', 'Grounded', ['2LP', '5LP', '236HP'])
        app.custom_combos.save('ryu', 'Jump', ['j.HP', '5HP', '236HP'])
        app.custom_combos.save('aki', 'Other fighter', ['2LP', '5LP', '236HP'])
        with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
            async with app.run_test(size=(140, 80)) as pilot:
                app.query_one('#custom-only', Checkbox).value = True
                await pilot.pause()
                self.assertFalse(app.query_one('#show-custom', Checkbox).value)
                self.assertEqual({combo['custom_name'] for _, combo in app.rows}, {'Grounded', 'Jump'})
                app.query_one('#no-jumping', Checkbox).value = True
                await pilot.pause()
                self.assertEqual([combo['custom_name'] for _, combo in app.rows], ['Grounded'])
                app.query_one('#no-jumping', Checkbox).value = False
                app.query_one('#random-count', Input).value = '1'
                await app.action_search()
                await pilot.pause()
                self.assertEqual(app.match_count, 2)
                self.assertEqual(len(app.rows), 1)
                self.assertFalse(app.query_one('#shuffle', Button).disabled)
                await app.action_shuffle()
                await pilot.pause()
                self.assertEqual(len(app.rows), 1)
                self.assertEqual(app.rows[0][1]['evidence']['kind'], 'custom')
                await app.action_star_combo()
                app.query_one('#starred-only', Checkbox).value = True
                await pilot.pause()
                self.assertEqual(app.match_count, 1)
                await app.action_hide_combo()
                await pilot.pause()
                self.assertEqual(app.rows, [])
                app.query_one('#hidden-only', Checkbox).value = True
                await pilot.pause()
                self.assertEqual(len(app.rows), 1)
                app.query_one('#custom-only', Checkbox).value = False
                await pilot.pause()
                self.assertEqual(app.rows, [])
                search.assert_not_called()

    async def test_custom_only_loads_saved_routes_outside_default_length_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.json'
            store = CustomCombos(path)
            store.save('aki', 'Create space in corner. Needs poison',
                       ['2LP', '5LP', '5LP', '236HP', '5LP', '5LP', '214HP'])
            store.save('aki', 'One input', ['2LP'])
            app = self.make_app(path)
            with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
                async with app.run_test(size=(140, 80)) as pilot:
                    app.query_one('#custom-only', Checkbox).value = True
                    await pilot.pause()
                    self.assertEqual({combo['length'] for _, combo in app.rows}, {1, 7})
                    self.assertEqual(app.match_count, 2)
                    self.assertEqual(app.query_one('#min-length', Input).value, '3')
                    self.assertEqual(app.query_one('#max-length', Input).value, '5')
                    self.assertEqual(str(app.query_one('#show-custom', Checkbox).label),
                                     'Include custom combos')
                    await app.action_search()
                    await pilot.pause()
                    self.assertEqual(app.match_count, 2)
                    search.assert_not_called()

    async def test_custom_only_toggles_cached_results_without_another_search(self):
        app = self.make_app(settings=SearchSettings(character='ryu', documented_only=True,
                                                   min_length=2, max_length=8))
        app.custom_combos.save('ryu', 'My route', ['2LP', '5LP', '236HP'])
        async with app.run_test(size=(140, 80)) as pilot:
            await app.action_search()
            await asyncio.wait_for(app.workers.wait_for_complete(), 30)
            await pilot.pause()
            builtin_total = app.match_count
            self.assertGreater(builtin_total, 0)
            with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
                app.query_one('#show-custom', Checkbox).value = True
                await pilot.pause()
                self.assertEqual(app.match_count, builtin_total + 1)
                app.query_one('#custom-only', Checkbox).value = True
                await pilot.pause()
                self.assertEqual(app.match_count, 1)
                self.assertEqual(app.rows[0][1]['custom_name'], 'My route')
                app.query_one('#show-custom', Checkbox).value = False
                await pilot.pause()
                self.assertEqual(app.match_count, 1)
                await app.action_search()
                await app.action_shuffle()
                await pilot.pause()
                self.assertEqual(app.match_count, 1)
                app.query_one('#custom-only', Checkbox).value = False
                await pilot.pause()
                self.assertEqual(app.match_count, builtin_total)
                self.assertTrue(all(combo['evidence']['kind'] != 'custom' for _, combo in app.rows))
                search.assert_not_called()

    async def test_click_buttons_and_full_motions_save_then_reload_in_combo_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.json'
            app = self.make_app(path, settings=SearchSettings(character='aki'))
            async with app.run_test(size=(140, 80)) as pilot:
                await self.click(app, pilot, '#custom-combos')
                self.assertIsInstance(app.screen, CustomCombosScreen)
                app.screen.query_one('#custom-name', Input).value = 'My poison route'
                for selector in ('#custom-dir-2', '#custom-dir-3', '#custom-dir-6',
                                 '#custom-attack-HP', '#custom-next', '#custom-dir-2',
                                 '#custom-attack-LP', '#custom-next', '#custom-motion-214214', '#custom-attack-K'):
                    await pilot.click(selector)
                self.assertIn('↓↘→RB', str(app.screen.query_one('#custom-preview', Static).render()))
                await pilot.click('#custom-save')
                await pilot.pause()
                self.assertEqual(CustomCombos(path).entries[0]['inputs'], ['236HP', '2LP', '214214K'])
                await pilot.click('#custom-close')
                await pilot.pause()
                self.assertTrue(app.query_one('#show-custom', Checkbox).value)
                self.assertEqual(len(app.rows), 1)
                row = app.query_one('#results', DataTable).get_row_at(0)
                self.assertIn('Custom combo', str(row[3]))
                self.assertIn('not recorded', str(app.query_one('#detail-text', Static).render()))
            restored = self.make_app(path, settings=SearchSettings(character='aki'))
            async with restored.run_test(size=(140, 80)) as pilot:
                restored.query_one('#show-custom', Checkbox).value = True
                await pilot.pause()
                self.assertEqual(restored.rows[0][1]['inputs'], ['236HP', '2LP', '214214K'])

    async def test_builder_tracks_controller_and_sf_notation_without_changing_saved_inputs(self):
        app = self.make_app(settings=SearchSettings(character='aki'), controller='playstation')
        async with app.run_test(size=(140, 80)) as pilot:
            await self.click(app, pilot, '#custom-combos')
            screen = app.screen
            self.assertEqual(str(screen.query_one('#custom-attack-LP', Button).label), '□')
            await pilot.click('#custom-motion-236')
            await pilot.click('#custom-attack-LP')
            for mode, label, expected in [('sf', 'LP', '236LP'), ('xbox', 'X', '↓↘→X'),
                                           ('playstation', '□', '↓↘→□')]:
                screen.query_one('#custom-mode', Select).value = mode
                await pilot.pause()
                self.assertEqual(str(screen.query_one('#custom-attack-LP', Button).label), label)
                self.assertIn(expected, str(screen.query_one('#custom-preview', Static).render()))
                self.assertEqual(screen.draft, '236LP')
            await pilot.click('#custom-next')
            await pilot.click('#custom-attack-LP')
            await pilot.click('#custom-attack-MP')
            self.assertEqual(screen.draft, 'LP+MP')
            await pilot.click('#custom-save')
            self.assertEqual(app.custom_combos.entries[0]['inputs'], ['236LP', '5LP+MP'])

    async def test_generated_combo_can_be_loaded_extended_and_saved_without_changing_original(self):
        app = self.make_app(settings=SearchSettings(character='aki', documented_only=True,
                                                   max_length=8))
        async with app.run_test(size=(140, 80)) as pilot:
            app.query_one('#random-count', Input).value = '5'
            await pilot.click('#search')
            await pilot.pause()
            await asyncio.wait_for(app.workers.wait_for_complete(), 30)
            await pilot.pause()
            finder, original = app.rows[0]
            before = deepcopy(original)
            await pilot.click('#extend-combo')
            screen = app.screen
            self.assertEqual(screen.inputs, normalize_inputs(original['inputs']))
            self.assertEqual(screen.character, finder.character)
            await pilot.click('#custom-motion-236')
            await pilot.click('#custom-attack-HP')
            await pilot.click('#custom-save')
            self.assertEqual(app.custom_combos.entries[0]['inputs'], normalize_inputs(original['inputs']) + ['236HP'])
            self.assertEqual(original, before)
            await pilot.click('#custom-new')
            screen.query_one('#custom-preset', Select).value = '0'
            await pilot.pause()
            self.assertEqual(screen.inputs, normalize_inputs(original['inputs']))
            await pilot.click('#custom-close')
            await pilot.pause()
            self.assertTrue(any(combo['evidence']['kind'] == 'custom' for _, combo in app.combo_pool))

    async def test_edit_delete_and_shortcuts_work_in_small_terminal(self):
        app = self.make_app(settings=SearchSettings(character='aki', min_length=1))
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press('ctrl+b')
            await self.click(app, pilot, '#custom-combos')
            for selector in ('#custom-attack-LP', '#custom-next', '#custom-motion-214', '#custom-attack-HK'):
                await self.click(app, pilot, selector)
            await pilot.press('ctrl+s')
            await pilot.pause()
            self.assertEqual(len(app.custom_combos.entries), 1)
            original_id = app.custom_combos.entries[0]['id']
            await pilot.press('ctrl+r', 'ctrl+n', 'ctrl+b', 'ctrl+d', 'ctrl+t')
            self.assertIsInstance(app.screen, CustomCombosScreen)
            self.assertIsNone(app.search_worker)
            await self.click(app, pilot, '#custom-edit')
            app.screen.query_one('#custom-name', Input).value = 'Edited route'
            await self.click(app, pilot, '#custom-motion-236236')
            await self.click(app, pilot, '#custom-attack-P')
            await pilot.press('ctrl+s')
            await pilot.pause()
            self.assertEqual(len(app.custom_combos.entries), 1)
            self.assertEqual(app.custom_combos.entries[0]['id'], original_id)
            self.assertEqual(app.custom_combos.entries[0]['inputs'], ['5LP', '214HK', '236236P'])
            await self.click(app, pilot, '#custom-delete')
            await pilot.pause()
            self.assertEqual(app.custom_combos.entries, [])
            await pilot.press('escape')
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
            self.assertEqual(app.rows, [])
