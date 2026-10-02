"""Spring-loaded slider: drag left to scale down, right to scale up, it snaps back.

The knob does not show a value. It rests in the middle; while it is dragged,
`scaleChanged(factor)` reports how much to scale relative to the moment the
drag started (factor 1.0 in the middle, `strength` at the right end,
1/`strength` at the left end). On release the knob springs back to the middle,
so the next drag scales again from the new size.

`value()` / `setValue()` are the *logical* value (e.g. the current text size),
kept for the code that reads and restores it; `sizeChanged(int)` is emitted
whenever it changes. With `auto_apply` the slider scales its own logical value
(text size); without it the owner applies the factor itself (thumbnail sizes,
which are per item).

A click on the groove or a mouse-wheel step makes one relative step and the
knob springs back at once.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSlider

_HALF = 100  # knob range: -_HALF .. +_HALF, rests at 0


class SpringSlider(QSlider):
    sizeChanged = Signal(int)      # logical value changed (by code or by the user)
    dragStarted = Signal()
    scaleChanged = Signal(float)   # user scaling, relative to the value at drag start
    dragFinished = Signal()

    def __init__(self, minimum, maximum, value, strength=4.0, auto_apply=True, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._min = minimum
        self._max = maximum
        self._value = self._clamp(value)
        self._strength = float(strength)
        self.auto_apply = auto_apply
        self._resetting = False
        self._active = False
        self._start_value = self._value
        super().setRange(-_HALF, _HALF)
        QSlider.setValue(self, 0)
        self.setSingleStep(4)
        self.setPageStep(20)
        self.setTickPosition(QSlider.TicksBelow)
        self.setTickInterval(_HALF)  # ticks at both ends and in the middle (rest position)
        # keyboard arrows belong to the canvas; the slider is used with the mouse
        self.setFocusPolicy(Qt.NoFocus)
        self.valueChanged.connect(self._on_knob)  # knob position (Qt signal)
        self.sliderPressed.connect(self._begin)
        self.sliderReleased.connect(self._release)

    # ---- logical value -------------------------------------------------------
    def _clamp(self, v):
        return int(max(self._min, min(self._max, round(v))))

    def value(self):  # noqa: D401 - logical value, not the knob position
        return self._value

    def setValue(self, value):
        v = self._clamp(value)
        if v != self._value:
            self._value = v
            self.sizeChanged.emit(v)

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def factor_at(self, knob_pos):
        return self._strength ** (knob_pos / float(_HALF))

    # ---- knob ----------------------------------------------------------------
    def _begin(self):
        if self._active:
            return
        self._active = True
        self._start_value = self._value
        self.dragStarted.emit()

    def _finish(self):
        if not self._active:
            return
        self._active = False
        self.dragFinished.emit()

    def _recenter(self):
        self._resetting = True
        try:
            QSlider.setValue(self, 0)
        finally:
            self._resetting = False

    def _apply(self, pos):
        f = self.factor_at(pos)
        if self.auto_apply:
            self.setValue(self._start_value * f)
        self.scaleChanged.emit(f)

    def _on_knob(self, pos):
        if self._resetting:
            return
        if self.isSliderDown():
            self._begin()
            self._apply(pos)
        else:
            # groove click / wheel / keys: one step, then spring back
            self._begin()
            self._apply(pos)
            self._finish()
            self._recenter()

    def _release(self):
        self._recenter()
        self._finish()
