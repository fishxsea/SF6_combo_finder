"""Dark combo-browser palettes; independent of Textual and gameplay rules."""
from dataclasses import dataclass
import json
from pathlib import Path


from .app_paths import PREFERENCES_PATH, read_personal_file
DEFAULT_THEME = 'bagels'


def blend(background: str, foreground: str, amount: float) -> str:
    channels = [round(int(background[i:i + 2], 16) * (1 - amount) +
                      int(foreground[i:i + 2], 16) * amount) for i in (1, 3, 5)]
    return '#' + ''.join(f'{channel:02x}' for channel in channels)


@dataclass(frozen=True)
class DarkPalette:
    label: str
    colors: tuple[str, ...]
    background: str
    foreground: str
    primary: str
    secondary: str
    border: str

    def variables(self) -> dict[str, str]:
        # Only dark, lightly tinted surfaces are used for backgrounds, even
        # for headers and selection. Pale palette colors are reserved for text.
        bg, fg = self.background, self.foreground
        surface = blend(bg, fg, 0.06)
        selection = blend(bg, self.secondary, 0.15)
        return {
            'cf-background': bg, 'cf-foreground': fg,
            'cf-muted': blend(bg, fg, 0.70),
            'cf-disabled': blend(bg, fg, 0.40),
            'cf-surface': surface, 'cf-focus': blend(bg, fg, 0.12),
            'cf-selection': selection, 'cf-hover': blend(bg, fg, 0.09),
            'cf-header': blend(bg, self.secondary, 0.12),
            'cf-border': self.border, 'cf-primary': self.primary,
            'cf-secondary': self.secondary,
            'footer-background': surface, 'footer-foreground': fg,
            'footer-key-foreground': self.primary,
            'footer-key-background': surface,
            'block-cursor-background': selection,
            'block-cursor-foreground': fg,
            'block-cursor-blurred-background': surface,
            'block-cursor-blurred-foreground': fg,
            'block-hover-background': surface,
            'input-selection-background': selection,
            'button-focus-text-style': 'bold',
        }


PALETTES = {
    'bagels': DarkPalette('Bagels', ('#191a23', '#c7c5d5', '#ff9d66', '#b695e9'),
                         '#191a23', '#c7c5d5', '#ff9d66', '#b695e9', '#494653'),
    'tropical': DarkPalette('Tropical', ('#ef476f', '#ffd166', '#06d6a0', '#118ab2', '#073b4c'),
                           '#073b4c', '#f7f2e5', '#ffd166', '#06d6a0', '#118ab2'),
    'ember': DarkPalette('Ember', ('#001524', '#15616d', '#ffecd1', '#ff7d00', '#78290f'),
                        '#001524', '#ffecd1', '#ff7d00', '#ffecd1', '#15616d'),
    'deep-blue': DarkPalette('Deep Blue', ('#0466c8', '#0353a4', '#023e7d', '#002855', '#001845',
                                         '#001233', '#33415c', '#5c677d', '#7d8597', '#979dac'),
                            '#001233', '#979dac', '#4e82ba', '#979dac', '#0353a4'),
    'sage': DarkPalette('Sage', ('#cad2c5', '#84a98c', '#52796f', '#354f52', '#2f3e46'),
                       '#2f3e46', '#cad2c5', '#84a98c', '#cad2c5', '#52796f'),
    'forest': DarkPalette('Forest', ('#d8f3dc', '#b7e4c7', '#95d5b2', '#74c69d', '#52b788',
                                    '#40916c', '#2d6a4f', '#1b4332', '#081c15'),
                         '#081c15', '#d8f3dc', '#52b788', '#95d5b2', '#2d6a4f'),
    'slate': DarkPalette('Slate', ('#0d1b2a', '#1b263b', '#415a77', '#778da9', '#e0e1dd'),
                        '#0d1b2a', '#e0e1dd', '#778da9', '#e0e1dd', '#415a77'),
}


def load_theme(path: Path | None = PREFERENCES_PATH) -> str:
    if path is None:
        return DEFAULT_THEME
    try:
        preferences = read_personal_file(path, PREFERENCES_PATH)
        name = json.loads(preferences)['theme']
        return name if isinstance(name, str) and name in PALETTES else DEFAULT_THEME
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_THEME


def save_theme(name: str, path: Path | None = PREFERENCES_PATH) -> None:
    if name not in PALETTES:
        raise ValueError(f'Unknown theme: {name}')
    save_preference('theme', name, path)


def save_preference(key: str, value: str, path: Path | None) -> None:
    if path is None:
        return
    try:
        preferences = json.loads(read_personal_file(path, PREFERENCES_PATH))
        if not isinstance(preferences, dict):
            preferences = {}
    except (FileNotFoundError, ValueError):
        preferences = {}
    preferences[key] = value
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(preferences, indent=2) + '\n', encoding='utf-8')


def load_controller(path: Path | None = PREFERENCES_PATH) -> str:
    if path is not None:
        try:
            name = json.loads(read_personal_file(path, PREFERENCES_PATH))['controller']
            if name in ('xbox', 'playstation'):
                return name
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return 'xbox'


def save_controller(name: str, path: Path | None = PREFERENCES_PATH) -> None:
    if name not in ('xbox', 'playstation'):
        raise ValueError(f'Unknown controller: {name}')
    save_preference('controller', name, path)
