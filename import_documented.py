"""Compile reviewed published recipes without adding speculative transitions.

The offline snapshot stores exact move references, provenance, and coverage gaps.
Follow-ups are recipe-local copies: their damage is for that hit, their input
does not repeat the parent motion, and they cannot enter generated searches.
"""
from copy import deepcopy
import argparse
import json
from pathlib import Path

from sf_combo_finder.combo_finder import DATA_PATH

ROOT = Path(__file__).parent
SNAPSHOT_PATH = ROOT / 'data' / 'documented_routes.json'


def apply_documented_routes(data, snapshot_path=SNAPSHOT_PATH):
    snapshot = json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    for character, recipes in snapshot['characters'].items():
        entry = data['characters'][character]
        moves = entry['moves']
        # Rebuilding is idempotent and retains separately curated recipes.
        for key in list(moves):
            if moves[key].get('documented_import'):
                del moves[key]
        retained = [r for r in entry.get('documented_combos', [])
                    if not r.get('documented_import')]
        imported = []
        for recipe in recipes:
            source = snapshot['sources'][recipe['source']]
            route = []
            for index, step in enumerate(recipe['steps']):
                key = step['move']
                base = moves[key]
                if set(step) != {'move'}:
                    key = f"doc_{recipe['id']}_{index}"
                    move = deepcopy(base)
                    move.update(documented_import=True, search_eligible=False,
                                search_exclusions=['Published recipe step only.'])
                    if 'input' in step:
                        move['input'] = {'sf': step['input']}
                        move.pop('sequence', None)
                    for field in ('category', 'meter_cost', 'damage_unknown'):
                        if field in step:
                            move[field] = deepcopy(step[field])
                    if step.get('requires_previous'):
                        if not route:
                            raise ValueError(f"Missing parent in {recipe['id']}")
                        move['requires'] = [route[-1]]
                    moves[key] = move
                route.append(key)
            imported.append(dict(
                id=recipe['id'], moves=route,
                transitions=['published_transition'] * (len(route) - 1),
                conditions=deepcopy(recipe['conditions']), sources=[source['url']],
                source_kind=source['kind'], source_label=source['label'],
                source_version=source['version'], title=recipe['section'],
                documented_import=True,
                notes=recipe.get('notes', []) + [source['version']],
            ))
        entry['documented_combos'] = imported + retained
        entry['documented_coverage'] = deepcopy(snapshot['coverage'][character])
    # Preserve measured link difficulty when the existing conservative engine
    # can describe a published transition. Unknown juggle/stance timing stays
    # qualitative and never grants new automatic cancel permissions.
    from sf_combo_finder.combo_finder import ComboFinder
    for character in snapshot['characters']:
        entry = data['characters'][character]
        for recipe in entry['documented_combos']:
            if not recipe.get('documented_import'):
                continue
            finder = ComboFinder(character, data=data, hit_type=recipe['conditions']['hit_type'])
            poisoned, started, previous, previous_id = recipe['conditions']['opponent_poisoned'], False, None, None
            for index, key in enumerate(recipe['moves']):
                move = entry['moves'][key]
                attacks = bool(move.get('damage')) or move.get('damage_unknown', False)
                effective, poisoned = finder._resolve(move, poisoned, attacks and not started)
                if previous is not None and finder._eligible(move) and finder._eligible(previous):
                    transition = finder._transition(previous_id, previous, key, effective)
                    if transition:
                        recipe['transitions'][index - 1] = transition[0]
                previous, previous_id, started = effective, key, started or attacks
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DATA_PATH,
                        help='Destination move database')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT_PATH,
                        help='Reviewed recipe snapshot')
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding='utf-8'))
    apply_documented_routes(data, args.snapshot)
    # Validate all references before replacing the working database.
    from sf_combo_finder.combo_finder import ComboFinder
    for character in data['characters']:
        ComboFinder(character, data=data)
    temporary = args.data.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(args.data)
    count = sum(len(c['documented_combos']) for c in data['characters'].values())
    print(f'Imported {count} published recipes across {len(data["characters"])} characters.')


if __name__ == '__main__':
    main()
