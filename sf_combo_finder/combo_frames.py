"""Frame explanations for the browser; durations are nominal at 60 FPS."""
from rich.text import Text


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _time(frames, *, signed=False):
    if not _number(frames):
        return 'unknown'
    sign = '+' if signed and frames >= 0 else ''
    return f'{sign}{frames:g}f ({sign}{frames * 1000 / 60:.1f} ms)'


def _advantage(finder, move):
    hit = move.get('hit', {})
    if _number(hit.get('advantage')):
        return hit['advantage'], ''
    field = 'advantage_max' if finder.optimistic_links else 'advantage_min'
    return hit.get(field), ' (variable contact timing; using ' + (
        'maximum)' if finder.optimistic_links else 'minimum)')


def _input_window(text, frames=None):
    unit = 'frame' if frames == 1 else 'frames'
    label = (f'{frames * 1000 / 60:.1f} ms ({frames:g} {unit}; nominal link window)'
             if _number(frames) else 'unknown (exact input window unavailable)')
    text.append('   Time to input next move: ' + label + '\n', style='bold')


def _move_frames(text, finder, move, *, startup=None, final=False):
    text.append('   Startup: ' + _time(startup) + '\n')
    label = 'Final hit active' if final else 'Active'
    text.append(f'   {label}: {_time(move.get("active_frames"))}'
                f' | Recovery on hit: {_time(move.get("recovery_on_hit"))}\n')
    hit = move.get('hit', {})
    advantage, note = _advantage(finder, move)
    if hit.get('state') == 'normal':
        text.append('   On-hit advantage: ' + _time(advantage, signed=True) + note + '\n')
    elif hit.get('state') not in (None, 'none'):
        state = hit['state'].replace('_', ' ')
        text.append(f'   Hit state: {state}; advantage: {_time(advantage, signed=True)}\n')
        text.append('   This is not a grounded link window.\n')


def _followup(text, finder, previous, following, kind):
    """Explain hitstun separately from the game's unmeasured input buffer."""
    text.append(f'   ↓ {kind.replace("_", " ").upper()}\n', style='bold')
    _, entry = finder._entry(following)
    startup = entry.get('startup') if entry else None
    if kind in ('link', 'documented_link'):
        advantage, note = _advantage(finder, previous)
        if previous.get('hit', {}).get('state') != 'normal' or not _number(advantage):
            _input_window(text)
            text.append('   Link timing: unknown for this hit state/setup.\n')
            return
        supported = _number(startup) and startup <= advantage
        _input_window(text, advantage - startup + 1 if supported else None)
        text.append('   Opponent hitstun remaining after your recovery: '
                    + _time(advantage) + note + '\n')
        text.append('   Next attack startup: ' + _time(startup) + '\n')
        if not _number(startup):
            text.append('   Link window: unknown.\n')
        elif startup > advantage:
            text.append('   Stored frames do not support this link without additional setup.\n')
        else:
            delay = advantage - startup
            text.append(f'   Calculation: {advantage:g} - {startup:g} + 1 = {_time(delay + 1)}.\n')
            text.append('   Latest next-attack start: ' + _time(delay)
                        + ' after your recovery ends.\n')
            text.append('   Let this move recover, then start the next attack before the opponent recovers.\n')
    elif kind in ('cancel', 'documented_cancel', 'chain'):
        _input_window(text)
        budget = finder._cancel_budget(previous)
        text.append('   Hitstun at the earliest modeled cancel: ' + _time(budget) + '\n')
        text.append('   Next attack startup: ' + _time(startup) + '\n')
        if _number(budget) and _number(startup):
            if startup <= budget:
                text.append('   Hitstun margin: ' + _time(budget - startup)
                            + ' (not a button-input window).\n')
            else:
                text.append('   Stored frames do not support an immediate cancel for this setup.\n')
        text.append('   Cancel during the move; exact input window: unknown.\n')
    else:
        _input_window(text)
        text.append('   Follow-up input window: unknown; use the published route notes.\n')


def frame_details(finder, combo, *, mapped=True, controller=None):
    """Show every input vertically, keeping atomic target timing on its final hit.

    Target entries mix opening startup and final-hit data. Later inputs must
    never borrow the independent normal's startup or the opener's frame data.
    """
    text = Text()
    text.append('FRAME SEQUENCE · 60 FPS · 1f = 16.7 ms\n', style='bold')
    text.append('Startup = time until the attack becomes active; active = time it can hit.\n')
    text.append('Recovery = time until you can act again without a cancel.\n\n')
    poisoned = combo.get('conditions', {}).get('opponent_poisoned', finder.opponent_poisoned)
    hit_started = False
    count = 0
    for index, key in enumerate(combo['moves']):
        move = finder.moves[key]
        attacks = bool(move.get('damage')) or move.get('damage_unknown', False)
        starter = attacks and not hit_started
        opening_poison = poisoned
        effective, poisoned = finder._resolve(move, poisoned, starter)
        hit_started = hit_started or attacks
        sequence = move.get('sequence') or [move['input']['sf']]
        for stage, notation in enumerate(sequence):
            count += 1
            text.append(f'{count}. ', style='bold')
            if mapped:
                text.append_text(Text.from_ansi(finder.format_input(notation, color=True,
                                                                   controller=controller)))
            else:
                text.append(notation, style='bold')
            suffix = f' (target input {stage + 1}/{len(sequence)})' if len(sequence) > 1 else ''
            text.append(f' — {move["name"]}{suffix}\n')
            if not attacks:
                text.append('   Movement/stance timing: unknown; not an attack startup.\n')
            elif len(sequence) == 1:
                _move_frames(text, finder, effective, startup=effective.get('startup'))
            elif stage == 0:
                _, entry = finder._entry(move)
                if entry:
                    opener, _ = finder._resolve(entry, opening_poison, starter)
                    _move_frames(text, finder, opener, startup=opener.get('startup'))
                else:
                    text.append('   Opening attack frame data: unknown.\n')
            elif stage == len(sequence) - 1:
                _move_frames(text, finder, effective, final=True)
            else:
                text.append('   Individual target-hit frame data: unknown.\n')
            if stage < len(sequence) - 1:
                text.append('   ↓ TARGET COMBO\n', style='bold')
                _input_window(text)
                text.append('   Use the target follow-up during the move; exact input window: unknown.\n')
            text.append('\n')
        if index < len(combo['moves']) - 1:
            following = finder.moves[combo['moves'][index + 1]]
            _followup(text, finder, effective, following, combo['transitions'][index])
            text.append('\n')
    text.append('Times exclude hitstop, input buffering and travel; spacing/pushback are unverified.\n')
    text.append('Link windows count the earliest valid start frame; input buffering is not modeled.\n')
    return text
