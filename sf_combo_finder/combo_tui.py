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
from .combo_library import ComboLibrary, LIBRARY_PATH
from .tui_search import SearchResult, SearchSettings, search_combos, sort_combo_rows, combo_startup
from .tui_themes import (DEFAULT_THEME, PALETTES, PREFERENCES_PATH, load_theme, save_theme,
                        load_controller, save_controller)


class SearchProgress(Message):
    def __init__(self, generation: int, count: int):
        super().__init__()
        self.generation, self.count = generation, count


class SearchCompleted(Message):
    def __init__(self, generation: int, result: SearchResult | None, error: str = ''):
        super().__init__()
        self.generation, self.result, self.error = generation, result, error


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
                'to show all matches. Set a count to sample results; Shuffle repeats the '
                'search with a new random sample. Sort by character, difficulty, length or '
                'raw damage or opening attack startup, in ascending or descending order, without searching again. '
                'Startup uses the first damaging attack; movement, jump travel and charge preparation '
                'are excluded. Unknown startup stays last in either direction.\n\n'
                'DISPLAY → Controller buttons: Xbox or PlayStation symbols. Changes apply '
                'immediately and are saved; SF notation displays the original move inputs. '
                'Button colors use explicit RGB values, independent of the terminal palette.\n\n'
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
                'Grounded/midscreen/normal/unpoisoned are the default starting conditions. '
                'Choose Corner, Poisoned or Counter to find routes for those situations. '
                'Documented only excludes automatically generated timing candidates. '
                'Optimistic links and unrestricted light chains are exploration options.\n\n'
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
    #filters Label { height: 1; margin-top: 1; color: $cf-muted; }
    #filters .section { margin-top: 1; color: $cf-primary; text-style: bold; }
    #filters Input { width: 100%; height: 1; padding: 0 1; border: none; background: $cf-surface; color: $cf-foreground; }
    #filters Input:focus { background: $cf-focus; color: $cf-primary; }
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
    #details { height: 10; max-height: 35%; margin-top: 1; padding: 0 1; border: round $cf-border; border-title-color: $cf-muted; }
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
                 library_path: Path | None = LIBRARY_PATH, controller: str | None = None):
        super().__init__()
        self.preferences_path = preferences_path
        self.controller = controller if controller is not None else load_controller(preferences_path)
        if self.controller not in CONTROLLERS:
            raise ValueError(f'Unknown controller: {self.controller}')
        self.library = ComboLibrary(library_path)
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
                                sample_size=None, opponent_state='grounded')
        with self.data_path.open(encoding='utf-8') as source:
            self.characters = json.load(source)['characters']
        if not self.characters:
            raise ValueError('The data file contains no characters')
        if self.settings.character.lower() not in ('all', *self.characters):
            raise ValueError(f'Unknown character: {self.settings.character}')
        self.mapped, self.show_details = mapped, show_details
        self.rows = []
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
            yield Button('Browse', id='browse', classes='nav-active')
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
                                     tooltip='After searching, repeat with a new random sample; blank count uses 25.')
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
                        with Vertical():
                            yield Label('Max length')
                            yield Input(str(s.max_length), type='integer', id='max-length',
                                        tooltip='Maximum input count. Larger searches take longer.')
                    yield Label('Random count · blank = all')
                    yield Input('', type='integer', id='random-count',
                                tooltip='Sample this many matches without replacement after filtering. Blank shows all.')
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
                    with Horizontal(classes='pair'):
                        with Vertical():
                            yield Label('Drive bars')
                            yield Input(str(s.drive_meter), type='integer', id='drive-meter',
                                        tooltip='0–6. OD costs 2; Drive Rush 1; Drive Rush Cancel 3. Regeneration is excluded.')
                        with Vertical():
                            yield Label('Super bars')
                            yield Input(str(s.super_meter), type='integer', id='super-meter', tooltip='0–3; supers cost their level.')
                    yield Checkbox('Opponent poisoned', s.opponent_poisoned, id='poisoned',
                                   tooltip='Start poisoned; poison and detonation changes are applied along the route.')
                    yield Label('ROUTE OPTIONS', classes='section')
                    yield Checkbox('Documented only', s.documented_only, id='documented',
                                   tooltip='Capcom trial transcriptions and community recipes for all characters, with source labels. Includes attack-ending prefixes; coverage is incomplete.')
                    yield Checkbox('Exclude jumping', s.no_jumping, id='no-jumping', tooltip='Exclude all jump attacks and jump-in starters.')
                    yield Checkbox('Exclude specials', s.no_specials, id='no-specials', tooltip='Exclude specials and supers.')
                    yield Checkbox('Optimistic links', s.optimistic_links, id='optimistic',
                                   tooltip='Use maximum variable advantage; favorable contact timing is required.')
                    yield Checkbox('Explore light chains', s.explore_light_chains, id='explore',
                                   tooltip='Bypass the conservative light-string filter; unchecked pushback may make strings impossible.')
                    yield Label('MY COMBOS', classes='section')
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
        self.set_filters_visible(self.size.width >= 110)
        table = self.query_one('#results', DataTable)
        table.add_columns('Difficulty / len / raw dmg', 'Combo', 'Fighter', 'Position', 'Source', 'Startup')
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
        self.set_filters_visible(True)
        selector = self.query_one('#color-theme', Select)
        selector.focus()
        selector.scroll_visible()

    def on_resize(self, event: Resize) -> None:
        if self.screen_stack:
            self.screen_stack[0].set_class(event.size.height < 32, 'compact')

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
        self.query_one('#star-combo', Button).disabled = True
        self.query_one('#hide-combo', Button).disabled = True

    def update_overview(self) -> None:
        settings = self.settings
        scope = 'All fighters' if settings.character == 'all' else self.characters[settings.character]['display_name']
        count = '—' if self.match_count is None else f'{self.match_count:,}'
        mode = 'All matches' if settings.sample_size is None else f'Random {settings.sample_size}'
        rows = [('Fighter', scope), ('Inputs', f'{settings.min_length}–{settings.max_length} · {mode}'),
                ('Meter', f'{settings.drive_meter} Drive · {settings.super_meter} Super'),
                ('Found' if self.searching else 'Matches', count), ('Shown', str(len(self.rows)))]
        colors = self.palette_colors()
        text = Text(' Search    Value'.ljust(32),
                    style=f"bold {colors['cf-secondary']} on {colors['cf-header']}")
        for index, (label, value) in enumerate(rows):
            text.append('\n')
            background = colors['cf-surface'] if index % 2 == 0 else colors['cf-background']
            text.append(f' {label:<9}{value}'.ljust(32), style=f"{colors['cf-foreground']} on {background}")
        self.query_one('#overview', Static).update(text)

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
            hit_type=selected('hit-type'), position=selected('position'), opponent_state='grounded',
            drive_meter=number('drive-meter', 'Drive bars'), super_meter=number('super-meter', 'Super bars'),
            max_difficulty=None if difficulty == 'any' else difficulty,
            no_specials=checked('no-specials'), no_jumping=checked('no-jumping'),
            opponent_poisoned=checked('poisoned'), documented_only=checked('documented'),
            optimistic_links=checked('optimistic'), explore_light_chains=checked('explore'),
            starred_only=checked('starred-only'), show_hidden=checked('show-hidden'),
            hidden_only=checked('hidden-only'),
        )

    @on(Button.Pressed, '#search')
    @on(Input.Submitted)
    def action_search(self) -> None:
        self.start_combo_search(close_filters=True)
        if self.searching:
            self.query_one('#results', DataTable).focus()

    @on(Checkbox.Changed)
    def route_option_changed(self, event: Checkbox.Changed) -> None:
        if not self.route_controls_ready or event.checkbox.id not in {
                'documented', 'no-jumping', 'no-specials', 'optimistic', 'explore', 'poisoned',
                'starred-only', 'show-hidden', 'hidden-only'}:
            return
        if not self.has_searched:
            return
        # Ignore initial checkbox messages when the mounted values already
        # match the running search. SF notation has its own display handler.
        try:
            if self.read_settings() == self.settings:
                return
        except ValueError:
            pass
        self.start_combo_search(close_filters=False)

    def start_combo_search(self, *, close_filters: bool, settings: SearchSettings | None = None) -> None:
        try:
            settings = settings if settings is not None else self.read_settings()
        except ValueError as error:
            self.query_one('#status', Static).update(str(error))
            return
        self.settings = settings
        self.has_searched = True
        self.query_one('#shuffle', Button).disabled = False
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
            result = search_combos(settings, self.data_path, cancelled=lambda: worker.is_cancelled,
                                   progress=lambda count: self.post_message(SearchProgress(generation, count)),
                                   library=self.library.snapshot())
            if not worker.is_cancelled:
                self.post_message(SearchCompleted(generation, result))
        except Exception as error:
            if not worker.is_cancelled:
                self.post_message(SearchCompleted(generation, None, str(error)))

    def on_search_progress(self, message: SearchProgress) -> None:
        if message.generation == self.generation:
            self.match_count = message.count
            self.update_overview()
            self.query_one('#status', Static).update(f'Searching… {message.count:,} matches found. Escape cancels.')

    async def on_search_completed(self, message: SearchCompleted) -> None:
        if message.generation != self.generation:
            return
        self.query_one('#cancel', Button).disabled = True
        self.searching = False
        if message.error:
            self.query_one('#status', Static).update(f'Search failed: {message.error}')
            self.reset_combo_selection('Correct the filters and search again.')
            self.update_overview()
            return
        self.rows = self.sorted_rows(message.result.rows)
        self.match_count = message.result.total
        self.update_overview()
        await self.render_rows(message.generation)
        if message.generation != self.generation:
            return
        if not self.rows:
            self.query_one('#status', Static).update('No matching combos. Try different lengths, meter, or starting conditions.')
            self.reset_combo_selection('No combo selected.')
        else:
            self.update_results_status()
            self.update_details(0)

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
        self.query_one('#status', Static).update(
            f'{len(self.rows):,} {mode} / {self.match_count:,} matches · {self.sort_description()}')

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
        table.clear()
        mapped = not self.query_one('#sf-notation', Checkbox).value
        for index, (finder, combo) in enumerate(self.rows):
            if generation != self.generation or render_generation != self.render_generation:
                return
            difficulty = combo['difficulty']['label']
            style = {'easy': 'green', 'medium': 'yellow', 'hard': 'red'}[difficulty]
            raw_damage = combo['damage']['raw_total']
            source = combo['evidence'].get('source_label')
            bracket = Text(f"[{difficulty} | len={combo['length']} | raw dmg={raw_damage if raw_damage is not None else 'unknown'}]", style=style)
            starred, hidden = self.library.marks(combo)
            if starred:
                bracket.append(' ★', style=self.palette_colors()['cf-primary'])
            if hidden:
                bracket.append(' [hidden]', style=self.palette_colors()['cf-muted'])
            notation = Text.from_ansi(finder.format_combo(combo, mapped=mapped, color=mapped,
                                                       controller=self.controller))
            position = combo.get('conditions', {}).get('position', '—')
            startup = combo_startup(finder, combo)
            startup_label = f'{startup:g}f' if startup is not None else 'unknown'
            table.add_row(bracket, notation, self.characters[finder.character].get('display_name', finder.character),
                          position, source or 'Frame timing', startup_label, key=str(index))
            if index % 100 == 99:
                await asyncio.sleep(0)
        if self.rows:
            table.move_cursor(row=selected_index)

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
        starred, hidden = self.library.marks(combo)
        if starred:
            meta.append(' · ★ Starred', style=colors['cf-primary'])
        if hidden:
            meta.append(' · Hidden', style=colors['cf-muted'])
        star_button = self.query_one('#star-combo', Button)
        star_button.label = '★ Unstar' if starred else '☆ Star'
        star_button.disabled = False
        hide_button = self.query_one('#hide-combo', Button)
        hide_button.label = 'Restore' if hidden else 'Hide'
        hide_button.disabled = False
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
        text.append_text(frame_details(finder, combo, mapped=mapped, controller=self.controller))
        text.append(f'\nOpening attack startup: {startup_label} (movement, jump travel and charge preparation excluded).\n')
        if combo['evidence']['kind'] == 'published_recipe':
            text.append(f"\n{kind}: {combo['evidence'].get('title', '')}\n")
        text.append(f"\nDrive: {combo['drive_spent']}  Super: {combo['super_spent']}  "
                    f"Difficulty score: {combo['difficulty']['score']}\n")
        text.append('Transitions: ' + ' → '.join(combo['transitions']) + '\n')
        if combo.get('conditions'):
            text.append('Requires: ' + ', '.join(f'{key}={value}' for key, value in combo['conditions'].items()) + '\n')
        for source in combo['evidence'].get('sources', []):
            text.append(source + '\n', style=f'link {source}')
        text.append('Difficulty: ' + ', '.join(f'{key.replace("_", " ")}={value}'
                                              for key, value in combo['difficulty']['components'].items()) + '\n')
        for note in combo['notes'] + combo['difficulty']['reasons'] + combo['difficulty']['caveats']:
            text.append(note + '\n')
        text.append('Raw damage is before scaling; poison damage over time is excluded.')
        self.query_one('#detail-text', Static).update(text)

    @on(Button.Pressed, '#star-combo')
    async def action_star_combo(self) -> None:
        await self.toggle_combo_mark('starred')

    @on(Button.Pressed, '#hide-combo')
    async def action_hide_combo(self) -> None:
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
            self.start_combo_search(close_filters=False, settings=self.settings)
        else:
            await self.render_rows(self.generation, selected_index=index)
            self.update_details(index)

    @on(Button.Pressed, '#shuffle')
    def action_shuffle(self) -> None:
        if not self.has_searched:
            return
        if not self.query_one('#random-count', Input).value.strip():
            self.query_one('#random-count', Input).value = '25'
        self.action_search()

    @on(Button.Pressed, '#cancel')
    def action_cancel_search(self) -> None:
        if self.search_worker and not self.search_worker.is_finished:
            self.search_worker.cancel()
            self.generation += 1
            self.rows = []
            self.searching = False
            self.match_count = None
            self.query_one('#results', DataTable).clear()
            self.query_one('#status', Static).update('Search cancelled. Adjust filters and search again.')
            self.reset_combo_selection('No combo selected.')
            self.update_overview()
            self.query_one('#cancel', Button).disabled = True

    @on(Button.Pressed, '#toggle-details')
    def action_details(self) -> None:
        details = self.query_one('#details')
        details.display = not details.display
        self.query_one('#toggle-details', Button).set_class(details.display, 'nav-active')

    @on(Button.Pressed, '#toggle-filters')
    def action_filters(self) -> None:
        filters = self.query_one('#filters')
        self.set_filters_visible(not filters.display)
        if filters.display:
            self.query_one('#character', Select).focus()
        else:
            self.query_one('#results', DataTable).focus()

    @on(Button.Pressed, '#browse')
    def focus_results(self) -> None:
        self.query_one('#results', DataTable).focus()

    def action_copy_combo(self) -> None:
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
