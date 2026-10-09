"""Search state shared by the Textual UI and dependency-free tests."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import random
from typing import Callable

from .combo_finder import ComboFinder, DATA_PATH
from .combo_library import ComboLibrary


@dataclass(frozen=True)
class SearchSettings:
    character: str = 'all'
    min_length: int = 3
    max_length: int = 5
    sample_size: int | None = None
    hit_type: str = 'normal'
    position: str = 'midscreen'
    opponent_state: str = 'grounded'
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


@dataclass
class SearchResult:
    rows: list[tuple[ComboFinder, dict]] = field(default_factory=list)
    total: int = 0
    cancelled: bool = False


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
    if combo.get('conditions', {}).get('opponent_poisoned'):
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
                   (sort_by == 'startup' and combo_startup(*row) is None))
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
