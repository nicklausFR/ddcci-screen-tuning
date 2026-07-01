from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QPushButton, QComboBox, QSystemTrayIcon, QMenu, QDialog, QTabWidget, QLineEdit)
from PySide6.QtGui import QIcon, QFont, QAction, QActionGroup, QColor, QPainter, QPen, QBrush, QPalette, QCursor
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from monitor import DDCCI_Monitor
from ddcci_screen_tuning import PresetManager, config
from ddcci_command_queue import submit_ddcci_command, submit_light_values
import sys
import math
import platform
import time
from midi_qt_signals import bus

if platform.system() == "Windows":
    try:
        from gamma_ramp import apply_strength, reset_gamma
    except Exception as e:
        apply_strength = None
        reset_gamma = None
        print("[WARN] Windows gamma ramp unavailable:", e)
else:
    apply_strength = None
    reset_gamma = None


LIGHT_CURVE_POINT_COUNT = 7
NIGHTLIGHT_BACKEND_DDCCI = "ddcci_rgb"
NIGHTLIGHT_BACKEND_GAMMA = "gamma_ramp"


class AmbientLuxGraph(QWidget):
    thresholds_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = []
        self.window_seconds = 10.0
        self.lux_zero = 5.0
        self.lux_full = 500.0
        self.current_lux = None
        self.current_filtered_lux = None
        self.current_saturated = False
        self._dragging = None
        self._plot_rect = None
        self._y_min_log = -1.0
        self._y_max_log = 3.0
        self._min_positive = 0.05
        self.setMinimumHeight(235)
        self.setMouseTracking(True)

    def set_thresholds(self, lux_zero, lux_full):
        self.lux_zero = max(0.001, float(lux_zero))
        self.lux_full = max(self.lux_zero + 0.001, float(lux_full))
        self.update()

    def add_sample(self, lux, filtered_lux=None, saturated=False):
        now = time.monotonic()
        try:
            lux = float(lux)
        except (TypeError, ValueError):
            return
        try:
            filtered_lux = float(filtered_lux) if filtered_lux is not None else None
        except (TypeError, ValueError):
            filtered_lux = None
        self.current_lux = lux
        self.current_filtered_lux = filtered_lux
        self.current_saturated = bool(saturated)
        self.samples.append((now, max(0.0, lux), filtered_lux))
        cutoff = now - self.window_seconds
        self.samples = [sample for sample in self.samples if sample[0] >= cutoff]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(52, 14, -58, -28)
        painter.fillRect(self.rect(), QColor("#202020"))
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(rect)

        now = time.monotonic()
        visible_samples = [sample for sample in self.samples if sample[0] >= now - self.window_seconds]
        values = [self.lux_zero, self.lux_full]
        for _, lux, filtered in visible_samples:
            values.append(lux)
            if filtered is not None:
                values.append(filtered)
        min_positive = self._min_positive
        log_values = [math.log10(max(min_positive, value)) for value in values]
        y_min = min(log_values)
        y_max = max(log_values)
        zero_log = math.log10(max(min_positive, self.lux_zero))
        full_log = math.log10(max(min_positive, self.lux_full))
        threshold_span = max(0.001, full_log - zero_log)
        y_min = min(y_min, zero_log - max(0.22, threshold_span * 0.18))
        y_max = max(y_max, full_log + max(0.16, threshold_span * 0.10))
        padding = max(0.12, (y_max - y_min) * 0.12)
        y_min -= padding
        y_max += padding
        if y_max <= y_min:
            y_max = y_min + 1.0
        self._plot_rect = rect
        self._y_min_log = y_min
        self._y_max_log = y_max

        def x_for(timestamp):
            return rect.left() + (timestamp - (now - self.window_seconds)) / self.window_seconds * rect.width()

        def y_for(value):
            log_value = math.log10(max(min_positive, value))
            return rect.bottom() - (log_value - y_min) / (y_max - y_min) * rect.height()

        for value, text, color in (
            (self.lux_zero, "Lux 0%", QColor("#64b5f6")),
            (self.lux_full, "Lux 100%", QColor("#ffb74d")),
        ):
            y = y_for(value)
            painter.setPen(QPen(color, 1, Qt.DashLine))
            painter.drawLine(rect.left(), round(y), rect.right(), round(y))
            painter.drawText(rect.right() + 6, round(y) + 4, text)

        painter.setPen(QPen(QColor("#aaa"), 1))
        painter.drawText(rect.left(), self.height() - 8, "10s")
        painter.drawText(rect.right() - 24, self.height() - 8, "now")
        painter.drawText(4, rect.top() + 8, f"{10 ** y_max:.0f}")
        painter.drawText(4, rect.bottom(), f"{10 ** y_min:.1f}")

        if len(visible_samples) < 2:
            painter.setPen(QPen(QColor("#888"), 1))
            painter.drawText(rect.center().x() - 42, rect.center().y(), "No samples")
            painter.end()
            return

        painter.setPen(QPen(QColor("#d8d8d8"), 2))
        previous = None
        for timestamp, lux, _ in visible_samples:
            point = (round(x_for(timestamp)), round(y_for(lux)))
            if previous is not None:
                painter.drawLine(previous[0], previous[1], point[0], point[1])
            previous = point

        filtered_samples = [(timestamp, filtered) for timestamp, _, filtered in visible_samples if filtered is not None]
        if len(filtered_samples) >= 2:
            painter.setPen(QPen(QColor("#7fd36b"), 2))
            previous = None
            for timestamp, filtered in filtered_samples:
                point = (round(x_for(timestamp)), round(y_for(filtered)))
                if previous is not None:
                    painter.drawLine(previous[0], previous[1], point[0], point[1])
                previous = point
        if self.current_lux is not None:
            measured_y = round(y_for(self.current_filtered_lux if self.current_filtered_lux is not None else self.current_lux))
            measured_y = max(rect.top() + 10, min(rect.bottom() - 4, measured_y))
            painter.setPen(QPen(QColor("#7fd36b" if self.current_filtered_lux is not None else "#d8d8d8"), 1))
            painter.drawText(4, measured_y + 4, f"{self.current_lux:.2f}")
        painter.end()

    def _y_for_lux(self, value):
        if self._plot_rect is None:
            return None
        log_value = math.log10(max(self._min_positive, value))
        return self._plot_rect.bottom() - (log_value - self._y_min_log) / (self._y_max_log - self._y_min_log) * self._plot_rect.height()

    def _lux_for_y(self, y):
        if self._plot_rect is None:
            return None
        y = max(self._plot_rect.top(), min(self._plot_rect.bottom(), y))
        position = (self._plot_rect.bottom() - y) / self._plot_rect.height()
        log_value = self._y_min_log + position * (self._y_max_log - self._y_min_log)
        return max(self._min_positive, 10 ** log_value)

    def _nearest_threshold(self, y):
        zero_y = self._y_for_lux(self.lux_zero)
        full_y = self._y_for_lux(self.lux_full)
        if zero_y is None or full_y is None:
            return None
        zero_distance = abs(y - zero_y)
        full_distance = abs(y - full_y)
        if min(zero_distance, full_distance) > 12:
            return None
        return "zero" if zero_distance <= full_distance else "full"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = self._nearest_threshold(event.position().y())
            if self._dragging is not None:
                self.setCursor(Qt.SizeVerCursor)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging is not None:
            return
        if self._nearest_threshold(event.position().y()) is not None:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging is not None:
            self._move_threshold(event.position().y())
            self._dragging = None
            self.setCursor(Qt.ArrowCursor)
            self.thresholds_changed.emit(self.lux_zero, self.lux_full)
            return
        super().mouseReleaseEvent(event)

    def _move_threshold(self, y):
        lux = self._lux_for_y(y)
        if lux is None:
            return
        if self._dragging == "zero":
            self.lux_zero = max(0.001, min(lux, self.lux_full - 0.001))
        elif self._dragging == "full":
            self.lux_full = max(self.lux_zero + 0.001, lux)
        self.update()


def _windows_uses_light_taskbar():
    if platform.system() != "Windows":
        return None
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return bool(value)
    except OSError:
        return None


def tray_icon_path():
    uses_light_theme = _windows_uses_light_taskbar()
    if uses_light_theme is None:
        palette = QApplication.palette()
        uses_light_theme = palette.color(QPalette.Window).lightness() >= 128
    suffix = "light" if uses_light_theme else "dark"
    return f"icons/systray_{suffix}.png"

