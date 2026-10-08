"""SF6 combo timing candidates at close range; verify spacing in training mode."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import random
import sys

DATA_PATH = Path(__file__).with_name('characters.json')
CONTROLLERS = ('xbox', 'playstation')
DEFAULT_PROFILES = {
    'xbox': {'buttons': {'LP': 'X', 'MP': 'Y', 'HP': 'RB', 'LK': 'A', 'MK': 'B', 'HK': 'RT'},
             'colors': {'X': '#0080FF', 'Y': '#FFD600', 'A': '#32CD32', 'B': '#FF3B30',
                        'RB': '#FFFFFF', 'RT': '#FFFFFF', 'R2': '#FFFFFF'}},
    'playstation': {'buttons': {'LP': '□', 'MP': '△', 'HP': 'R1', 'LK': '×', 'MK': '○', 'HK': 'R2'},
                    'colors': {'□': '#FF69B4', '△': '#00D084', '×': '#0080FF', '○': '#FF3B30',
                               'R1': '#FFFFFF', 'R2': '#FFFFFF'}},
}
DIFFICULTY_LIMITS = {'easy': 3, 'medium': 7, 'hard': float('inf')}


class ComboFinder:
    def __init__(self, character, min_combo_length=3, max_combo_length=None,
                 includes_specials=True, *, data_path=DATA_PATH, data=None, hit_type='normal',
                 drive_meter=6, super_meter=3, opponent_poisoned=False,
                 optimistic_links=False, explore_light_chains=False,
                 max_difficulty=None, no_jumping=False, position='midscreen',
                 opponent_state='grounded', documented_only=False, controller='xbox'):
        if data is None:
            with Path(data_path).open(encoding='utf-8') as source:
                data = json.load(source)
        self.data = data
        self.character = character.lower()
        if self.character not in self.data['characters']:
            raise ValueError(f"Unknown character: {character}. Available: {', '.join(self.data['characters'])}")
        self.moves = self.data['characters'][self.character]['moves']
        self.documented_routes = self.data['characters'][self.character].get('documented_combos', [])
        self.supported_light_sequences = self.data['characters'][self.character].get(
            'combo_search', {}).get('supported_light_sequences', [])
        self.explore_light_chains = explore_light_chains
        self.direction_mapping = self.data['notation']['directions']
        self.controller = controller
        self.button_mapping, self.button_colors = self.controller_profile(controller)
        self.min_combo_length = min_combo_length
        self.max_combo_length = 5 if max_combo_length is None else max_combo_length
        if not 1 <= min_combo_length <= self.max_combo_length:
            raise ValueError('Require 1 <= min_combo_length <= max_combo_length')
        if hit_type not in ('normal', 'counter', 'punish_counter'):
            raise ValueError('Invalid hit type')
        if not 0 <= drive_meter <= 6 or not 0 <= super_meter <= 3:
            raise ValueError('Drive meter must be 0–6; Super meter must be 0–3')
        if max_difficulty is not None and max_difficulty not in DIFFICULTY_LIMITS:
            raise ValueError('Maximum difficulty must be easy, medium, or hard')
        self.max_difficulty = max_difficulty
        if position not in ('midscreen', 'corner', 'any'):
            raise ValueError('Position must be midscreen, corner, or any')
        if opponent_state not in ('grounded', 'airborne'):
            raise ValueError('Opponent state must be grounded or airborne')
        self.position = position
        self.opponent_state = opponent_state
        self.documented_only = documented_only
        self.includes_specials = includes_specials
        self.no_jumping = no_jumping
        self.hit_type = hit_type
        self.drive_meter = drive_meter
        self.super_meter = super_meter
        self.opponent_poisoned = opponent_poisoned
        self.optimistic_links = optimistic_links
        self.found_combos = []
        self._validate_documented_routes()

    def _validate_documented_routes(self):
        """Reject broken recipe references rather than silently losing routes."""
        for recipe in self.documented_routes:
            route = recipe.get('moves', [])
            if not recipe.get('id') or not recipe.get('sources') or not route:
                raise ValueError('Documented combos require an id, sources, and moves')
            if len(recipe.get('transitions', [])) != len(route) - 1:
                raise ValueError(f"Invalid transition count in documented combo {recipe['id']}")
            conditions = recipe.get('conditions', {})
            if (conditions.get('position') not in ('midscreen', 'corner', 'any') or
                    conditions.get('opponent_state') not in ('grounded', 'airborne') or
                    conditions.get('hit_type') not in ('normal', 'counter', 'punish_counter') or
                    not isinstance(conditions.get('opponent_poisoned'), bool)):
                raise ValueError(f"Invalid conditions in documented combo {recipe['id']}")
            for index, key in enumerate(route):
                if key not in self.moves:
                    raise ValueError(f"Unknown move {key} in documented combo {recipe['id']}")
                requires = self.moves[key].get('requires', [])
                if requires and (index == 0 or route[index - 1] not in requires):
                    raise ValueError(f"Missing prerequisite for {key} in documented combo {recipe['id']}")

    def _eligible(self, move):
        return (move.get('search_eligible', True)
                and isinstance(move.get('startup'), (int, float)) and bool(move.get('damage'))
                and move['category'] != 'throw' and 'throw' not in move.get('properties', [])
                and (not self.no_jumping or move['category'] != 'jump_normal')
                and (self.includes_specials or move['category'] in
                     ('normal', 'unique', 'jump_normal', 'target_combo')))

    @staticmethod
    def _length(move):
        return len(move.get('sequence') or [None])

    @staticmethod
    def _cost(move):
        if 'meter_cost' in move:
            return move['meter_cost'].get('drive', 0), move['meter_cost'].get('super', 0)
        return (2 if move['category'] == 'od_special' or
                'overdrive' in move.get('properties', []) else 0, move.get('super_level', 0))

    def _resolve(self, move, poisoned, starter):
        result = deepcopy(move)
        for key, enabled in (('opponent_poisoned', poisoned),
                             (self.hit_type, starter and self.hit_type != 'normal')):
            if enabled:
                for field, value in move.get('conditions', {}).get(key, {}).items():
                    if isinstance(value, dict) and isinstance(result.get(field), dict):
                        result[field].update(value)
                    else:
                        result[field] = value
        # A counter affects the first hit, not the final hit of a target combo
        # or multi-hit attack. Explicit move-specific hit data is already final.
        override = move.get('conditions', {}).get(self.hit_type, {}) if starter else {}
        if (starter and len(move.get('damage', [])) == 1 and not move.get('sequence')
                and move.get('counter_bonus_on_final_hit', True)
                and result.get('hit', {}).get('state') == 'normal' and 'hit' not in override):
            bonus = {'normal': 0, 'counter': 2, 'punish_counter': 4}[self.hit_type]
            for field in ('advantage', 'advantage_min', 'advantage_max'):
                if isinstance(result['hit'].get(field), (int, float)):
                    result['hit'][field] += bonus
        properties = result.get('properties', [])
        if result.get('detonates_poison') or 'detonates_poison' in properties:
            poisoned = False
        elif result.get('applies_poison') or 'applies_poison' in properties:
            poisoned = True
        return result, poisoned

    def _entry(self, move):
        """A target combo must first connect its opening normal."""
        sequence = move.get('sequence')
        if sequence:
            key = sequence[0].lower()
            return key, self.moves.get(key)
        return None, move

    def _is_light(self, key):
        move = self.moves[key]
        if move.get('sequence'):
            return all(re.fullmatch(r'[1-9]?L[PK]', value, re.I)
                       for value in move['sequence'])
        return (move['category'] in ('normal', 'unique')
                and re.fullmatch(r'[1-9]L[PK]', move['input']['sf'], re.I) is not None)

    def _light_sequence_supported(self, route):
        """Do not extrapolate pairwise light chains into arbitrary long strings."""
        if self.explore_light_chains:
            return True
        lights = []
        for key in reversed(route):
            if not self._is_light(key):
                break
            lights.insert(0, key)
        if len(lights) <= 1:
            return True
        return any(sequence[:len(lights)] == lights
                   for sequence in self.supported_light_sequences)

    @staticmethod
    def _cancel_budget(move):
        """Frames available after an immediate cancel on the first active frame."""
        hit = move.get('hit', {})
        if hit.get('state') != 'normal':
            return None
        if isinstance(move.get('cancel', {}).get('hitstun_budget'), (int, float)):
            return move['cancel']['hitstun_budget']
        advantage = hit.get('advantage')
        active, recovery = move.get('active_frames'), move.get('recovery_on_hit')
        if all(isinstance(value, (int, float)) for value in (advantage, active, recovery)):
            return advantage + active - 1 + recovery
        return None

    def _transition(self, previous_id, previous, next_id, following):
        category = following['category']
        entry_id, entry = self._entry(following)
        if entry is None or category == 'jump_normal':
            return None  # Jump time isn't supplied; jump attacks are openers only.
        entry_id = entry_id or next_id
        if entry_id in previous.get('cancel', {}).get('target_followups', []):
            return None  # This input invokes a target follow-up, not a fresh normal.
        requires = following.get('requires', [])
        if requires and previous_id not in requires:
            return None
        cancel = previous.get('cancel', {})
        targets = cancel.get('specific_targets')
        if targets is not None:
            permitted = next_id in targets or f"level_{following.get('super_level')}" in targets
        else:
            permitted = ((category in ('special', 'od_special') and cancel.get('special'))
                         or (category == 'super' and cancel.get('super')))
        if category == 'super':
            # Permission still comes from the move's cancel flags/target list.
            levels = cancel.get('super_levels')
            if levels is None:
                levels = {'special': [3], 'od_special': [2, 3]}.get(previous['category'], [1, 2, 3])
            permitted = permitted and following.get('super_level') in levels
        if permitted and previous['category'] != 'jump_normal' and not cancel.get('condition'):
            budget = self._cancel_budget(previous)
            if budget is not None and entry['startup'] <= budget:
                return 'cancel', f'Immediate cancel required; {budget} frames of hitstun available'
        if requires:
            return None
        hit = previous.get('hit', {})
        if hit.get('state') != 'normal':
            return None  # Wake-up advantage is not combo hitstun.
        if entry_id in cancel.get('chain_targets', []):
            budget = self._cancel_budget(previous)
            if budget is not None and entry['startup'] <= budget:
                return 'chain', 'Immediate light chain; range/pushback must be verified'
        advantage = hit.get('advantage')
        note = None
        if advantage is None:
            field = 'advantage_max' if self.optimistic_links else 'advantage_min'
            advantage = hit.get(field)
            if advantage is not None:
                note = f'Variable hit advantage: uses {field}={advantage}'
        if isinstance(advantage, (int, float)) and entry['startup'] <= advantage:
            return 'link', note
        return None

    def estimate_difficulty(self, combo):
        """Heuristic execution score, independent of a route's validity."""
        components = {'length': max(0, combo['length'] - 2),
                      'motions': 0, 'simultaneous_buttons': 0,
                      'links': 0, 'positioning': 0, 'route_timing': 0}
        reasons, link_windows = [], []
        caveats = ['Spacing and pushback difficulty are not measured.']
        resolved = []
        poisoned = self.opponent_poisoned
        for index, key in enumerate(combo['moves']):
            move = self.moves[key]
            effective, poisoned = self._resolve(move, poisoned, index == 0)
            resolved.append(effective)
            notation = move['input']['sf']
            for motion in re.findall(r'[1-9]{2,}', notation):
                components['motions'] += 2 if len(motion) >= 6 else 1
            components['simultaneous_buttons'] += len(re.findall(r'PP|KK|\+', notation))
            if move['category'] == 'jump_normal':
                components['positioning'] += 2
                reasons.append('Jump-in height/position required (+2).')
                caveats.append('Jump-in timing depends on contact height.')
            if move['category'] == 'system':
                components['route_timing'] += 2
                reasons.append(f"{move['name']}: timing/position adjustment (+2).")
        for index, kind in enumerate(combo['transitions']):
            if kind != 'link':
                if kind in ('juggle', 'crumple', 'delayed_cancel'):
                    components['route_timing'] += 2
                    reasons.append(f'Transition {index + 1}: {kind.replace("_", " ")} timing (+2).')
                if combo.get('evidence', {}).get('kind') == 'published_recipe':
                    caveats.append('Published-route timing is qualitative; exact input windows are not measured.')
                if kind == 'cancel':
                    caveats.append('Actual cancel input windows are unavailable; cancel precision is not scored.')
                elif kind == 'chain':
                    caveats.append('Actual light-chain input windows are unavailable; chain precision is not scored.')
                continue
            hit = resolved[index]['hit']
            advantage = hit.get('advantage')
            variable = advantage is None
            if variable:
                advantage = hit.get('advantage_max' if self.optimistic_links else 'advantage_min')
            _, entry = self._entry(self.moves[combo['moves'][index + 1]])
            window = advantage - entry['startup'] + 1
            points = 3 if window <= 1 else 2 if window <= 2 else 1 if window <= 3 else 0
            components['links'] += points + (1 if variable else 0)
            link_windows.append({'from': combo['moves'][index], 'to': combo['moves'][index + 1],
                                 'nominal_frames': window, 'variable_advantage': variable})
            reasons.append(f'Link {index + 1}: nominal {window:g}-frame window (+{points}).')
            if variable:
                reasons.append(f'Link {index + 1}: variable contact timing (+1).')
        if link_windows:
            caveats.append('Link windows use frame advantage; the game input buffer is not modeled.')
        if self.explore_light_chains:
            caveats.append('Exploration may include impossible routes; difficulty does not verify a combo.')
        score = sum(components.values())
        label = next(label for label, limit in DIFFICULTY_LIMITS.items() if score <= limit)
        return dict(label=label, score=score, estimated=True, components=components,
                    reasons=reasons, link_windows=link_windows,
                    caveats=list(dict.fromkeys(caveats)))

    def _iter_documented_combos(self):
        """Yield only sourced complete routes and their prefixes, never stitch them."""
        for recipe in self.documented_routes:
            conditions = recipe['conditions']
            if (conditions['hit_type'] != self.hit_type or
                    conditions['opponent_poisoned'] != self.opponent_poisoned or
                    conditions['opponent_state'] != self.opponent_state or
                    (self.position != 'any' and conditions['position'] not in ('any', self.position))):
                continue
            route, length, drive, super_meter, raw_damage = [], 0, 0, 0, 0
            poisoned, hit_started, damage_known = self.opponent_poisoned, False, True
            for index, key in enumerate(recipe['moves']):
                move = self.moves[key]
                if (self.no_jumping and (move['category'] == 'jump_normal' or
                        move['input']['sf'].startswith(('8', '9', '7')))) or (
                        not self.includes_specials and move['category'] not in
                        ('normal', 'unique', 'jump_normal', 'target_combo', 'system')):
                    break
                drive_cost, super_cost = self._cost(move)
                drive += drive_cost
                super_meter += super_cost
                length += self._length(move)
                if length > self.max_combo_length or drive > self.drive_meter or super_meter > self.super_meter:
                    break
                attacks = bool(move.get('damage')) or move.get('damage_unknown', False)
                effective, poisoned = self._resolve(move, poisoned, attacks and not hit_started)
                hit_started = hit_started or attacks
                raw_damage += sum(effective.get('damage', []))
                damage_known = damage_known and not move.get('damage_unknown', False)
                route.append(key)
                # Do not present an unfinished movement/stance as a combo ending.
                if length < self.min_combo_length or not attacks:
                    continue
                inputs = [self.moves[step]['input']['sf'] for step in route]
                combo = dict(character=self.character, moves=list(route), inputs=inputs,
                             mapped_inputs=[self.format_input(value) for value in inputs],
                             length=length, transitions=recipe['transitions'][:index],
                             damage={'raw_total': raw_damage if damage_known else None,
                                     'scaling_applied': False},
                             drive_spent=drive, super_spent=super_meter, hit_type=self.hit_type,
                             conditions=dict(conditions), status='candidate',
                             evidence={'kind': 'published_recipe', 'recipe_id': recipe['id'],
                                       'sources': recipe['sources'],
                                       'source_kind': recipe.get('source_kind', 'community_guide'),
                                       'source_label': recipe.get('source_label', 'Community guide'),
                                       'source_version': recipe.get('source_version'),
                                       'title': recipe.get('title', recipe['id']),
                                       'complete': index == len(recipe['moves']) - 1},
                             notes=['Published recipe/prefix; not tested in the current game patch.'] +
                                   recipe.get('notes', []))
                combo['difficulty'] = self.estimate_difficulty(combo)
                yield combo

    def iter_combos(self):
        """Yield all candidates within the configured input length and meter limits.

        Published recipes include sourced juggle, stance and Drive Rush routes.
        They are not concatenated with generated routes. Target combos are
        atomic entries counting as len(sequence) inputs.
        Cancels require known active/recovery timing, an immediate cancel and
        sufficient remaining hitstun. Unknown juggle, stance, projectile
        follow-up, conditional-cancel and Drive Rush transitions are excluded
        from automatic generation; published recipes can cover specific routes.
        Hitboxes and accumulated pushback are not simulated.
        """
        seen, documented_moves = set(), set()
        for combo in self._iter_documented_combos():
            position = self.position if self.position != 'any' else combo['conditions']['position']
            identity = (tuple(combo['moves']), position)
            if identity not in seen:
                seen.add(identity)
                documented_moves.add(identity[0])
                if (self.max_difficulty is None or
                        combo['difficulty']['score'] <= DIFFICULTY_LIMITS[self.max_difficulty]):
                    yield combo
        if self.documented_only or self.opponent_state != 'grounded':
            return
        eligible = {key: move for key, move in self.moves.items() if self._eligible(move)}

        def visit(route, transitions, notes, previous, poisoned, drive, meter, length, raw_damage):
            if length >= self.min_combo_length:
                combo = dict(character=self.character, moves=list(route),
                           inputs=[self.moves[key]['input']['sf'] for key in route],
                           mapped_inputs=[self.format_input(self.moves[key]['input']['sf'])
                                          for key in route],
                           length=length, transitions=list(transitions),
                           damage={'raw_total': raw_damage, 'scaling_applied': False},
                           drive_spent=self.drive_meter - drive,
                           super_spent=self.super_meter - meter, hit_type=self.hit_type,
                           notes=list(dict.fromkeys(notes)), status='candidate')
                combo['evidence'] = {'kind': 'frame_timing'}
                attribution = self.data['characters'][self.character].get('data_source')
                if attribution:
                    combo['evidence'].update(
                        provider=attribution['provider'], license=attribution['license'],
                        sources=list(dict.fromkeys(source for key in route
                                                   for source in self.moves[key].get('sources', []))),
                        fetched_at=attribution['fetched_at'])
                combo['difficulty'] = self.estimate_difficulty(combo)
                if (self.max_difficulty is None or
                        combo['difficulty']['score'] <= DIFFICULTY_LIMITS[self.max_difficulty]):
                    # Any published version takes precedence over a theoretical
                    # route with the same moves in the selected scenario.
                    if tuple(route) not in documented_moves:
                        yield combo
            if length >= self.max_combo_length:
                return
            for key, move in eligible.items():
                next_length = length + self._length(move)
                if next_length > self.max_combo_length:
                    continue
                if not self._light_sequence_supported(route + [key]):
                    continue
                transition = self._transition(route[-1], previous, key, move)
                if transition is None:
                    continue
                drive_cost, super_cost = self._cost(move)
                if drive_cost > drive or super_cost > meter:
                    continue
                resolved, next_poisoned = self._resolve(move, poisoned, False)
                kind, note = transition
                yield from visit(route + [key], transitions + [kind],
                                 notes + ([note] if note else []), resolved, next_poisoned,
                                 drive - drive_cost, meter - super_cost, next_length,
                                 raw_damage + sum(resolved['damage']))

        for key, move in eligible.items():
            if move.get('requires') or self._length(move) > self.max_combo_length:
                continue
            drive_cost, super_cost = self._cost(move)
            if drive_cost > self.drive_meter or super_cost > self.super_meter:
                continue
            resolved, poisoned = self._resolve(move, self.opponent_poisoned, True)
            notes = ['Range/pushback must be verified']
            if self.explore_light_chains:
                notes.append('Exploration: unrestricted light strings; accumulated pushback is unchecked')
            yield from visit([key], [], notes, resolved,
                             poisoned, self.drive_meter - drive_cost,
                             self.super_meter - super_cost, self._length(move),
                             sum(resolved['damage']))

    def get_combo(self):
        self.found_combos = sorted(self.iter_combos(),
                                   key=lambda combo: (combo['difficulty']['score'], combo['length']))
        return self.found_combos

    def controller_profile(self, controller):
        if controller not in CONTROLLERS:
            raise ValueError(f'Unknown controller: {controller}')
        profile = self.data['notation'].get('controllers', {}).get(controller, DEFAULT_PROFILES[controller])
        # Preserve custom legacy Xbox mappings in existing data files.
        buttons = self.data['notation'].get('buttons', profile['buttons']) if controller == 'xbox' else profile['buttons']
        return buttons, profile['colors']

    def format_input(self, notation, color=False, *, controller=None):
        """Map SF input tokens in one pass, preserving names and mapped digits."""
        mapping, colors = ((self.button_mapping, self.button_colors) if controller is None
                           else self.controller_profile(controller))
        buttons = sorted(mapping, key=len, reverse=True)
        tokens = '|'.join(re.escape(button) for button in buttons)
        pattern = rf'(?<![A-Za-z])(?:{tokens}|PP|KK|P|K)(?![A-Za-z])|[1-9]'

        def button_label(button):
            label = mapping[button]
            shade = colors.get(label.upper()) if color else None
            if shade:
                red, green, blue = (int(shade[i:i+2], 16) for i in (1, 3, 5))
                return f'\033[38;2;{red};{green};{blue}m{label}\033[0m'
            return label

        def replace(match):
            token = match.group()
            if token in self.direction_mapping:
                return '' if token == '5' else self.direction_mapping[token]['symbol']
            if token in mapping:
                return button_label(token)
            # P/K means any strength; PP/KK means any two together.
            choices = [button_label(strength + token[0]) for strength in ('L', 'M', 'H')]
            if len(token) == 2:
                choices = [f'{choices[a]}+{choices[b]}' for a, b in ((0, 1), (0, 2), (1, 2))]
            return '(' + '/'.join(choices) + ')'

        return re.sub(pattern, replace, notation)

    def format_combo(self, combo, mapped=True, color=False, *, controller=None):
        inputs = [self.format_input(value, color=color, controller=controller) for value in combo['inputs']] if mapped else combo['inputs']
        return ' > '.join(inputs)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Length counts move inputs, not individual hits; target combos count their '
               'sequence inputs. Output sorts each character by estimated difficulty score, '
               'then by length for ties, and labels each combo [difficulty | len=N | raw dmg=N]. '
               'Damage is before scaling and excludes poison damage over time. The search omits '
               'unknown routes; sourced recipes add Drive Rush, stance, juggle, and crumple continuations.')
    parser.add_argument('character', nargs='?', default='all',
                        help='Character ID from the data file, such as aki, or all (default: all)')
    parser.add_argument('--data', type=Path, default=DATA_PATH,
                        help='Path to the character/notation JSON file (default: bundled roster)')
    parser.add_argument('--tui', action='store_true',
                        help='Open the Textual combo browser with these filters; requires requirements.txt')
    parser.add_argument('--list-characters', action='store_true',
                        help='List available character IDs and names from the data file, then exit')
    parser.add_argument('--min-length', type=int, default=3,
                        help='Minimum number of move inputs per combo, at least 1 (default: 3)')
    parser.add_argument('--max-length', type=int, default=5,
                        help='Maximum number of move inputs per combo; must be at least --min-length (default: 5)')
    parser.add_argument('--max-difficulty', choices=list(DIFFICULTY_LIMITS),
                        help='Keep estimated difficulty at or below this level; scores use length, motions, buttons, and links (default: no filter)')
    parser.add_argument('--random', type=int, metavar='N',
                        help='Show up to N randomly selected combos total, after filtering; N must be positive. Selected combos remain sorted by difficulty')
    parser.add_argument('--no-specials', action='store_true',
                        help='Exclude specials and supers; keep normals, unique attacks, jump normals, and target combos')
    parser.add_argument('--no-jumping', action='store_true',
                        help='Exclude jump attacks, including jump-in starters')
    parser.add_argument('--position', choices=['midscreen', 'corner', 'any'], default='midscreen',
                        help='Filter published recipes by screen position (default: midscreen); any labels position-dependent output')
    parser.add_argument('--opponent-state', choices=['grounded', 'airborne'], default='grounded',
                        help='Opponent state at the opening hit; airborne uses sourced routes only (default: grounded)')
    parser.add_argument('--documented-only', action='store_true',
                        help='Show source-labelled Capcom trial transcriptions and community recipes/prefixes for all characters; coverage is incomplete')
    parser.add_argument('--starred-only', action='store_true',
                        help='Show saved favorites matching the other filters')
    parser.add_argument('--show-hidden', action='store_true',
                        help='Include combos you excluded in the TUI (hidden by default)')
    parser.add_argument('--hidden-only', action='store_true',
                        help='Show only excluded combos, regardless of --show-hidden; combine with --starred-only if desired')
    from .combo_library import LIBRARY_PATH
    parser.add_argument('--library', type=Path, default=LIBRARY_PATH,
                        help='Saved favorites/exclusions file (default: user app-data directory)')
    parser.add_argument('--hit-type', choices=['normal', 'counter', 'punish_counter'], default='normal',
                        help='Opening hit condition; counter bonuses affect only the first hit (default: normal)')
    parser.add_argument('--drive-meter', type=int, default=6,
                        help='Available Drive bars, from 0 to 6; each OD special costs 2 (default: 6)')
    parser.add_argument('--super-meter', type=int, default=3,
                        help='Available Super bars, from 0 to 3; supers cost their level (default: 3)')
    parser.add_argument('--opponent-poisoned', action='store_true',
                        help='Start with the opponent already poisoned and apply poison/detonation changes along the route')
    parser.add_argument('--optimistic-links', action='store_true',
                        help='Use maximum variable on-hit advantage instead of minimum; requires favorable hit timing')
    parser.add_argument('--explore-light-chains', action='store_true',
                        help='Bypass the conservative light-string filter; may produce impossible strings because pushback is unchecked')
    notation = parser.add_mutually_exclusive_group()
    notation.add_argument('--mapped', dest='mapped', action='store_true', default=True,
                          help='Show direction symbols and mapped controller buttons (default)')
    notation.add_argument('--sf', dest='mapped', action='store_false',
                          help='Show original SF notation such as 2LP and 236HP instead of mapped arrows/buttons')
    parser.add_argument('--color', choices=['auto', 'always', 'never'], default='auto',
                        help='Explicit RGB controller button colors: auto for terminals, always to force colors, never to disable (default: auto)')
    parser.add_argument('--controller', choices=CONTROLLERS,
                        help='Mapped button layout: xbox or playstation (CLI default: xbox; TUI uses saved choice)')
    parser.add_argument('--json', action='store_true',
                        help='Output a JSON array of routes and metadata; overrides text, color, and verbose output')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Include headings, numbering, transitions, estimated difficulty with its breakdown, notes, and totals')
    args = parser.parse_args()
    if args.random is not None and args.random < 1:
        parser.error('--random must be a positive integer')
    if args.list_characters:
        try:
            with args.data.open(encoding='utf-8') as source:
                characters = json.load(source)['characters']
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
        if args.json:
            print(json.dumps([{'id': key, 'name': value.get('display_name', key)}
                              for key, value in characters.items()], ensure_ascii=False))
        else:
            for key, value in characters.items():
                print(f"{key:<12} {value.get('display_name', key)}")
        return
    if args.tui:
        if args.json:
            parser.error('--tui and --json cannot be combined')
        try:
            from .combo_tui import ComboFinderApp
            from .tui_search import SearchSettings
        except ModuleNotFoundError as error:
            parser.error(f'TUI dependency missing: {error.name}. Run python3 -m pip install -r requirements.txt')
        try:
            settings = SearchSettings(
                character=args.character, min_length=args.min_length, max_length=args.max_length,
                sample_size=None,
                hit_type=args.hit_type, position=args.position, opponent_state=args.opponent_state,
                drive_meter=args.drive_meter, super_meter=args.super_meter,
                max_difficulty=args.max_difficulty, no_specials=args.no_specials,
                no_jumping=args.no_jumping, opponent_poisoned=args.opponent_poisoned,
                documented_only=args.documented_only, optimistic_links=args.optimistic_links,
                explore_light_chains=args.explore_light_chains,
                starred_only=args.starred_only, show_hidden=args.show_hidden, hidden_only=args.hidden_only,
            )
            ComboFinderApp(args.data, settings, mapped=args.mapped, show_details=args.verbose,
                           library_path=args.library, controller=args.controller).run()
        except (ValueError, OSError, KeyError) as error:
            parser.error(str(error))
        return
    color = args.color == 'always' or (args.color == 'auto' and sys.stdout.isatty())
    try:
        from .combo_library import ComboLibrary
        library = ComboLibrary(args.library)

        def personal_matches(combo):
            return library.matches(combo, starred_only=args.starred_only,
                                   show_hidden=args.show_hidden, hidden_only=args.hidden_only)

        with args.data.open(encoding='utf-8') as source:
            data = json.load(source)
            characters = data['characters']
        selected = list(characters) if args.character.lower() == 'all' else [args.character]
        # Validate every selected character before producing output.
        finders = [ComboFinder(c, args.min_length, args.max_length, not args.no_specials,
                              data_path=args.data, data=data, hit_type=args.hit_type,
                              drive_meter=args.drive_meter, super_meter=args.super_meter,
                              opponent_poisoned=args.opponent_poisoned,
                              optimistic_links=args.optimistic_links,
                              explore_light_chains=args.explore_light_chains,
                              max_difficulty=args.max_difficulty,
                              no_jumping=args.no_jumping, position=args.position,
                              opponent_state=args.opponent_state,
                              documented_only=args.documented_only,
                              controller=args.controller or 'xbox') for c in selected]
        sampled = None
        if args.random is not None:
            pool = [(finder, combo) for finder in finders for combo in finder.iter_combos()
                    if personal_matches(combo)]
            sampled = {finder: [] for finder in finders}
            indices = sorted(random.sample(range(len(pool)), min(args.random, len(pool))))
            for index in indices:
                finder, combo = pool[index]
                sampled[finder].append(combo)
            for combos in sampled.values():
                combos.sort(key=lambda combo: (combo['difficulty']['score'], combo['length']))
        if args.json:
            print('[')
        first = True
        for finder in finders:
            count = 0
            if not args.json and args.verbose:
                print(f"{characters[finder.character].get('display_name', finder.character)} — candidate routes")
                attribution = characters[finder.character].get('data_source')
                if attribution:
                    print(f"Frame data: {attribution['provider']} ({attribution['license']}); {attribution['snapshot_url']}")
            combos = finder.get_combo() if sampled is None else sampled[finder]
            for combo in combos:
                if not personal_matches(combo):
                    continue
                count += 1
                if args.json:
                    print(('' if first else ',') + json.dumps(combo, ensure_ascii=False))
                    first = False
                else:
                    combo_string = finder.format_combo(combo, args.mapped, color=color)
                    difficulty = combo['difficulty']
                    bracket = (f"[{difficulty['label']} | len={combo['length']} | "
                               f"raw dmg={combo['damage']['raw_total'] if combo['damage']['raw_total'] is not None else 'unknown'}]")
                    if combo['evidence']['kind'] == 'published_recipe':
                        bracket = bracket[:-1] + f" | {combo['evidence']['source_label']}]"
                    starred, hidden = library.marks(combo)
                    if starred or hidden:
                        marks = ' | '.join(label for label, enabled in [('★', starred), ('hidden', hidden)] if enabled)
                        bracket = bracket[:-1] + f' | {marks}]'
                    conditions = combo.get('conditions', {})
                    if args.position == 'any' and conditions.get('position') in ('midscreen', 'corner'):
                        bracket = bracket[:-1] + f" | {conditions['position']}]"
                    labeled_combo = f'{bracket:<36} {combo_string}'
                    if args.verbose:
                        print(f"{count}. {labeled_combo} [{' / '.join(combo['transitions'])}]")
                        print(f"   Estimated difficulty: {difficulty['label']} (score {difficulty['score']})")
                        print('   Damage is before scaling; poison damage over time is excluded.')
                        if combo['evidence']['kind'] == 'published_recipe':
                            print(f"   {combo['evidence']['source_label']}: {combo['evidence']['title']}")
                        if conditions:
                            print('   Requires: ' + ', '.join(f'{key}={value}' for key, value in conditions.items()))
                            print('   Source: ' + ', '.join(combo['evidence']['sources']))
                        print('   Score breakdown: ' + ', '.join(
                            f'{factor.replace("_", " ")}={points}'
                            for factor, points in difficulty['components'].items()))
                        for detail in difficulty['reasons'] + difficulty['caveats']:
                            print(f'   {detail}')
                        for note in combo['notes']:
                            print(f'   {note}')
                    else:
                        print(labeled_combo)
            if not args.json and args.verbose:
                print(f'{count} candidates. Published recipes and timing candidates require in-game spacing/patch verification.')
        if args.json:
            print(']')
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
