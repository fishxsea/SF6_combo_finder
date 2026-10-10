"""Integer slider with mouse dragging and keyboard controls."""
from rich.text import Text
from textual.binding import Binding
from textual.events import MouseDown, MouseMove, MouseUp
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static


class IntegerSlider(Static, can_focus=True):
    """A compact slider; callers may expand its range for typed values."""

    COMPONENT_CLASSES = {'slider--filled', 'slider--track', 'slider--thumb'}
    DEFAULT_CSS = """
    IntegerSlider { height: 1; width: 1fr; padding: 0 1; }
    IntegerSlider:focus { background: $boost; }
    IntegerSlider > .slider--filled { color: $accent; }
    IntegerSlider > .slider--track { color: $text-muted; }
    IntegerSlider > .slider--thumb { color: $accent; text-style: bold; }
    IntegerSlider:focus > .slider--thumb { color: $text; }
    """
    BINDINGS = [
        Binding('left,down', 'adjust(-1)', 'Decrease', show=False),
        Binding('right,up', 'adjust(1)', 'Increase', show=False),
        Binding('home', 'minimum', 'Minimum', show=False),
        Binding('end', 'maximum', 'Maximum', show=False),
    ]
    value = reactive(0, init=False, always_update=True)

    class Changed(Message):
        def __init__(self, slider: 'IntegerSlider', value: int):
            super().__init__()
            self.slider, self.value = slider, value

        @property
        def control(self) -> 'IntegerSlider':
            return self.slider

    def __init__(self, minimum: int, maximum: int, value: int, *, tooltip: str = '', **kwargs):
        super().__init__(**kwargs)
        self.tooltip = tooltip
        self.minimum, self.maximum = minimum, maximum
        self.dragging = False
        with self.prevent(self.Changed):
            self.value = value

    def validate_value(self, value: int) -> int:
        return max(self.minimum, min(self.maximum, value))

    def watch_value(self, value: int) -> None:
        self.post_message(self.Changed(self, value))

    def render(self) -> Text:
        width = max(1, self.content_size.width)
        span = self.maximum - self.minimum
        position = round((self.value - self.minimum) * (width - 1) / span) if span else 0
        text = Text('━' * position, style=self.get_component_rich_style('slider--filled'))
        text.append('●', style=self.get_component_rich_style('slider--thumb'))
        text.append('─' * (width - position - 1), style=self.get_component_rich_style('slider--track'))
        return text

    def action_adjust(self, amount: int) -> None:
        self.value += amount

    def action_minimum(self) -> None:
        self.value = self.minimum

    def action_maximum(self) -> None:
        self.value = self.maximum

    def set_from_mouse(self, event: MouseDown | MouseMove | MouseUp) -> None:
        offset = event.get_content_offset_capture(self)
        width = self.content_size.width
        if width > 1:
            fraction = max(0, min(1, offset.x / (width - 1)))
            self.value = self.minimum + round(fraction * (self.maximum - self.minimum))

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button == 1:
            self.focus()
            self.dragging = True
            self.capture_mouse()
            self.set_from_mouse(event)
            event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if self.dragging:
            self.set_from_mouse(event)
            event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        if self.dragging and event.button == 1:
            self.set_from_mouse(event)
            self.dragging = False
            self.capture_mouse(False)
            event.stop()