class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class CurveEditor(QWidget):
    points_changed = Signal(list)
    point_edit_finished = Signal(list)
    preview_changed = Signal(int)

    def __init__(
        self,
        points,
        x_labels=None,
        y_label="Value",
        y_tick_labels=None,
        y_min=0,
        y_max=100,
        current_x=None,
        current_y=None,
        preview_x=None,
    ):
        super().__init__()
        self.y_min = int(y_min)
        self.y_max = int(y_max)
        if self.y_max <= self.y_min:
            self.y_max = self.y_min + 1
        self.points = [self._clamp_value(point) for point in points]
        self.x_labels = x_labels or ("0", "50", "100")
        self.y_label = y_label
        self.y_tick_labels = y_tick_labels or {
            self.y_min: str(self.y_min),
            round((self.y_min + self.y_max) / 2): str(round((self.y_min + self.y_max) / 2)),
            self.y_max: str(self.y_max),
        }
        self.current_x = current_x
        self.current_y = current_y
        self.preview_x = preview_x
        self.active_index = None
        self.preview_dragging = False
        self.hover_index = None
        self.setMinimumSize(260, 205)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(34, 18, -14, -34)
        painter.fillRect(self.rect(), QColor(38, 38, 38))

        grid_pen = QPen(QColor(75, 75, 75), 1)
        painter.setPen(grid_pen)
        for i in range(6):
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(rect.left(), round(y), rect.right(), round(y))
        for i in range(5):
            x = rect.left() + rect.width() * i / 4
            painter.drawLine(round(x), rect.top(), round(x), rect.bottom())

        painter.setPen(QPen(QColor(185, 185, 185), 1))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        tick_values = (self.y_min, round((self.y_min + self.y_max) / 2), self.y_max)
        for value in tick_values:
            y = self._y_for_value(rect, value)
            label = self.y_tick_labels.get(value, str(value))
            painter.drawText(2, round(y) - 6, 30, 12, Qt.AlignRight | Qt.AlignVCenter, label)
        for index, label in enumerate(self.x_labels):
            x = rect.left() + rect.width() * index / (len(self.x_labels) - 1)
            painter.drawText(round(x) - 28, rect.bottom() + 6, 56, 14, Qt.AlignCenter, label)
        painter.drawText(rect.left(), 2, rect.width(), 14, Qt.AlignCenter, self.y_label)

        curve_points = self._screen_points()

        painter.setPen(QPen(QColor(0, 170, 255), 2))
        sampled_curve = []
        for i in range(101):
            x = rect.left() + rect.width() * i / 100
            y = self._y_for_value(rect, self._interpolated_value(i))
            sampled_curve.append((round(x), round(y)))
        for left, right in zip(sampled_curve, sampled_curve[1:]):
            painter.drawLine(left[0], left[1], right[0], right[1])

        if self.current_x is not None and self.current_y is not None:
            current_x = max(0.0, min(float(self.current_x), 100.0))
            current_y = self._clamp_value(self.current_y)
            x = rect.left() + rect.width() * current_x / 100
            y = self._y_for_value(rect, current_y)
            painter.setPen(QPen(QColor(255, 209, 102), 1, Qt.DashLine))
            painter.drawLine(round(x), rect.top(), round(x), rect.bottom())
            painter.setBrush(QBrush(QColor(255, 209, 102)))
            painter.setPen(QPen(QColor(25, 25, 25), 1))
            painter.drawEllipse(round(x) - 5, round(y) - 5, 10, 10)

        if self.preview_x is not None:
            preview_x = max(0.0, min(float(self.preview_x), 100.0))
            x = rect.left() + rect.width() * preview_x / 100
            painter.setPen(QPen(QColor(255, 209, 102), 2))
            painter.drawLine(round(x), rect.top(), round(x), rect.bottom())

        painter.setBrush(QBrush(QColor(245, 245, 245)))
        painter.setPen(QPen(QColor(25, 25, 25), 1))
        for i, point in enumerate(curve_points):
            radius = 7
            if i == self.hover_index:
                radius = 9
            if i == self.active_index:
                radius = 10
            painter.drawEllipse(point[0] - radius, point[1] - radius, radius * 2, radius * 2)

    def _screen_points(self):
        rect = self.rect().adjusted(34, 18, -14, -34)
        points = []
        for i, value in enumerate(self.points):
            x = rect.left() + rect.width() * i / (len(self.points) - 1)
            y = self._y_for_value(rect, value)
            points.append((round(x), round(y)))
        return points

    def _interpolated_value(self, x):
        x = max(0.0, min(float(x), 100.0))
        return self._bezier_value(self.points, x / 100.0)

    @staticmethod
    def _bezier_value(points, t):
        values = [float(point) for point in points]
        while len(values) > 1:
            values = [
                values[index] + (values[index + 1] - values[index]) * t
                for index in range(len(values) - 1)
            ]
        return values[0]

    def _index_for_x(self, x):
        rect = self.rect().adjusted(34, 18, -14, -34)
        if rect.width() <= 0:
            return 0
        index = round((x - rect.left()) / rect.width() * (len(self.points) - 1))
        return max(0, min(len(self.points) - 1, index))

    def _index_for_position(self, position):
        hit_index = self._hit_point_index(position)
        if hit_index is not None:
            return hit_index
        return self._index_for_x(position.x())

    def _hit_point_index(self, position):
        grab_radius = 18
        best_index = None
        best_distance = grab_radius * grab_radius
        for index, point in enumerate(self._screen_points()):
            dx = position.x() - point[0]
            dy = position.y() - point[1]
            distance = dx * dx + dy * dy
            if distance <= best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _value_for_y(self, y):
        rect = self.rect().adjusted(34, 18, -14, -34)
        if rect.height() <= 0:
            return self.y_min
        value = self.y_min + (rect.bottom() - y) / rect.height() * (self.y_max - self.y_min)
        return self._clamp_value(value)

    def _y_for_value(self, rect, value):
        normalized = (float(value) - self.y_min) / (self.y_max - self.y_min)
        normalized = max(0.0, min(1.0, normalized))
        return rect.bottom() - rect.height() * normalized

    def _clamp_value(self, value):
        try:
            value = int(round(float(value)))
        except (TypeError, ValueError):
            value = self.y_min
        return max(self.y_min, min(self.y_max, value))

    def _preview_value_for_x(self, x):
        rect = self.rect().adjusted(34, 18, -14, -34)
        if rect.width() <= 0:
            return 0
        value = round((x - rect.left()) / rect.width() * 100)
        return max(0, min(100, value))

    def _set_point(self, index, value):
        if self.points[index] == value:
            return
        self.points[index] = value
        self.update()
        self.points_changed.emit(list(self.points))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        point_index = self._hit_point_index(event.position())
        if point_index is not None:
            self.active_index = point_index
            self.setCursor(Qt.ClosedHandCursor)
            self._set_point(self.active_index, self._value_for_y(event.position().y()))
            return
        if self.preview_x is not None:
            rect = self.rect().adjusted(34, 18, -14, -34)
            preview_pixel = rect.left() + rect.width() * self.preview_x / 100
            if abs(event.position().x() - preview_pixel) <= 10:
                self.preview_dragging = True
                self.setCursor(Qt.ClosedHandCursor)
                return
        self.active_index = self._index_for_position(event.position())
        self.setCursor(Qt.ClosedHandCursor)
        self._set_point(self.active_index, self._value_for_y(event.position().y()))

    def mouseMoveEvent(self, event):
        if self.preview_dragging:
            return
        if self.active_index is not None:
            self._set_point(self.active_index, self._value_for_y(event.position().y()))
            return

        hover_index = self._index_for_position(event.position())
        screen_point = self._screen_points()[hover_index]
        dx = event.position().x() - screen_point[0]
        dy = event.position().y() - screen_point[1]
        self.hover_index = hover_index if dx * dx + dy * dy <= 18 * 18 else None
        self.setCursor(Qt.OpenHandCursor if self.hover_index is not None else Qt.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, event):
        was_preview_dragging = self.preview_dragging
        was_point_dragging = self.active_index is not None
        if was_preview_dragging:
            self.preview_x = self._preview_value_for_x(event.position().x())
        self.active_index = None
        self.preview_dragging = False
        self.setCursor(Qt.OpenHandCursor if self.hover_index is not None else Qt.ArrowCursor)
        if was_preview_dragging:
            self.preview_changed.emit(round(self.preview_x))
        if was_point_dragging:
            self.point_edit_finished.emit(list(self.points))
        self.update()

    def leaveEvent(self, event):
        self.hover_index = None
        if self.active_index is None:
            self.setCursor(Qt.ArrowCursor)
        self.update()

