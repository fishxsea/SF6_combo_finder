"""Personal combo strings, stored independently of the bundled move database."""
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from .app_paths import CUSTOM_COMBOS_PATH
from .combo_finder import ComboFinder


def normalize_inputs(inputs):
    result = []
    for value in inputs:
        if not isinstance(value, str):
            raise ValueError('Combo inputs must be strings')
        for part in value.split('>'):
            part = re.sub(r'\s+', '', part).upper()
            part = re.sub(r'^J\.', '8', part)
            if re.fullmatch(r'(?:LP|MP|HP|LK|MK|HK|PP|KK|P|K)(?:\+(?:LP|MP|HP|LK|MK|HK))*', part):
                part = '5' + part
            if not part:
                raise ValueError('Add at least one input to the combo')
            result.append(part)
    if not result:
        raise ValueError('Add at least one input to the combo')
    return result


class CustomCombos:
    def __init__(self, path=CUSTOM_COMBOS_PATH):
        self.path = Path(path) if path is not None else None
        self.entries = self._read()

    def _read(self):
        if self.path is None:
            return []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return []
        try:
            if data.get('version') != 1 or not isinstance(data.get('combos'), list):
                raise ValueError('Unsupported custom combo format')
            ids = set()
            for entry in data['combos']:
                if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str)
                        or not entry['id'] or entry['id'] in ids
                        or not isinstance(entry.get('name'), str)
                        or not isinstance(entry.get('description', ''), str)
                        or not isinstance(entry.get('character'), str) or not entry['character']
                        or not isinstance(entry.get('inputs'), list)):
                    raise ValueError('Invalid saved custom combo')
                normalize_inputs(entry['inputs'])
                ids.add(entry['id'])
            return data['combos']
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError(f'Cannot read custom combos {self.path}: {error}') from error

    def reload(self):
        if self.path is not None:
            self.entries = self._read()

    def _write(self, entries):
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                                 prefix=self.path.name + '.', delete=False) as output:
                    temporary = Path(output.name)
                    json.dump({'version': 1, 'combos': entries}, output, ensure_ascii=False, indent=2)
                    output.write('\n')
                temporary.replace(self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        self.entries = entries

    def save(self, character, name, inputs, *, entry_id=None, description=None):
        if description is not None and not isinstance(description, str):
            raise ValueError('Combo notes must be text')
        entry = dict(id=entry_id or uuid4().hex, character=character.lower(),
                     name=name.strip() or 'My combo', inputs=normalize_inputs(inputs))
        if not entry['character'] or entry['character'] == 'all':
            raise ValueError('Choose a fighter for your combo')
        entries = self._read() if self.path is not None else deepcopy(self.entries)
        index = next((i for i, saved in enumerate(entries) if saved['id'] == entry['id']), None)
        entry['description'] = (description.strip() if description is not None else
                                entries[index].get('description', '') if index is not None else '')
        if index is None:
            entries.append(entry)
        else:
            entries[index] = entry
        self._write(entries)
        return entry

    def delete(self, entry_id):
        entries = self._read() if self.path is not None else deepcopy(self.entries)
        self._write([entry for entry in entries if entry['id'] != entry_id])

    def rows(self, data, settings, library):
        """Display authored routes without claiming measured timing or damage."""
        if not (settings.show_custom or settings.custom_only):
            return []
        rows = []
        for entry in self.entries:
            character = entry['character']
            if character not in data['characters'] or settings.character not in ('all', character):
                continue
            inputs = normalize_inputs(entry['inputs'])
            if not settings.custom_only and not settings.min_length <= len(inputs) <= settings.max_length:
                continue
            if settings.no_jumping and any(value.startswith(('7', '8', '9')) for value in inputs):
                continue
            if settings.no_specials and any(re.search(r'(?:[1-9]{2,}|\[).*?(?:P|K)', value) for value in inputs):
                continue
            finder = ComboFinder(character, data=data)
            keys = [f'custom_{index}' for index in range(len(inputs))]
            finder.moves = {key: dict(name=value, input={'sf': value}, category='custom',
                                      startup=None, active_frames=None, recovery_on_hit=None,
                                      damage=[], damage_unknown=True, hit={'state': 'unknown'},
                                      cancel={}) for key, value in zip(keys, inputs)}
            combo = dict(character=character, inputs=inputs, moves=keys, length=len(inputs),
                         custom_id=entry['id'], custom_name=entry['name'],
                         custom_description=entry.get('description', ''),
                         damage={'raw_total': None}, drive_spent=None, super_spent=None,
                         transitions=['custom'] * (len(inputs) - 1), conditions={},
                         evidence={'kind': 'custom', 'source_label': 'Custom combo', 'sources': []},
                         difficulty={'label': 'custom', 'score': float('inf'), 'estimated': False,
                                     'components': {}, 'reasons': [], 'caveats': []}, notes=[])
            if library.matches(combo, show_hidden=settings.show_hidden, hidden_only=settings.hidden_only,
                               starred_only=settings.starred_only):
                rows.append((finder, combo))
        return rows
