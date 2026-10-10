"""Compile reviewed A.K.I. data and convert the bundled SF6 Sensei snapshots."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

from sf_combo_finder.combo_finder import DATA_PATH

SOURCE_DIR = Path(__file__).with_name('data') / 'sf6-sensei'
PROVIDER = 'SF6 Sensei / SuperCombo Wiki'
LICENSE = 'CC-BY-SA-4.0'
SOURCE_BASE = 'https://github.com/RyoSogawa/sf6-sensei/tree/main/packages/data/src/generated'
REVIEWED_ON = '2026-10-07'


def text_field(record, field):
    value = record.get(field) or {}
    return value.get('en') or ''


def numeric(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def parse_damage(value, description=None):
    """Parse explicit hit lists; never guess damage from an unparsed expression."""
    if description:
        base = description.split('(')[0].strip()
        if re.fullmatch(r'\d+(?:x\d+)?(?:\s*[,+]\s*\d+(?:x\d+)?)*', base):
            result = []
            for part in re.split(r'[,+]', base):
                pieces = part.strip().split('x')
                result.extend([int(pieces[0])] * (int(pieces[1]) if len(pieces) == 2 else 1))
            return result
        # A parenthetical alternate/scaled value is optional when the base is explicit.
        if not base or not re.fullmatch(r'\d+', base):
            return None
    return [int(value)] if numeric(value) is not None and value > 0 else []


def canonical_input(value):
    value = (value or '').strip().replace(' ', '')
    value = value.replace('j.', '8')
    if re.fullmatch(r'[LMH][PK]', value):
        value = '5' + value
    return value


def chain_destinations(notes):
    match = re.search(r'chains? (?:into|to) ([^;.]+)', notes, re.I)
    return [token.lower() for token in re.findall(r'\b[1-9][LMH][PK]\b', match[1])] if match else []


def baseline_variant(record, character):
    """Return variant exclusions and an explicit DL0 damage override if supplied."""
    name, notes = text_field(record, 'name'), text_field(record, 'notes')
    drink_damage = None
    if character == 'jamie' and '(DL2)' in name:
        # The source's neutral table is often DL2 (100% damage). Use its explicit
        # DL0 figures only for moves documented as available at Drink Level 0.
        match = re.search(r'Damage DL0-DL\d:\s*([\d,x+ ]+)/', notes)
        if match:
            drink_damage = parse_damage(None, match[1].strip())
        else:
            return ['Drink-level variant is not modeled'], None
    elif re.search(r'\([^)]*(?:DL[1-4]|FSE|Flame|Wind|Stock|Denjin|Hold|Charge|Perfect|Buff|Bayani|Install)[^)]*\)', name, re.I):
        return ['Conditional or charged variant is not modeled'], None
    if re.search(r'\b(?:Denjin|Enhanced|Perfect)\b', name, re.I):
        return ['Resource/timing variant is not modeled'], None
    if re.search(r'\brequires?\b.{0,45}(?:stock|drink|stance|mode|medal|install)', notes, re.I):
        return ['Required character state is not modeled'], None
    return [], drink_damage


def convert_character(source, super_inputs):
    character = source['id']
    moves, records, by_input = {}, {}, {}
    for index, record in enumerate(source['moves']):
        notation = canonical_input((record.get('input') or {}).get('numpad'))
        name, notes = text_field(record, 'name'), text_field(record, 'notes')
        key = re.sub(r'[^a-z0-9]+', '_', notation.lower()).strip('_') or f'move_{index + 1}'
        if key in moves:
            key += f'_variant_{index + 1}'
        category = {'normal': 'normal', 'special': 'special', 'super_art': 'super',
                    'throw': 'throw', 'drive': 'system', 'taunt': 'system'}.get(record['category'], 'unknown')
        if record['category'] == 'normal':
            if notation.startswith('8'):
                category = 'jump_normal'
            elif '~' in notation:
                category = 'target_combo'
            elif not re.fullmatch(r'[125][LMH][PK]', notation):
                category = 'unique'
        od = (record.get('driveGauge') or {}).get('gain') == -20000 or bool(re.search(r'(?:PP|KK)$', notation))
        if category == 'special' and od:
            category = 'od_special'
        reasons, drink_damage = baseline_variant(record, character)
        damage = drink_damage if drink_damage is not None else parse_damage(record.get('damage'), record.get('damageText'))
        if damage is None:
            reasons.append('Damage expression needs a reviewed hit-count/variant conversion')
            damage = []
        simple = re.fullmatch(r'[1-9]*(?:LP|MP|HP|LK|MK|HK|PP|KK|P|K)', notation)
        if not simple:
            reasons.append('Charge, follow-up, target-combo or input variant requires explicit route data')
        if ((record.get('input') or {}).get('numpad') or '').startswith('j.') and category != 'jump_normal':
            reasons.append('Air-only special requires explicit airborne route data')
        if 'throw' in (record.get('properties') or []):
            reasons.append('Throw cannot use ordinary grounded combo cancels')
        if category in ('throw', 'system', 'unknown'):
            reasons.append('Not a supported standalone combo attack')
        if numeric(record.get('startup')) is None or not damage:
            reasons.append('Missing startup or attack damage')
        if category == 'special' and re.search(r'\b(?:hitgrab|hit-grab|command grab|stance)\b', notes, re.I):
            reasons.append('Conditional grab/stance behavior needs explicit route data')

        advantage, hitstun = numeric(record.get('onHit')), numeric(record.get('hitstun'))
        # The upstream normalization removes KD markers. Known normal hitstun
        # plus modest advantage is needed before treating a value as a link.
        state = 'normal' if hitstun is not None and advantage is not None and advantage <= 15 else 'unknown'
        active_text = str(record.get('active') or '')
        active = int(active_text) if active_text.isdigit() else None
        recovery = numeric(record.get('recovery'))
        permissions = record.get('cancel') or []
        cancel = {'chain': 'chain' in permissions, 'chain_targets': [],
                  'special': 'special' in permissions, 'super': 'super' in permissions}
        if cancel['super']:
            cancel['super_levels'] = [2, 3] if od else [3] if category == 'special' else [1, 2, 3]
        if category in ('special', 'od_special', 'super'):
            # A special may be used as a known-startup ender, but projectile,
            # grab and multi-hit cancel windows are not supplied by this import.
            state = 'unknown'
            cancel['condition'] = 'Imported special continuation needs explicit route/timing data'
        if len(damage) > 1 or active is None:
            cancel['condition'] = 'Multi-hit/variable-active cancel window is not modeled'
        budget = None
        if state == 'normal' and all(value is not None for value in (advantage, active, recovery, hitstun)):
            budget = min(hitstun, advantage + active - 1 + recovery)
            if re.search(r'(?:special|super)[^;]*cancel[^;]*delayed', notes, re.I):
                delayed = re.search(r'cancel[^;]*delayed until after (\d+)(?:st|nd|rd|th) active frame', notes, re.I)
                if delayed:
                    budget -= int(delayed[1])
                elif re.search(r'cancel[^;]*delayed until after active frames', notes, re.I):
                    budget -= active
                else:
                    cancel['condition'] = 'Unparsed delayed cancel window'
        if budget is not None:
            cancel['hitstun_budget'] = max(0, budget)

        single_hit = len(damage) == 1 and active is not None and not re.search(r'\b[2-9][- ]hits?\b', notes, re.I)
        conditions = {}
        if category in ('normal', 'unique') and single_hit:
            punish = numeric(record.get('onPunishCounter'))
            if punish is not None:
                pc_state = 'normal' if state == 'normal' and punish <= 15 else 'unknown'
                conditions['punish_counter'] = {'hit': {'state': pc_state, 'advantage': punish,
                                                       'advantage_min': punish, 'advantage_max': punish}}
        move = dict(name=name or notation or record['id'], category=category,
                    input={'sf': notation or '?'}, startup=numeric(record.get('startup')),
                    active_frames=active, recovery_on_hit=recovery, damage=damage,
                    hit={'state': state, 'advantage': advantage, 'advantage_min': advantage, 'advantage_max': advantage},
                    block={'advantage': numeric(record.get('onBlock'))}, cancel=cancel,
                    conditions=conditions, search_eligible=not reasons,
                    properties=record.get('properties') or [],
                    counter_bonus_on_final_hit=single_hit,
                    search_exclusions=reasons, sources=[record['source']['url']],
                    source_record_id=record['id'], source_index=index,
                    notes=[notes] if notes else [])
        if drink_damage is not None:
            move['name'] = name.replace('(DL2)', '(DL0)')
            move['notes'].append('Damage uses the explicit DL0 values; other drink levels are not searched.')
        if category == 'super':
            level = next((int(label[-1]) for label, command in super_inputs.items() if notation == command), None)
            if level is None:
                move['search_eligible'] = False
                move['search_exclusions'].append('Super-level/input variant needs explicit data')
            else:
                move['super_level'] = level
                move['meter_cost'] = {'drive': 0, 'super': level}
        elif od:
            move['meter_cost'] = {'drive': 2, 'super': 0}
        if category == 'target_combo':
            parts, sequence = notation.split('~'), []
            for part in parts:
                sequence.append(part if re.match(r'[1-9]', part) else '5' + part)
            move['sequence'] = sequence
            move['input']['sf'] = ' > '.join(sequence)
        moves[key], records[key] = move, record
        by_input.setdefault(notation, []).append(key)

    # At most one unconditioned variant for each input. Ambiguous duplicates
    # stay recorded but cannot silently change the move a generated string uses.
    for keys in by_input.values():
        eligible = [key for key in keys if moves[key]['search_eligible']]
        if len(eligible) > 1:
            for key in eligible:
                moves[key]['search_eligible'] = False
                moves[key]['search_exclusions'].append('Ambiguous duplicate input variants')

    light_sequences = []
    for key, move in moves.items():
        if not move['search_eligible']:
            continue
        raw = records[key]
        allowed = chain_destinations(text_field(raw, 'notes')) if move['cancel']['chain'] else []
        for destination in allowed:
            if destination in moves and moves[destination]['search_eligible']:
                move['cancel']['chain_targets'].append(destination)
        if re.fullmatch(r'[125]L[PK]', move['input']['sf']):
            for next_key, following in moves.items():
                if not following['search_eligible'] or not re.fullmatch(r'[125]L[PK]', following['input']['sf']):
                    continue
                advantage = move['hit']['advantage'] if move['hit']['state'] == 'normal' else None
                if next_key in move['cancel']['chain_targets'] or (
                        advantage is not None and following['startup'] <= advantage):
                    light_sequences.append([key, next_key])
        # Inputs that trigger target follow-ups cannot also be fresh normals.
        for target_key, target in moves.items():
            sequence = target.get('sequence') or []
            if len(sequence) == 2 and sequence[0] == move['input']['sf']:
                followup = sequence[1].lower()
                if followup in moves:
                    move['cancel'].setdefault('target_followups', []).append(followup)

    enabled = sum(move['search_eligible'] for move in moves.values())
    return {
        'display_name': re.sub(r'^([CEM])\.(?=\w)', r'\1. ', source['name']['en'].replace('_', ' ')),
        'stats': {'health': source.get('hp')},
        'movement': deepcopy(source.get('movement', {})),
        'data_source': {'provider': PROVIDER, 'license': LICENSE,
                        'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
                        'url': source['source']['url'], 'snapshot_url': f'{SOURCE_BASE}/{character}.json',
                        'fetched_at': source['source']['fetchedAt'], 'imported_on': REVIEWED_ON},
        'combo_search': {
            'supported_light_sequences': light_sequences,
            'coverage': {'complete': False, 'reviewed_on': REVIEWED_ON,
                         'source_move_count': len(source['moves']), 'searchable_move_count': enabled,
                         'method': 'Conservative baseline frame timing; all source variants retained.',
                         'limitations': ['No character-state/resource, charge or stance simulation',
                                         'No imported special-to-special/super or juggle continuations',
                                         'Target-combo inputs require reviewed complete recipes',
                                         'No hitbox, projectile travel or accumulated pushback simulation',
                                         'Missing source values remain unknown; no in-game verification'],
                         },
        },
        'moves': moves,
        'documented_combos': [],
    }


def import_roster(source_dir=SOURCE_DIR, data_path=DATA_PATH):
    source_dir, data_path = Path(source_dir), Path(data_path)
    with data_path.open(encoding='utf-8') as source:
        data = json.load(source)
    with (source_dir / 'sa-levels.json').open(encoding='utf-8') as source:
        levels = json.load(source)
    for path in sorted(source_dir.glob('*.json')):
        if path.stem == 'sa-levels':
            continue
        with path.open(encoding='utf-8') as source:
            character = json.load(source)
        if character['id'] == 'aki':
            # A.K.I. is already in the reviewed app schema, including poison
            # variants and explicit recipes; it does not need raw conversion.
            if not isinstance(character.get('moves'), dict):
                raise ValueError('aki.json must contain the reviewed A.K.I. move dictionary')
            data['characters']['aki'] = {key: deepcopy(value) for key, value in character.items()
                                       if key != 'id'}
        else:
            data['characters'][character['id']] = convert_character(character, levels[character['id']])
    data['game']['roster_reviewed_on'] = REVIEWED_ON
    data['game']['roster_source'] = SOURCE_BASE
    data['game']['roster_count'] = len(data['characters'])
    from import_documented import apply_documented_routes
    apply_documented_routes(data)
    # Preserve existing data if conversion or JSON validation fails.
    temporary = data_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(data_path)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=SOURCE_DIR, help='Directory of source snapshots')
    parser.add_argument('--data', type=Path, default=DATA_PATH, help='Destination characters.json')
    args = parser.parse_args()
    data = import_roster(args.source_dir, args.data)
    print(f"Imported roster: {len(data['characters'])} characters.")


if __name__ == '__main__':
    main()