class PopupPanel(QWidget):
    def __init__(
        self,
        monitor,
        monitor_names=None,
        selected_monitor_index=0,
        on_nightlight_backend_changed=None,
        ambient_source=None,
        on_source_selected=None,
        active_source="tray",
        on_nightlight_source_selected=None,
        active_nightlight_source="manual",
    ):
        super().__init__()
        self.config = config
        self.monitor = monitor
        self.monitor_names = monitor_names or [self.monitor.name()]
        self.selected_monitor_index = selected_monitor_index
        self.on_nightlight_backend_changed = on_nightlight_backend_changed
        self.ambient_source = ambient_source
        self.on_source_selected = on_source_selected
        self.active_source = active_source
        self.on_nightlight_source_selected = on_nightlight_source_selected
        self.active_nightlight_source = active_nightlight_source
        self._updating_source_selector = False
        self._updating_nightlight_source_selector = False
        self._panel_closed = False
        self._monitor_load_attempts = 0
        self.light_mode = bool(getattr(self.config, "LIGHT_MODE", False))
        self._last_nightlight_strength = None
        self._detail_rows_visible = bool(getattr(self.config, "DETAIL_ROWS_VISIBLE", True))
        self.debounce_timers = {}
        slider_debounce = int(getattr(self.config, "SLIDER_DEBOUNCE", 0.1) * 1000)
        slider_keys = ["brightness", "contrast", "nightlight"]
        if self.light_mode:
            slider_keys.insert(0, "light")
        for key in slider_keys:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self.send_debounced(k))
            self.debounce_timers[key] = timer
        self.slider_debounce_delay = slider_debounce

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(280, 338 if self.light_mode else 308)

        self.bg = QWidget(self)
        self.bg.setStyleSheet("background-color: rgba(45, 45, 45, 230); border-radius: 12px;")
        self.bg.setGeometry(0, 0, 280, 338 if self.light_mode else 308)

        layout = QVBoxLayout(self.bg)
        monitor_icon = QLabel()
        monitor_icon.setPixmap(QIcon(f"icons/monitor_dark.png").pixmap(QSize(14, 14)))

        title_row = QHBoxLayout()
        title_row.addWidget(monitor_icon)
        title_row.addSpacing(6)
        if len(self.monitor_names) > 1:
            self.screen_selector = QComboBox()
            self.screen_selector.setInsertPolicy(QComboBox.NoInsert)
            self.screen_selector.addItems(self.monitor_names)
            self.screen_selector.setCurrentIndex(self.selected_monitor_index)
            self.screen_selector.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
            self.screen_selector.currentIndexChanged.connect(self.switch_monitor)
            title_row.addWidget(self.screen_selector, 1)
            screen_label_font = self.screen_selector.font()
        else:
            screen_label = QLabel(self.monitor.name())
            screen_label.setStyleSheet("color: white; font-weight: bold;")
            title_row.addWidget(screen_label)
            screen_label_font = screen_label.font()
        close_button = QPushButton("\u2715")
        close_button.setFixedSize(24, 24)
        close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #ff5c5c;
            }
        """)
        close_button.clicked.connect(self.close)
        title_row.addStretch()
        title_row.addWidget(close_button)
        layout.addLayout(title_row)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        source_row = QHBoxLayout()
        source_label = QLabel("Light control")
        source_label.setStyleSheet("color: white;")
        self.source_selector = QComboBox()
        self.source_selector.setInsertPolicy(QComboBox.NoInsert)
        self.source_selector.addItem("Manual", "tray")
        self.source_selector.addItem("Sensor", "ambient")
        self.source_selector.addItem("Daytime", "daytime")
        self.source_selector.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
        self.source_selector.currentIndexChanged.connect(self._source_selector_changed)
        source_row.addWidget(source_label)
        source_row.addWidget(self.source_selector, 1)
        layout.addLayout(source_row)
        self.set_source_control(active_source)

        icon_paths = {
            "light": "icons/auto_dark.png",
            "brightness": "icons/brightness_dark.png",
            "contrast": "icons/contrast_dark.png",
            "nightlight": "icons/nightlight_dark.png",
        }

        self.sliders = {}
        self.value_labels = {}
        self.slider_rows = {}
        visible_sliders = ["brightness", "contrast", "nightlight"]
        if self.light_mode:
            visible_sliders.insert(0, "light")

        for name in visible_sliders:
            if name == "nightlight":
                nightlight_source_row = QHBoxLayout()
                nightlight_source_label = QLabel("Color control")
                nightlight_source_label.setStyleSheet("color: white;")
                self.nightlight_source_selector = QComboBox()
                self.nightlight_source_selector.setInsertPolicy(QComboBox.NoInsert)
                self.nightlight_source_selector.addItem("Manual", "manual")
                self.nightlight_source_selector.addItem("Daytime", "daytime")
                self.nightlight_source_selector.addItem("Linked to light", "light_linked")
                self.nightlight_source_selector.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
                self.nightlight_source_selector.currentIndexChanged.connect(self._nightlight_source_selector_changed)
                nightlight_source_row.addWidget(nightlight_source_label)
                nightlight_source_row.addWidget(self.nightlight_source_selector, 1)
                layout.addLayout(nightlight_source_row)
                self.set_nightlight_source_control(active_nightlight_source)

            icon_path = icon_paths[name]
            row = QHBoxLayout()
            row.setSpacing(10)

            row_widgets = []

            if name == "nightlight":
                icon_btn = QPushButton()
                icon_btn.setIcon(QIcon(icon_path))
                icon_btn.setIconSize(QSize(14, 14))
                icon_btn.setFixedSize(18, 18)
                icon_btn.setCursor(Qt.PointingHandCursor)
                icon_btn.setStyleSheet("background: transparent; border: none;")
                icon_btn.clicked.connect(self.handle_nightlight_click)
                icon_btn.setContextMenuPolicy(Qt.CustomContextMenu)
                icon_btn.customContextMenuRequested.connect(self.show_nightlight_backend_menu)
                self.nightlight_button = icon_btn
                row.addWidget(icon_btn)
                row_widgets.append(icon_btn)
            elif name == "light":
                icon_btn = QPushButton()
                icon_btn.setIcon(QIcon(icon_path))
                icon_btn.setIconSize(QSize(14, 14))
                icon_btn.setFixedSize(18, 18)
                icon_btn.setCursor(Qt.PointingHandCursor)
                icon_btn.setStyleSheet("background: transparent; border: none;")
                icon_btn.clicked.connect(self.toggle_detail_rows)
                row.addWidget(icon_btn)
                row_widgets.append(icon_btn)
            else:
                icon_label = QLabel()
                icon_label.setPixmap(QIcon(icon_path).pixmap(QSize(14, 14)))
                icon_label.setFixedSize(18, 18)
                icon_label.setAlignment(Qt.AlignCenter)
                row.addWidget(icon_label)
                row_widgets.append(icon_label)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(49)
            slider.setFixedHeight(16)
            slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 4px;
                    background: #666;
                    border-radius: 2px;
                }
                QSlider::handle:horizontal {
                    width: 12px;
                    background: #00aaff;
                    margin: -4px 0;
                    border-radius: 6px;
                }
            """)

            self.sliders[name] = slider
            row_widgets.append(slider)

            if name in ("light", "nightlight"):
                value_label = ClickableLabel("49")
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                value_label.setFixedWidth(24)
                value_label.setCursor(Qt.PointingHandCursor)
                value_label.setStyleSheet("""
                    QLabel {
                        color: white;
                    }
                    QLabel:hover {
                        color: #ffd166;
                    }
                """)
                if name == "light":
                    value_label.clicked.connect(self.choose_light_curve)
                else:
                    value_label.clicked.connect(self.choose_nightlight_settings)
            else:
                value_label = QLabel("49")
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                value_label.setFixedWidth(24)
                value_label.setStyleSheet("color: white;")
            self.value_labels[name] = value_label
            row_widgets.append(value_label)
            def on_slider_change(val, lbl=value_label, k=name, s=slider):
                lbl.setText(str(val))
                if s.isSliderDown():
                    return
                delay = self.slider_debounce_delay
                self.debounce_timers[k].start(delay)

            def on_slider_released(slider=slider, lbl=value_label, k=name):
                value = slider.sliderPosition()
                slider.setValue(value)
                lbl.setText(str(value))
                self.debounce_timers[k].stop()
                QTimer.singleShot(0, lambda key=k: self.send_debounced(key))

            slider.valueChanged.connect(lambda val, lbl=value_label, k=name: on_slider_change(val, lbl, k))
            slider.sliderMoved.connect(lambda val, lbl=value_label: lbl.setText(str(val)))
            slider.sliderReleased.connect(on_slider_released)

            row.addWidget(slider, 1)
            row.addWidget(value_label)
            self.slider_rows[name] = row_widgets
            layout.addLayout(row)

        self._load_cached_values()

        preset_combo = QComboBox()
        preset_combo.setInsertPolicy(QComboBox.NoInsert)
        preset_combo.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
        preset_combo.setFixedWidth(120)
        preset_combo.setFont(screen_label_font)
        preset_combo.clear()
        preset_combo.addItem("New preset")
        self.preset_manager = PresetManager()
        preset_combo.addItems(self.preset_manager.get_all_names())

        bus.midi_update.connect(self.handle_midi_update)
        self.auto_source_timer = QTimer(self)
        self.auto_source_timer.timeout.connect(self._sync_active_source_sliders)
        self.auto_source_timer.start(100)

        def apply_preset(name):
            if preset_combo.isEditable() and preset_combo.lineEdit().hasFocus():
                return
            if name == "New preset":
                return
            values = self.preset_manager.get(name)
            for timer in self.debounce_timers.values():
                timer.stop()

            if 'light_brightness_curve_points' in values:
                points = self._validated_curve_points(values['light_brightness_curve_points'])
                if points is not None:
                    self.config.set("LIGHT_BRIGHTNESS_CURVE_POINTS", points)
                    self.config.set("LIGHT_CURVE_POINTS", points)
            if 'light_contrast_curve_points' in values:
                points = self._validated_curve_points(values['light_contrast_curve_points'])
                if points is not None:
                    self.config.set("LIGHT_CONTRAST_CURVE_POINTS", points)
            if 'brightness' in values:
                brightness = max(0, min(100, int(values['brightness'])))
                self._set_slider_silent("brightness", brightness)
                self.monitor.set_brightness(brightness)
            if 'contrast' in values:
                contrast = max(0, min(100, int(values['contrast'])))
                self._set_slider_silent("contrast", contrast)
                self.monitor.set_contrast(contrast)
            if self.light_mode:
                if 'brightness' in values:
                    self._set_slider_silent("light", self._brightness_to_light(values["brightness"]))
                elif 'light' in values:
                    light = max(0, min(100, int(values['light'])))
                    self._set_slider_silent("light", light)
                    brightness, contrast = self._light_to_brightness_contrast(light)
                    self._set_slider_silent("brightness", brightness)
                    self._set_slider_silent("contrast", contrast)
                    self.monitor.set_brightness(brightness)
                    self.monitor.set_contrast(contrast)
            if 'nightlight_neutral_rgb' in values:
                neutral = values['nightlight_neutral_rgb']
                if isinstance(neutral, (list, tuple)) and len(neutral) == 3:
                    self.config.set("NIGHTLIGHT_NEUTRAL_RGB", list(neutral))
                    self.monitor.nightlight_set_neutral_rgb(*neutral, apply_current=False)
            target = values.get('nightlight_target_rgb')
            if (
                isinstance(target, (list, tuple))
                and len(target) == 3
                and 'nightlight_target_color' in values
                and 'nightlight_target_amber' in values
                and 'nightlight_target_tint' in values
            ):
                self.config.set("NIGHTLIGHT_TARGET_COLOR", max(0, min(100, int(values['nightlight_target_color']))))
                self.config.set("NIGHTLIGHT_TARGET_AMBER", max(-50, min(50, int(values['nightlight_target_amber']))))
                self.config.set("NIGHTLIGHT_TARGET_TINT", max(-50, min(50, int(values['nightlight_target_tint']))))
                self.config.set("NIGHTLIGHT_TARGET_RGB", list(target))
                self.monitor.nightlight_set_target_rgb(*target, apply_current=False)
            if 'nightlight' in values:
                nightlight = max(0, min(100, int(values['nightlight'])))
                self._set_slider_silent("nightlight", nightlight)
                self._safe_set_nightlight_strength(nightlight)

            self._remember_slider_values()

        QTimer.singleShot(0, self.update)
        preset_combo.currentTextChanged.connect(apply_preset)

        save_button = QPushButton()
        save_button.setIcon(QIcon("icons/save_dark.png"))
        save_button.setIconSize(QSize(14, 14))
        save_button.setFixedSize(24, 24)
        save_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:pressed {
                background-color: #2d8cf0;
                border-radius: 6px;
            }
        """)

        erase_button = QPushButton()
        erase_button.setIcon(QIcon("icons/erase_dark.png"))
        erase_button.setIconSize(QSize(14, 14))
        erase_button.setFixedSize(24, 24)
        erase_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:pressed {
                background-color: #2d8cf0;
                border-radius: 6px;
            }
        """)

        def erase_preset():
            name = preset_combo.currentText()
            if name and name != "New preset" and self.preset_manager.exists(name):
                self.preset_manager.delete(name)
                preset_combo.clear()
                preset_combo.addItem("New preset")
                preset_combo.addItems(self.preset_manager.get_all_names())

        erase_button.clicked.connect(erase_preset)

        def save_preset():
            name = preset_combo.currentText().strip()
            if name == "New preset" or not name:
                if not preset_combo.isEditable():
                    preset_combo.setEditable(True)
                    preset_combo.setCurrentText("")
                    preset_combo.lineEdit().setPlaceholderText("Enter preset name")
                    preset_combo.lineEdit().setFocus()
                    return
                else:
                    name = preset_combo.currentText().strip()
                    if not name:
                        return
            values = {
                "brightness": self.sliders['brightness'].value(),
                "contrast": self.sliders['contrast'].value(),
                "nightlight": self.sliders['nightlight'].value(),
                "nightlight_neutral_rgb": list(self.monitor.nightlight_get_neutral_rgb()),
                "nightlight_target_rgb": list(self.monitor.nightlight_get_target_rgb()),
                "nightlight_target_color": self._config_int("NIGHTLIGHT_TARGET_COLOR", 100),
                "nightlight_target_amber": self._config_signed_int("NIGHTLIGHT_TARGET_AMBER", 0, -50, 50),
                "nightlight_target_tint": self._config_signed_int("NIGHTLIGHT_TARGET_TINT", 0, -50, 50),
            }
            if self.light_mode:
                values["light"] = self._brightness_to_light(values["brightness"])
                values["light_brightness_curve_points"] = self._light_brightness_curve_points()
                values["light_contrast_curve_points"] = self._light_contrast_curve_points()
            self.preset_manager.set(name, values)
            preset_combo.setEditable(False)
            preset_combo.clear()
            preset_combo.addItem("New preset")
            preset_combo.addItems(self.preset_manager.get_all_names())
            preset_combo.setCurrentText("New preset")
            preset_combo.setCurrentText(name)

        save_button.clicked.connect(save_preset)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)

        config_button = QPushButton()
        config_button.setIcon(QIcon("icons/config_dark.png"))
        config_button.setIconSize(QSize(14, 14))
        config_button.setStyleSheet("background: transparent; border: none;")
        config_button.clicked.connect(self.open_display_settings)

        bottom_row.addWidget(preset_combo)
        bottom_row.addWidget(save_button)
        bottom_row.addWidget(erase_button)
        bottom_row.addStretch()
        bottom_row.addWidget(config_button)

        layout.addSpacing(8)
        layout.addLayout(bottom_row)
        self._update_detail_rows_visibility()

        # Robust delayed loading for initial DDC/CI values.
        def _load_initial_values():
            # brightness
            try:
                brightness = self.monitor.get_brightness()
                self._set_slider_silent("brightness", brightness)
            except Exception as e:
                print("[WARN] Brightness unavailable, retrying in 1 s:", e)
                QTimer.singleShot(1000, _load_initial_values)
                return

            # contrast
            try:
                contrast = self.monitor.get_contrast()
                self._set_slider_silent("contrast", contrast)
            except Exception as e:
                print("[WARN] Contrast unavailable, retrying in 1 s:", e)
                QTimer.singleShot(1000, _load_initial_values)
                return

            if self.light_mode:
                light = self._brightness_to_light(brightness)
                self._set_slider_silent("light", light)
                self._set_slider_silent("brightness", brightness)
                self._set_slider_silent("contrast", contrast)

            # nightlight (non bloquant)
            if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
                nightlight = self._config_int("LAST_NIGHTLIGHT", 0)
                self._set_slider_silent("nightlight", nightlight)
            else:
                try:
                    nightlight = self.monitor.nightlight_get_strength()
                    self._set_slider_silent("nightlight", nightlight)
                except Exception as e:
                    print("[WARN] Night Light unavailable at startup:", e)
                    self._set_slider_silent("nightlight", 0)

            self._remember_slider_values()

        # First attempt after a short delay to let DDC/CI wake up.
        self._load_monitor_values()
        # --- fin patch ---

        self.place_bottom_right()
        self.installEventFilter(self)
        self.setFocusPolicy(Qt.StrongFocus)

    def switch_monitor(self, index):
        if index == self.selected_monitor_index:
            return

        try:
            self.monitor.close()
        except Exception as e:
            print("[WARN] Failed to close monitor:", e)

        try:
            self.monitor = DDCCI_Monitor(index=index)
            self.selected_monitor_index = index
            self._monitor_load_attempts = 0
            self.config.set("SELECTED_MONITOR_INDEX", index)
            self._load_monitor_values()
        except Exception as e:
            print("[WARN] Monitor selection failed:", e)
            if hasattr(self, "screen_selector"):
                self.screen_selector.blockSignals(True)
                self.screen_selector.setCurrentIndex(self.selected_monitor_index)
                self.screen_selector.blockSignals(False)

    def _load_monitor_values(self):
        if self._panel_closed:
            return

        self._monitor_load_attempts += 1
        max_attempts = 3
        try:
            brightness = self.monitor.get_brightness()
            self._set_slider_silent("brightness", brightness)
        except Exception as e:
            if self._monitor_load_attempts < max_attempts:
                print("[WARN] Brightness unavailable, retrying in 1 s:", e)
                QTimer.singleShot(1000, self._load_monitor_values)
            else:
                print("[WARN] Brightness unavailable, using cached value:", e)
            return

        try:
            contrast = self.monitor.get_contrast()
            self._set_slider_silent("contrast", contrast)
        except Exception as e:
            if self._monitor_load_attempts < max_attempts:
                print("[WARN] Contrast unavailable, retrying in 1 s:", e)
                QTimer.singleShot(1000, self._load_monitor_values)
            else:
                print("[WARN] Contrast unavailable, using cached value:", e)
            return

        self._monitor_load_attempts = 0
        if self.light_mode:
            light = self._brightness_to_light(brightness)
            self._set_slider_silent("light", light)
            self._set_slider_silent("brightness", brightness)
            self._set_slider_silent("contrast", contrast)

        if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
            nightlight = self._config_int("LAST_NIGHTLIGHT", 0)
            self._set_slider_silent("nightlight", nightlight)
        else:
            try:
                nightlight = self.monitor.nightlight_get_strength()
                self._set_slider_silent("nightlight", nightlight)
            except Exception as e:
                print("[WARN] Night Light unavailable at startup:", e)
                self._set_slider_silent("nightlight", 0)

        self._remember_slider_values()

    def _config_int(self, name, default):
        try:
            return max(0, min(100, int(getattr(self.config, name, default))))
        except (TypeError, ValueError):
            return default

    def _config_signed_int(self, name, default, minimum, maximum):
        try:
            return max(minimum, min(maximum, int(getattr(self.config, name, default))))
        except (TypeError, ValueError):
            return default

    def _nightlight_backend(self):
        backend = str(getattr(self.config, "NIGHTLIGHT_BACKEND", NIGHTLIGHT_BACKEND_DDCCI))
        if backend == NIGHTLIGHT_BACKEND_GAMMA:
            return NIGHTLIGHT_BACKEND_GAMMA
        return NIGHTLIGHT_BACKEND_DDCCI

    def _set_nightlight_backend(self, backend):
        if backend not in (NIGHTLIGHT_BACKEND_DDCCI, NIGHTLIGHT_BACKEND_GAMMA):
            backend = NIGHTLIGHT_BACKEND_DDCCI
        previous_backend = self._nightlight_backend()
        self.config.set("NIGHTLIGHT_BACKEND", backend)
        if previous_backend == NIGHTLIGHT_BACKEND_GAMMA and backend != NIGHTLIGHT_BACKEND_GAMMA and reset_gamma is not None:
            try:
                reset_gamma()
            except Exception as e:
                print("[WARN] Gamma ramp reset failed:", e)
        if previous_backend != NIGHTLIGHT_BACKEND_GAMMA and backend == NIGHTLIGHT_BACKEND_GAMMA:
            submit_ddcci_command(
                "nightlight",
                "Nightlight RGB off",
                lambda monitor=self.monitor: monitor.nightlight_set_strength(0),
            )
        self._safe_set_nightlight_strength(self.sliders["nightlight"].value())
        if self.on_nightlight_backend_changed is not None:
            self.on_nightlight_backend_changed(backend)

    def _gamma_warm_kelvin(self):
        try:
            kelvin = int(getattr(self.config, "GAMMA_RAMP_WARM_KELVIN", 5000))
        except (TypeError, ValueError):
            kelvin = 5000
        return max(1000, min(5000, kelvin))

    def _apply_gamma_nightlight_strength(self, strength):
        if apply_strength is None or reset_gamma is None:
            print("[WARN] Gamma ramp backend unavailable on this system.")
            return False
        strength = max(0, min(100, int(strength)))
        try:
            if strength <= 0:
                reset_gamma()
            else:
                apply_strength(self._gamma_warm_kelvin(), strength)
            return True
        except Exception as e:
            print("[WARN] Gamma ramp Night Light failed:", e)
            return False

    def _load_cached_values(self):
        cached = {
            "brightness": self._config_int("LAST_BRIGHTNESS", 49),
            "contrast": self._config_int("LAST_CONTRAST", 49),
            "nightlight": self._config_int("LAST_NIGHTLIGHT", 49),
        }
        if self.light_mode:
            cached["light"] = self._config_int(
                "LAST_LIGHT",
                self._brightness_to_light(cached["brightness"]),
            )

        for key, value in cached.items():
            if key in self.sliders:
                self._set_slider_silent(key, value)

    def _remember_slider_values(self):
        self.config.set("LAST_BRIGHTNESS", self.sliders["brightness"].value())
        self.config.set("LAST_CONTRAST", self.sliders["contrast"].value())
        self.config.set("LAST_NIGHTLIGHT", self.sliders["nightlight"].value())
        if self.light_mode:
            self.config.set("LAST_LIGHT", self.sliders["light"].value())
        if not bool(getattr(self.config, "DAYTIME_SOURCE_ENABLED", False)):
            self.config.set("TRAY_BRIGHTNESS", self.sliders["brightness"].value())
            self.config.set("TRAY_CONTRAST", self.sliders["contrast"].value())
            self.config.set("TRAY_NIGHTLIGHT", self.sliders["nightlight"].value())
            if self.light_mode:
                self.config.set("TRAY_LIGHT", self.sliders["light"].value())

    def toggle_detail_rows(self):
        self._detail_rows_visible = not self._detail_rows_visible
        self.config.set("DETAIL_ROWS_VISIBLE", self._detail_rows_visible)
        self._update_detail_rows_visibility()

    def _update_detail_rows_visibility(self):
        if not self.light_mode:
            return

        for key in ("brightness", "contrast"):
            for widget in self.slider_rows.get(key, []):
                widget.setVisible(self._detail_rows_visible)

        height = 270 if self._detail_rows_visible else 210
        self.setFixedSize(280, height)
        self.bg.setGeometry(0, 0, 280, height)
        self.place_bottom_right()

    def show_nightlight_backend_menu(self, position):
        menu = QMenu(self)
        ddcci_action = QAction("DDC/CI RGB", menu)
        ddcci_action.setCheckable(True)
        gamma_action = QAction("Gamma ramp", menu)
        gamma_action.setCheckable(True)
        backend = self._nightlight_backend()
        ddcci_action.setChecked(backend == NIGHTLIGHT_BACKEND_DDCCI)
        gamma_action.setChecked(backend == NIGHTLIGHT_BACKEND_GAMMA)
        menu.addAction(ddcci_action)
        menu.addAction(gamma_action)
        ddcci_action.triggered.connect(lambda checked: self._set_nightlight_backend(NIGHTLIGHT_BACKEND_DDCCI))
        gamma_action.triggered.connect(lambda checked: self._set_nightlight_backend(NIGHTLIGHT_BACKEND_GAMMA))
        menu.exec(self.nightlight_button.mapToGlobal(position))

    def _config_range(self, name, default):
        value = getattr(self.config, name, default)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return default
        return float(value[0]), float(value[1])

    def _set_slider_silent(self, key, value):
        slider = self.sliders[key]
        slider.blockSignals(True)
        slider.setValue(max(0, min(100, round(value))))
        slider.blockSignals(False)
        self.value_labels[key].setText(str(slider.value()))

    def _validated_curve_points(self, points):
        if isinstance(points, (list, tuple)) and len(points) == LIGHT_CURVE_POINT_COUNT:
            try:
                values = [max(0, min(100, int(point))) for point in points]
            except (TypeError, ValueError):
                values = None
            return values
        return None

    def _default_light_curve_points(self):
        curve = max(0.1, float(getattr(self.config, "LIGHT_CURVE", 0.75)))
        return [
            round(100 * math.pow(i / (LIGHT_CURVE_POINT_COUNT - 1), curve))
            for i in range(LIGHT_CURVE_POINT_COUNT)
        ]

    def _light_brightness_curve_points(self):
        points = self._validated_curve_points(getattr(self.config, "LIGHT_BRIGHTNESS_CURVE_POINTS", None))
        if points is not None:
            return points

        return self._default_light_curve_points()

    def _light_contrast_curve_points(self):
        points = self._validated_curve_points(getattr(self.config, "LIGHT_CONTRAST_CURVE_POINTS", None))
        if points is not None:
            return points

        return [
            round(100 * math.sqrt(self._curve_value_from_points(
                self._light_brightness_curve_points(),
                i * 100 / (LIGHT_CURVE_POINT_COUNT - 1)
            ) / 100.0))
            for i in range(LIGHT_CURVE_POINT_COUNT)
        ]

    def _light_nightlight_curve_points(self):
        points = self._validated_curve_points(getattr(self.config, "LIGHT_NIGHTLIGHT_CURVE_POINTS", None))
        if points is not None:
            return points
        return [80, 65, 45, 25, 12, 4, 0]

    def _curve_points_to_slider_values(self, points, value_range):
        minimum, maximum = value_range
        if maximum <= minimum:
            return [minimum for _ in points]
        return [
            round(minimum + (maximum - minimum) * point / 100.0)
            for point in points
        ]

    def _slider_values_to_curve_points(self, values, value_range):
        minimum, maximum = value_range
        if maximum <= minimum:
            return [0 for _ in values]
        return [
            round((max(minimum, min(maximum, value)) - minimum) / (maximum - minimum) * 100)
            for value in values
        ]

    def _light_curve_points(self):
        return self._light_brightness_curve_points()

    def _curve_value_from_points(self, points, x):
        x = max(0.0, min(float(x), 100.0))
        values = [float(point) for point in points]
        t = x / 100.0
        while len(values) > 1:
            values = [
                values[index] + (values[index + 1] - values[index]) * t
                for index in range(len(values) - 1)
            ]
        return values[0]

    def _curve_value(self, kind, x):
        if kind == "contrast":
            points = self._light_contrast_curve_points()
        else:
            points = self._light_brightness_curve_points()
        return self._curve_value_from_points(points, x)

    def _light_to_brightness_contrast(self, value):
        brightness_y = self._curve_value("brightness", value) / 100.0
        contrast_y = self._curve_value("contrast", value) / 100.0

        b_min, b_max = self._config_range("LIGHT_BRIGHTNESS_RANGE", (0, 100))
        c_min, c_max = self._config_range("LIGHT_CONTRAST_RANGE", (35, 100))

        brightness = b_min + (b_max - b_min) * brightness_y
        contrast = c_min + (c_max - c_min) * contrast_y
        return round(brightness), round(contrast)

    def _brightness_to_light(self, brightness):
        b_min, b_max = self._config_range("LIGHT_BRIGHTNESS_RANGE", (0, 100))
        if b_max <= b_min:
            return 50

        y = (float(brightness) - b_min) / (b_max - b_min)
        y = max(0.0, min(y, 1.0))
        target = y * 100
        best_value = 0
        best_error = float("inf")
        for value in range(101):
            error = abs(self._curve_value("brightness", value) - target)
            if error < best_error:
                best_error = error
                best_value = value
        return best_value

    def _safe_set_nightlight_target(self, target, apply_current=True):
        if self._panel_closed:
            return False
        target = tuple(target)
        submit_ddcci_command(
            "nightlight",
            "Nightlight target",
            lambda monitor=self.monitor, target=target, apply_current=apply_current: monitor.nightlight_set_target_rgb(
                *target,
                apply_current=apply_current,
            ),
        )
        return True

    def _safe_apply_nightlight_target_and_strength(self, target, strength):
        if self._panel_closed:
            return False
        target = tuple(target)
        strength = max(0, min(100, int(strength)))

        def apply_values(monitor=self.monitor, target=target, strength=strength):
            monitor.nightlight_set_target_rgb(*target, apply_current=False)
            monitor.nightlight_set_strength(strength)

        submit_ddcci_command("nightlight", "Nightlight target and strength", apply_values)
        return True

    def _safe_restore_nightlight_state(self, target_rgb, current_rgb=None, strength=None):
        if self._panel_closed:
            return False
        target_rgb = tuple(target_rgb)
        current_rgb = tuple(current_rgb) if current_rgb is not None else None

        def restore_state(monitor=self.monitor, target_rgb=target_rgb, current_rgb=current_rgb, strength=strength):
            monitor.nightlight_set_target_rgb(*target_rgb, apply_current=False)
            if current_rgb is not None:
                monitor.set_rgb(*current_rgb)
            elif strength is not None:
                monitor.nightlight_set_strength(strength)

        submit_ddcci_command("nightlight", "Nightlight restore", restore_state)
        return True

    def _safe_set_nightlight_strength(self, strength):
        if self._panel_closed:
            return False
        if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
            return self._apply_gamma_nightlight_strength(strength)
        submit_ddcci_command(
            "nightlight",
            "Nightlight strength",
            lambda monitor=self.monitor, strength=strength: monitor.nightlight_set_strength(strength),
        )
        return True

    def _safe_set_light_values(self, brightness, contrast):
        if self._panel_closed:
            return False
        submit_light_values(self.monitor, brightness, contrast)
        return True

    def apply_light_value(self, value):
        value = max(0, min(100, int(value)))
        if not self.light_mode:
            return False
        brightness, contrast = self._light_to_brightness_contrast(value)
        self._set_slider_silent("light", value)
        self._set_slider_silent("brightness", brightness)
        self._set_slider_silent("contrast", contrast)
        if self._safe_set_light_values(brightness, contrast):
            self._remember_slider_values()
            return True
        return False

    def _build_light_curve_settings(self, parent, include_cancel=True):
        brightness_range = self._config_range("LIGHT_BRIGHTNESS_RANGE", (0, 100))
        contrast_range = self._config_range("LIGHT_CONTRAST_RANGE", (35, 100))
        original_brightness_points = self._curve_points_to_slider_values(
            self._light_brightness_curve_points(),
            brightness_range,
        )
        original_contrast_points = self._curve_points_to_slider_values(
            self._light_contrast_curve_points(),
            contrast_range,
        )
        curve_templates = {
            "Stable calibrated": {
                "brightness": [8, 28, 45, 60, 74, 88, 100],
                "contrast": [62, 64, 66, 68, 70, 72, 74],
            },
            "Dark room": {
                "brightness": [2, 10, 20, 34, 52, 72, 92],
                "contrast": [58, 60, 63, 66, 68, 70, 72],
            },
            "Office": {
                "brightness": [10, 30, 48, 65, 80, 92, 100],
                "contrast": [60, 62, 65, 68, 71, 73, 75],
            },
            "Daylight": {
                "brightness": [28, 48, 66, 80, 90, 97, 100],
                "contrast": [64, 66, 70, 74, 78, 82, 86],
            },
            "Soft reading": {
                "brightness": [4, 14, 26, 42, 58, 74, 88],
                "contrast": [48, 50, 53, 56, 60, 64, 68],
            },
            "Media": {
                "brightness": [8, 24, 42, 62, 78, 90, 100],
                "contrast": [62, 66, 72, 78, 84, 90, 96],
            },
        }

        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)

        template_combo = QComboBox()
        template_combo.setInsertPolicy(QComboBox.NoInsert)
        template_combo.addItem("Custom")
        template_combo.addItems(curve_templates.keys())
        template_combo.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
        layout.addWidget(template_combo)

        brightness_label = QLabel("Brightness")
        brightness_label.setStyleSheet("color: white;")
        brightness_editor = CurveEditor(
            original_brightness_points,
            x_labels=("Auto 0", "Auto 50", "Auto 100"),
            y_label="Brightness",
            y_min=brightness_range[0],
            y_max=brightness_range[1],
            y_tick_labels={
                brightness_range[0]: str(brightness_range[0]),
                round((brightness_range[0] + brightness_range[1]) / 2): str(round((brightness_range[0] + brightness_range[1]) / 2)),
                brightness_range[1]: str(brightness_range[1]),
            },
        )
        contrast_label = QLabel("Contrast")
        contrast_label.setStyleSheet("color: white;")
        contrast_editor = CurveEditor(
            original_contrast_points,
            x_labels=("Auto 0", "Auto 50", "Auto 100"),
            y_label="Contrast",
            y_min=contrast_range[0],
            y_max=contrast_range[1],
            y_tick_labels={
                contrast_range[0]: str(contrast_range[0]),
                round((contrast_range[0] + contrast_range[1]) / 2): str(round((contrast_range[0] + contrast_range[1]) / 2)),
                contrast_range[1]: str(contrast_range[1]),
            },
        )
        layout.addWidget(brightness_label)
        layout.addWidget(brightness_editor)
        layout.addWidget(contrast_label)
        layout.addWidget(contrast_editor)

        button_row = QHBoxLayout()
        reset_button = QPushButton("Reset")
        cancel_button = QPushButton("Cancel")
        apply_button = QPushButton("Apply")
        button_row.addWidget(reset_button)
        button_row.addStretch()
        if include_cancel:
            button_row.addWidget(cancel_button)
        button_row.addWidget(apply_button)
        layout.addLayout(button_row)

        def reset_points():
            default_brightness = self._default_light_curve_points()
            default_contrast = [
                round(100 * math.sqrt(point / 100.0))
                for point in default_brightness
            ]
            brightness_editor.points = self._curve_points_to_slider_values(default_brightness, brightness_range)
            contrast_editor.points = self._curve_points_to_slider_values(default_contrast, contrast_range)
            brightness_editor.update()
            contrast_editor.update()

        def apply_template(name):
            template = curve_templates.get(name)
            if template is None:
                return
            brightness_editor.points = self._curve_points_to_slider_values(template["brightness"], brightness_range)
            contrast_editor.points = self._curve_points_to_slider_values(template["contrast"], contrast_range)
            brightness_editor.update()
            contrast_editor.update()

        def apply_points():
            brightness_points = self._slider_values_to_curve_points(brightness_editor.points, brightness_range)
            contrast_points = self._slider_values_to_curve_points(contrast_editor.points, contrast_range)
            self.config.set("LIGHT_BRIGHTNESS_CURVE_POINTS", brightness_points)
            self.config.set("LIGHT_CURVE_POINTS", brightness_points)
            self.config.set("LIGHT_CONTRAST_CURVE_POINTS", contrast_points)
            light = self.sliders["light"].value()
            brightness, contrast = self._light_to_brightness_contrast(light)
            self._set_slider_silent("brightness", brightness)
            self._set_slider_silent("contrast", contrast)
            self._safe_set_light_values(brightness, contrast)
            self._remember_slider_values()

        template_combo.currentTextChanged.connect(apply_template)
        reset_button.clicked.connect(reset_points)
        apply_button.clicked.connect(apply_points)
        return cancel_button, apply_button

    def choose_light_curve(self):
        original_light = self.sliders["light"].value()
        original_brightness = self.sliders["brightness"].value()
        original_contrast = self.sliders["contrast"].value()

        dialog = QDialog(self)
        self._light_curve_dialog = dialog
        dialog.setWindowTitle("Light curve")
        dialog.setFixedSize(310, 515)
        cancel_button, apply_button = self._build_light_curve_settings(dialog, include_cancel=True)
        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.Accepted:
            self._set_slider_silent("light", original_light)
            self._set_slider_silent("brightness", original_brightness)
            self._set_slider_silent("contrast", original_contrast)
            self._light_curve_dialog = None
            return

        self._light_curve_dialog = None

    def _build_gamma_ramp_settings(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        general_label = QLabel("General")
        general_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(general_label)

        reset_button = QPushButton("Reset gamma")
        reset_button.setStyleSheet("""
            QPushButton {
                color: white;
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:pressed {
                background: #2d8cf0;
            }
        """)
        layout.addWidget(reset_button)

        target_label = QLabel("Nightlight target color")
        target_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(target_label)

        preview_button = QPushButton("Preview OFF")
        preview_button.setCheckable(True)
        preview_button.setStyleSheet("""
            QPushButton {
                color: white;
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:checked {
                background: #2d8cf0;
            }
        """)
        layout.addWidget(preview_button)

        temperature_label = QLabel()
        temperature_label.setStyleSheet("color: white;")
        layout.addWidget(temperature_label)

        temperature_slider = QSlider(Qt.Orientation.Horizontal)
        temperature_slider.setRange(1000, 5000)
        temperature_slider.setFixedHeight(20)
        temperature_slider.setInvertedAppearance(True)
        temperature_slider.setValue(self._gamma_warm_kelvin())
        temperature_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0.00 #d8efff,
                    stop: 0.50 #ffd166,
                    stop: 1.00 #ff7a1a
                );
            }
            QSlider::handle:horizontal {
                width: 14px;
                background: #f4f4f4;
                border: 1px solid #333;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        layout.addWidget(temperature_slider)

        button_row = QHBoxLayout()
        apply_button = QPushButton("Apply")
        button_row.addStretch()
        button_row.addWidget(apply_button)
        layout.addLayout(button_row)
        layout.addStretch()

        original_strength = {"value": self.sliders["nightlight"].value()}
        original_kelvin = self._gamma_warm_kelvin()
        applied = {"value": False}
        preview_active = {"value": False}

        def update_label():
            temperature_label.setText(f"Approx. temperature: {temperature_slider.value()}K")

        def preview_temperature():
            if preview_button.isChecked():
                old_kelvin = self._gamma_warm_kelvin()
                self.config.set("GAMMA_RAMP_WARM_KELVIN", temperature_slider.value())
                self._apply_gamma_nightlight_strength(100)
                self.config.set("GAMMA_RAMP_WARM_KELVIN", old_kelvin)

        def reset_gamma_ramp():
            preview_button.setChecked(False)
            if reset_gamma is None:
                print("[WARN] Gamma ramp reset unavailable on this system.")
                return
            try:
                reset_gamma()
                self._set_slider_silent("nightlight", 0)
                original_strength["value"] = 0
                self._remember_slider_values()
            except Exception as e:
                print("[WARN] Gamma ramp reset failed:", e)

        def preview_toggled(checked):
            preview_active["value"] = checked
            preview_button.setText("Preview ON" if checked else "Preview OFF")
            if checked:
                preview_temperature()
            elif self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
                self._safe_set_nightlight_strength(original_strength["value"])
            elif reset_gamma is not None:
                try:
                    reset_gamma()
                except Exception as e:
                    print("[WARN] Gamma ramp reset failed:", e)
            else:
                self._safe_set_nightlight_strength(original_strength["value"])

        def apply_temperature():
            applied["value"] = True
            self.config.set("GAMMA_RAMP_WARM_KELVIN", temperature_slider.value())
            strength = self.sliders["nightlight"].value()
            original_strength["value"] = strength
            if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
                self._safe_set_nightlight_strength(strength)
            elif reset_gamma is not None:
                try:
                    reset_gamma()
                except Exception as e:
                    print("[WARN] Gamma ramp reset failed:", e)

        preview_button.toggled.connect(preview_toggled)
        reset_button.clicked.connect(reset_gamma_ramp)
        temperature_slider.valueChanged.connect(lambda value: update_label())
        temperature_slider.sliderReleased.connect(preview_temperature)
        apply_button.clicked.connect(apply_temperature)
        update_label()
        return {
            "applied": applied,
            "preview_active": preview_active,
            "original_strength": original_strength,
            "original_kelvin": original_kelvin,
        }

    def _build_light_linked_nightlight_settings(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        source_row = QHBoxLayout()
        source_label = QLabel("Nightlight")
        source_label.setStyleSheet("color: white;")
        source_combo = QComboBox()
        source_combo.setInsertPolicy(QComboBox.NoInsert)
        source_combo.addItem("Manual", "manual")
        source_combo.addItem("Daytime", "daytime")
        source_combo.addItem("Linked to light", "light_linked")
        source_combo.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
        source_combo.setCurrentIndex(max(0, source_combo.findData(getattr(self.config, "NIGHTLIGHT_SOURCE", "manual"))))
        source_row.addWidget(source_label)
        source_row.addWidget(source_combo, 1)
        layout.addLayout(source_row)

        editor_label = QLabel("Light -> Nightlight")
        editor_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(editor_label)

        current_light = getattr(self.config, "LAST_LIGHT", None)
        current_nightlight = None
        if current_light is not None:
            current_nightlight = self._curve_value_from_points(self._light_nightlight_curve_points(), current_light)
        editor = CurveEditor(
            self._light_nightlight_curve_points(),
            x_labels=("Light 0%", "Light 50%", "Light 100%"),
            y_label="Nightlight",
            y_tick_labels={0: "0%", 50: "50%", 100: "100%"},
            current_x=current_light,
            current_y=current_nightlight,
        )
        layout.addWidget(editor)

        button_row = QHBoxLayout()
        reset_button = QPushButton("Reset")
        apply_button = QPushButton("Apply")
        button_row.addWidget(reset_button)
        button_row.addStretch()
        button_row.addWidget(apply_button)
        layout.addLayout(button_row)
        layout.addStretch()

        def reset_points():
            editor.points = [80, 65, 45, 25, 12, 4, 0]
            if current_light is not None:
                editor.current_y = self._curve_value_from_points(editor.points, current_light)
            editor.update()

        def apply_settings():
            source = source_combo.currentData() or "manual"
            self.config.set("LIGHT_NIGHTLIGHT_CURVE_POINTS", list(editor.points))
            if self.on_nightlight_source_selected is not None:
                self.on_nightlight_source_selected(source)
            else:
                self.config.set("NIGHTLIGHT_SOURCE", source)
                self.set_nightlight_source_control(source)
            if source == "light_linked" and current_light is not None:
                value = round(self._curve_value_from_points(editor.points, current_light))
                self._set_slider_silent("nightlight", value)
                self._safe_set_nightlight_strength(value)
                self._remember_slider_values()

        reset_button.clicked.connect(reset_points)
        apply_button.clicked.connect(apply_settings)
        return {"save": apply_settings}

    def _ambient_config_float(self, name, default, minimum, maximum):
        try:
            value = float(getattr(self.config, name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _build_ambient_sensor_settings(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        def label(text, bold=False):
            item = QLabel(text)
            if bold:
                item.setStyleSheet("color: white; font-weight: bold;")
            else:
                item.setStyleSheet("color: white;")
            return item

        field_style = "color: white; background: #333; border: 1px solid #555; border-radius: 4px; padding: 3px;"
        graph = AmbientLuxGraph()
        layout.addWidget(graph)

        layout.addWidget(label("Calibration", bold=True))
        min_lux_row = QHBoxLayout()
        min_lux_row.addWidget(label("Lux 0%"))
        min_lux_edit = QLineEdit(str(self._ambient_config_float("AMBIENT_MIN_LUX", 5.0, 0.001, 100000.0)))
        min_lux_edit.setStyleSheet(field_style)
        min_lux_row.addWidget(min_lux_edit)
        layout.addLayout(min_lux_row)

        max_lux_row = QHBoxLayout()
        max_lux_row.addWidget(label("Lux 100%"))
        max_lux_edit = QLineEdit(str(self._ambient_config_float("AMBIENT_MAX_LUX", 500.0, 0.001, 100000.0)))
        max_lux_edit.setStyleSheet(field_style)
        max_lux_row.addWidget(max_lux_edit)
        layout.addLayout(max_lux_row)

        smoothing_row = QHBoxLayout()
        smoothing_row.addWidget(label("Smoothing (s)"))
        smoothing_edit = QLineEdit(str(self._ambient_config_float("AMBIENT_SMOOTHING_SECONDS", 2.0, 0.0, 60.0)))
        smoothing_edit.setStyleSheet(field_style)
        smoothing_row.addWidget(smoothing_edit)
        layout.addLayout(smoothing_row)
        layout.addStretch()
        updating_thresholds = {"active": False}

        def parse_float(edit, fallback, minimum, maximum):
            try:
                value = float(edit.text().replace(",", "."))
            except ValueError:
                value = fallback
            return max(minimum, min(maximum, value))

        def save_settings():
            min_lux = parse_float(min_lux_edit, 5.0, 0.001, 100000.0)
            max_lux = parse_float(max_lux_edit, 500.0, min_lux + 0.001, 100000.0)
            smoothing_seconds = parse_float(smoothing_edit, 2.0, 0.0, 60.0)
            min_lux_edit.setText(f"{min_lux:g}")
            max_lux_edit.setText(f"{max_lux:g}")
            smoothing_edit.setText(f"{smoothing_seconds:g}")
            self.config.set("AMBIENT_MIN_LUX", min_lux)
            self.config.set("AMBIENT_MAX_LUX", max_lux)
            self.config.set("AMBIENT_SMOOTHING_SECONDS", smoothing_seconds)
            if not updating_thresholds["active"]:
                graph.set_thresholds(min_lux, max_lux)

        def format_number(value, decimals=2):
            if value is None:
                return "-"
            try:
                return f"{float(value):.{decimals}f}"
            except (TypeError, ValueError):
                return "-"

        def refresh_status():
            if self.ambient_source is None:
                return
            status = self.ambient_source.status()
            if graph._dragging is None:
                graph.set_thresholds(
                    self._ambient_config_float("AMBIENT_MIN_LUX", 5.0, 0.001, 100000.0),
                    self._ambient_config_float("AMBIENT_MAX_LUX", 500.0, 0.001, 100000.0),
                )
            graph.add_sample(status.get("lux"), status.get("filtered_lux"), status.get("saturated"))

        def graph_thresholds_changed(min_lux, max_lux):
            updating_thresholds["active"] = True
            min_lux_edit.setText(f"{min_lux:.3g}")
            max_lux_edit.setText(f"{max_lux:.3g}")
            self.config.set("AMBIENT_MIN_LUX", min_lux)
            self.config.set("AMBIENT_MAX_LUX", max_lux)
            updating_thresholds["active"] = False

        graph.thresholds_changed.connect(graph_thresholds_changed)
        min_lux_edit.editingFinished.connect(save_settings)
        max_lux_edit.editingFinished.connect(save_settings)
        smoothing_edit.editingFinished.connect(save_settings)

        status_timer = QTimer(parent)
        status_timer.timeout.connect(refresh_status)
        status_timer.start(100)
        save_settings()
        refresh_status()
        return {"timer": status_timer, "save": save_settings}

    def open_display_settings(self, initial_tab=None):
        dialog = QDialog(self)
        self._display_settings_dialog = dialog
        dialog.setWindowTitle("Display settings")
        dialog_width = 340
        light_height = 620
        color_height = 360
        gamma_height = 315
        nightlight_curve_height = 370
        ambient_height = 475
        dialog.setFixedSize(dialog_width, light_height)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
            }
            QTabBar::tab {
                color: white;
                background: #333;
                padding: 6px 10px;
            }
            QTabBar::tab:selected {
                background: #444;
            }
        """)

        light_tab = QWidget()
        self._build_light_curve_settings(light_tab, include_cancel=False)
        tabs.addTab(light_tab, "Light curve")

        color_tab = QWidget()
        color_controls = self._build_nightlight_color_settings(color_tab, include_cancel=False, preview_changes=False)
        tabs.addTab(color_tab, "RGB color")

        gamma_tab = QWidget()
        gamma_controls = self._build_gamma_ramp_settings(gamma_tab)
        tabs.addTab(gamma_tab, "Gamma ramp")

        nightlight_curve_tab = QWidget()
        nightlight_curve_controls = self._build_light_linked_nightlight_settings(nightlight_curve_tab)
        tabs.addTab(nightlight_curve_tab, "Light-Nightlight link")

        ambient_tab = QWidget()
        ambient_controls = self._build_ambient_sensor_settings(ambient_tab)
        tabs.addTab(ambient_tab, "Ambient sensor")

        layout.addWidget(tabs)

        button_row = QHBoxLayout()
        close_button = QPushButton("Close")
        button_row.addStretch()
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        cleanup_done = {"value": False}

        def cleanup_display_settings():
            if cleanup_done["value"]:
                return
            cleanup_done["value"] = True
            original_target_rgb = color_controls[3]
            applied = color_controls[4]
            original_strength = color_controls[5]
            original_current_rgb = color_controls[6]
            color_preview_active = color_controls[2]
            if color_preview_active["value"] and not applied["value"]:
                self._safe_restore_nightlight_state(original_target_rgb, current_rgb=original_current_rgb)
                self._set_slider_silent("nightlight", original_strength["value"])
            elif applied["value"]:
                self._safe_set_nightlight_strength(original_strength["value"])
                self._set_slider_silent("nightlight", original_strength["value"])
            if gamma_controls["preview_active"]["value"] and not gamma_controls["applied"]["value"]:
                self.config.set("GAMMA_RAMP_WARM_KELVIN", gamma_controls["original_kelvin"])
                if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
                    self._safe_set_nightlight_strength(gamma_controls["original_strength"]["value"])
                elif reset_gamma is not None:
                    try:
                        reset_gamma()
                    except Exception as e:
                        print("[WARN] Gamma ramp reset failed:", e)
            nightlight_curve_controls["save"]()
            ambient_controls["save"]()

        def close_display_settings():
            cleanup_display_settings()
            dialog.accept()

        close_button.clicked.connect(close_display_settings)
        dialog.finished.connect(lambda result: cleanup_display_settings())
        dialog.finished.connect(lambda result: setattr(self, "_display_settings_dialog", None))

        def resize_for_tab(index):
            if tabs.widget(index) is color_tab:
                height = color_height
            elif tabs.widget(index) is gamma_tab:
                height = gamma_height
            elif tabs.widget(index) is nightlight_curve_tab:
                height = nightlight_curve_height
            elif tabs.widget(index) is ambient_tab:
                height = ambient_height
            else:
                height = light_height
            dialog.setFixedSize(dialog_width, height)

        tabs.currentChanged.connect(resize_for_tab)
        if initial_tab == "rgb":
            tabs.setCurrentWidget(color_tab)
        elif initial_tab == "gamma":
            tabs.setCurrentWidget(gamma_tab)
        elif initial_tab == "nightlight_curve":
            tabs.setCurrentWidget(nightlight_curve_tab)
        elif initial_tab == "ambient":
            tabs.setCurrentWidget(ambient_tab)
        QTimer.singleShot(0, lambda: resize_for_tab(tabs.currentIndex()))
        QTimer.singleShot(0, dialog.raise_)
        QTimer.singleShot(0, dialog.activateWindow)
        dialog.exec()

    def choose_nightlight_settings(self):
        if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
            self.open_display_settings(initial_tab="gamma")
        else:
            self.choose_nightlight_target_color()

    def handle_nightlight_click(self):
        if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
            current = self.sliders["nightlight"].value()
        else:
            try:
                current = self.monitor.nightlight_get_strength()
            except Exception as e:
                print("[WARN] Failed to read Night Light:", e)
                return

        if current > 0:
            self._last_nightlight_strength = current
            self._safe_set_nightlight_strength(0)
            self._set_slider_silent("nightlight", 0)
            self.sliders['nightlight'].setEnabled(False)
            self.sliders['nightlight'].setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 4px;
                    background: #444;
                    border-radius: 2px;
                }
                QSlider::handle:horizontal {
                    width: 12px;
                    background: #777;
                    margin: -4px 0;
                    border-radius: 6px;
                }
            """)
        elif self._last_nightlight_strength is not None:
            self._safe_set_nightlight_strength(self._last_nightlight_strength)
            self._set_slider_silent("nightlight", self._last_nightlight_strength)
            self.sliders['nightlight'].setEnabled(True)
            self.sliders['nightlight'].setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 4px;
                    background: #666;
                    border-radius: 2px;
                }
                QSlider::handle:horizontal {
                    width: 12px;
                    background: #00aaff;
                    margin: -4px 0;
                    border-radius: 6px;
                }
            """)

    def choose_nightlight_target_color(self):
        original_target = list(self.monitor.nightlight_get_target_rgb())
        dialog = QDialog(self)
        self._nightlight_target_dialog = dialog
        dialog.setWindowTitle("RGB color")
        dialog.setFixedSize(300, 300)

        cancel_button, apply_button, preview_active, original_target_rgb, applied, original_strength, original_current_rgb = self._build_nightlight_color_settings(
            dialog,
            include_cancel=True,
        )
        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.Accepted:
            self._safe_restore_nightlight_state(original_target, current_rgb=original_current_rgb)
            self._nightlight_target_dialog = None
            return

        if not applied["value"]:
            self._safe_restore_nightlight_state(original_target_rgb, current_rgb=original_current_rgb)
        else:
            self._safe_set_nightlight_strength(original_strength["value"])
        self._set_slider_silent("nightlight", original_strength["value"])
        self.config.set("NIGHTLIGHT_TARGET_RGB", list(self.monitor.nightlight_get_target_rgb()))
        self._nightlight_target_dialog = None

    def _build_nightlight_color_settings(self, parent, include_cancel=True, preview_changes=True):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        general_label = QLabel("General")
        general_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(general_label)

        reset_rgb_button = QPushButton("Reset RGB monitor")
        reset_rgb_button.setStyleSheet("""
            QPushButton {
                color: white;
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:pressed {
                background: #2d8cf0;
            }
        """)
        layout.addWidget(reset_rgb_button)

        target_section_label = QLabel("Nightlight target color")
        target_section_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(target_section_label)

        preview_button = QPushButton("Preview OFF")
        preview_button.setCheckable(True)
        preview_button.setStyleSheet("""
            QPushButton {
                color: white;
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:checked {
                background: #2d8cf0;
            }
        """)
        layout.addWidget(preview_button)

        color_label = QLabel()
        color_label.setStyleSheet("color: white;")
        layout.addWidget(color_label)

        color_slider = QSlider(Qt.Orientation.Horizontal)
        color_slider.setRange(0, 100)
        color_slider.setFixedHeight(20)
        color_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0.00 #ffc04a,
                    stop: 0.35 #ff9a24,
                    stop: 0.70 #ff5f1f,
                    stop: 1.00 #ff3631
                );
            }
            QSlider::handle:horizontal {
                width: 14px;
                background: #f4f4f4;
                border: 1px solid #333;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        layout.addWidget(color_slider)

        amber_row = QHBoxLayout()
        amber_label = QLabel("Amber")
        amber_label.setStyleSheet("color: white;")
        yellow_label = QLabel("Yellow")
        yellow_label.setStyleSheet("color: white;")
        amber_slider = QSlider(Qt.Orientation.Horizontal)
        amber_slider.setRange(-50, 50)
        amber_slider.setFixedHeight(20)
        amber_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0.00 #ff5f1f,
                    stop: 0.50 #ff9a24,
                    stop: 1.00 #ffe100
                );
            }
            QSlider::handle:horizontal {
                width: 14px;
                background: #f4f4f4;
                border: 1px solid #333;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        amber_row.addWidget(amber_label)
        amber_row.addWidget(amber_slider, 1)
        amber_row.addWidget(yellow_label)
        layout.addLayout(amber_row)

        tint_row = QHBoxLayout()
        magenta_label = QLabel("Magenta")
        magenta_label.setStyleSheet("color: white;")
        green_label = QLabel("Green")
        green_label.setStyleSheet("color: white;")
        tint_slider = QSlider(Qt.Orientation.Horizontal)
        tint_slider.setRange(-50, 50)
        tint_slider.setFixedHeight(20)
        tint_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0.00 #ff4fd8,
                    stop: 0.50 #f0c04a,
                    stop: 1.00 #59d66d
                );
            }
            QSlider::handle:horizontal {
                width: 14px;
                background: #f4f4f4;
                border: 1px solid #333;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        tint_row.addWidget(magenta_label)
        tint_row.addWidget(tint_slider, 1)
        tint_row.addWidget(green_label)
        layout.addLayout(tint_row)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        apply_button = QPushButton("Apply")
        button_row.addStretch()
        if include_cancel:
            button_row.addWidget(cancel_button)
        button_row.addWidget(apply_button)
        layout.addLayout(button_row)

        target_rgb = list(self.monitor.nightlight_get_target_rgb())
        original_target_rgb = list(target_rgb)
        try:
            original_current_rgb = list(self.monitor.get_rgb())
            original_strength = {"value": self.monitor.nightlight_get_strength()}
        except Exception:
            original_current_rgb = list(target_rgb)
            original_strength = {"value": self.sliders["nightlight"].value()}
        preview_active = {"value": False}
        applied = {"value": False}
        preview_strength = {"value": 100}

        def reset_rgb_monitor():
            preview_button.setChecked(False)
            submit_ddcci_command(
                "nightlight",
                "Reset RGB monitor",
                lambda monitor=self.monitor: monitor.nightlight_set_strength(0),
            )
            self._set_slider_silent("nightlight", 0)
            original_strength["value"] = 0
            self._remember_slider_values()

        def update_color_label(target):
            color_label.setText(f"Approx. temperature: {self._warmth_to_kelvin(color_slider.value())}K")

        def update_target_from_controls():
            target_rgb[:] = self._warmth_tint_to_rgb(
                color_slider.value(),
                amber_slider.value(),
                tint_slider.value(),
            )
            update_color_label(target_rgb)

        def preview_target():
            if preview_button.isChecked():
                self._apply_nightlight_preview_rgb(
                    target_rgb,
                    preview_strength["value"],
                )
                self._set_slider_silent("nightlight", preview_strength["value"])
            update_color_label(target_rgb)

        def warmth_or_tint_released():
            update_target_from_controls()
            preview_target()

        def preview_toggled(checked):
            preview_active["value"] = checked
            preview_button.setText("Preview ON" if checked else "Preview OFF")
            if checked:
                self._apply_nightlight_preview_rgb(
                    target_rgb,
                    preview_strength["value"],
                )
                self._set_slider_silent("nightlight", preview_strength["value"])
            else:
                self._safe_restore_nightlight_state(original_target_rgb, current_rgb=original_current_rgb)
                self._set_slider_silent("nightlight", original_strength["value"])

        preview_button.toggled.connect(preview_toggled)
        reset_rgb_button.clicked.connect(reset_rgb_monitor)
        color_slider.sliderReleased.connect(warmth_or_tint_released)
        amber_slider.sliderReleased.connect(warmth_or_tint_released)
        tint_slider.sliderReleased.connect(warmth_or_tint_released)

        color_slider.setValue(self._config_int("NIGHTLIGHT_TARGET_COLOR", 75))
        amber_slider.setValue(self._config_signed_int("NIGHTLIGHT_TARGET_AMBER", 0, -50, 50))
        tint_slider.setValue(self._config_signed_int("NIGHTLIGHT_TARGET_TINT", 0, -50, 50))
        update_target_from_controls()
        update_color_label(target_rgb)

        def remember_target():
            applied["value"] = True
            update_target_from_controls()
            self.config.set("NIGHTLIGHT_TARGET_COLOR", color_slider.value())
            self.config.set("NIGHTLIGHT_TARGET_AMBER", amber_slider.value())
            self.config.set("NIGHTLIGHT_TARGET_TINT", tint_slider.value())
            self.config.set("NIGHTLIGHT_TARGET_RGB", list(target_rgb))
            self.config.set("NIGHTLIGHT_COLOR_CURVE_POINTS", [0, 17, 33, 50, 67, 83, 100])
            strength = self.sliders["nightlight"].value()
            original_strength["value"] = strength
            self._safe_apply_nightlight_target_and_strength(target_rgb, strength)
            self._set_slider_silent("nightlight", strength)

        apply_button.clicked.connect(remember_target)
        return cancel_button, apply_button, preview_active, original_target_rgb, applied, original_strength, original_current_rgb

    def _rgb_to_kelvin(self, rgb):
        target_r, target_g, target_b = [
            max(0.0, min(float(channel), 100.0)) for channel in rgb
        ]
        if target_r <= 0:
            return 6500
        target_green_ratio = target_g / target_r
        target_blue_ratio = target_b / target_r

        best_kelvin = 6500
        best_error = float("inf")
        for kelvin in range(1000, 3001, 5):
            sample_r, sample_g, sample_b = self._kelvin_to_rgb(kelvin)
            if sample_r <= 0:
                continue
            sample_green_ratio = sample_g / sample_r
            sample_blue_ratio = sample_b / sample_r
            error = (
                (target_green_ratio - sample_green_ratio) ** 2
                + 1.6 * (target_blue_ratio - sample_blue_ratio) ** 2
            )
            if error < best_error:
                best_error = error
                best_kelvin = kelvin
        return round(best_kelvin, -1)

    def _kelvin_to_rgb(self, kelvin):
        kelvin = max(1000, min(40000, float(kelvin))) / 100.0
        if kelvin <= 66:
            red = 255
            green = 99.4708025861 * math.log(kelvin) - 161.1195681661
            if kelvin <= 19:
                blue = 0
            else:
                blue = 138.5177312231 * math.log(kelvin - 10) - 305.0447927307
        else:
            red = 329.698727446 * math.pow(kelvin - 60, -0.1332047592)
            green = 288.1221695283 * math.pow(kelvin - 60, -0.0755148492)
            blue = 255
        return [
            round(max(0, min(255, channel)) / 255 * 100)
            for channel in (red, green, blue)
        ]

    def _warmth_to_kelvin(self, warmth):
        warmth = max(0.0, min(float(warmth), 100.0)) / 100.0
        return round(3000 + (1000 - 3000) * warmth)

    def _warmth_tint_to_rgb(self, color, amber_yellow, tint):
        color = max(0.0, min(float(color), 100.0))
        target_luma = 0.50
        rgb = self._scale_rgb_to_luma(self._kelvin_to_rgb(self._warmth_to_kelvin(color)), target_luma)

        amber_yellow = max(-50, min(50, int(amber_yellow)))
        if amber_yellow < 0:
            amount = abs(amber_yellow)
            rgb[0] = max(0, rgb[0] - round(amount * 0.01))
            rgb[1] = max(0, rgb[1] - round(amount * 0.06))
            rgb[2] = min(100, rgb[2] + round(amount * 0.02))
        elif amber_yellow > 0:
            amount = amber_yellow
            rgb[0] = min(100, rgb[0] + round(amount * 0.01))
            rgb[1] = min(100, rgb[1] + round(amount * 0.06))
            rgb[2] = max(0, rgb[2] - round(amount * 0.02))

        tint = max(-50, min(50, int(tint)))
        if tint < 0:
            amount = abs(tint)
            rgb[0] = min(100, rgb[0] + round(amount * 0.10))
            rgb[1] = max(0, rgb[1] - round(amount * 0.18))
            rgb[2] = min(100, rgb[2] + round(amount * 0.16))
        elif tint > 0:
            rgb[0] = max(0, rgb[0] - round(tint * 0.08))
            rgb[1] = min(100, rgb[1] + round(tint * 0.18))
            rgb[2] = max(0, rgb[2] - round(tint * 0.08))
        return self._scale_rgb_to_luma(rgb, target_luma)

    def _scale_rgb_to_luma(self, rgb, target_luma):
        current_luma = self._relative_luma(rgb)
        scale = target_luma / current_luma if current_luma > 0 else 1.0
        return [
            round(max(0, min(100, channel * scale)))
            for channel in rgb
        ]

    def _rgb_to_warmth(self, rgb):
        kelvin = self._rgb_to_kelvin(rgb)
        warmth = (3000 - kelvin) / (3000 - 1000) * 100
        return round(max(0, min(100, warmth)))

    def _apply_nightlight_preview_rgb(self, target_rgb, strength):
        neutral = list(self.monitor.nightlight_get_neutral_rgb())
        mix = max(0.0, min(float(strength), 100.0)) / 100.0
        mix = 1.0 - (1.0 - mix) ** 1.8
        raw = [
            neutral[channel] + (target_rgb[channel] - neutral[channel]) * mix
            for channel in range(3)
        ]
        rgb = [
            round(max(0, min(100, channel)))
            for channel in raw
        ]
        submit_ddcci_command(
            "nightlight",
            "Nightlight preview",
            lambda monitor=self.monitor, rgb=tuple(rgb): monitor.set_rgb(*rgb),
        )
        return True

    def _relative_luma(self, rgb):
        r, g, b = [max(0.0, min(float(channel), 100.0)) / 100.0 for channel in rgb]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _warmth_to_nightlight_target(self, value):
        points = (
            (0, (100, 100, 0)),
            (35, (100, 82, 16)),
            (68, (100, 54, 11)),
            (100, (100, 0, 0)),
        )
        value = max(0, min(int(value), 100))

        for index in range(len(points) - 1):
            left_value, left_rgb = points[index]
            right_value, right_rgb = points[index + 1]
            if value <= right_value:
                span = right_value - left_value
                t = 0.0 if span == 0 else (value - left_value) / span
                return [
                    round(left_rgb[channel] + (right_rgb[channel] - left_rgb[channel]) * t)
                    for channel in range(3)
                ]

        return list(points[-1][1])

    def _nightlight_target_to_warmth(self, target):
        best_value = 0
        best_error = float("inf")
        target = tuple(target)
        for value in range(101):
            candidate = self._warmth_to_nightlight_target(value)
            error = sum(abs(candidate[channel] - target[channel]) for channel in range(3))
            if error < best_error:
                best_error = error
                best_value = value
        return best_value

    def handle_midi_update(self, key, value):
        if key in self.sliders:
            self.sliders[key].setValue(value)

    def set_source_control(self, source):
        source = source if source in ("tray", "ambient", "daytime") else "tray"
        self.active_source = source
        if hasattr(self, "source_selector"):
            index = self.source_selector.findData(source)
            if index >= 0 and self.source_selector.currentIndex() != index:
                self._updating_source_selector = True
                self.source_selector.setCurrentIndex(index)
                self._updating_source_selector = False

    def set_nightlight_source_control(self, source):
        source = source if source in ("manual", "daytime", "light_linked") else "manual"
        self.active_nightlight_source = source
        if hasattr(self, "nightlight_source_selector"):
            index = self.nightlight_source_selector.findData(source)
            if index >= 0 and self.nightlight_source_selector.currentIndex() != index:
                self._updating_nightlight_source_selector = True
                self.nightlight_source_selector.setCurrentIndex(index)
                self._updating_nightlight_source_selector = False

    def _source_selector_changed(self, index):
        if self._updating_source_selector:
            return
        source = self.source_selector.itemData(index)
        if source is None:
            source = "tray"
        self.active_source = source
        if self.on_source_selected is not None:
            self.on_source_selected(source)

    def _nightlight_source_selector_changed(self, index):
        if self._updating_nightlight_source_selector:
            return
        source = self.nightlight_source_selector.itemData(index)
        if source is None:
            source = "manual"
        self.active_nightlight_source = source
        if self.on_nightlight_source_selected is not None:
            self.on_nightlight_source_selected(source)

    def _sync_active_source_sliders(self):
        if self.active_source == "ambient" and self.ambient_source is not None:
            status = self.ambient_source.status()
            light = status.get("light")
            brightness = status.get("brightness")
            contrast = status.get("contrast")
            if light is not None and "light" in self.sliders:
                self._set_slider_silent("light", light)
            if brightness is not None:
                self._set_slider_silent("brightness", brightness)
            if contrast is not None:
                self._set_slider_silent("contrast", contrast)
        elif self.active_source == "daytime":
            light = getattr(self.config, "LAST_LIGHT", None)
            brightness = getattr(self.config, "LAST_BRIGHTNESS", None)
            contrast = getattr(self.config, "LAST_CONTRAST", None)
            nightlight = getattr(self.config, "LAST_NIGHTLIGHT", None)
            if light is not None and "light" in self.sliders:
                self._set_slider_silent("light", light)
            if brightness is not None:
                self._set_slider_silent("brightness", brightness)
            if contrast is not None:
                self._set_slider_silent("contrast", contrast)
            if nightlight is not None:
                self._set_slider_silent("nightlight", nightlight)

    def send_debounced(self, key):
        try:
            if key == "light":
                brightness, contrast = self._light_to_brightness_contrast(self.sliders['light'].value())
                self._set_slider_silent("brightness", brightness)
                self._set_slider_silent("contrast", contrast)
                self._safe_set_light_values(brightness, contrast)
            elif key == "brightness":
                value = self.sliders['brightness'].value()
                submit_ddcci_command(
                    "brightness",
                    "Brightness set",
                    lambda monitor=self.monitor, value=value: monitor.set_brightness(value),
                )
            elif key == "contrast":
                value = self.sliders['contrast'].value()
                submit_ddcci_command(
                    "contrast",
                    "Contrast set",
                    lambda monitor=self.monitor, value=value: monitor.set_contrast(value),
                )
            elif key == "nightlight":
                value = self.sliders['nightlight'].value()
                self._safe_set_nightlight_strength(value)
            self._remember_slider_values()
        except Exception as e:
            print(f"[WARN] {key} set failed:", e)

    def place_bottom_right(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()
        x = screen_rect.right() - self.width() - 10
        y = screen_rect.bottom() - self.height() - 10
        self.move(x, y)

    def _has_visible_child_dialog(self):
        for dialog_name in ("_nightlight_target_dialog", "_light_curve_dialog", "_display_settings_dialog"):
            dialog = getattr(self, dialog_name, None)
            if dialog is not None and dialog.isVisible():
                return True
        return False

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowDeactivate:
            if not self._has_visible_child_dialog():
                self.close()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self._panel_closed = True
        for dialog_name in ("_nightlight_target_dialog", "_light_curve_dialog", "_display_settings_dialog"):
            dialog = getattr(self, dialog_name, None)
            if dialog is not None:
                dialog.reject()
                setattr(self, dialog_name, None)
        try:
            self.monitor.close()
        except Exception as e:
            print("[WARN] Failed to close monitor:", e)
        super().closeEvent(event)

def create_tray_icon(
    on_triggered,
    on_configuration=None,
    on_daytime_settings=None,
    on_source_selected=None,
    active_source="tray",
    on_nightlight_backend_selected=None,
    active_nightlight_backend=NIGHTLIGHT_BACKEND_DDCCI,
):
    tray_icon = QSystemTrayIcon()
    tray_icon.setIcon(QIcon(tray_icon_path()))
    tray_menu = QMenu()

    def set_source_actions(source):
        return

    backend_menu = tray_menu.addMenu("Night Light backend")
    backend_action_group = QActionGroup(backend_menu)
    backend_action_group.setExclusive(True)
    ddcci_backend_action = QAction("DDC/CI RGB", backend_menu)
    ddcci_backend_action.setCheckable(True)
    backend_action_group.addAction(ddcci_backend_action)
    ddcci_backend_action.setChecked(active_nightlight_backend != NIGHTLIGHT_BACKEND_GAMMA)
    backend_menu.addAction(ddcci_backend_action)
    gamma_backend_action = QAction("Gamma ramp", backend_menu)
    gamma_backend_action.setCheckable(True)
    backend_action_group.addAction(gamma_backend_action)
    gamma_backend_action.setChecked(active_nightlight_backend == NIGHTLIGHT_BACKEND_GAMMA)
    backend_menu.addAction(gamma_backend_action)
    updating_backend_actions = {"active": False}

    def set_backend_actions(backend):
        updating_backend_actions["active"] = True
        ddcci_backend_action.setChecked(backend == NIGHTLIGHT_BACKEND_DDCCI)
        gamma_backend_action.setChecked(backend == NIGHTLIGHT_BACKEND_GAMMA)
        updating_backend_actions["active"] = False

    def select_backend(backend):
        if updating_backend_actions["active"]:
            return
        set_backend_actions(backend)
        if on_nightlight_backend_selected is not None:
            on_nightlight_backend_selected(backend)

    ddcci_backend_action.triggered.connect(lambda checked: select_backend(NIGHTLIGHT_BACKEND_DDCCI))
    gamma_backend_action.triggered.connect(lambda checked: select_backend(NIGHTLIGHT_BACKEND_GAMMA))
    tray_menu.addSeparator()
    config_action = QAction("Display settings", tray_menu)
    if on_configuration is not None:
        config_action.triggered.connect(on_configuration)
    tray_menu.addAction(config_action)
    tray_menu.addSeparator()
    quit_action = QAction("Quit", tray_menu)
    quit_action.triggered.connect(QApplication.instance().quit)
    tray_menu.addAction(quit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.tray_menu = tray_menu
    tray_icon.set_source_control = set_source_actions
    tray_icon.set_nightlight_backend = set_backend_actions
    def handle_activation(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            QTimer.singleShot(0, on_triggered)
    tray_icon.activated.connect(handle_activation)
    QTimer.singleShot(100, tray_icon.show)
    return tray_icon
