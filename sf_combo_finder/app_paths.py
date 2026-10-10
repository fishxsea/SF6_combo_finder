"""Bundled resources stay with the app; personal files live in user storage."""
import os
from pathlib import Path
import sys


def user_data_dir():
    override = os.environ.get('SF_COMBO_FINDER_HOME')
    if override:
        return Path(override).expanduser()
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'SF Combo Finder'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'SF Combo Finder'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'sf-combo-finder'


USER_DATA_DIR = user_data_dir()
LIBRARY_PATH = USER_DATA_DIR / '.combo_library.json'
CUSTOM_COMBOS_PATH = USER_DATA_DIR / 'custom_combos.json'
PREFERENCES_PATH = USER_DATA_DIR / '.tui_preferences.json'


def read_personal_file(path, default_path):
    """Read old checkout files until the first save in the new location."""
    path = Path(path)
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        checkout = Path(__file__).resolve().parent.parent
        if (path == default_path and not getattr(sys, 'frozen', False)
                and not os.environ.get('SF_COMBO_FINDER_HOME')
                and (checkout / 'pyproject.toml').is_file()):
            return (checkout / path.name).read_text(encoding='utf-8')
        raise
