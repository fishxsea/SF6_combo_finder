"""Search state shared by the Textual UI and dependency-free tests."""
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
import random
from typing import Callable

from .combo_finder import ComboFinder, DATA_PATH, DIFFICULTY_LIMITS
from .combo_library import ComboLibrary, combo_identity


@dataclass(frozen=True)
class SearchSettings:
    character: str = 'all'
    min_length: int = 3
    max_length: int = 5
    sample_size: int | None = None
    hit_type: str = 'normal'
    position: str = 'midscreen'
    opponent_state: str = 'grounded'
    opponent_posture: str = 'any'
    drive_meter: int = 6
    super_meter: int = 3
    max_difficulty: str | None = None
    no_specials: bool = False
    no_jumping: bool = False
    opponent_poisoned: bool = False
    documented_only: bool = False
    optimistic_links: bool = False
    explore_light_chains: bool = False
    show_hidden: bool = False
    hidden_only: bool = False
    starred_only: bool = False
    show_custom: bool = False
    custom_only: bool = False


@dataclass
class SearchResult:
    rows: list[tuple[ComboFinder, dict]] = field(default_factory=list)
    total: int = 0
    cancelled: bool = False
    route_pool: 'CachedRoutePool | None' = None


@dataclass
class CachedRoutePool:
    """Cached routes for the timing options selected when Search was pressed."""
    modes: dict[tuple[bool, bool], list[tuple[ComboFinder, dict]]] = field(default_factory=dict)


def route_pool_settings(settings):
    """Preserve generation options while broadening inexpensive display filters."""
    return replace(settings, sample_size=None, max_difficulty=None,
                   no_specials=False, no_jumping=False,
                   starred_only=False, show_hidden=True, hidden_only=False,
                   show_custom=False, custom_only=False)


def filter_route_pool(pool, settings, library):
    """Filter a prepared pool without enumerating routes or rereading data."""
    if settings.custom_only:
        return []
    if not library.entries and (settings.starred_only or settings.hidden_only):
        return []
    rows = []
    for finder, combo in pool.modes[(settings.optimistic_links, settings.explore_light_chains)]:
        published = combo['evidence']['kind'] == 'published_recipe'
        if settings.documented_only and not published:
            continue
        moves = [finder.moves[key] for key in combo['moves']]
        if settings.no_jumping and any(move['category'] == 'jump_normal' or
                (published and move['input']['sf'].startswith(('7', '8', '9'))) for move in moves):
            continue
        allowed = ('normal', 'unique', 'jump_normal', 'target_combo', 'system') if published else (
            'normal', 'unique', 'jump_normal', 'target_combo')
        if settings.no_specials and any(move['category'] not in allowed for move in moves):
            continue
        if (settings.max_difficulty is not None and
                combo['difficulty']['score'] > DIFFICULTY_LIMITS[settings.max_difficulty]):
            continue
        if library.entries and not library.matches(combo, show_hidden=settings.show_hidden,
                hidden_only=settings.hidden_only, starred_only=settings.starred_only):
            continue
        rows.append((finder, combo))
    return rows


def search_route_pool(settings, data_path=DATA_PATH, *, cancelled=lambda: False,
                      progress=lambda count: None, library=None):
    """Enumerate only the selected timing/light mode for later filtering."""
    result = search_combos(route_pool_settings(settings), data_path, cancelled=cancelled,
                           progress=progress, library=library)
    if result.cancelled:
        return result
    mode = (settings.optimistic_links, settings.explore_light_chains)
    result.route_pool = CachedRoutePool(modes={mode: result.rows})
    return result


def sample_combo_rows(pool, sample_size, *, rng=None):
    """Choose a fresh subset of a completed pool without generating combos."""
    if sample_size is None:
        return list(pool)
    if sample_size < 1:
        raise ValueError('Random count must be positive, or blank for all results')
    return (rng or random).sample(pool, min(sample_size, len(pool)))


def combo_row_key(row):
    """Match input sequences across poison variants, keeping positions distinct."""
    finder, combo = row
    position = combo.get('conditions', {}).get('position', finder.position)
    if position == 'any':
        position = finder.position
    return combo_identity(combo), position


def index_combo_rows(rows):
    return {combo_row_key(row): row for row in rows}


def retain_combo_rows(pool, index, previous_rows, sample_size):
    """Keep displayed routes valid in the new state, filling missing sample slots."""
    if sample_size is None:
        return list(pool)
    if sample_size < 1:
        raise ValueError('Random count must be positive, or blank for all results')
    kept, seen = [], set()
    for row in previous_rows:
        key = combo_row_key(row)
        if key in index and key not in seen:
            kept.append(index[key])
            seen.add(key)
            if len(kept) == sample_size:
                return kept
    remaining = [row for key, row in index.items() if key not in seen]
    return kept + sample_combo_rows(remaining, sample_size - len(kept))


def combo_startup(finder, combo):
    """Opening damaging attack's startup, not elapsed time from the first input.

    Skip non-attacking actions. Target combos use their opening normal rather
    than the final stage. An unknown opening attack stays unknown; never use a
    later attack to supply its startup.
    """
    for key in combo['moves']:
        move = finder.moves[key]
        if not move.get('damage') and not move.get('damage_unknown', False):
            continue
        _, entry = finder._entry(move)
        startup = entry.get('startup') if entry is not None else None
        return startup if isinstance(startup, (int, float)) and not isinstance(startup, bool) else None
    return None


