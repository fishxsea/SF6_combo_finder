"""Selectable combo table columns, with a compact default layout."""
import json

from .app_paths import PREFERENCES_PATH, read_personal_file
from .tui_themes import save_preference

COLUMNS = (
    ('summary', 'Diff / len / dmg'),
    ('combo', 'Combo'),
    ('fighter', 'Fighter'),
    ('position', 'Position'),
    ('source', 'Source'),
    ('startup', 'Startup'),
    ('requirements', 'Setup / requirements'),
    ('variations', 'Published setups'),
)
DEFAULT_COLUMNS = ('summary', 'combo', 'fighter', 'source', 'startup')


def load_columns(path=PREFERENCES_PATH):
    if path is not None:
        try:
            selected = json.loads(read_personal_file(path, PREFERENCES_PATH))['table_columns']
            if isinstance(selected, list) and all(isinstance(key, str) for key in selected):
                known = tuple(key for key, _ in COLUMNS if key in selected)
                if known:
                    return known
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return DEFAULT_COLUMNS


def save_columns(selected, path=PREFERENCES_PATH):
    save_preference('table_columns', list(selected), path)
