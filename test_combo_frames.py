from copy import deepcopy
import importlib.util
import unittest

from sf_combo_finder.combo_finder import ComboFinder
HAS_RICH = importlib.util.find_spec('rich') is not None
if HAS_RICH:
    from sf_combo_finder.combo_frames import frame_details


@unittest.skipUnless(HAS_RICH, 'Install requirements.txt to run browser frame-detail tests')
class FrameDetailsTests(unittest.TestCase):
    def details(self, moves, transitions, **options):
        finder = ComboFinder('aki', **options)
        combo = {'moves': moves, 'transitions': transitions}
        return frame_details(finder, combo).plain

    def test_mk_to_hundun_shows_each_input_and_correct_link_delay(self):
        text = self.details(['5mk', 'hundun'], ['link'])
        self.assertIn('1. B — Standing Medium Kick', text)
        self.assertIn('2. X — Hun Dun (target input 1/2)', text)
        self.assertIn('3. X — Hun Dun (target input 2/2)', text)
        self.assertIn('Startup: 8f (133.3 ms)', text)
        self.assertIn('Opponent hitstun remaining after your recovery: 6f (100.0 ms)', text)
        self.assertIn('Next attack startup: 5f (83.3 ms)', text)
        self.assertIn('Latest next-attack start: 1f (16.7 ms) after your recovery ends.', text)
        window = 'Time to input next move: 33.3 ms (2 frames; nominal link window)'
        self.assertIn(window, text)
        self.assertLess(text.index('1. B'), text.index(window))
        self.assertLess(text.index(window), text.index('2. X'))
        unknown = 'Time to input next move: unknown (exact input window unavailable)'
        self.assertLess(text.index('2. X'), text.index(unknown))
        self.assertLess(text.index(unknown), text.index('3. X'))
        self.assertEqual(text.count('Time to input next move:'), 2)
        final = text.split('3. X')[1]
        self.assertIn('Startup: unknown', final)
        self.assertIn('Final hit active: 2f (33.3 ms) | Recovery on hit: 15f (250.0 ms)', final)
        self.assertIn('On-hit advantage: +1f (+16.7 ms)', final)
        self.assertNotIn('Startup: 5f', final)

    def test_one_frame_link_requires_start_immediately_after_recovery(self):
        text = self.details(['5mk', '5mp'], ['link'])
        self.assertIn('Latest next-attack start: 0f (0.0 ms)', text)
        self.assertIn('Time to input next move: 16.7 ms (1 frame; nominal link window)', text)

    def test_counter_only_changes_opener(self):
        text = self.details(['5mk', '5lp', '5lk'], ['link', 'link'], hit_type='counter')
        self.assertIn('Opponent hitstun remaining after your recovery: 8f (133.3 ms)', text)
        self.assertIn('Opponent hitstun remaining after your recovery: 4f (66.7 ms)', text)
        self.assertIn('Latest next-attack start: 3f (50.0 ms)', text)

    def test_cancel_margin_is_not_an_input_window(self):
        text = self.details(['2lp', 'heavy_serpent_lash'], ['cancel'])
        self.assertIn('Hitstun at the earliest modeled cancel: 14f (233.3 ms)', text)
        self.assertIn('Hitstun margin: 3f (50.0 ms) (not a button-input window)', text)
        self.assertIn('exact input window: unknown', text)
        self.assertIn('Time to input next move: unknown', text)
        self.assertNotIn('; nominal link window)', text)

    def test_poison_crumple_and_movement_do_not_get_grounded_link_windows(self):
        text = self.details(['heavy_serpent_lash', 'drive_rush', '5mp'],
                            ['crumple', 'drive_rush_attack'], opponent_poisoned=True)
        self.assertIn('Hit state: crumple; advantage: +53f (+883.3 ms)', text)
        self.assertIn('Movement/stance timing: unknown', text)
        self.assertIn('Follow-up input window: unknown', text)
        self.assertEqual(text.count('Time to input next move: unknown'), 2)
        self.assertNotIn('; nominal link window)', text)

    def test_unknown_cancel_budget_and_invalid_published_link_stay_explicit(self):
        finder = ComboFinder('aki')
        finder.moves = deepcopy(finder.moves)
        finder.moves['2lp'].pop('recovery_on_hit')
        text = frame_details(finder, {'moves': ['2lp', 'heavy_serpent_lash'],
                                      'transitions': ['documented_cancel']}).plain
        self.assertIn('Hitstun at the earliest modeled cancel: unknown', text)
        self.assertNotIn('Hitstun margin:', text)
        text = self.details(['5mp', '5mk'], ['documented_link'])
        self.assertIn('Stored frames do not support this link without additional setup.', text)
        self.assertIn('Time to input next move: unknown', text)
        self.assertNotIn('; nominal link window)', text)

    def test_unknown_target_opener_does_not_fall_back_to_final_startup(self):
        finder = ComboFinder('aki')
        finder.moves = deepcopy(finder.moves)
        finder.moves['hundun']['sequence'][0] = 'missing'
        text = frame_details(finder, {'moves': ['hundun'], 'transitions': []}).plain
        self.assertIn('Opening attack frame data: unknown', text)
        self.assertNotIn('Startup: 5f', text)

    def test_controller_and_sf_notation(self):
        finder = ComboFinder('aki')
        combo = {'moves': ['5mk', 'hundun'], 'transitions': ['link']}
        ps = frame_details(finder, combo, controller='playstation')
        self.assertIn('1. ○', ps.plain)
        self.assertIn('2. □', ps.plain)
        self.assertTrue(any(span.style for span in ps.spans))
        sf = frame_details(finder, combo, mapped=False).plain
        self.assertIn('1. 5MK', sf)
        self.assertIn('2. 5LP', sf)
        self.assertIn('3. LP', sf)

    def test_variable_hit_advantage_respects_selected_assumption(self):
        conservative = self.details(['j_hp', '5mp'], ['link'])
        optimistic = self.details(['j_hp', '5mp'], ['link'], optimistic_links=True)
        self.assertIn('variable contact timing; using minimum', conservative)
        self.assertIn('variable contact timing; using maximum', optimistic)
        self.assertNotEqual(conservative, optimistic)


if __name__ == '__main__':
    unittest.main()