def combo_poison_notes(finder, combo):
    """Describe A.K.I.'s poison interactions, even with the checkbox off.

    A marker means a move has a poison variant, not that the opponent must
    already be poisoned before the whole combo. A prior hit can apply poison.
    Published starting-poison requirements are reported separately.
    """
    if finder.character != 'aki':
        return []
    notes = []
    if (combo.get('evidence', {}).get('kind') == 'published_recipe'
            and combo.get('conditions', {}).get('opponent_poisoned')):
        notes.append('This published route requires the opponent to start poisoned.')
    fields = {'damage': 'damage', 'hit': 'hit state/advantage', 'cancel': 'cancel options',
              'startup': 'startup', 'active_frames': 'active frames',
              'recovery_on_hit': 'recovery', 'detonates_poison': 'poison detonation'}
    seen, hit_started = set(), False
    for key in combo['moves']:
        move = finder.moves[key]
        attacks = bool(move.get('damage')) or move.get('damage_unknown', False)
        starter = attacks and not hit_started
        hit_started = hit_started or attacks
        if key in seen or not move.get('conditions', {}).get('opponent_poisoned'):
            continue
        seen.add(key)
        normal, _ = finder._resolve(move, False, starter)
        poisoned, _ = finder._resolve(move, True, starter)
        changes = [label for field, label in fields.items()
                   if normal.get(field) != poisoned.get(field)]
        if changes:
            notes.append(f'{move["name"]}: poison affects {", ".join(changes)} '
                         'when the opponent is poisoned at this hit.')
    return notes


def sort_combo_rows(rows, sort_by: str = 'difficulty', *, descending: bool = False):
    """Sort an existing result pool without repeating or resampling a search."""
    if sort_by not in ('character', 'difficulty', 'length', 'damage', 'startup'):
        raise ValueError(f'Unknown sort field: {sort_by}')

    def key(row):
        finder, combo = row
        name = finder.data['characters'][finder.character].get('display_name', finder.character).casefold()
        score, length = combo['difficulty']['score'], combo['length']
        primary = combo_startup(finder, combo) if sort_by == 'startup' else {
            'character': name, 'difficulty': score, 'length': length,
            'damage': combo['damage']['raw_total']}[sort_by]
        return primary, score, length, name

    known, unknown = [], []
    for row in rows:
        missing = ((sort_by == 'damage' and row[1]['damage']['raw_total'] is None) or
                   (sort_by == 'startup' and combo_startup(*row) is None) or
                   (sort_by == 'difficulty' and row[1].get('evidence', {}).get('kind') == 'custom'))
        (unknown if missing else known).append(row)
    return sorted(known, key=key, reverse=descending) + unknown


def search_combos(settings: SearchSettings, data_path: Path = DATA_PATH, *,
                  cancelled: Callable[[], bool] = lambda: False,
                  progress: Callable[[int], None] = lambda count: None,
                  rng=None, library=None) -> SearchResult:
    """Use the existing engine; reservoir sampling bounds random-search memory."""
    if settings.sample_size is not None and settings.sample_size < 1:
        raise ValueError('Random count must be positive, or blank for all results')
    rng = rng or random
    library = library if library is not None else ComboLibrary()
    with Path(data_path).open(encoding='utf-8') as source:
        data = json.load(source)
        characters = data['characters']
    selected = list(characters) if settings.character.lower() == 'all' else [settings.character]
    # Validate the entire configuration before generating any results.
    finders = [ComboFinder(
        character, settings.min_length, settings.max_length,
        not settings.no_specials, data_path=data_path, data=data,
        hit_type=settings.hit_type, position=settings.position,
        opponent_state=settings.opponent_state, drive_meter=settings.drive_meter,
        opponent_posture=settings.opponent_posture,
        super_meter=settings.super_meter, max_difficulty=settings.max_difficulty,
        no_jumping=settings.no_jumping, opponent_poisoned=settings.opponent_poisoned,
        documented_only=settings.documented_only, optimistic_links=settings.optimistic_links,
        explore_light_chains=settings.explore_light_chains,
    ) for character in selected]
    result = SearchResult()
    pool = []
    for finder in finders:
        if cancelled():
            return SearchResult(total=result.total, cancelled=True)
        for combo in finder.iter_combos():
            if cancelled():
                return SearchResult(total=result.total, cancelled=True)
            if not library.matches(combo, show_hidden=settings.show_hidden,
                                   hidden_only=settings.hidden_only, starred_only=settings.starred_only):
                continue
            result.total += 1
            entry = (result.total, finder, combo)
            if settings.sample_size is None or len(pool) < settings.sample_size:
                pool.append(entry)
            else:
                slot = rng.randrange(result.total)
                if slot < settings.sample_size:
                    pool[slot] = entry
            if result.total % 250 == 0:
                progress(result.total)
    if cancelled():
        return SearchResult(total=result.total, cancelled=True)
    pool.sort(key=lambda row: (row[2]['difficulty']['score'], row[2]['length'], row[0]))
    result.rows = [(finder, combo) for _, finder, combo in pool]
    return result
