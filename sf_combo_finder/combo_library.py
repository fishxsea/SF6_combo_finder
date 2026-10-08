"""Persistent personal marks, independent of move IDs and recipe sources."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .app_paths import LIBRARY_PATH, read_personal_file


def combo_identity(combo):
    """Identify the exact fighter/input string across imports and UI notation.

    Marks apply across starting conditions, but never to prefixes or extensions.
    Flatten atomic target combos so equivalent recipe representations match.
    """
    inputs = []
    for value in combo['inputs']:
        for part in value.split('>'):
            part = re.sub(r'\s+', '', part).upper()
            part = re.sub(r'^J\.', '8', part)
            if re.fullmatch(r'[LMH][PK]', part):
                part = '5' + part
            inputs.append(part)
    canonical = json.dumps([combo['character'].lower(), inputs], separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


class ComboLibrary:
    def __init__(self, path=LIBRARY_PATH, *, entries=None):
        self.path = Path(path) if path is not None else None
        self.entries = deepcopy(entries) if entries is not None else self._read()

    def _read(self):
        if self.path is None:
            return {}
        try:
            data = json.loads(read_personal_file(self.path, LIBRARY_PATH))
            entries = data['combos']
            if data.get('version') != 1 or not isinstance(entries, dict):
                raise ValueError('Unsupported library format')
            for key, value in entries.items():
                if not isinstance(value, dict) or not isinstance(value.get('starred'), bool) or not isinstance(value.get('hidden'), bool):
                    raise ValueError('Invalid saved combo marks')
            return entries
        except FileNotFoundError:
            return {}
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f'Cannot read combo library {self.path}: {error}') from error

    def snapshot(self):
        return ComboLibrary(None, entries=self.entries)

    def marks(self, combo):
        entry = self.entries.get(combo_identity(combo), {})
        return bool(entry.get('starred')), bool(entry.get('hidden'))

    def matches(self, combo, *, show_hidden=False, hidden_only=False, starred_only=False):
        starred, hidden = self.marks(combo)
        return ((not starred_only or starred) and
                (hidden if hidden_only else show_hidden or not hidden))

    def toggle(self, combo, mark):
        if mark not in ('starred', 'hidden'):
            raise ValueError(f'Unknown combo mark: {mark}')
        # Merge the latest file so another app instance's marks are retained.
        entries = self._read() if self.path is not None else deepcopy(self.entries)
        key = combo_identity(combo)
        entry = entries.setdefault(key, dict(character=combo['character'], inputs=list(combo['inputs']),
                                            starred=False, hidden=False))
        entry[mark] = not entry[mark]
        enabled = entry[mark]
        if not entry['starred'] and not entry['hidden']:
            del entries[key]
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
        return enabled
