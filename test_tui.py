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
from sf_combo_finder.tui_search import (SearchResult, SearchSettings, search_combos,
                                      search_route_pool, filter_route_pool,
                                      combo_startup, combo_poison_notes)
from sf_combo_finder.combo_library import ComboLibrary, LIBRARY_PATH
from sf_combo_finder.tui_themes import PALETTES, load_theme

HAS_TEXTUAL = importlib.util.find_spec('textual') is not None
if HAS_TEXTUAL:
    from sf_combo_finder.combo_tui import ComboFinderApp, SearchCompleted
    from sf_combo_finder.tui_slider import IntegerSlider
    from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static


class BrowserSearchTests(unittest.TestCase):
    def test_poison_marker_distinguishes_interactions_from_ordinary_normals(self):
        for starting_poison in (False, True):
            finder = ComboFinder('aki', opponent_poisoned=starting_poison)
            self.assertEqual(combo_poison_notes(finder, {'moves': ['5mk', 'hundun']}), [])
            self.assertEqual(combo_poison_notes(finder, {'moves': ['nightshade_pulse']}), [])
            notes = combo_poison_notes(finder, {'moves': ['2lp', 'heavy_serpent_lash']})
            self.assertEqual(len(notes), 1)
            self.assertIn('Heavy Serpent Lash', notes[0])
            self.assertIn('damage, hit state/advantage', notes[0])
            self.assertIn('poison detonation', notes[0])
            self.assertNotIn('requires', notes[0])

    def test_poison_marker_reports_published_starting_requirement(self):
        finder = ComboFinder('aki')
        notes = combo_poison_notes(finder, {'moves': ['5mp'],
                                           'evidence': {'kind': 'published_recipe'},
                                           'conditions': {'opponent_poisoned': True}})
        self.assertEqual(notes, ['This published route requires the opponent to start poisoned.'])
        self.assertEqual(combo_poison_notes(ComboFinder('ryu'),
                                          {'moves': ['5mp'], 'evidence': {'kind': 'published_recipe'},
                                           'conditions': {'opponent_poisoned': True}}), [])

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

    def test_documented_cache_never_enumerates_generated_routes(self):
        library = ComboLibrary(None)
        for minimum, maximum in ((3, 8), (20, 20)):
            settings = SearchSettings(documented_only=True, min_length=minimum,
                                      max_length=maximum)
            expected = search_combos(settings, library=library)
            # Fail immediately if the cache enters the generated-search path.
            with patch.object(ComboFinder, '_eligible',
                              side_effect=AssertionError('Generated search in published-only mode')):
                result = search_route_pool(settings, library=library)
            self.assertEqual(result.total, expected.total)
            actual = filter_route_pool(result.route_pool, settings, library)
            def routes(rows):
                return {(c['character'], tuple(c['moves']), c['conditions']['position']): c
                        for _, c in rows}
            self.assertEqual(routes(actual), routes(expected.rows))

    def test_cache_searches_only_the_selected_character_and_exploration_options(self):
        library = ComboLibrary(None)
        for optimistic, explore, maximum in ((False, False, 7), (True, False, 3),
                                             (False, True, 3), (True, True, 3)):
            with self.subTest(optimistic=optimistic, explore=explore):
                settings = SearchSettings(character='aki', min_length=2, max_length=maximum,
                                          optimistic_links=optimistic, explore_light_chains=explore)
                expected = ComboFinder('aki', 2, maximum, optimistic_links=optimistic,
                                       explore_light_chains=explore).get_combo()
                with patch('sf_combo_finder.tui_search.ComboFinder', wraps=ComboFinder) as finders:
                    result = search_route_pool(settings, library=library)
                self.assertEqual(finders.call_count, 1)
                self.assertEqual(finders.call_args.args[0], 'aki')
                self.assertEqual(finders.call_args.kwargs['optimistic_links'], optimistic)
                self.assertEqual(finders.call_args.kwargs['explore_light_chains'], explore)
                self.assertEqual(result.total, len(expected))
                actual = filter_route_pool(result.route_pool, settings, library)
                self.assertEqual([c for _, c in actual], expected)
                self.assertTrue(all(f.character == 'aki' for f, _ in actual))

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
    async def test_numeric_sliders_follow_typing_and_preserve_blank_or_invalid_edits(self):
        app = ComboFinderApp(preferences_path=None, library_path=None)
        with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
            async with app.run_test(size=(140, 50)) as pilot:
                await pilot.pause()
                for field_id, initial, value in [('min-length', 3, 4),
                                                  ('max-length', 5, 30),
                                                  ('random-count', 0, 250)]:
                    slider = app.query_one(f'#{field_id}-slider', IntegerSlider)
                    field = app.query_one(f'#{field_id}', Input)
                    self.assertEqual(slider.value, initial)
                    field.value = str(value)
                    await pilot.pause()
                    self.assertEqual(slider.value, value)
                    self.assertGreaterEqual(slider.maximum, value)
                    slider.focus()
                    await pilot.press('left')
                    self.assertEqual(field.value, str(value - 1))
                field = app.query_one('#random-count', Input)
                slider = app.query_one('#random-count-slider', IntegerSlider)
                field.value = ''
                await pilot.pause()
                self.assertEqual(slider.value, 0)
                self.assertIsNone(app.read_settings().sample_size)
                for invalid in ('0', '-1'):
                    field.value = invalid
                    await pilot.pause()
                    self.assertEqual(field.value, invalid)
                    self.assertEqual(app.read_settings().sample_size, int(invalid))
                slider.focus()
                await pilot.press('home')
                self.assertEqual(field.value, '')
                self.assertIsNone(app.read_settings().sample_size)
                self.assertEqual(app.generation, 0)
                search.assert_not_called()

    async def test_length_sliders_keep_range_in_order_and_support_keyboard_endpoints(self):
        app = ComboFinderApp(preferences_path=None, library_path=None)
        async with app.run_test(size=(140, 50)) as pilot:
            minimum = app.query_one('#min-length-slider', IntegerSlider)
            maximum = app.query_one('#max-length-slider', IntegerSlider)
            minimum.focus()
            await pilot.press('end')
            self.assertEqual(app.read_settings().min_length, 20)
            self.assertEqual(app.read_settings().max_length, 20)
            self.assertEqual(maximum.value, 20)
            maximum.focus()
            await pilot.press('home')
            self.assertEqual(app.read_settings().min_length, 1)
            self.assertEqual(app.read_settings().max_length, 1)
            self.assertEqual(minimum.value, 1)
            await pilot.press('right', 'up')
            self.assertEqual(app.read_settings().max_length, 3)

    async def test_slider_mouse_drag_and_all_position_apply_on_search(self):
        app = ComboFinderApp(settings=SearchSettings(documented_only=True, max_length=8),
                             preferences_path=None, library_path=None)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press('ctrl+b')
            slider = app.query_one('#random-count-slider', IntegerSlider)
            await pilot.pause()
            start = slider.gutter.left
            end = start + slider.content_size.width - 1
            self.assertGreater(end, start)
            await pilot.mouse_down(slider, offset=(start, 0))
            await pilot.hover(slider, offset=(end, 0))
            await pilot.mouse_up(slider, offset=(end, 0))
            self.assertEqual(app.read_settings().sample_size, 100)
            self.assertFalse(slider.dragging)
            self.assertIsNone(app.mouse_captured)
            self.assertIsNone(app.search_worker)
            slider.focus()
            await pilot.press('home', 'right', 'right', 'right')
            self.assertEqual(app.read_settings().sample_size, 3)
            await pilot.click('#filter-search')
            await self.finish(app, pilot)
            self.assertEqual(app.settings.sample_size, 3)
            self.assertEqual(len(app.rows), 3)
            await pilot.press('ctrl+b')
            await pilot.click(slider, offset=(start, 0))
            self.assertEqual(app.query_one('#random-count', Input).value, '')
            await pilot.click('#filter-search')
            await self.finish(app, pilot)
            self.assertIsNone(app.settings.sample_size)
            self.assertEqual(len(app.rows), app.match_count)

    async def test_poison_badge_is_in_table_and_details_with_checkbox_on_or_off(self):
        app = ComboFinderApp(settings=SearchSettings(character='aki'),
                             preferences_path=None, library_path=None)
        async with app.run_test(size=(140, 50)):
            for starting_poison in (False, True):
                finder = ComboFinder('aki', 2, 3, opponent_poisoned=starting_poison)
                combos = {tuple(c['moves']): c for c in finder.iter_combos()}
                app.rows = [(finder, combos[('5mk', 'hundun')]),
                            (finder, combos[('2lp', 'heavy_serpent_lash')])]
                await app.render_rows(app.generation)
                table = app.query_one('#results', DataTable)
                self.assertNotIn('[Poison]', table.get_row_at(0)[0].plain)
                self.assertIn('[Poison]', table.get_row_at(1)[0].plain)
                app.update_details(1)
                details = str(app.query_one('#detail-text', Static).render())
                self.assertIn('[Poison] Poison interaction', details)
                self.assertIn('Heavy Serpent Lash: poison affects', details)
                self.assertIn('[Poison]', str(app.query_one('#selection-meta', Static).render()))
                app.update_details(0)
                self.assertNotIn('[Poison]', str(app.query_one('#detail-text', Static).render()))

    async def test_notes_panel_is_larger_and_resizes_to_fit_terminal(self):
        app = ComboFinderApp(show_details=True, preferences_path=None, library_path=None)
        async with app.run_test(size=(140, 70)) as pilot:
            self.assertFalse(app.query('#browse'))
            details = app.query_one('#details')
            previous_height = details.region.height
            self.assertGreater(previous_height, 10)
            self.assertGreater(app.query_one('#results').size.height, 0)
            for width, height in ((100, 40), (80, 24)):
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                self.assertGreaterEqual(details.region.height, 4)
                self.assertLess(details.region.height, previous_height)
                previous_height = details.region.height
                self.assertLessEqual(details.region.bottom, height - 1)
                self.assertGreater(app.query_one('#results').size.height, 0)
            app.action_details()
            await pilot.pause()
            self.assertFalse(details.display)

    async def test_poison_control_only_applies_when_aki_is_selected(self):
        app = ComboFinderApp(settings=SearchSettings(character='aki', opponent_poisoned=True),
                             preferences_path=None, library_path=None)
        with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
            async with app.run_test(size=(120, 40)) as pilot:
                poisoned = app.query_one('#poisoned', Checkbox)
                character = app.query_one('#character', Select)
                self.assertTrue(poisoned.display)
                self.assertTrue(app.read_settings().opponent_poisoned)
                # Clearing a hidden checkbox must not trigger a search with
                # the newly selected fighter before the user presses Search.
                app.has_searched = True
                for fighter in ('ryu', 'all'):
                    character.value = fighter
                    await pilot.pause()
                    self.assertFalse(poisoned.display)
                    self.assertFalse(poisoned.value)
                    self.assertFalse(app.read_settings().opponent_poisoned)
                character.value = 'aki'
                await pilot.pause()
                self.assertTrue(poisoned.display)
                self.assertFalse(poisoned.value)
                search.assert_not_called()
                self.assertEqual(app.generation, 0)

    async def test_non_aki_launch_clears_hidden_poison_filter(self):
        app = ComboFinderApp(settings=SearchSettings(character='ryu', opponent_poisoned=True),
                             preferences_path=None, library_path=None)
        async with app.run_test(size=(120, 40)):
            self.assertFalse(app.settings.opponent_poisoned)
            self.assertFalse(app.query_one('#poisoned', Checkbox).display)
            self.assertFalse(app.read_settings().opponent_poisoned)

    async def test_details_show_vertical_frames_and_milliseconds(self):
        finder = ComboFinder('aki', 3, 3, no_jumping=True)
        combo = next(c for c in finder.iter_combos() if c['moves'] == ['5mk', 'hundun'])
        app = ComboFinderApp(settings=SearchSettings(character='aki'),
                             preferences_path=None, library_path=None, show_details=True)
        async with app.run_test(size=(120, 40)):
            app.rows = [(finder, combo)]
            app.update_details(0)
            detail = str(app.query_one('#detail-text', Static).render())
            self.assertIn('FRAME SEQUENCE', detail)
            self.assertIn('1. B', detail)
            self.assertIn('2. X', detail)
            self.assertIn('3. X', detail)
            self.assertIn('Time to input next move: 33.3 ms (2 frames; nominal link window)', detail)

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
        await asyncio.wait_for(app.workers.wait_for_complete(), timeout=30)
        await pilot.pause()

    async def search(self, app, pilot, sample_size=5):
        app.query_one('#random-count', Input).value = '' if sample_size is None else str(sample_size)
        await pilot.click('#search')
        await self.finish(app, pilot)

    async def test_startup_waits_for_search_and_random_count_is_always_blank(self):
        app = ComboFinderApp(settings=SearchSettings(sample_size=5), preferences_path=None)
        with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
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
            app.query_one('#no-jumping', Checkbox).scroll_visible(animate=False)
            await pilot.pause()
            # Finish scrolling before clicking inside the checkbox.
            self.assertTrue(await pilot.click('#no-jumping', offset=(2, 0)))
            await self.finish(app, pilot)
            self.assertTrue(app.settings.no_jumping)
            self.assertGreater(app.generation, generation)
            self.assertLess(app.match_count, baseline_count)
            self.assertTrue(app.query_one('#sidebar').display)
            self.assertTrue(all(finder.moves[key]['category'] != 'jump_normal'
                                for finder, combo in app.rows for key in combo['moves']))

    async def test_aki_jump_filter_preserves_random_count_and_restores_full_match_total(self):
        settings = SearchSettings(character='aki', min_length=4, max_length=7,
                                  max_difficulty='medium')
        baseline = search_combos(settings).total
        grounded = search_combos(replace(settings, no_jumping=True)).total
        app = ComboFinderApp(settings=settings, preferences_path=None, library_path=None)
        async with app.run_test(size=(140, 60)) as pilot:
            await self.search(app, pilot, sample_size=None)
            self.assertEqual(app.match_count, baseline)
            self.assertEqual(len(app.rows), baseline)
            slider = app.query_one('#random-count-slider', IntegerSlider)
            slider.focus()
            await pilot.press(*(['right'] * 25))
            self.assertEqual(app.read_settings().sample_size, 25)
            # Selecting a count then toggling a live route filter samples the
            # full cached pool rather than counting only the previous sample.
            jumping = app.query_one('#no-jumping', Checkbox)
            jumping.scroll_visible(animate=False)
            await pilot.pause()
            with patch('sf_combo_finder.combo_tui.search_route_pool') as search:
                for enabled, expected in ((True, grounded), (False, baseline),
                                          (True, grounded), (False, baseline)):
                    self.assertTrue(await pilot.click('#no-jumping', offset=(2, 0)))
                    await self.finish(app, pilot)
                    self.assertEqual(app.settings.no_jumping, enabled)
                    self.assertEqual(app.settings.sample_size, 25)
                    self.assertEqual(app.query_one('#random-count', Input).value, '25')
                    self.assertEqual(slider.value, 25)
                    self.assertEqual(app.match_count, expected)
                    self.assertEqual(len(app.rows), min(25, expected))
                    if enabled:
                        self.assertTrue(all(finder.moves[key]['category'] != 'jump_normal'
                                            for finder, combo in app.rows for key in combo['moves']))
                search.assert_not_called()
            # All returns the complete pool when jumping is enabled or disabled.
            slider.focus()
            await pilot.press('home')
            jumping.scroll_visible(animate=False)
            await pilot.pause()
            for enabled, expected in ((True, grounded), (False, baseline)):
                await pilot.click('#no-jumping', offset=(2, 0))
                await self.finish(app, pilot)
                self.assertEqual(app.settings.no_jumping, enabled)
                self.assertIsNone(app.settings.sample_size)
                self.assertEqual(len(app.rows), expected)
                self.assertEqual(app.match_count, expected)

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
        def slow_search(settings, data_path, *, cancelled, progress=None, library):
            while not cancelled():
                time.sleep(0.005)
            return SearchResult(cancelled=True)

        with patch('sf_combo_finder.combo_tui.search_route_pool', slow_search):
            app = ComboFinderApp()
            async with app.run_test(size=(120, 36)) as pilot:
                await pilot.click('#search')
                await pilot.pause()
                await pilot.press('escape')
                await asyncio.sleep(0.02)
                await pilot.pause()
                self.assertIn('Search cancelled', str(app.query_one('#status', Static).render()))
                self.assertEqual(app.rows, [])

    async def test_documented_toggle_generates_only_when_requested_then_reuses_cache(self):
        app = ComboFinderApp(settings=SearchSettings(character='ryu', min_length=2,
                                                    max_length=3, documented_only=True),
                             preferences_path=None, library_path=None)
        with patch('sf_combo_finder.combo_tui.search_route_pool', wraps=search_route_pool) as search:
            async with app.run_test(size=(140, 42)) as pilot:
                await self.search(app, pilot, sample_size=None)
                self.assertEqual(search.call_count, 1)
                self.assertTrue(app.rows)
                self.assertTrue(all(c['evidence']['kind'] == 'published_recipe' for _, c in app.rows))
                published_count = app.match_count

                app.query_one('#documented', Checkbox).value = False
                await self.finish(app, pilot)
                self.assertEqual(search.call_count, 2)
                self.assertGreater(app.match_count, published_count)
                self.assertTrue(any(c['evidence']['kind'] == 'frame_timing' for _, c in app.rows))

                app.query_one('#documented', Checkbox).value = True
                await self.finish(app, pilot)
                self.assertEqual(search.call_count, 2)
                self.assertEqual(app.match_count, published_count)
                self.assertTrue(all(c['evidence']['kind'] == 'published_recipe' for _, c in app.rows))
                await pilot.press('ctrl+n')
                await self.finish(app, pilot)
                self.assertEqual(search.call_count, 2)
                self.assertTrue(all(c['evidence']['kind'] == 'published_recipe' for _, c in app.rows))

    async def test_exploration_options_wait_for_search_from_either_button(self):
        app = ComboFinderApp(settings=SearchSettings(character='aki', min_length=2, max_length=3),
                             preferences_path=None, library_path=None)
        with patch('sf_combo_finder.combo_tui.search_route_pool', wraps=search_route_pool) as search:
            async with app.run_test(size=(140, 42)) as pilot:
                button = app.query_one('#filter-search', Button)
                self.assertLess(button.region.y, app.query_one('#character').region.y)
                self.assertTrue(await pilot.click('#filter-search'))
                await self.finish(app, pilot)
                self.assertTrue(app.rows)

                for optimistic, explore in ((True, False), (False, True), (True, True), (False, False)):
                    call_count, generation, previous = search.call_count, app.generation, list(app.rows)
                    app.query_one('#optimistic', Checkbox).value = optimistic
                    app.query_one('#explore', Checkbox).value = explore
                    await pilot.pause()
                    self.assertEqual(search.call_count, call_count)
                    self.assertEqual(app.generation, generation)
                    self.assertEqual(app.rows, previous)
                    self.assertIn('press Search to apply', str(app.query_one('#status', Static).render()))

                    # Alternate buttons; both must apply the selected mode.
                    selector = '#filter-search' if optimistic != explore else '#search'
                    app.query_one(selector, Button).scroll_visible(animate=False)
                    await pilot.pause()
                    self.assertTrue(await pilot.click(selector))
                    await self.finish(app, pilot)
                    self.assertEqual(app.settings.optimistic_links, optimistic)
                    self.assertEqual(app.settings.explore_light_chains, explore)
                    calls = search.call_args_list[call_count:]
                    # A.K.I.'s alternate poison state must use the same mode.
                    self.assertTrue(calls)
                    for call in calls:
                        self.assertEqual(call.args[0].optimistic_links, optimistic)
                        self.assertEqual(call.args[0].explore_light_chains, explore)
                    for finder, _ in app.rows:
                        self.assertEqual(finder.optimistic_links, optimistic)
                        self.assertEqual(finder.explore_light_chains, explore)

    async def test_live_filters_and_shuffle_do_not_apply_pending_exploration(self):
        app = ComboFinderApp(settings=SearchSettings(character='ryu', min_length=2, max_length=3),
                             preferences_path=None, library_path=None)
        with patch('sf_combo_finder.combo_tui.search_route_pool', wraps=search_route_pool) as search:
            async with app.run_test(size=(140, 42)) as pilot:
                await self.search(app, pilot)
                self.assertEqual(search.call_count, 1)
                app.query_one('#optimistic', Checkbox).value = True
                app.query_one('#explore', Checkbox).value = True
                app.query_one('#no-jumping', Checkbox).value = True
                await self.finish(app, pilot)
                self.assertTrue(app.settings.no_jumping)
                self.assertEqual(search.call_count, 1)
                await pilot.press('ctrl+n')
                await self.finish(app, pilot)
                self.assertEqual(search.call_count, 1)

                # Shuffle may need a new length pool, but must keep the searched mode.
                app.query_one('#max-length', Input).value = '4'
                await pilot.press('ctrl+n')
                await self.finish(app, pilot)
                self.assertEqual(search.call_count, 2)
                self.assertEqual(app.settings.max_length, 4)
                for call in search.call_args_list:
                    self.assertFalse(call.args[0].optimistic_links)
                    self.assertFalse(call.args[0].explore_light_chains)
                self.assertIn('press Search to apply', str(app.query_one('#status', Static).render()))

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
            self.assertTrue(await pilot.click('#filter-search'))
            await self.finish(app, pilot)
            self.assertFalse(app.query_one('#filters').display)
            self.assertFalse(app.query_one('#sidebar').display)
            self.assertGreater(app.query_one('#results', DataTable).row_count, 0)


if __name__ == '__main__':
    unittest.main()
