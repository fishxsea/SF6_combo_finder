"""Clickable controller inputs and a personal combo editor."""
import re

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea

from .combo_finder import ComboFinder
from .custom_combos import normalize_inputs


MOTIONS = [('236', 'Quarter-circle forward'), ('214', 'Quarter-circle back'),
           ('623', 'Dragon punch'), ('421', 'Reverse dragon punch'),
           ('63214', 'Half-circle back'), ('41236', 'Half-circle forward'),
           ('236236', 'Double quarter-circle forward'), ('214214', 'Double quarter-circle back')]
ATTACKS = ('LP', 'MP', 'HP', 'LK', 'MK', 'HK')


class CustomCombosScreen(ModalScreen):
    BINDINGS = [('escape', 'close', 'Close')]
    DEFAULT_CSS = """
    CustomCombosScreen { align: center middle; background: $cf-background 85%; }
    #custom-box { width: 90; max-width: 96%; height: 94%; padding: 0 2;
                  border: round $cf-primary; background: $cf-background; }
    #custom-box Label { height: 1; margin-top: 1; color: $cf-muted; }
    #custom-title { color: $cf-primary; text-style: bold; }
    #custom-box Input { height: 1; padding: 0 1; border: none;
                        background: $cf-surface; color: $cf-foreground; }
    #custom-box Input:focus { background: $cf-focus; }
    #custom-notes { height: 5; border: round $cf-border; padding: 0 1;
                    background: $cf-surface; color: $cf-foreground; }
    #custom-notes:focus { border: round $cf-primary; }
    #custom-box Select { height: 1; border: none; padding: 0; }
    #custom-box Button { min-width: 1; height: 1; margin: 0; }
    .custom-row { height: auto; margin-top: 1; }
    .custom-row > * { width: 1fr; margin-right: 1; }
    .custom-row Label { margin-top: 0; }
    #custom-pad { width: 18; height: 3; grid-size: 3 3; grid-gutter: 0 1; }
    #custom-attacks { width: 1fr; height: 3; grid-size: 3 3; grid-gutter: 0 1; }
    #custom-controls { height: 3; }
    #custom-motion-grid { height: 4; grid-size: 2 4; grid-gutter: 0 1; margin-top: 1; }
    #custom-extra-grid { height: 1; grid-size: 4 1; grid-gutter: 0 1; margin-top: 1; }
    #custom-draft { height: 2; padding: 0 1; background: $cf-surface; }
    #custom-preview { height: auto; min-height: 2; padding: 0 1; background: $cf-surface; }
    #custom-message { height: auto; min-height: 1; color: $cf-secondary; margin-top: 1; }
    #custom-saved { height: 6; margin-top: 1; }
    #custom-instructions { height: auto; color: $cf-muted; margin-top: 1; }
    """

    def __init__(self, store, data, *, character, mode, candidates=(), seed=None):
        super().__init__()
        self.store, self.data = store, data
        self.character = character if character in data['characters'] else next(iter(data['characters']))
        self.mode = mode
        self.formatter = ComboFinder(self.character, data=data)
        self.candidates = list(candidates)
        self.inputs = normalize_inputs(seed['inputs']) if seed else []
        self.combo_name = (seed.get('custom_name', '') + ' (extended)' if seed and seed.get('custom_name')
                     else '')
        self.combo_description = seed.get('custom_description', '') if seed else ''
        self.draft = ''
        self.editing_id = None
        self.changed = False
        self.ready = False

    def formatted(self, value):
        return (Text(value) if self.mode == 'sf' else
                Text.from_ansi(self.formatter.format_input(value, color=True, controller=self.mode)))

    def compose(self) -> ComposeResult:
        with VerticalScroll(id='custom-box'):
            yield Label('MY CUSTOM COMBOS', id='custom-title')
            with Horizontal(classes='custom-row'):
                yield Select([(entry.get('display_name', key), key)
                              for key, entry in self.data['characters'].items()],
                             value=self.character, allow_blank=False, id='custom-character')
                yield Select([('Xbox', 'xbox'), ('PlayStation', 'playstation'), ('SF notation', 'sf')],
                             value=self.mode, allow_blank=False, id='custom-mode')
            yield Label('Combo name (optional)')
            yield Input(self.combo_name, id='custom-name', placeholder='e.g. Corner extension')
            yield Label('Notes / explanation (optional)')
            yield TextArea(self.combo_description, id='custom-notes',
                           tooltip='Add setup requirements, timing tips, or what this combo is for. Enter adds a new line.')
            yield Static('Click a direction or full motion, then the attack buttons. '
                         'Next move adds it to the sequence. Save also includes the current input. '
                         'Click two attack buttons for a simultaneous input.', id='custom-instructions')
            yield Label('Directions and attack buttons')
            with Horizontal(id='custom-controls', classes='custom-row'):
                with Grid(id='custom-pad'):
                    for direction in ('7', '8', '9', '4', '5', '6', '1', '2', '3'):
                        yield Button(direction, id=f'custom-dir-{direction}')
                with Grid(id='custom-attacks'):
                    for token in (*ATTACKS, 'P', 'K', 'PP'):
                        yield Button(token, id=f'custom-attack-{token}')
            yield Label('Full motions')
            with Grid(id='custom-motion-grid'):
                for motion, name in MOTIONS:
                    yield Button(motion, id=f'custom-motion-{motion}', tooltip=name)
            with Grid(id='custom-extra-grid'):
                for token, label in [('KK', 'Two kicks'), ('DR', 'Drive Rush'),
                                     ('DRC', 'Rush cancel'), ('[4]6', 'Back charge')]:
                    yield Button(label, id=f'custom-extra-{token.replace("[", "").replace("]", "")}',
                                 name=token)
            yield Label('Current input')
            yield Static('', id='custom-draft', markup=False)
            with Horizontal(classes='custom-row'):
                yield Button('Next move', variant='primary', id='custom-next')
                yield Button('Clear input', id='custom-clear-input')
                yield Button('Undo move', id='custom-undo')
                yield Button('New combo', id='custom-new')
            yield Label('Combo output')
            yield Static('', id='custom-preview', markup=False)
            if self.candidates:
                yield Label('Start with a displayed combo')
                yield Select([(f'{i + 1}. ' + self.candidate_label(row), str(i))
                              for i, row in enumerate(self.candidates)],
                             prompt='Choose a starting combo', id='custom-preset')
            with Horizontal(classes='custom-row'):
                yield Button('Save combo', variant='primary', id='custom-save')
                yield Button('Copy output', id='custom-copy')
                yield Button('Close', id='custom-close')
            yield Static('', id='custom-message', markup=False)
            yield Label('Saved combos · select one, then Edit or Delete')
            yield DataTable(id='custom-saved', cursor_type='row', zebra_stripes=False)
            with Horizontal(classes='custom-row'):
                yield Button('Edit selected', id='custom-edit')
                yield Button('Delete selected', id='custom-delete')

    def candidate_label(self, row):
        finder, combo = row
        name = self.data['characters'][finder.character].get('display_name', finder.character)
        return name + ': ' + finder.format_combo(combo, mapped=self.mode != 'sf',
                                                controller=self.mode if self.mode != 'sf' else 'xbox')

    def on_mount(self):
        self.query_one('#custom-box').border_title = 'Combo builder'
        table = self.query_one('#custom-saved', DataTable)
        table.add_columns('Name', 'Fighter', 'Combo')
        self.ready = True
        self.update_labels()
        self.refresh_saved()
        self.update_preview()

    def update_labels(self):
        for direction in range(1, 10):
            self.query_one(f'#custom-dir-{direction}', Button).label = (
                '5' if self.mode == 'sf' and direction == 5 else
                '·' if direction == 5 else self.formatted(str(direction)))
        for token in (*ATTACKS, 'P', 'K', 'PP'):
            label = {'P': 'Any punch', 'K': 'Any kick', 'PP': 'Two punches'}.get(token)
            self.query_one(f'#custom-attack-{token}', Button).label = label or self.formatted(token)
        for motion, _ in MOTIONS:
            self.query_one(f'#custom-motion-{motion}', Button).label = self.formatted(motion)
        self.query_one('#custom-extra-KK', Button).label = 'Two kicks'
        self.query_one('#custom-extra-46', Button).label = self.formatted('[4]6')
        if self.candidates:
            selector = self.query_one('#custom-preset', Select)
            selected = selector.value
            with selector.prevent(Select.Changed):
                selector.set_options([(f'{i + 1}. ' + self.candidate_label(row), str(i))
                                      for i, row in enumerate(self.candidates)])
                selector.value = selected

    def update_preview(self):
        self.query_one('#custom-draft', Static).update(self.formatted(self.draft) if self.draft else 'Choose an input.')
        preview = Text()
        for i, value in enumerate(self.inputs + ([self.draft] if self.draft else [])):
            if i:
                preview.append(' > ')
            preview.append_text(self.formatted(value))
        self.query_one('#custom-preview', Static).update(preview if preview else 'Your combo will appear here.')

    @on(Button.Pressed)
    def input_pressed(self, event: Button.Pressed):
        button_id = event.button.id or ''
        if ((button_id.startswith('custom-dir-') or button_id.startswith('custom-motion-'))
                and re.search(r'(?:LP|MP|HP|LK|MK|HK|PP|KK|P|K)$', self.draft)):
            self.next_input()
        if button_id.startswith('custom-dir-'):
            self.draft += button_id.removeprefix('custom-dir-')
        elif button_id.startswith('custom-motion-'):
            self.draft += button_id.removeprefix('custom-motion-')
        elif button_id.startswith('custom-attack-') or button_id.startswith('custom-extra-'):
            token = event.button.name or button_id.removeprefix('custom-attack-')
            if re.search(r'(?:LP|MP|HP|LK|MK|HK|PP|KK|P|K)$', self.draft):
                self.draft += '+' + token
            else:
                self.draft += token
        else:
            return
        event.stop()
        self.update_preview()

    @on(Button.Pressed, '#custom-next')
    def next_input(self):
        if self.draft:
            self.inputs.extend(normalize_inputs([self.draft]))
            self.draft = ''
            self.update_preview()

    @on(Button.Pressed, '#custom-clear-input')
    def clear_input(self):
        self.draft = ''
        self.update_preview()

    @on(Button.Pressed, '#custom-undo')
    def undo_input(self):
        if self.draft:
            self.draft = ''
        elif self.inputs:
            self.inputs.pop()
        self.update_preview()

    @on(Button.Pressed, '#custom-new')
    def new_combo(self):
        self.editing_id = None
        self.inputs, self.draft = [], ''
        self.query_one('#custom-name', Input).value = ''
        self.query_one('#custom-notes', TextArea).load_text('')
        self.query_one('#custom-message', Static).update('')
        self.update_preview()

    @on(Select.Changed, '#custom-mode')
    def mode_changed(self, event: Select.Changed):
        if self.ready:
            self.mode = str(event.value)
            self.update_labels()
            self.update_preview()
            self.refresh_saved()

    @on(Select.Changed, '#custom-character')
    def character_changed(self, event: Select.Changed):
        if self.ready:
            self.character = str(event.value)
            self.refresh_saved()

    @on(Select.Changed, '#custom-preset')
    def preset_selected(self, event: Select.Changed):
        if self.ready and event.value != Select.BLANK:
            finder, combo = self.candidates[int(str(event.value))]
            self.new_combo()
            self.query_one('#custom-character', Select).value = finder.character
            self.inputs = normalize_inputs(combo['inputs'])
            self.query_one('#custom-notes', TextArea).load_text(combo.get('custom_description', ''))
            self.update_preview()

    def refresh_saved(self):
        table = self.query_one('#custom-saved', DataTable)
        table.clear()
        for entry in self.store.entries:
            if entry['character'] != self.character:
                continue
            text = self.formatted(' > '.join(entry['inputs']))
            table.add_row(Text(entry['name']), Text(self.data['characters'].get(entry['character'], {}).get(
                'display_name', entry['character'])), text, key=entry['id'])
        disabled = table.row_count == 0
        self.query_one('#custom-edit', Button).disabled = disabled
        self.query_one('#custom-delete', Button).disabled = disabled

    def selected_entry(self):
        table = self.query_one('#custom-saved', DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return next((entry for entry in self.store.entries if entry['id'] == key), None)

    @on(Button.Pressed, '#custom-edit')
    def edit_selected(self):
        entry = self.selected_entry()
        if entry:
            self.editing_id = entry['id']
            self.inputs, self.draft = list(entry['inputs']), ''
            self.query_one('#custom-name', Input).value = entry['name']
            self.query_one('#custom-notes', TextArea).load_text(entry.get('description', ''))
            self.query_one('#custom-message', Static).update('Editing ' + entry['name'])
            self.update_preview()
            self.query_one('#custom-name', Input).scroll_visible()

    @on(Button.Pressed, '#custom-delete')
    def delete_selected(self):
        entry = self.selected_entry()
        if entry:
            try:
                self.store.delete(entry['id'])
            except (OSError, ValueError) as error:
                self.query_one('#custom-message', Static).update(f'Could not delete: {error}')
                return
            if self.editing_id == entry['id']:
                self.new_combo()
            self.changed = True
            self.refresh_saved()
            self.query_one('#custom-message', Static).update('Deleted ' + entry['name'])

    @on(Button.Pressed, '#custom-save')
    def save_combo(self):
        try:
            entry = self.store.save(self.character, self.query_one('#custom-name', Input).value,
                                    self.inputs + ([self.draft] if self.draft else []), entry_id=self.editing_id,
                                    description=self.query_one('#custom-notes', TextArea).text)
        except (OSError, ValueError) as error:
            self.query_one('#custom-message', Static).update(f'Could not save: {error}')
            return
        self.editing_id = entry['id']
        self.inputs, self.draft = list(entry['inputs']), ''
        self.changed = True
        self.update_preview()
        self.refresh_saved()
        self.query_one('#custom-message', Static).update('Saved ' + entry['name'])

    @on(Button.Pressed, '#custom-copy')
    def copy_output(self):
        values = self.inputs + ([self.draft] if self.draft else [])
        if values:
            self.app.copy_to_clipboard(self.formatted(' > '.join(values)).plain)
            self.query_one('#custom-message', Static).update('Combo copied.')

    @on(Button.Pressed, '#custom-close')
    def action_close(self):
        self.dismiss({'changed': self.changed, 'mode': self.mode})
