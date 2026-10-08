import asyncio
from contextlib import redirect_stderr
from dataclasses import replace
import importlib.util
from io import StringIO
import random
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sf_combo_finder.combo_finder import ComboFinder, main as cli_main
from sf_combo_finder.tui_search import SearchResult, SearchSettings, search_combos, combo_startup
from sf_combo_finder.combo_library import LIBRARY_PATH
from sf_combo_finder.tui_themes import PALETTES, load_theme

HAS_TEXTUAL = importlib.util.find_spec('textual') is not None
if HAS_TEXTUAL:
    from sf_combo_finder.combo_tui import ComboFinderApp, SearchCompleted
    from textual.widgets import Checkbox, DataTable, Input, Select, Static


class BrowserSearchTests(unittest.TestCase):
    def test_all_results_match_existing_engine(self):
        settings = SearchSettings(character='aki', sample_size=None, documented_only=True, max_length=8)
        result = search_combos(settings)
        expected = ComboFinder('aki', 3, 8, documented_only=True).get_combo()
        self.assertEqual(result.total, len(expected))
        self.assertEqual([combo for _, combo in result.rows], expected)

    def test_sample_is_unique_sorted_and_drawn_from_filtered_pool(self):
        settings = SearchSettings(character='aki', max_length=8, sample_size=5,
                                  documented_only=True, no_jumping=True)
        sample = search_combos(settings, rng=random.Random(42))
        pool = search_combos(replace(settings, sample_size=None))
        self.assertEqual(sample.total, pool.total)
        self.assertEqual(len(sample.rows), 5)
        self.assertEqual(len({tuple(combo['moves']) for _, combo in sample.rows}), 5)
        order = [(combo['difficulty']['score'], combo['length']) for _, combo in sample.rows]
        self.assertEqual(order, sorted(order))
        self.assertTrue(all(combo in [c for _, c in pool.rows] for _, combo in sample.rows))
        other = search_combos(settings, rng=random.Random(43))
        self.assertNotEqual([c['moves'] for _, c in sample.rows], [c['moves'] for _, c in other.rows])

    def test_small_pool_returns_every_match(self):
        result = search_combos(SearchSettings(sample_size=1000, documented_only=True))
        self.assertEqual(len(result.rows), result.total)

    def test_conditions_and_meter_are_forwarded(self):
        settings = SearchSettings(character='aki', sample_size=None, documented_only=True,
                                  position='corner', opponent_poisoned=True, max_length=12,
                                  drive_meter=0, super_meter=0)
        result = search_combos(settings)
        self.assertTrue(result.rows)
        for _, combo in result.rows:
            self.assertIn(combo['conditions']['position'], ('corner', 'any'))
            self.assertTrue(combo['conditions']['opponent_poisoned'])
            self.assertEqual(combo['drive_spent'], 0)
            self.assertEqual(combo['super_spent'], 0)

    def test_route_options_change_the_filtered_pool(self):
        settings = SearchSettings(character='aki', min_length=2, max_length=3, sample_size=None)
        baseline = search_combos(settings)
        baseline_routes = {tuple(combo['moves']) for _, combo in baseline.rows}
        for option in ('documented_only', 'no_jumping', 'no_specials',
                       'optimistic_links', 'explore_light_chains'):
            with self.subTest(option=option):
                result = search_combos(replace(settings, **{option: True}))
                routes = {tuple(combo['moves']) for _, combo in result.rows}
                self.assertNotEqual(routes, baseline_routes)
                self.assertTrue(routes)
                if option == 'documented_only':
                    self.assertTrue(all(combo['evidence']['kind'] == 'published_recipe'
                                        for _, combo in result.rows))
                elif option == 'no_jumping':
                    self.assertTrue(all(finder.moves[key]['category'] != 'jump_normal'
                                        for finder, combo in result.rows for key in combo['moves']))
                elif option == 'no_specials':
                    self.assertTrue(all(finder.moves[key]['category'] not in ('special', 'super')
                                        for finder, combo in result.rows for key in combo['moves']))
                else:
                    self.assertTrue(baseline_routes < routes)

    def test_validation_matches_cli(self):
        for settings in (SearchSettings(min_length=7, max_length=3),
                         SearchSettings(drive_meter=7), SearchSettings(sample_size=0),
                         SearchSettings(character='missing')):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                search_combos(settings)

    def test_cancellation_discards_partial_results(self):
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls > 4

        result = search_combos(SearchSettings(sample_size=None), cancelled=cancelled)
        self.assertTrue(result.cancelled)
        self.assertGreater(result.total, 0)
        self.assertEqual(result.rows, [])

    def test_empty_pool(self):
        result = search_combos(SearchSettings(documented_only=True, opponent_state='airborne', no_jumping=True,
                                             min_length=20, max_length=20))
        self.assertEqual(result.total, 0)
        self.assertEqual(result.rows, [])

    def test_cli_prefills_browser_filters(self):
        fake_app = unittest.mock.MagicMock()
        module = SimpleNamespace(ComboFinderApp=fake_app)
        argv = ['combo_finder.py', 'aki', '--tui', '--min-length', '4', '--max-length', '8',
                '--random', '5', '--no-jumping', '--position', 'corner', '--opponent-poisoned',
                '--documented-only', '--sf', '-v']
        with patch.dict('sys.modules', {'sf_combo_finder.combo_tui': module}), patch('sys.argv', argv):
            cli_main()
        settings = fake_app.call_args.args[1]
        self.assertEqual(settings.min_length, 4)
        self.assertEqual(settings.max_length, 8)
        self.assertIsNone(settings.sample_size)
        self.assertEqual(settings.position, 'corner')
        self.assertTrue(settings.no_jumping and settings.opponent_poisoned and settings.documented_only)
        self.assertEqual(fake_app.call_args.kwargs, {'mapped': False, 'show_details': True,
                                                    'library_path': LIBRARY_PATH, 'controller': None})
        fake_app.return_value.run.assert_called_once()

    def test_cli_rejects_json_with_tui(self):
        with patch('sys.argv', ['combo_finder.py', '--tui', '--json']), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as error:
                cli_main()
        self.assertEqual(error.exception.code, 2)


