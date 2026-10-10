"""Interactive SF6 combo browser using the existing ComboFinder engine."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize
from textual.message import Message
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Button, Checkbox, DataTable, Footer, Input, Label, Select, Static
from textual.worker import get_current_worker

from .combo_finder import CONTROLLERS, DATA_PATH
from .combo_frames import frame_details
from .combo_setups import route_requirements, variation_label
from .combo_library import ComboLibrary, LIBRARY_PATH
from .tui_search import (SearchResult, SearchSettings, search_route_pool, route_pool_settings,
                         filter_route_pool, sort_combo_rows,
                         combo_startup, combo_poison_notes, sample_combo_rows,
                         combo_row_key, index_combo_rows, retain_combo_rows)
from .tui_themes import (DEFAULT_THEME, PALETTES, PREFERENCES_PATH, load_theme, save_theme,
                        load_controller, save_controller)
from .tui_columns import COLUMNS, DEFAULT_COLUMNS, load_columns, save_columns
from .tui_slider import IntegerSlider
from .custom_combos import CustomCombos
from .app_paths import CUSTOM_COMBOS_PATH
from .tui_custom_combos import CustomCombosScreen


class SearchProgress(Message):
    def __init__(self, generation: int, count: int):
        super().__init__()
        self.generation, self.count = generation, count


class SearchCompleted(Message):
    def __init__(self, generation: int, result: SearchResult | None, error: str = '', *, index=None):
        super().__init__()
        self.generation, self.result, self.error = generation, result, error
        self.index = index


class PoisonCacheCompleted(Message):
    def __init__(self, cache_generation: int, settings: SearchSettings,
                 result: SearchResult | None, index=None, error: str = ''):
        super().__init__()
        self.cache_generation, self.settings = cache_generation, settings
        self.result, self.index, self.error = result, index, error


class HelpScreen(ModalScreen):
    BINDINGS = [('escape', 'dismiss', 'Close'), ('f1', 'dismiss', 'Close')]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; background: $background 70%; }
    #help-box { width: 70; max-width: 95%; height: 85%; border: round $accent; padding: 1 2; background: $surface; }
    #help-box Static { height: auto; margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id='help-box'):
            yield Static(Text('SF6 Combo Finder', style='bold'))
            yield Static(
                'Change filters, then press Search or Ctrl+R. Enter in a numeric field also searches. '
                'The browser waits for Search before finding combos. Random count starts blank '
                'to show all matches. '
                'Use the length and random-count sliders or type exact values. Click or drag '
                'a slider; arrow keys adjust one step and Home/End select its endpoints. '
                'The left end of Random count selects All. Slider changes wait for Search or Shuffle. '
                'Set a count to sample results; Shuffle chooses a new '
                'sample from the cached search pool. Optimistic links and unrestricted light '
                'chains apply only when selected before pressing Search; changing these '
                'checkboxes waits for Search. Other route checkboxes filter cached routes. Character, length, '
                'meter and starting-condition changes load another pool. '
                'Documented-only searches prepare published routes; turning that option off '
                'loads generated candidates when needed. '
                'Sort by character, difficulty, length or '
                'raw damage or opening attack startup, in ascending or descending order, without searching again. '
                'Startup uses the first damaging attack; movement, jump travel and charge preparation '
                'are excluded. Unknown startup stays last in either direction.\n\n'
                'DISPLAY → Controller buttons: Xbox or PlayStation symbols. Changes apply '
                'immediately and are saved; SF notation displays the original move inputs. '
                'Button colors use explicit RGB values, independent of the terminal palette.\n\n'
                'Columns: choose which table columns to display, then Apply. The default '
                'columns are Diff / len / dmg (with poison badges), Combo, Fighter, Source '
                'and Startup. Defaults restores that layout. Choices are saved. Hiding a '
                'column keeps its information available in Details.\n\n'
                'Tab / Shift+Tab: move between controls\n'
                'Arrow keys: navigate results\n'
                'Enter on a result: open its details\n'
                'Ctrl+B: show/hide the right filter panel (hidden initially in small terminals)\n'
                'Ctrl+D: toggle details\n'
                'Ctrl+T: choose a dark theme (saved for the next launch)\n'
                'Ctrl+Y: copy selected combo\n'
                'Ctrl+S: star/unstar selected combo\n'
                'Ctrl+X: hide/restore selected combo\n'
                'Ctrl+R: search   Ctrl+N: shuffle\n'
                'Escape: cancel search   Ctrl+Q: quit\n\n'
                'Length counts inputs, including movement actions and target-combo inputs. '
                'Raw damage is before scaling and excludes poison damage over time. '
                'Difficulty is an estimate. Published recipes retain starting conditions '
                'and source links; timing candidates still require spacing checks.\n\n'
                '[Poison] in an A.K.I. table row marks a poison interaction or a published '
                'starting-poison requirement. Details explain the affected moves; a badge '
                'does not always require starting poisoned. A.K.I. searches load the selected '
                'poison state first and prepare the other in the background. Toggling poison '
                'reuses completed pools and keeps displayed routes that still connect. '
                'Counts can change when poison changes valid follow-ups.\n\n'
                'Grounded/midscreen/normal/unpoisoned are the default starting conditions. '
                'Choose Corner, Poisoned or Counter to find routes for those situations. '
                'Opponent state and posture select recorded starting conditions. '
                'Setup / requirements and Published setups show recorded variations. '
                '[Corner] marks a recorded corner setup. Source distinguishes published '
                'routes from timing candidates. '
                'Documented only excludes automatically generated timing candidates. '
                'Optimistic links and unrestricted light chains are exploration options.\n\n'
                'MY COMBOS → Build / edit combos: click directions, full motions and attack '
                'buttons to build a saved route. Next move extends the input string; Save '
                'includes the current input. The builder follows Xbox, PlayStation or SF '
                'notation. Add notes or an explanation for each route; Enter adds a new line '
                'in Notes, and saved notes appear in the combo details panel. '
                'Extend combo loads the selected result, and the builder can '
                'also load a displayed route as a starting point. Include custom combos '
                'includes saved routes in the table with a Custom combo source label. '
                'Custom combos only shows your saved routes of any length on their own, even when '
                'Include custom combos is off. '
                'Custom routes have no measured difficulty, damage, meter or frame timing. '
                'Your fighter, jumping/special exclusions and personal marks still '
                'filter them. Length limits apply when including custom combos in search results. '
                'Random sampling includes the displayed pool.\n\n'
                'Star saves a favorite; Hide excludes a combo from future searches. '
                'Show hidden includes excluded combos; Hidden only lets you review and restore them. '
                'Starred only shows favorites matching your other search filters. These filters combine. '
                'Marks persist across restarts and apply to the exact fighter/input string across '
                'starting conditions, not to its prefixes or extensions.\n\n'
                'Hover a filter for its description. Press Escape to close this help.',
                markup=False,
            )
            yield Static('Imported frame data: SF6 Sensei / SuperCombo Wiki (CC-BY-SA-4.0).\n'
                         'https://github.com/RyoSogawa/sf6-sensei\n'
                         'https://wiki.supercombo.gg/w/Street_Fighter_6\n'
                         'See DATA_NOTICE.md for attribution and import changes.', markup=False)
            yield Button('Close help', id='close-help')

    @on(Button.Pressed, '#close-help')
    def close_help(self) -> None:
        self.dismiss()


class ColumnsScreen(ModalScreen):
    BINDINGS = [('escape', 'dismiss', 'Cancel')]
    DEFAULT_CSS = """
    ColumnsScreen { align: center middle; background: $cf-background 85%; }
    #columns-box { width: 48; max-width: 95%; height: auto; max-height: 90%;
                   border: round $cf-primary; padding: 1 2; background: $cf-background; }
    #columns-box Checkbox { width: 100%; height: 1; border: none; padding: 0; margin: 0 0 1 0; }
    #columns-actions { height: 1; margin-top: 1; }
    #columns-actions Button { margin-right: 1; }
    #columns-warning { height: 1; color: $cf-secondary; }
    """

    def __init__(self, selected):
        super().__init__()
        self.selected = selected

    def compose(self):
        with VerticalScroll(id='columns-box'):
            yield Label('TABLE COLUMNS')
            for key, label in COLUMNS:
                yield Checkbox(label, key in self.selected, id=f'column-{key}')
            yield Static('', id='columns-warning', markup=False)
            with Horizontal(id='columns-actions'):
                yield Button('Apply', variant='primary', id='apply-columns')
                yield Button('Defaults', id='default-columns')
                yield Button('Cancel', id='cancel-columns')

    @on(Button.Pressed, '#apply-columns')
    def apply_columns(self):
        selected = tuple(key for key, _ in COLUMNS if self.query_one(f'#column-{key}', Checkbox).value)
        if not selected:
            self.query_one('#columns-warning', Static).update('Select at least one column.')
            return
        self.dismiss(selected)

    @on(Button.Pressed, '#default-columns')
    def default_columns(self):
        for key, _ in COLUMNS:
            self.query_one(f'#column-{key}', Checkbox).value = key in DEFAULT_COLUMNS
        self.query_one('#columns-warning', Static).update('')

    @on(Button.Pressed, '#cancel-columns')
    def cancel_columns(self):
        self.dismiss()


class ComboFinderApp(App):
    TITLE = 'SF6 Combo Finder'
    SUB_TITLE = 'Combo browser'
    BINDINGS = [
        Binding('ctrl+r', 'search', 'Search', priority=True),
        Binding('ctrl+n', 'shuffle', 'Shuffle', priority=True),
        Binding('ctrl+d', 'details', 'Details', priority=True),
        Binding('ctrl+b', 'filters', 'Filters', priority=True),
        Binding('ctrl+y', 'copy_combo', 'Copy', priority=True),
        Binding('ctrl+t', 'theme_picker', 'Theme', priority=True),
        Binding('ctrl+s', 'star_combo', 'Star', priority=True),
        Binding('ctrl+x', 'hide_combo', 'Hide/restore', priority=True),
        Binding('f1', 'help', 'Help'),
        Binding('escape', 'cancel_search', 'Cancel'),
        Binding('ctrl+q', 'quit', 'Quit', priority=True),
    ]
    CSS = """
    Screen {
        background: $cf-background;
        color: $cf-foreground;
        scrollbar-background: $cf-surface;
        scrollbar-color: $cf-border;
        scrollbar-color-hover: $cf-primary;
        scrollbar-color-active: $cf-secondary;
        scrollbar-size: 1 1;
    }
    #navigation { height: 3; padding: 1 2; background: $cf-background; }
    #brand { width: 23; height: 1; }
    #navigation Button { width: auto; min-width: 9; margin-right: 1; }
    #navigation .nav-active { background: $cf-selection; color: $cf-secondary; text-style: bold; }
    #roster-label { width: 1fr; height: 1; text-align: right; color: $cf-muted; }
    Button { height: 1; min-width: 9; padding: 0 1; border: none; background: $cf-surface; color: $cf-muted; }
    Button:hover, Button:focus { background: $cf-focus; color: $cf-primary; text-style: bold; }
    Button.-primary { background: $cf-selection; color: $cf-primary; text-style: bold; }
    Button:disabled { background: $cf-surface; color: $cf-disabled; }
    #body { height: 1fr; margin: 0 1 1 1; }
    #results-pane { width: 1fr; height: 1fr; }
    #results-box { height: 1fr; border: round $cf-border; border-title-color: $cf-primary; }
    #command-bar { height: 1; margin: 0 1 1 1; }
    #command-bar Button { margin-right: 1; }
    #sort-bar { height: 1; margin: 0 1 1 1; }
    #sort-bar Static { width: 8; height: 1; color: $cf-muted; }
    #sort-bar Select { width: 20; height: 1; padding: 0; border: none; margin-right: 1; }
    #sort-label { width: 1fr; height: 1; text-align: right; color: $cf-muted; }
    #status { height: 2; padding: 0 1; color: $cf-muted; }
    #results { height: 1fr; background: $cf-background; color: $cf-foreground; }
    DataTable > .datatable--header { background: $cf-header; color: $cf-secondary; text-style: bold; }
    DataTable > .datatable--odd-row { background: $cf-background; }
    DataTable > .datatable--even-row { background: $cf-background; }
    DataTable > .datatable--cursor { background: $cf-selection; color: $cf-foreground; }
    DataTable > .datatable--hover { background: $cf-hover; }
    #selection-panel { height: 11; margin-top: 1; padding: 0 1; border: round $cf-border; border-title-color: $cf-muted; }
    #combo-actions { height: 1; margin-bottom: 1; }
    #combo-actions Button { margin-right: 1; }
    #selected-combo { height: auto; max-height: 3; margin-bottom: 1; }
    #selection-meta { height: 2; }
    #selection-meter { height: 1; }
    #sidebar { width: 38; margin-left: 1; }
    #filters { height: 1fr; padding: 0 1; border: round $cf-border; border-title-color: $cf-muted; }
    #filter-search { width: 100%; margin-top: 1; }
    #filters Label { height: 1; margin-top: 1; color: $cf-muted; }
    #filters .section { margin-top: 1; color: $cf-primary; text-style: bold; }
    #filters Input { width: 100%; height: 1; padding: 0 1; border: none; background: $cf-surface; color: $cf-foreground; }
    #filters Input:focus { background: $cf-focus; color: $cf-primary; }
    #filters IntegerSlider:focus { background: $cf-focus; }
    #filters IntegerSlider > .slider--filled { color: $cf-secondary; }
    #filters IntegerSlider > .slider--track { color: $cf-border; }
    #filters IntegerSlider > .slider--thumb { color: $cf-primary; }
    #filters IntegerSlider:focus > .slider--thumb { color: $cf-secondary; }
    #filters Select { width: 100%; height: 1; border: none; padding: 0; }
    SelectCurrent { height: 1; padding: 0 1; border: none; background: $cf-surface; color: $cf-foreground; }
    Select:focus SelectCurrent { background: $cf-focus; color: $cf-primary; }
    SelectOverlay { border: round $cf-secondary; background: $cf-surface; }
    OptionList > .option-list--option-highlighted { background: $cf-selection; color: $cf-secondary; }
    #filters Checkbox { width: 100%; height: 1; padding: 0; border: none; margin-top: 1; background: $cf-background; color: $cf-muted; }
    #filters Checkbox:focus { background: $cf-focus; }
    #filters Checkbox > .toggle--button { color: $cf-surface; background: $cf-surface; }
    #filters Checkbox.-on > .toggle--button { color: $cf-secondary; background: $cf-surface; text-style: bold; }
    #filters Checkbox > .toggle--label { color: $cf-muted; background: transparent; }
    #filters Checkbox.-on > .toggle--label { color: $cf-secondary; text-style: bold; }
    #filters Checkbox:focus > .toggle--label { background: $cf-focus; text-style: underline; }
    .pair { height: auto; }
    .pair Vertical { width: 1fr; height: auto; margin-right: 1; }
    #overview-panel { height: 8; margin-top: 1; padding: 0 1; border: round $cf-border; border-title-color: $cf-muted; }
    #overview { height: auto; }
    #details { height: 45vh; min-height: 4; margin-top: 1; padding: 0 1; border: round $cf-border; border-title-color: $cf-muted; }
    #detail-text { height: auto; }
    Screen.compact #selection-panel { height: 9; }
    Screen.compact #selected-combo { max-height: 2; margin-bottom: 0; }
    Footer { background: $cf-surface; color: $cf-foreground; }
    Footer > .footer--key { background: $cf-surface; color: $cf-primary; }
    Footer > .footer--highlight { background: $cf-selection; color: $cf-secondary; }
    HelpScreen { background: $cf-background 85%; }
    #help-box { background: $cf-background; color: $cf-foreground; border: round $cf-primary; }
    """

    def __init__(self, data_path: Path = DATA_PATH, settings: SearchSettings | None = None,
                 *, mapped: bool = True, show_details: bool = False,
                 preferences_path: Path | None = PREFERENCES_PATH,
                 library_path: Path | None = LIBRARY_PATH, controller: str | None = None,
                 custom_combos_path: Path | None = CUSTOM_COMBOS_PATH):
        super().__init__()
        self.preferences_path = preferences_path
        self.visible_columns = load_columns(preferences_path)
        self.controller = controller if controller is not None else load_controller(preferences_path)
        if self.controller not in CONTROLLERS:
            raise ValueError(f'Unknown controller: {self.controller}')
        self.library = ComboLibrary(library_path)
        self.custom_combos = CustomCombos(custom_combos_path)
        self.palette_name = load_theme(preferences_path)
        for name, palette in PALETTES.items():
            variables = palette.variables()
            self.register_theme(Theme(
                name=name, primary=palette.primary, secondary=palette.secondary,
                accent=palette.primary, foreground=palette.foreground,
                background=palette.background, surface=variables['cf-surface'],
                panel=variables['cf-surface'], dark=True, variables=variables,
            ))
        self.theme = self.palette_name
        # Offer only this app's dark palettes, including in Textual's command
        # palette; no built-in light themes can be selected accidentally.
        for name in list(self.available_themes):
            if name not in PALETTES:
                self.unregister_theme(name)
        self.data_path = Path(data_path)
        initial_settings = settings or SearchSettings()
        self.settings = replace(initial_settings, character=initial_settings.character.lower(),
                                sample_size=None,
                                opponent_poisoned=(initial_settings.opponent_poisoned
                                                   and initial_settings.character.lower() == 'aki'))
        with self.data_path.open(encoding='utf-8') as source:
            self.combo_data = json.load(source)
            self.characters = self.combo_data['characters']
        if not self.characters:
            raise ValueError('The data file contains no characters')
        if self.settings.character.lower() not in ('all', *self.characters):
            raise ValueError(f'Unknown character: {self.settings.character}')
        self.mapped, self.show_details = mapped, show_details
        self.rows = []
        self.combo_pool = None
        self.pool_settings = None
        self.combo_pools = {}
        self.cache_generation = 0
        self.poison_cache_worker = None
        self.warming_pool_settings = None
        self.pending_poison_settings = None
        self.generation = 0
        self.render_generation = 0
        self.search_worker = None
        self.match_count = None
        self.searching = False
        self.route_controls_ready = False
        self.has_searched = False

    def compose(self) -> ComposeResult:
        s = self.settings
        with Horizontal(id='navigation'):
            brand = self.brand_text()
            yield Static(brand, id='brand')
            yield Button('Filters', id='toggle-filters')
            yield Button('Details', id='toggle-details')
            yield Button('Themes', id='toggle-theme')
            yield Static(f'{len(self.characters)} fighters', id='roster-label', markup=False)
        with Horizontal(id='body'):
            with Vertical(id='results-pane'):
                with Vertical(id='results-box'):
                    with Horizontal(id='command-bar'):
                        yield Button('Search', variant='primary', id='search')
                        yield Button('Shuffle', id='shuffle', disabled=True,
                                     tooltip='Choose a new sample from the cached matching pool; blank count uses 25.')
                        yield Button('Columns', id='choose-columns', tooltip='Choose which table columns to show. Your layout is saved.')
                        yield Button('Cancel', id='cancel', disabled=True)
                        yield Static('Difficulty ↑', id='sort-label', markup=False)
                    with Horizontal(id='sort-bar'):
                        yield Static('Sort by', markup=False)
                        yield Select([('Character', 'character'), ('Difficulty', 'difficulty'),
                                      ('Length', 'length'), ('Raw damage', 'damage'), ('Startup', 'startup')],
                                     value='difficulty', allow_blank=False, id='sort-by',
                                     tooltip='Startup sorts the opening damaging attack in frames; movement, jump travel and charge preparation are excluded. Unknown values stay last.')
                        yield Select([('Ascending ↑', 'ascending'), ('Descending ↓', 'descending')],
                                     value='ascending', allow_blank=False, id='sort-order')
                    yield DataTable(id='results', cursor_type='row', zebra_stripes=False,
                                    cursor_foreground_priority='renderable')
                    yield Static('Choose filters, then press Search (Ctrl+R).', id='status', markup=False)
                with Vertical(id='selection-panel'):
                    with Horizontal(id='combo-actions'):
                        yield Button('Extend combo', id='extend-combo', disabled=True,
                                     tooltip='Load this route into the clickable builder and save an extended custom combo.')
                        yield Button('☆ Star', id='star-combo', disabled=True,
                                     tooltip='Star/unstar this exact combo; saved across restarts (Ctrl+S).')
                        yield Button('Hide', id='hide-combo', disabled=True,
                                     tooltip='Hide/restore this exact combo. Use Show hidden or Hidden only to restore it (Ctrl+X).')
                    yield Static('Select a combo to inspect it.', id='selected-combo', markup=False)
                    yield Static('', id='selection-meta', markup=False)
                    yield Static('', id='selection-meter', markup=False)
                with VerticalScroll(id='details'):
                    yield Static('Select a combo to inspect it.', id='detail-text', markup=False)
            with Vertical(id='sidebar'):
                with VerticalScroll(id='filters'):
                    yield Button('Search', variant='primary', id='filter-search',
                                 tooltip='Search using the selected filters (Ctrl+R).')
                    yield Label('SEARCH FILTERS', classes='section')
                    yield Label('Character')
                    options = [('All characters', 'all')] + [
                        (data.get('display_name', key.upper()), key) for key, data in self.characters.items()]
                    yield Select(options, value=s.character.lower(), allow_blank=False, id='character')
                    with Horizontal(classes='pair'):
                        with Vertical():
                            yield Label('Min length')
                            yield Input(str(s.min_length), type='integer', id='min-length',
                                        tooltip='Minimum input count, including movement and target-combo inputs.')
                            yield IntegerSlider(1, max(20, s.min_length), s.min_length,
                                                id='min-length-slider',
                                                tooltip='Minimum length: click, drag or use arrow keys. Type above for exact values.')
                        with Vertical():
                            yield Label('Max length')
                            yield Input(str(s.max_length), type='integer', id='max-length',
                                        tooltip='Maximum input count. Larger searches take longer.')
                            yield IntegerSlider(1, max(20, s.max_length), s.max_length,
                                                id='max-length-slider',
                                                tooltip='Maximum length: click, drag or use arrow keys. Larger searches take longer.')
                    yield Label('Random count · blank = all')
                    yield Input('', type='integer', id='random-count',
                                tooltip='Sample this many matches without replacement after filtering. Blank shows all.')
                    yield IntegerSlider(0, 100, 0, id='random-count-slider',
                                        tooltip='Random count: left end = All; otherwise 1–100. Type a larger count to extend the range.')
                    yield Label('Maximum difficulty')
                    yield Select([('Any difficulty', 'any'), ('Easy', 'easy'), ('Medium', 'medium'), ('Hard', 'hard')],
                                 value=s.max_difficulty or 'any', allow_blank=False, id='difficulty',
                                 tooltip='Keep the selected estimated level and all easier levels.')
                    yield Label('STARTING CONDITIONS', classes='section')
                    yield Label('Opening hit')
                    yield Select([('Normal', 'normal'), ('Counter', 'counter'), ('Punish counter', 'punish_counter')],
                                 value=s.hit_type, allow_blank=False, id='hit-type',
                                 tooltip='Counter bonuses apply only to the opening hit.')
                    yield Label('Screen position')
                    yield Select([('Midscreen', 'midscreen'), ('Corner', 'corner'), ('Any position', 'any')],
                                 value=s.position, allow_blank=False, id='position',
                                 tooltip='Position filter for published routes. Any labels the required position.')
                    yield Label('Opponent state')
                    yield Select([('Grounded', 'grounded'), ('Airborne', 'airborne')],
                                 value=s.opponent_state, allow_blank=False, id='opponent-state',
                                 tooltip='Airborne starts use published routes; trajectory remains unverified.')
                    yield Label('Opponent posture', id='opponent-posture-label')
                    yield Select([('Unspecified', 'any'), ('Standing', 'standing'), ('Crouching', 'crouching')],
                                 value=s.opponent_posture, allow_blank=False, id='opponent-posture',
                                 tooltip='Filter published routes with explicit standing/crouching requirements.')
                    with Horizontal(classes='pair'):
                        with Vertical():
                            yield Label('Drive bars')
                            yield Input(str(s.drive_meter), type='integer', id='drive-meter',
                                        tooltip='0–6. OD costs 2; Drive Rush 1; Drive Rush Cancel 3. Regeneration is excluded.')
                        with Vertical():
                            yield Label('Super bars')
                            yield Input(str(s.super_meter), type='integer', id='super-meter', tooltip='0–3; supers cost their level.')
                    yield Checkbox('Opponent poisoned', s.opponent_poisoned, id='poisoned',
                                   tooltip='Switch cached starting-poison variants, keeping displayed routes that still connect. Poison can change damage and valid follow-ups.')
                    yield Label('ROUTE OPTIONS', classes='section')
                    yield Checkbox('Documented only', s.documented_only, id='documented',
                                   tooltip='Capcom trial transcriptions and community recipes for all characters, with source labels. Includes attack-ending prefixes; coverage is incomplete.')
                    yield Checkbox('Exclude jumping', s.no_jumping, id='no-jumping', tooltip='Exclude all jump attacks and jump-in starters.')
                    yield Checkbox('Exclude specials', s.no_specials, id='no-specials', tooltip='Exclude specials and supers.')
                    yield Checkbox('Optimistic links', s.optimistic_links, id='optimistic',
                                   tooltip='Use maximum variable advantage; favorable contact timing is required. Press Search to apply.')
                    yield Checkbox('Explore light chains', s.explore_light_chains, id='explore',
                                   tooltip='Bypass the conservative light-string filter; unchecked pushback may make strings impossible. Press Search to apply.')
                    yield Label('MY COMBOS', classes='section')
                    yield Button('Build / edit combos', id='custom-combos',
                                 tooltip='Create personal combos by clicking direction, motion and attack buttons.')
                    yield Checkbox('Include custom combos', s.show_custom, id='show-custom',
                                   tooltip='Include your saved routes matching fighter, length and exclusion filters. Custom routes have no measured difficulty, damage or meter data.')
                    yield Checkbox('Custom combos only', s.custom_only, id='custom-only',
                                   tooltip='Show only your saved routes of any length, even when Include custom combos is off. Fighter, exclusions and personal marks still apply.')
                    yield Checkbox('Starred only', s.starred_only, id='starred-only',
                                   tooltip='Only saved favorites matching the other filters. Hidden favorites remain excluded unless revealed.')
                    yield Checkbox('Show hidden', s.show_hidden, id='show-hidden',
                                   tooltip='Include excluded combos alongside visible ones. Select a hidden combo and choose Restore.')
                    yield Checkbox('Hidden only', s.hidden_only, id='hidden-only',
                                   tooltip='Only excluded combos matching the other filters, regardless of Show hidden. Combine with Starred only if desired.')
                    yield Label('DISPLAY', classes='section')
                    yield Label('Controller buttons')
                    yield Select([('Xbox', 'xbox'), ('PlayStation', 'playstation')],
                                 value=self.controller, allow_blank=False, id='controller',
                                 tooltip='Change button symbols and colors immediately; saved for the next launch.')
                    yield Label('Color theme · dark only')
                    yield Select([(palette.label, name) for name, palette in PALETTES.items()],
                                 value=self.theme, allow_blank=False, id='color-theme',
                                 tooltip='Apply a dark palette immediately; saved for the next launch.')
                    yield Checkbox('SF notation', not self.mapped, id='sf-notation',
                                   tooltip='Show 2LP/236HP instead of mapped arrows and colored controller buttons.')
                with Vertical(id='overview-panel'):
                    yield Static('', id='overview', markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.theme_changed_signal.subscribe(self, self.on_combo_theme_changed)
        self.screen.set_class(self.size.height < 32, 'compact')
        for widget_id, title in (('results-box', 'Combos'), ('selection-panel', 'Selected combo'),
                                 ('filters', 'Search'), ('overview-panel', 'Session'), ('details', 'Notes & sources')):
            self.query_one(f'#{widget_id}').border_title = title
        self.query_one('#details').display = self.show_details
        self.query_one('#toggle-details', Button).set_class(self.show_details, 'nav-active')
        self.resize_details(self.size.height)
        self.update_character_controls(self.settings.character)
        self.set_filters_visible(self.size.width >= 110)
        table = self.query_one('#results', DataTable)
        self.configure_columns(table)
        table.focus()
        self.reset_combo_selection('Choose filters, then press Search.')
        self.update_overview()
        self.route_controls_ready = True

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return PALETTES[DEFAULT_THEME].variables()

    def palette_colors(self) -> dict[str, str]:
        return PALETTES[self.theme].variables()

    def brand_text(self) -> Text:
        colors = self.palette_colors()
        brand = Text('↪ SF6 ', style=colors['cf-primary'])
        brand.append('combo finder', style=colors['cf-muted'])
        return brand

    @on(Select.Changed, '#color-theme')
    def combo_theme_selected(self, event: Select.Changed) -> None:
        name = str(event.value)
        if name in PALETTES and name != self.theme:
            self.theme = name

    def on_combo_theme_changed(self, theme: Theme) -> None:
        if theme.name not in PALETTES or theme.name != self.theme:
            return
        selector = self.query_one('#color-theme', Select)
        with selector.prevent(Select.Changed):
            selector.value = theme.name
        self.query_one('#brand', Static).update(self.brand_text())
        self.update_overview()
        if self.rows:
            self.update_details(self.query_one('#results', DataTable).cursor_row)
        if theme.name != self.palette_name:
            self.palette_name = theme.name
            try:
                save_theme(theme.name, self.preferences_path)
            except OSError:
                self.notify('Theme applied, but the preference could not be saved.', severity='warning')

    @on(Button.Pressed, '#toggle-theme')
    def action_theme_picker(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            return
        self.set_filters_visible(True)
        selector = self.query_one('#color-theme', Select)
        selector.focus()
        selector.scroll_visible()

    def on_resize(self, event: Resize) -> None:
        if self.screen_stack:
            self.screen_stack[0].set_class(event.size.height < 32, 'compact')
        self.resize_details(event.size.height)

    def resize_details(self, terminal_height: int) -> None:
        # Cap the proportional panel so navigation and results still fit.
        reserved = 26 if terminal_height < 32 else 28
        for details in self.query('#details'):
            details.styles.max_height = max(4, terminal_height - reserved)

    def update_character_controls(self, character: str) -> None:
        selected = self.characters.values() if character == 'all' else [self.characters.get(character, {})]
        has_posture = any(recipe.get('conditions', {}).get('opponent_posture', 'any') != 'any'
                          for entry in selected for recipe in entry.get('documented_combos', []))
        posture = self.query_one('#opponent-posture', Select)
        posture.display = has_posture
        self.query_one('#opponent-posture-label', Label).display = has_posture
        if not has_posture:
            with posture.prevent(Select.Changed):
                posture.value = 'any'
        poisoned = self.query_one('#poisoned', Checkbox)
        poisoned.display = character == 'aki'
        if character != 'aki':
            # Changing fighters applies on Search, like the other Select fields.
            if self.pending_poison_settings is not None:
                self.pending_poison_settings = None
                if not self.searching:
                    self.query_one('#cancel', Button).disabled = True
                    self.update_results_status()
            with poisoned.prevent(Checkbox.Changed):
                poisoned.value = False

    @on(Select.Changed, '#character')
    def character_changed(self, event: Select.Changed) -> None:
        self.update_character_controls(str(event.value))

    def set_filters_visible(self, visible: bool) -> None:
        self.query_one('#sidebar').display = visible
        self.query_one('#filters').display = visible
        self.query_one('#toggle-filters', Button).set_class(visible, 'nav-active')

    def reset_combo_selection(self, message: str) -> None:
        self.query_one('#selected-combo', Static).update(message)
        self.query_one('#detail-text', Static).update(message)
        self.query_one('#selection-meta', Static).update('')
        self.query_one('#selection-meter', Static).update('')
        self.query_one('#selection-panel').border_subtitle = ''
        self.query_one('#extend-combo', Button).disabled = True
        self.query_one('#star-combo', Button).disabled = True
        self.query_one('#hide-combo', Button).disabled = True

    def update_overview(self) -> None:
        settings = self.settings
        scope = 'All fighters' if settings.character == 'all' else self.characters[settings.character]['display_name']
        count = '—' if self.match_count is None else f'{self.match_count:,}'
        mode = 'All matches' if settings.sample_size is None else f'Random {settings.sample_size}'
        rows = [('Fighter', scope), ('Inputs', f'{settings.min_length}–{settings.max_length} · {mode}'),
                ('Meter', f'{settings.drive_meter} Drive · {settings.super_meter} Super'),
                ('Prepared' if self.searching else 'Matches', count), ('Shown', str(len(self.rows)))]
        colors = self.palette_colors()
        text = Text(' Search    Value'.ljust(32),
                    style=f"bold {colors['cf-secondary']} on {colors['cf-header']}")
        for index, (label, value) in enumerate(rows):
            text.append('\n')
            background = colors['cf-surface'] if index % 2 == 0 else colors['cf-background']
            text.append(f' {label:<9}{value}'.ljust(32), style=f"{colors['cf-foreground']} on {background}")
        self.query_one('#overview', Static).update(text)

    def sync_numeric_slider(self, field_id: str) -> None:
        field = self.query_one(f'#{field_id}', Input)
        slider = self.query_one(f'#{field_id}-slider', IntegerSlider)
        raw = field.value.strip()
        try:
            value = 0 if field_id == 'random-count' and not raw else int(raw)
        except ValueError:
            return  # Keep incomplete edits available for normal search validation.
        if value < slider.minimum or (field_id == 'random-count' and raw and value == 0):
            return
        slider.maximum = max(100 if field_id == 'random-count' else 20, value)
        with slider.prevent(IntegerSlider.Changed):
            slider.value = value
        slider.refresh()

    @on(Input.Changed, '#min-length')
    @on(Input.Changed, '#max-length')
    @on(Input.Changed, '#random-count')
    def numeric_input_changed(self, event: Input.Changed) -> None:
        self.sync_numeric_slider(event.input.id)

    @on(IntegerSlider.Changed)
    def numeric_slider_changed(self, event: IntegerSlider.Changed) -> None:
        field_id = event.slider.id.removesuffix('-slider')
        field = self.query_one(f'#{field_id}', Input)
        with field.prevent(Input.Changed):
            field.value = '' if field_id == 'random-count' and event.value == 0 else str(event.value)
        if field_id in {'min-length', 'max-length'}:
            other_id = 'max-length' if field_id == 'min-length' else 'min-length'
            other = self.query_one(f'#{other_id}', Input)
            try:
                other_value = int(other.value)
            except ValueError:
                return
            if ((field_id == 'min-length' and event.value > other_value) or
                    (field_id == 'max-length' and event.value < other_value)):
                with other.prevent(Input.Changed):
                    other.value = str(event.value)
                self.sync_numeric_slider(other_id)

    def read_settings(self) -> SearchSettings:
        def number(widget_id, label, optional=False):
            value = self.query_one(f'#{widget_id}', Input).value.strip()
            if optional and not value:
                return None
            try:
                return int(value)
            except ValueError:
                raise ValueError(f'{label} must be a whole number') from None

        def selected(widget_id):
            return str(self.query_one(f'#{widget_id}', Select).value)

        def checked(widget_id):
            return self.query_one(f'#{widget_id}', Checkbox).value

        difficulty = selected('difficulty')
        return SearchSettings(
            character=selected('character'), min_length=number('min-length', 'Minimum length'),
            max_length=number('max-length', 'Maximum length'),
            sample_size=number('random-count', 'Random count', optional=True),
            hit_type=selected('hit-type'), position=selected('position'), opponent_state=selected('opponent-state'),
            opponent_posture=selected('opponent-posture'),
            drive_meter=number('drive-meter', 'Drive bars'), super_meter=number('super-meter', 'Super bars'),
            max_difficulty=None if difficulty == 'any' else difficulty,
            no_specials=checked('no-specials'), no_jumping=checked('no-jumping'),
            opponent_poisoned=(selected('character') == 'aki' and checked('poisoned')),
            documented_only=checked('documented'),
            optimistic_links=checked('optimistic'), explore_light_chains=checked('explore'),
            starred_only=checked('starred-only'), show_hidden=checked('show-hidden'),
            hidden_only=checked('hidden-only'),
            show_custom=checked('show-custom'),
            custom_only=checked('custom-only'),
        )

    def active_route_settings(self) -> SearchSettings:
        """Live filters and Shuffle keep the last explicitly searched timing mode."""
        return replace(self.read_settings(), optimistic_links=self.settings.optimistic_links,
                       explore_light_chains=self.settings.explore_light_chains)

    @on(Button.Pressed, '#filter-search')
    @on(Button.Pressed, '#search')
    @on(Input.Submitted)
    async def action_search(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            return
        try:
            settings = self.read_settings()
            if settings.sample_size is not None and settings.sample_size < 1:
                raise ValueError('Random count must be positive, or blank for all results')
        except ValueError as error:
            self.query_one('#status', Static).update(str(error))
            return
        if settings.custom_only:
            if self.searching:
                self.action_cancel_search()
            if self.size.width < 110:
                self.set_filters_visible(False)
            await self.show_custom_without_search(settings=settings)
            self.query_one('#results', DataTable).focus()
            return
        if not self.searching and (self.cached_pool_key(settings) in self.combo_pools or
                (self.combo_pool is not None and
                 self.poison_pool_key(settings) == self.poison_pool_key(self.settings))):
            if self.size.width < 110:
                self.set_filters_visible(False)
            await self.switch_poison_pool(settings, shuffle=True)
        else:
            self.start_combo_search(close_filters=True, settings=settings)
        if self.searching or self.combo_pool is not None:
            self.query_one('#results', DataTable).focus()

    @on(Checkbox.Changed)
    async def route_option_changed(self, event: Checkbox.Changed) -> None:
        if not self.route_controls_ready or event.checkbox.id not in {
                'documented', 'no-jumping', 'no-specials', 'optimistic', 'explore', 'poisoned',
                'starred-only', 'show-hidden', 'hidden-only', 'show-custom', 'custom-only'}:
            return
        if not self.has_searched:
            if event.checkbox.id in {'show-custom', 'custom-only'} or ((self.settings.show_custom
                    or self.settings.custom_only)
                    and event.checkbox.id not in {'optimistic', 'explore'}):
                await self.show_custom_without_search()
            return
        if event.checkbox.id in {'optimistic', 'explore'}:
            if not self.searching:
                self.update_results_status()
            return
        # Ignore initial checkbox messages when the mounted values already
        # match the running search. SF notation has its own display handler.
        try:
            settings = self.active_route_settings()
            if settings.custom_only and not self.searching:
                await self.show_custom_without_search(settings=settings)
                return
            if settings == self.settings:
                if self.pending_poison_settings is not None and not self.searching:
                    self.query_one('#cancel', Button).disabled = True
                    self.update_results_status()
                self.pending_poison_settings = None
                return
            if not self.searching and self.cached_pool_key(settings) in self.combo_pools:
                await self.switch_poison_pool(settings)
                return
            if self.poison_pool_key(settings) == self.poison_pool_key(self.settings):
                if settings.sample_size is not None and settings.sample_size < 1:
                    raise ValueError('Random count must be positive, or blank for all results')
                if self.searching:
                    # Apply the latest options to the broad pool when it finishes.
                    self.pending_poison_settings = settings
                else:
                    await self.switch_poison_pool(settings)
                return
        except ValueError as error:
            self.query_one('#status', Static).update(str(error))
            return
        self.start_combo_search(close_filters=False, settings=settings)

    @staticmethod
    def poison_pool_key(settings: SearchSettings) -> SearchSettings:
        return replace(route_pool_settings(settings), opponent_poisoned=False)

    def cached_pool_key(self, settings: SearchSettings) -> SearchSettings:
        key = route_pool_settings(settings)
        if key.documented_only and key not in self.combo_pools:
            broader = replace(key, documented_only=False)
            if broader in self.combo_pools:
                return broader
        return key

    def clear_pool_cache(self) -> None:
        self.cache_generation += 1
        if self.poison_cache_worker and not self.poison_cache_worker.is_finished:
            self.poison_cache_worker.cancel()
        self.poison_cache_worker = None
        self.warming_pool_settings = None
        self.combo_pools.clear()
        self.pending_poison_settings = None
        self.combo_pool = None
        self.pool_settings = None

    def prepare_poison_pool(self, settings: SearchSettings) -> None:
        key = route_pool_settings(settings)
        if key in self.combo_pools or key == self.warming_pool_settings:
            return
        self.warming_pool_settings = key
        self.poison_cache_worker = self.warm_poison_cache(key, self.cache_generation)

    async def switch_poison_pool(self, settings: SearchSettings, *, shuffle=False) -> None:
        if settings.custom_only:
            await self.show_custom_without_search(settings=settings)
            return
        key = self.cached_pool_key(settings)
        if key not in self.combo_pools:
            self.pending_poison_settings = settings
            state = 'poisoned' if settings.opponent_poisoned else 'unpoisoned'
            self.query_one('#status', Static).update(
                f'Preparing {state} results in the background; current combos remain visible.')
            self.query_one('#cancel', Button).disabled = False
            self.prepare_poison_pool(key)
            return
        selected_index = self.query_one('#results', DataTable).cursor_row
        selected_key = (combo_row_key(self.rows[selected_index])
                        if 0 <= selected_index < len(self.rows) else None)
        pool = self.with_custom_rows(filter_route_pool(self.combo_pools[key], settings, self.library), settings)
        rows = (sample_combo_rows(pool, settings.sample_size) if shuffle else
                retain_combo_rows(pool, index_combo_rows(pool), self.rows, settings.sample_size))
        self.pending_poison_settings = None
        self.settings = settings
        self.combo_pool, self.pool_settings = pool, key
        self.generation += 1
        self.query_one('#cancel', Button).disabled = True
        self.query_one('#shuffle', Button).disabled = False
        await self.present_results(rows, len(pool), self.generation, selected_key=selected_key)

    def start_combo_search(self, *, close_filters: bool, settings: SearchSettings | None = None) -> None:
        try:
            settings = settings if settings is not None else self.read_settings()
            if settings.sample_size is not None and settings.sample_size < 1:
                raise ValueError('Random count must be positive, or blank for all results')
        except ValueError as error:
            self.query_one('#status', Static).update(str(error))
            return
        self.settings = settings
        self.has_searched = True
        self.clear_pool_cache()
        self.query_one('#shuffle', Button).disabled = True
        self.generation += 1
        if close_filters and self.size.width < 110:
            self.set_filters_visible(False)
        self.rows = []
        self.match_count = None
        self.searching = True
        self.query_one('#results', DataTable).clear()
        self.reset_combo_selection('Searching for combos…')
        self.update_overview()
        self.query_one('#status', Static).update('Searching… Escape cancels. Large length ranges take longer.')
        self.query_one('#cancel', Button).disabled = False
        self.search_worker = self.run_search(settings, self.generation)

    @work(thread=True, exclusive=True, group='combo-search')
    def run_search(self, settings: SearchSettings, generation: int) -> None:
        worker = get_current_worker()
        try:
            # Retain all matches; the UI samples this pool after completion.
            result = search_route_pool(settings, self.data_path,
                                   cancelled=lambda: worker.is_cancelled,
                                   progress=lambda count: self.post_message(SearchProgress(generation, count)),
                                   library=self.library.snapshot())
            if not worker.is_cancelled:
                self.post_message(SearchCompleted(generation, result))
        except Exception as error:
            if not worker.is_cancelled:
                self.post_message(SearchCompleted(generation, None, str(error)))

    @work(thread=True, exclusive=True, group='poison-cache')
    def warm_poison_cache(self, settings: SearchSettings, cache_generation: int) -> None:
        worker = get_current_worker()
        try:
            result = search_route_pool(settings, self.data_path, cancelled=lambda: worker.is_cancelled,
                                   library=self.library.snapshot())
            if not worker.is_cancelled and not result.cancelled:
                self.post_message(PoisonCacheCompleted(cache_generation, settings, result))
        except Exception as error:
            if not worker.is_cancelled:
                self.post_message(PoisonCacheCompleted(cache_generation, settings, None, error=str(error)))

    async def on_poison_cache_completed(self, message: PoisonCacheCompleted) -> None:
        # Shuffling and sorting do not invalidate the background cache.
        if message.cache_generation != self.cache_generation:
            return
        if message.settings == self.warming_pool_settings:
            self.warming_pool_settings = None
        if message.error or message.result is None:
            if self.pending_poison_settings is not None:
                self.pending_poison_settings = None
                self.query_one('#cancel', Button).disabled = True
                poisoned = self.query_one('#poisoned', Checkbox)
                with poisoned.prevent(Checkbox.Changed):
                    poisoned.value = self.settings.opponent_poisoned
                self.query_one('#status', Static).update(f'Could not prepare poison results: {message.error}')
            return
        self.combo_pools[message.settings] = message.result.route_pool
        if self.pending_poison_settings is not None:
            settings = self.pending_poison_settings
            if route_pool_settings(settings) == message.settings:
                await self.switch_poison_pool(settings)

    def on_search_progress(self, message: SearchProgress) -> None:
        if message.generation == self.generation:
            self.match_count = message.count
            self.update_overview()
            self.query_one('#status', Static).update(f'Searching… {message.count:,} candidate routes prepared. Escape cancels.')

    async def on_search_completed(self, message: SearchCompleted) -> None:
        if message.generation != self.generation:
            return
        self.query_one('#cancel', Button).disabled = True
        self.searching = False
        if message.error or message.result is None:
            self.pending_poison_settings = None
            error = message.error or 'No result returned'
            self.query_one('#status', Static).update(f'Search failed: {error}')
            self.reset_combo_selection('Correct the filters and search again.')
            self.update_overview()
            return
        if message.result.cancelled:
            self.pending_poison_settings = None
            self.query_one('#status', Static).update('Search cancelled. Adjust filters and search again.')
            self.reset_combo_selection('No combo selected.')
            self.update_overview()
            return
        self.pool_settings = route_pool_settings(self.settings)
        self.combo_pools[self.pool_settings] = message.result.route_pool
        if (self.pending_poison_settings is not None
                and route_pool_settings(self.pending_poison_settings) == self.pool_settings):
            self.settings = self.pending_poison_settings
            self.pending_poison_settings = None
        self.combo_pool = self.with_custom_rows(
            filter_route_pool(message.result.route_pool, self.settings, self.library), self.settings)
        self.query_one('#shuffle', Button).disabled = False
        if self.settings.character == 'aki':
            # Prepare the alternate while the completed results are being drawn.
            alternate = replace(self.pool_settings, opponent_poisoned=not self.settings.opponent_poisoned)
            self.prepare_poison_pool(alternate)
        rows = sample_combo_rows(self.combo_pool, self.settings.sample_size)
        await self.present_results(rows, len(self.combo_pool), message.generation)
        if message.generation != self.generation:
            return
        if self.pending_poison_settings is not None:
            await self.switch_poison_pool(self.pending_poison_settings)

    async def present_results(self, rows, total: int, generation: int, *, selected_key=None) -> None:
        self.rows = self.sorted_rows(rows)
        self.match_count = total
        self.update_overview()
        index = (next((i for i, row in enumerate(self.rows) if combo_row_key(row) == selected_key), 0)
                 if selected_key else 0)
        await self.render_rows(generation, selected_index=index)
        if generation != self.generation:
            return
        if not self.rows:
            self.query_one('#status', Static).update('No matching combos. Try different lengths, meter, or starting conditions.')
            self.reset_combo_selection('No combo selected.')
        else:
            self.update_results_status()
            self.update_details(index)

    def sorted_rows(self, rows):
        return sort_combo_rows(rows, str(self.query_one('#sort-by', Select).value),
                               descending=self.query_one('#sort-order', Select).value == 'descending')

    def sort_description(self) -> str:
        field = str(self.query_one('#sort-by', Select).value)
        label = {'character': 'Character', 'difficulty': 'Difficulty', 'length': 'Length',
                 'damage': 'Raw damage', 'startup': 'Startup'}[field]
        arrow = '↓' if self.query_one('#sort-order', Select).value == 'descending' else '↑'
        return f'{label} {arrow}'

    def update_results_status(self) -> None:
        mode = 'sampled' if self.settings.sample_size is not None else 'shown'
        pending = (self.query_one('#optimistic', Checkbox).value != self.settings.optimistic_links
                   or self.query_one('#explore', Checkbox).value != self.settings.explore_light_chains)
        hint = ' · Link options changed; press Search to apply.' if pending else ''
        self.query_one('#status', Static).update(
            f'{len(self.rows):,} {mode} / {self.match_count:,} matches · {self.sort_description()}{hint}')

    @on(Select.Changed, '#sort-by')
    @on(Select.Changed, '#sort-order')
    async def combo_sort_changed(self) -> None:
        if not self.route_controls_ready:
            return
        self.query_one('#sort-label', Static).update(self.sort_description())
        if self.rows:
            index = self.query_one('#results', DataTable).cursor_row
            selected = self.rows[index] if 0 <= index < len(self.rows) else None
            self.rows = self.sorted_rows(self.rows)
            index = self.rows.index(selected) if selected is not None else 0
            await self.render_rows(self.generation, selected_index=index)
            self.update_details(index)
            if not self.searching:
                self.update_results_status()

    async def render_rows(self, generation: int, *, selected_index: int = 0) -> None:
        self.render_generation += 1
        render_generation = self.render_generation
        table = self.query_one('#results', DataTable)
        table.clear(columns=True)
        self.configure_columns(table)
        mapped = not self.query_one('#sf-notation', Checkbox).value
        for index, (finder, combo) in enumerate(self.rows):
            if generation != self.generation or render_generation != self.render_generation:
                return
            difficulty = combo['difficulty']['label']
            style = {'easy': 'green', 'medium': 'yellow', 'hard': 'red'}.get(difficulty, self.palette_colors()['cf-secondary'])
            raw_damage = combo['damage']['raw_total']
            source = combo['evidence'].get('source_label')
            damage_label = f'{raw_damage:,}' if raw_damage is not None else 'unknown'
            bracket = Text(f"[{difficulty} | {combo['length']} | {damage_label}]", style=style)
            if combo_poison_notes(finder, combo):
                bracket.append(' [Poison]', style=f'bold {self.palette_colors()["cf-secondary"]}')
            conditions = combo.get('conditions', {})
            if combo['evidence'].get('kind') == 'published_recipe' and conditions.get('position') == 'corner':
                bracket.append(' [Corner]', style=f'bold {self.palette_colors()["cf-secondary"]}')
            hit_type = conditions.get('hit_type', finder.hit_type)
            if hit_type != 'normal':
                bracket.append(' [CH]' if hit_type == 'counter' else ' [PC]')
            if conditions.get('opponent_state', finder.opponent_state) == 'airborne':
                bracket.append(' [Airborne]')
            starred, hidden = self.library.marks(combo)
            if starred:
                bracket.append(' ★', style=self.palette_colors()['cf-primary'])
            if hidden:
                bracket.append(' [hidden]', style=self.palette_colors()['cf-muted'])
            notation = Text.from_ansi(finder.format_combo(combo, mapped=mapped, color=mapped,
                                                       controller=self.controller))
            published = combo['evidence'].get('kind') == 'published_recipe'
            position = conditions.get('position', '—') if published else '—'
            setup = combo.get('setup', {})
            startup = combo_startup(finder, combo)
            startup_label = f'{startup:g}f' if startup is not None else 'unknown'
            cells = dict(summary=bracket, combo=notation,
                         fighter=self.characters[finder.character].get('display_name', finder.character),
                         position=position, source=source or 'Frame timing', startup=startup_label)
            if 'requirements' in self.visible_columns:
                cells['requirements'] = '; '.join(setup.get('requirements') or route_requirements(finder, combo)) or '—'
            if 'variations' in self.visible_columns:
                cells['variations'] = '; '.join(variation_label(item) for item in
                                              setup.get('published_variations', [])) or '—'
            table.add_row(*(cells[key] for key in self.visible_columns), key=str(index))
            if index % 100 == 99:
                await asyncio.sleep(0)
        if self.rows:
            table.move_cursor(row=selected_index)

    def configure_columns(self, table):
        for key, label in COLUMNS:
            if key in self.visible_columns:
                table.add_column(label, key=key)

    @on(Button.Pressed, '#choose-columns')
    def choose_columns(self):
        self.push_screen(ColumnsScreen(self.visible_columns), self.columns_selected)

    async def columns_selected(self, selected):
        if selected is None or selected == self.visible_columns:
            return
        self.visible_columns = selected
        try:
            save_columns(selected, self.preferences_path)
        except OSError:
            self.notify('Columns changed, but the layout could not be saved.', severity='warning')
        table = self.query_one('#results', DataTable)
        index = table.cursor_row
        await self.render_rows(self.generation, selected_index=index)

    @on(Checkbox.Changed, '#sf-notation')
    async def notation_changed(self) -> None:
        if self.rows:
            index = self.query_one('#results', DataTable).cursor_row
            await self.render_rows(self.generation, selected_index=index)
            self.update_details(index)

    @on(Select.Changed, '#controller')
    async def controller_changed(self, event: Select.Changed) -> None:
        name = str(event.value)
        if name not in CONTROLLERS or name == self.controller:
            return
        self.controller = name
        try:
            save_controller(name, self.preferences_path)
        except OSError:
            self.notify('Controller changed, but the preference could not be saved.', severity='warning')
        if self.rows:
            index = self.query_one('#results', DataTable).cursor_row
            await self.render_rows(self.generation, selected_index=index)
            self.update_details(index)

    @on(DataTable.RowHighlighted, '#results')
    def row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value is not None:
            self.update_details(int(event.row_key.value))

    @on(DataTable.RowSelected, '#results')
    def row_selected(self) -> None:
        self.query_one('#details').display = True
        self.query_one('#toggle-details', Button).add_class('nav-active')

    def update_details(self, index: int) -> None:
        if not 0 <= index < len(self.rows):
            return
        finder, combo = self.rows[index]
        text = Text()
        mapped = not self.query_one('#sf-notation', Checkbox).value
        notation = Text.from_ansi(finder.format_combo(combo, mapped=mapped, color=mapped,
                                                   controller=self.controller))
        self.query_one('#selected-combo', Static).update(notation)
        self.query_one('#extend-combo', Button).disabled = False
        name = self.characters[finder.character].get('display_name', finder.character)
        self.query_one('#selection-panel').border_subtitle = f'{index + 1}/{len(self.rows)} · {name}'
        kind = combo['evidence'].get('source_label', 'Timing candidate')
        conditions = combo.get('conditions', {})
        position = conditions.get('position', self.settings.position)
        colors = self.palette_colors()
        raw_damage = combo['damage']['raw_total']
        damage_label = f'{raw_damage:,}' if raw_damage is not None else 'unknown'
        startup = combo_startup(finder, combo)
        startup_label = f'{startup:g}f' if startup is not None else 'unknown'
        meta = Text(f"{combo['difficulty']['label'].upper()} · {combo['length']} inputs · "
                    f"raw damage {damage_label} · startup {startup_label}", style=colors['cf-primary'])
        meta.append(f'\n{position} · {kind}', style=colors['cf-muted'])
        if combo['evidence']['kind'] == 'custom':
            self.query_one('#selection-meta', Static).update(meta)
            self.query_one('#selection-meter', Static).update('Drive / Super: not recorded')
            details = Text()
            details.append(combo['custom_name'] + '\n\n', style='bold')
            details.append_text(notation)
            if combo.get('custom_description'):
                details.append('\n\nNOTES / EXPLANATION\n', style='bold')
                details.append(combo['custom_description'])
            details.append('\n\nSaved custom combo. Frame timing, damage, meter and difficulty are not recorded.\n')
            self.query_one('#detail-text', Static).update(details)
            self.update_mark_buttons(combo)
            return
        poison_notes = combo_poison_notes(finder, combo)
        text.append_text(frame_details(finder, combo, mapped=mapped, controller=self.controller))
        if poison_notes:
            meta.append(' · [Poison]', style=colors['cf-secondary'])
        starred, hidden = self.library.marks(combo)
        if starred:
            meta.append(' · ★ Starred', style=colors['cf-primary'])
        if hidden:
            meta.append(' · Hidden', style=colors['cf-muted'])
        self.update_mark_buttons(combo)
        self.query_one('#selection-meta', Static).update(meta)
        meter = Text('Drive  ', style=colors['cf-muted'])
        drive, super_spent = combo['drive_spent'], combo['super_spent']
        meter.append('█' * drive, style=colors['cf-primary'])
        meter.append('░' * max(0, self.settings.drive_meter - drive), style=colors['cf-border'])
        meter.append(f' {drive}/{self.settings.drive_meter}    Super  ', style=colors['cf-muted'])
        meter.append('█' * super_spent, style=colors['cf-secondary'])
        meter.append('░' * max(0, self.settings.super_meter - super_spent), style=colors['cf-border'])
        meter.append(f' {super_spent}/{self.settings.super_meter}', style=colors['cf-muted'])
        self.query_one('#selection-meter', Static).update(meter)
        if poison_notes:
            text.append('[Poison] Poison interaction\n', style=f'bold {colors["cf-secondary"]}')
            for note in poison_notes:
                text.append(note + '\n')
            text.append('\n')
        setup = combo.get('setup', {})
        requirements = setup.get('requirements') or route_requirements(finder, combo)
        if requirements:
            text.append('\nSETUP / REQUIREMENTS\n', style='bold')
            text.append(' · '.join(requirements) + '\n')
        variations = setup.get('published_variations', [])
        if variations:
            text.append('Published setups for this input sequence:\n')
            for variant in variations:
                text.append('  • ' + variation_label(variant) + '\n')
        text.append(f'\nOpening attack startup: {startup_label} (movement, jump travel and charge preparation excluded).\n')
        if combo['evidence']['kind'] == 'published_recipe':
            text.append(f"\n{kind}: {combo['evidence'].get('title', '')}\n")
        text.append(f"\nDrive: {combo['drive_spent']}  Super: {combo['super_spent']}  "
                    f"Difficulty score: {combo['difficulty']['score']}\n")
        text.append('Transitions: ' + ' → '.join(combo['transitions']) + '\n')
        for source in combo['evidence'].get('sources', []):
            text.append(source + '\n', style=f'link {source}')
        text.append('Difficulty: ' + ', '.join(f'{key.replace("_", " ")}={value}'
                                              for key, value in combo['difficulty']['components'].items()) + '\n')
        for note in combo['notes'] + combo['difficulty']['reasons'] + combo['difficulty']['caveats']:
            text.append(note + '\n')
        text.append('Raw damage is before scaling; poison damage over time is excluded.')
        self.query_one('#detail-text', Static).update(text)

    def update_mark_buttons(self, combo):
        starred, hidden = self.library.marks(combo)
        star_button = self.query_one('#star-combo', Button)
        star_button.label = '★ Unstar' if starred else '☆ Star'
        star_button.disabled = False
        hide_button = self.query_one('#hide-combo', Button)
        hide_button.label = 'Restore' if hidden else 'Hide'
        hide_button.disabled = False

    def with_custom_rows(self, pool, settings):
        return ([] if settings.custom_only else list(pool)) + self.custom_combos.rows(
            self.combo_data, settings, self.library)

    async def show_custom_without_search(self, *, settings=None):
        try:
            settings = settings if settings is not None else self.active_route_settings()
            pool = self.custom_combos.rows(self.combo_data, settings, self.library)
            rows = sample_combo_rows(pool, settings.sample_size)
        except ValueError as error:
            self.notify(str(error), severity='error')
            return
        self.settings = settings
        self.pending_poison_settings = None
        self.query_one('#cancel', Button).disabled = True
        self.query_one('#shuffle', Button).disabled = not (self.has_searched or settings.custom_only)
        self.generation += 1
        await self.present_results(rows, len(pool), self.generation)

    @on(Button.Pressed, '#custom-combos')
    @on(Button.Pressed, '#extend-combo')
    def open_custom_combos(self, event: Button.Pressed):
        seed = None
        character = str(self.query_one('#character', Select).value)
        index = self.query_one('#results', DataTable).cursor_row
        if event.button.id == 'extend-combo' and 0 <= index < len(self.rows):
            finder, seed = self.rows[index]
            character = finder.character
        try:
            self.custom_combos.reload()
        except (OSError, ValueError) as error:
            self.notify(f'Could not open custom combos: {error}', severity='error')
            return
        self.push_screen(CustomCombosScreen(self.custom_combos, self.combo_data, character=character,
                         mode='sf' if self.query_one('#sf-notation', Checkbox).value else self.controller,
                         candidates=self.rows, seed=seed), self.custom_combos_closed)

    async def custom_combos_closed(self, result):
        mode = result['mode']
        self.query_one('#sf-notation', Checkbox).value = mode == 'sf'
        if mode != 'sf':
            self.query_one('#controller', Select).value = mode
        if not result['changed']:
            return
        checkbox = self.query_one('#show-custom', Checkbox)
        with checkbox.prevent(Checkbox.Changed):
            checkbox.value = True
        if self.searching:
            self.pending_poison_settings = replace(self.settings, show_custom=True)
        elif self.has_searched and self.cached_pool_key(self.settings) in self.combo_pools:
            await self.switch_poison_pool(replace(self.settings, show_custom=True))
        else:
            await self.show_custom_without_search()

    @on(Button.Pressed, '#star-combo')
    async def action_star_combo(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            self.screen.save_combo()
            return
        await self.toggle_combo_mark('starred')

    @on(Button.Pressed, '#hide-combo')
    async def action_hide_combo(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            return
        await self.toggle_combo_mark('hidden')

    async def toggle_combo_mark(self, mark: str) -> None:
        index = self.query_one('#results', DataTable).cursor_row
        if self.searching or not 0 <= index < len(self.rows):
            return
        _, combo = self.rows[index]
        try:
            enabled = self.library.toggle(combo, mark)
        except (OSError, ValueError) as error:
            self.notify(f'Could not save combo: {error}', severity='error')
            return
        message = ('Starred' if enabled else 'Unstarred') if mark == 'starred' else ('Hidden' if enabled else 'Restored')
        self.notify(f'{message} combo.')
        # Refill a filtered/random result pool when membership changes. A star
        # in the ordinary view updates in place without changing the selection.
        if (mark == 'starred' and self.settings.starred_only) or (
                mark == 'hidden' and (self.settings.hidden_only or not self.settings.show_hidden)):
            if not self.has_searched:
                await self.show_custom_without_search()
            else:
                await self.switch_poison_pool(self.settings)
        else:
            await self.render_rows(self.generation, selected_index=index)
            self.update_details(index)

    @on(Button.Pressed, '#shuffle')
    async def action_shuffle(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            return
        if (not self.has_searched and not self.settings.custom_only) or self.searching:
            return
        if not self.query_one('#random-count', Input).value.strip():
            self.query_one('#random-count', Input).value = '25'
        try:
            settings = self.active_route_settings()
            if settings.sample_size is not None and settings.sample_size < 1:
                raise ValueError('Random count must be positive, or blank for all results')
        except ValueError as error:
            self.query_one('#status', Static).update(str(error))
            return
        if settings.custom_only:
            await self.show_custom_without_search(settings=settings)
            self.query_one('#results', DataTable).focus()
            return
        key = self.cached_pool_key(settings)
        if key not in self.combo_pools:
            if (self.combo_pool is not None
                    and self.poison_pool_key(settings) == self.poison_pool_key(self.settings)):
                await self.switch_poison_pool(settings, shuffle=True)
            else:
                self.start_combo_search(close_filters=True, settings=settings)
            return
        if self.size.width < 110:
            self.set_filters_visible(False)
        await self.switch_poison_pool(settings, shuffle=True)
        self.query_one('#results', DataTable).focus()

    @on(Button.Pressed, '#cancel')
    def action_cancel_search(self) -> None:
        if self.searching:
            if self.search_worker:
                self.search_worker.cancel()
            self.generation += 1
            self.rows = []
            self.clear_pool_cache()
            self.query_one('#shuffle', Button).disabled = True
            self.searching = False
            self.match_count = None
            self.query_one('#results', DataTable).clear()
            self.query_one('#status', Static).update('Search cancelled. Adjust filters and search again.')
            self.reset_combo_selection('No combo selected.')
            self.update_overview()
            self.query_one('#cancel', Button).disabled = True
        elif self.pending_poison_settings is not None:
            self.pending_poison_settings = None
            self.cache_generation += 1
            self.warming_pool_settings = None
            if self.poison_cache_worker and not self.poison_cache_worker.is_finished:
                self.poison_cache_worker.cancel()
            poisoned = self.query_one('#poisoned', Checkbox)
            with poisoned.prevent(Checkbox.Changed):
                poisoned.value = self.settings.opponent_poisoned
            self.query_one('#cancel', Button).disabled = True
            self.update_results_status()

    @on(Button.Pressed, '#toggle-details')
    def action_details(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            return
        details = self.query_one('#details')
        details.display = not details.display
        self.query_one('#toggle-details', Button).set_class(details.display, 'nav-active')

    @on(Button.Pressed, '#toggle-filters')
    def action_filters(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            return
        filters = self.query_one('#filters')
        self.set_filters_visible(not filters.display)
        if filters.display:
            self.query_one('#character', Select).focus()
        else:
            self.query_one('#results', DataTable).focus()

    def action_copy_combo(self) -> None:
        if isinstance(self.screen, CustomCombosScreen):
            self.screen.copy_output()
            return
        index = self.query_one('#results', DataTable).cursor_row
        if 0 <= index < len(self.rows):
            finder, combo = self.rows[index]
            self.copy_to_clipboard(finder.format_combo(combo, mapped=not self.query_one('#sf-notation', Checkbox).value,
                                                      controller=self.controller))
            self.notify('Combo copied (requires terminal clipboard support).')

    def action_help(self) -> None:
        self.push_screen(HelpScreen())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DATA_PATH, help='Character/notation JSON file')
    parser.add_argument('--controller', choices=CONTROLLERS, help='Button layout (default: saved choice or xbox)')
    args = parser.parse_args()
    try:
        ComboFinderApp(args.data, controller=args.controller).run()
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