@unittest.skipUnless(HAS_TEXTUAL, 'Install requirements.txt to run Textual interaction tests')
class BrowserInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_switch_updates_rows_details_copy_without_search(self):
        from sf_combo_finder.tui_themes import load_controller
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.json'
            app = ComboFinderApp(settings=SearchSettings(character='ryu', documented_only=True),
                                 preferences_path=path, library_path=None)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.press('ctrl+r')
                await self.finish(app, pilot)
                generation = app.generation
                selected = app.rows[0]
                table = app.query_one('#results', DataTable)
                self.assertEqual(table.cursor_foreground_priority, 'renderable')
                app.query_one('#controller', Select).value = 'playstation'
                await pilot.pause()
                self.assertEqual(app.generation, generation)
                self.assertIs(app.rows[table.cursor_row], selected)
                finder, combo = selected
                expected = finder.format_combo(combo, controller='playstation')
                self.assertEqual(table.get_row_at(table.cursor_row)[1].plain, expected)
                self.assertIn(expected, str(app.query_one('#selected-combo', Static).render()))
                self.assertEqual(load_controller(path), 'playstation')
                with patch.object(app, 'copy_to_clipboard') as copy:
                    app.action_copy_combo()
                    copy.assert_called_once_with(expected)
                app.query_one('#sf-notation', Checkbox).value = True
                await pilot.pause()
                self.assertEqual(table.get_row_at(table.cursor_row)[1].plain,
                                 finder.format_combo(combo, mapped=False))

    async def test_star_hide_reveal_restore_and_reload(self):
        from sf_combo_finder.combo_library import ComboLibrary, combo_identity
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library.json'
            settings = SearchSettings(character='ryu', documented_only=True)
            app = ComboFinderApp(settings=settings, library_path=path, preferences_path=None)
            async with app.run_test(size=(120, 40)) as pilot:
                self.assertFalse(app.has_searched)
                self.assertTrue(app.query_one('#star-combo').disabled)
                await pilot.press('ctrl+r')
                await self.finish(app, pilot)
                combo = app.rows[0][1]
                key = combo_identity(combo)
                await pilot.press('ctrl+s')
                await pilot.pause()
                self.assertEqual(ComboLibrary(path).marks(combo), (True, False))
                self.assertIn('★', app.query_one('#results', DataTable).get_row_at(0)[0].plain)
                await pilot.press('ctrl+x')
                await self.finish(app, pilot)
                self.assertFalse(any(combo_identity(c)==key for _, c in app.rows))
                self.assertEqual(ComboLibrary(path).marks(combo), (True, True))
                app.query_one('#hidden-only', Checkbox).value = True
                await self.finish(app, pilot)
                self.assertTrue(app.rows)
                self.assertTrue(all(combo_identity(c)==key for _, c in app.rows))
                self.assertEqual(str(app.query_one('#hide-combo').label), 'Restore')
                app.query_one('#starred-only', Checkbox).value = True
                await self.finish(app, pilot)
                self.assertTrue(app.rows)
                await pilot.press('ctrl+x')
                await self.finish(app, pilot)
                self.assertFalse(app.rows)
                self.assertEqual(ComboLibrary(path).marks(combo), (True, False))
                app.query_one('#hidden-only', Checkbox).value = False
                await self.finish(app, pilot)
                self.assertTrue(app.rows)
                await pilot.press('ctrl+s')
                await self.finish(app, pilot)
                self.assertFalse(app.rows)
                self.assertEqual(ComboLibrary(path).marks(combo), (False, False))

    async def finish(self, app, pilot):
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

    async def search(self, app, pilot, sample_size=5):
        app.query_one('#random-count', Input).value = '' if sample_size is None else str(sample_size)
        await pilot.click('#search')
        await self.finish(app, pilot)

    async def test_startup_waits_for_search_and_random_count_is_always_blank(self):
        app = ComboFinderApp(settings=SearchSettings(sample_size=5), preferences_path=None)
        with patch('sf_combo_finder.combo_tui.search_combos') as search:
            async with app.run_test(size=(140, 42)) as pilot:
                await pilot.pause()
                self.assertEqual(app.query_one('#random-count', Input).value, '')
                self.assertIsNone(app.settings.sample_size)
                self.assertEqual(app.query_one('#results', DataTable).row_count, 0)
                self.assertIsNone(app.search_worker)
                app.query_one('#documented', Checkbox).value = True
                app.query_one('#sort-by', Select).value = 'damage'
                await pilot.pause()
                await pilot.press('ctrl+n')
                await pilot.pause()
                self.assertEqual(app.generation, 0)
                search.assert_not_called()

    async def test_sort_changes_preserve_selection_without_searching_again(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True, max_length=8),
                             preferences_path=None)
        async with app.run_test(size=(140, 42)) as pilot:
            await self.search(app, pilot)
            generation, count = app.generation, app.match_count
            selected = app.rows[0]
            for field in ('character', 'difficulty', 'length', 'damage', 'startup'):
                app.query_one('#sort-by', Select).value = field
                for order in ('ascending', 'descending'):
                    app.query_one('#sort-order', Select).value = order
                    await pilot.pause()
                    keys = []
                    for finder, combo in app.rows:
                        keys.append(combo_startup(finder, combo) if field == 'startup' else {
                                     'character': app.characters[finder.character]['display_name'].casefold(),
                                     'difficulty': combo['difficulty']['score'], 'length': combo['length'],
                                     'damage': combo['damage']['raw_total']}[field])
                    known = [key for key in keys if key is not None]
                    self.assertEqual(keys, sorted(known, reverse=order == 'descending') +
                                     [None] * (len(keys) - len(known)))
                    self.assertIs(app.rows[app.query_one('#results', DataTable).cursor_row], selected)
                    self.assertEqual(app.generation, generation)
                    self.assertEqual(app.match_count, count)

    async def test_live_dark_themes_preserve_results_and_checkbox_states(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            preferences = Path(directory) / 'preferences.json'
            app = ComboFinderApp(settings=SearchSettings(documented_only=True, no_jumping=True,
                                                        max_length=8, sample_size=5),
                                 preferences_path=preferences)
            async with app.run_test(size=(140, 42)) as pilot:
                await self.search(app, pilot)
                generation = app.generation
                notation = app.query_one('#results', DataTable).get_row_at(0)[1].plain
                self.assertEqual(set(app.available_themes), set(PALETTES))
                for name, palette in PALETTES.items():
                    app.query_one('#color-theme', Select).value = name
                    await pilot.pause()
                    self.assertEqual(app.theme, name)
                    self.assertTrue(app.current_theme.dark)
                    self.assertEqual(app.screen.styles.background.hex.lower(), palette.background)
                    self.assertEqual(app.generation, generation)
                    self.assertEqual(app.query_one('#results', DataTable).get_row_at(0)[1].plain, notation)
                    self.assertTrue(app.query_one('#no-jumping', Checkbox).value)
                    self.assertTrue(app.query_one('#no-jumping', Checkbox).has_class('-on'))
                    if name != 'bagels':
                        self.assertEqual(load_theme(preferences), name)

    async def test_search_details_and_notation(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True, max_length=8, sample_size=5))
        async with app.run_test(size=(140, 42)) as pilot:
            await self.search(app, pilot)
            table = app.query_one('#results', DataTable)
            self.assertEqual(table.row_count, 5)
            self.assertFalse(app.query_one('#details').display)
            self.assertIn('[', table.get_row_at(0)[0].plain)
            self.assertGreater(app.query_one('#sidebar').region.x, table.region.x)
            self.assertGreater(app.query_one('#selection-panel').region.y, table.region.y)
            await pilot.press('down')
            finder, combo = app.rows[table.cursor_row]
            self.assertIn(finder.format_combo(combo, mapped=True),
                          str(app.query_one('#selected-combo', Static).render()))
            self.assertIn(f"{combo['drive_spent']}/{app.settings.drive_meter}",
                          str(app.query_one('#selection-meter', Static).render()))
            self.assertIn(f"{table.cursor_row + 1}/{len(app.rows)}",
                          app.query_one('#selection-panel').border_subtitle)
            await pilot.press('up')
            await pilot.press('ctrl+d')
            self.assertTrue(app.query_one('#details').display)
            self.assertIn('Transitions:', str(app.query_one('#detail-text', Static).render()))
            app.query_one('#sf-notation', Checkbox).value = True
            await pilot.pause()
            finder, combo = app.rows[0]
            self.assertEqual(table.get_row_at(0)[1].plain, finder.format_combo(combo, mapped=False))
            with patch.object(app, 'copy_to_clipboard') as copy:
                app.action_copy_combo()
                copy.assert_called_once_with(finder.format_combo(combo, mapped=False))

    async def test_route_checkbox_refreshes_without_search_and_keeps_panel_open(self):
        app = ComboFinderApp(settings=SearchSettings(character='aki', min_length=2, max_length=3,
                                                    sample_size=5))
        async with app.run_test(size=(100, 40)) as pilot:
            await self.search(app, pilot)
            baseline_count, generation = app.match_count, app.generation
            await pilot.press('ctrl+b')
            app.query_one('#no-jumping', Checkbox).scroll_visible()
            await pilot.pause()
            await pilot.click('#no-jumping')
            await self.finish(app, pilot)
            self.assertTrue(app.settings.no_jumping)
            self.assertGreater(app.generation, generation)
            self.assertLess(app.match_count, baseline_count)
            self.assertTrue(app.query_one('#sidebar').display)
            self.assertTrue(all(finder.moves[key]['category'] != 'jump_normal'
                                for finder, combo in app.rows for key in combo['moves']))

    async def test_invalid_filters_then_recovery(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True))
        async with app.run_test(size=(120, 36)) as pilot:
            await self.search(app, pilot)
            app.query_one('#min-length', Input).value = '9'
            await pilot.press('ctrl+r')
            await self.finish(app, pilot)
            self.assertIn('Search failed', str(app.query_one('#status', Static).render()))
            self.assertEqual(app.query_one('#results', DataTable).row_count, 0)
            app.query_one('#min-length', Input).value = '3'
            await pilot.press('ctrl+r')
            await self.finish(app, pilot)
            self.assertGreater(app.query_one('#results', DataTable).row_count, 0)

    async def test_empty_results_and_stale_messages(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True, min_length=20, max_length=20))
        async with app.run_test(size=(120, 36)) as pilot:
            await self.search(app, pilot)
            self.assertIn('No matching combos', str(app.query_one('#status', Static).render()))
            self.assertIn('No combo selected.', str(app.query_one('#selected-combo', Static).render()))
            self.assertEqual(app.query_one('#selection-panel').border_subtitle, '')
            app.post_message(SearchCompleted(app.generation - 1, None, 'stale error'))
            await pilot.pause()
            self.assertNotIn('stale error', str(app.query_one('#status', Static).render()))

    async def test_cancel_background_search(self):
        def slow_search(settings, data_path, *, cancelled, progress, library):
            while not cancelled():
                time.sleep(0.005)
            return SearchResult(cancelled=True)

        with patch('sf_combo_finder.combo_tui.search_combos', slow_search):
            app = ComboFinderApp()
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.click('#search')
                await pilot.pause()
                await pilot.press('escape')
                await asyncio.sleep(0.02)
                await pilot.pause()
                self.assertIn('Search cancelled', str(app.query_one('#status', Static).render()))
                self.assertEqual(app.rows, [])

    async def test_help_and_shuffle_from_all_results(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True, sample_size=None))
        async with app.run_test(size=(100, 30)) as pilot:
            await self.search(app, pilot, sample_size=None)
            await pilot.press('f1')
            self.assertIsNot(app.screen, app.screen_stack[0])
            await pilot.press('escape')
            await pilot.press('ctrl+n')
            await self.finish(app, pilot)
            self.assertEqual(app.query_one('#random-count', Input).value, '25')

    async def test_small_terminal_filter_toggle(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True))
        async with app.run_test(size=(80, 24)) as pilot:
            await self.search(app, pilot)
            self.assertFalse(app.query_one('#filters').display)
            self.assertFalse(app.query_one('#sidebar').display)
            await pilot.press('ctrl+b')
            self.assertTrue(app.query_one('#filters').display)
            self.assertTrue(app.query_one('#sidebar').display)
            await pilot.press('ctrl+r')
            await self.finish(app, pilot)
            self.assertFalse(app.query_one('#filters').display)
            self.assertFalse(app.query_one('#sidebar').display)
            self.assertGreater(app.query_one('#results', DataTable).row_count, 0)


if __name__ == '__main__':
    unittest.main()
