from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QPushButton, QComboBox, QSystemTrayIcon, QMenu, QDialog, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget, QTabWidget)
from PySide6.QtGui import QIcon, QFont, QAction, QActionGroup, QColor, QPainter, QPen, QBrush, QPalette, QCursor
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from monitor import DDCCI_Monitor
from ddcci_screen_tuning import PresetManager, config
from ddcci_command_queue import submit_ddcci_command, submit_light_values
from daytime import daytime_position, format_hour, parse_hour, solar_hours
import sys
import datetime
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

# Countries are split only when the mainland span is roughly above this
# threshold north-south or east-west. Smaller countries keep one entry.
DAYTIME_LOCATION_SPLIT_THRESHOLD_KM = 1500
DAYTIME_LOCATION_PRESETS = {
    "Algeria - North": (36.8, 3.1),
    "Algeria - South": (23.3, 5.4),
    "Argentina - Central": (-34.6, -58.4),
    "Argentina - North": (-24.8, -65.4),
    "Argentina - South": (-51.6, -69.2),
    "Australia - East": (-33.9, 151.2),
    "Australia - South-East": (-37.8, 144.9),
    "Australia - West": (-31.9, 115.9),
    "Austria": (48.2, 16.4),
    "Bangladesh": (23.8, 90.4),
    "Belgium": (50.8, 4.4),
    "Bolivia": (-16.5, -68.1),
    "Brazil - North": (-3.1, -60.0),
    "Brazil - South-East": (-23.5, -46.6),
    "Brazil - South": (-30.0, -51.2),
    "Bulgaria": (42.7, 23.3),
    "Canada - Central": (49.9, -97.1),
    "Canada - East": (45.5, -73.6),
    "Canada - West": (49.3, -123.1),
    "Chile - Central": (-33.4, -70.7),
    "Chile - North": (-23.7, -70.4),
    "Chile - South": (-41.5, -72.9),
    "China - East": (31.2, 121.5),
    "China - North": (39.9, 116.4),
    "China - South": (23.1, 113.3),
    "China - West": (30.6, 104.1),
    "Colombia": (4.7, -74.1),
    "Costa Rica": (9.9, -84.1),
    "Croatia": (45.8, 16.0),
    "Czechia": (50.1, 14.4),
    "Denmark": (55.7, 12.6),
    "Egypt": (30.0, 31.2),
    "Estonia": (59.4, 24.8),
    "Finland": (60.2, 24.9),
    "France": (46.6, 2.4),
    "Germany": (51.2, 10.4),
    "Greece": (37.98, 23.73),
    "Hungary": (47.5, 19.0),
    "Iceland": (64.1, -21.9),
    "India - North": (28.6, 77.2),
    "India - South": (12.9, 77.6),
    "India - West": (19.1, 72.9),
    "Indonesia - Central": (-5.1, 119.4),
    "Indonesia - East": (-2.5, 140.7),
    "Indonesia - West": (-6.2, 106.8),
    "Ireland": (53.3, -6.3),
    "Israel": (31.8, 35.2),
    "Italy": (41.9, 12.5),
    "Japan - North": (43.1, 141.4),
    "Japan - South": (34.7, 135.5),
    "Kenya": (-1.3, 36.8),
    "Latvia": (56.9, 24.1),
    "Lithuania": (54.7, 25.3),
    "Luxembourg": (49.6, 6.1),
    "Malaysia": (3.1, 101.7),
    "Mexico - Central": (19.4, -99.1),
    "Mexico - North": (25.7, -100.3),
    "Mexico - South": (16.8, -93.1),
    "Morocco": (34.0, -6.8),
    "Netherlands": (52.4, 4.9),
    "New Zealand - North": (-36.8, 174.8),
    "New Zealand - South": (-43.5, 172.6),
    "Nigeria": (6.5, 3.4),
    "Norway - North": (69.6, 18.9),
    "Norway - South": (59.9, 10.8),
    "Pakistan - North": (33.7, 73.1),
    "Pakistan - South": (24.9, 67.0),
    "Peru - North": (-6.8, -79.8),
    "Peru - South": (-16.4, -71.5),
    "Philippines - North": (14.6, 121.0),
    "Philippines - South": (7.1, 125.6),
    "Poland": (52.2, 21.0),
    "Portugal": (38.7, -9.1),
    "Romania": (44.4, 26.1),
    "Russia - West": (55.8, 37.6),
    "Russia - Central": (56.0, 92.9),
    "Russia - East": (43.1, 131.9),
    "Saudi Arabia - East": (26.4, 50.1),
    "Saudi Arabia - West": (21.5, 39.2),
    "Serbia": (44.8, 20.5),
    "Singapore": (1.35, 103.8),
    "Slovakia": (48.1, 17.1),
    "Slovenia": (46.1, 14.5),
    "South Africa - East": (-26.2, 28.0),
    "South Africa - West": (-33.9, 18.4),
    "South Korea": (37.6, 127.0),
    "Spain": (40.4, -3.7),
    "Sweden - North": (65.6, 22.2),
    "Sweden - South": (59.3, 18.1),
    "Switzerland": (46.9, 8.2),
    "Thailand": (13.8, 100.5),
    "Tunisia": (36.8, 10.2),
    "Turkey - East": (39.9, 41.3),
    "Turkey - West": (41.0, 29.0),
    "Ukraine": (50.5, 30.5),
    "United Arab Emirates": (25.2, 55.3),
    "United Kingdom": (52.4, -1.5),
    "United States - Central": (41.9, -87.6),
    "United States - East": (40.7, -74.0),
    "United States - West-Central": (39.7, -105.0),
    "United States - West": (37.8, -122.4),
    "Uruguay": (-34.9, -56.2),
    "Vietnam - North": (21.0, 105.8),
    "Vietnam - South": (10.8, 106.7),
}


class AmbientLuxGraph(QWidget):
    thresholds_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = []
        self.window_seconds = 10.0
        self.lux_zero = 0.1
        self.lux_full = 1000.0
        self.current_lux = None
        self.current_filtered_lux = None
        self.current_saturated = False
        self._dragging = None
        self._plot_rect = None
        self._y_min_log = -1.0
        self._y_max_log = 3.0
        self._min_positive = 0.05
        self._threshold_edits = {}
        self.setMinimumHeight(235)
        self.setMouseTracking(True)

    def _format_lux(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return "-"
        if value >= 100:
            return f"{value:.0f} lx"
        if value >= 10:
            return f"{value:.1f} lx"
        return f"{value:.2f} lx"

    def set_thresholds(self, lux_zero, lux_full):
        self.lux_zero = max(0.001, float(lux_zero))
        self.lux_full = max(self.lux_zero + 0.001, float(lux_full))
        self.update()

    def set_threshold_edits(self, min_edit, max_edit):
        self._threshold_edits = {"zero": min_edit, "full": max_edit}
        for edit in self._threshold_edits.values():
            edit.setParent(self)
            edit.raise_()
            edit.show()
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
        rect = self.rect().adjusted(42, 14, -58, -28)
        painter.fillRect(self.rect(), QColor("#202020"))
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor("#aaa"), 1))
        painter.drawText(2, 2, 38, 12, Qt.AlignLeft | Qt.AlignVCenter, "Lux")

        now = time.monotonic()
        visible_samples = [sample for sample in self.samples if sample[0] >= now - self.window_seconds]
        values = [self.lux_zero, self.lux_full]
        for _, lux, filtered in visible_samples:
            values.append(lux)
            if filtered is not None:
                values.append(filtered)
        min_positive = self._min_positive
        y_min = math.log10(0.1)
        y_max = math.log10(1000.0)
        self._plot_rect = rect
        self._y_min_log = y_min
        self._y_max_log = y_max

        def x_for(timestamp):
            return rect.left() + (timestamp - (now - self.window_seconds)) / self.window_seconds * rect.width()

        def y_for(value):
            log_value = math.log10(max(min_positive, value))
            return rect.bottom() - (log_value - y_min) / (y_max - y_min) * rect.height()

        decade_min = math.floor(y_min)
        decade_max = math.ceil(y_max)
        for exponent in range(decade_min, decade_max + 1):
            for multiplier in range(1, 10):
                value = multiplier * (10 ** exponent)
                y = y_for(value)
                if rect.top() - 1 <= y <= rect.bottom() + 1:
                    color = QColor("#505050") if multiplier == 1 else QColor("#333333")
                    painter.setPen(QPen(color, 1))
                    painter.drawLine(rect.left(), round(y), rect.right(), round(y))
                    if multiplier == 1:
                        painter.setPen(QPen(QColor("#8a8a8a"), 1))
                        label_y = max(rect.top(), min(rect.bottom() - 12, round(y) - 6))
                        painter.drawText(0, label_y, 38, 12, Qt.AlignRight | Qt.AlignVCenter, self._format_lux(value).replace(" lx", ""))

        painter.setPen(QPen(QColor("#aaa"), 1))
        painter.drawText(rect.left(), self.height() - 8, "10s")
        painter.drawText(rect.right() - 24, self.height() - 8, "now")

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
            measured_value = self.current_filtered_lux if self.current_filtered_lux is not None else self.current_lux
            measured_y = round(y_for(measured_value))
            measured_y = max(rect.top() + 10, min(rect.bottom() - 4, measured_y))
            painter.setPen(QPen(QColor("#7fd36b" if self.current_filtered_lux is not None else "#d8d8d8"), 1))
            painter.drawText(rect.right() + 6, measured_y + 4, self._format_lux(self.current_lux))
        painter.end()

    def _position_threshold_edits(self, y_for):
        if not self._threshold_edits:
            return
        for key, value in (("zero", self.lux_zero), ("full", self.lux_full)):
            edit = self._threshold_edits.get(key)
            if edit is None:
                continue
            y = round(y_for(value))
            y = max(18, min(self.height() - 42, y - 11))
            edit.setGeometry(self._plot_rect.right() + 92, y, 72, 22)

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


class LinkBracket(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(QColor("#9a9a9a"), 1))
        x = 1
        top = 0
        bottom = self.height() - 1
        painter.drawLine(x, top, x, bottom)
        painter.drawLine(x, top, self.width() - 1, top)
        painter.drawLine(x, bottom, self.width() - 1, bottom)
        painter.end()


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
        x_display_exponent=1.0,
        x_tick_labels=None,
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
        try:
            self.x_display_exponent = max(0.1, float(x_display_exponent))
        except (TypeError, ValueError):
            self.x_display_exponent = 1.0
        self.x_tick_labels = x_tick_labels
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
        if self.x_tick_labels:
            grid_values = sorted(set(self.x_tick_labels) | {12.5, 37.5, 62.5, 87.5})
            for value in grid_values:
                x = self._x_for_value(rect, value)
                color = QColor(75, 75, 75) if value in self.x_tick_labels else QColor(50, 50, 50)
                painter.setPen(QPen(color, 1))
                painter.drawLine(round(x), rect.top(), round(x), rect.bottom())
        else:
            painter.setPen(grid_pen)
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
        if self.x_tick_labels:
            for value, label in self.x_tick_labels.items():
                x = self._x_for_value(rect, value)
                if value <= 0:
                    label_rect = (round(x), rect.bottom() + 6, 64, 14)
                    alignment = Qt.AlignLeft | Qt.AlignVCenter
                elif value >= 100:
                    label_rect = (round(x) - 64, rect.bottom() + 6, 64, 14)
                    alignment = Qt.AlignRight | Qt.AlignVCenter
                else:
                    label_rect = (round(x) - 32, rect.bottom() + 6, 64, 14)
                    alignment = Qt.AlignCenter
                painter.drawText(*label_rect, alignment, label)
        else:
            for index, label in enumerate(self.x_labels):
                value = 100 * index / (len(self.x_labels) - 1)
                x = self._x_for_value(rect, value)
                painter.drawText(round(x) - 28, rect.bottom() + 6, 56, 14, Qt.AlignCenter, label)
        painter.drawText(rect.left(), 2, rect.width(), 14, Qt.AlignCenter, self.y_label)

        curve_points = self._screen_points()

        painter.setPen(QPen(QColor(0, 170, 255), 2))
        sampled_curve = []
        for i in range(101):
            x = rect.left() + rect.width() * i / 100
            y = self._y_for_value(rect, self._interpolated_value(self._value_for_x_ratio(i / 100.0)))
            sampled_curve.append((round(x), round(y)))
        for left, right in zip(sampled_curve, sampled_curve[1:]):
            painter.drawLine(left[0], left[1], right[0], right[1])

        if self.current_x is not None and self.current_y is not None:
            current_x = max(0.0, min(float(self.current_x), 100.0))
            current_y = self._clamp_value(self.current_y)
            x = self._x_for_value(rect, current_x)
            y = self._y_for_value(rect, current_y)
            painter.setPen(QPen(QColor(255, 209, 102), 1, Qt.DashLine))
            painter.drawLine(round(x), rect.top(), round(x), rect.bottom())
            painter.setBrush(QBrush(QColor(255, 209, 102)))
            painter.setPen(QPen(QColor(25, 25, 25), 1))
            painter.drawEllipse(round(x) - 5, round(y) - 5, 10, 10)

        if self.preview_x is not None:
            preview_x = max(0.0, min(float(self.preview_x), 100.0))
            x = self._x_for_value(rect, preview_x)
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
            logical_x = 100 * i / (len(self.points) - 1)
            x = self._x_for_value(rect, logical_x)
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

    def _x_ratio_for_value(self, value):
        value = max(0.0, min(float(value), 100.0)) / 100.0
        return value ** self.x_display_exponent

    def _value_for_x_ratio(self, ratio):
        ratio = max(0.0, min(float(ratio), 1.0))
        return 100.0 * (ratio ** (1.0 / self.x_display_exponent))

    def _x_for_value(self, rect, value):
        return rect.left() + rect.width() * self._x_ratio_for_value(value)

    def _index_for_x(self, x):
        rect = self.rect().adjusted(34, 18, -14, -34)
        if rect.width() <= 0:
            return 0
        ratio = (x - rect.left()) / rect.width()
        logical_x = self._value_for_x_ratio(ratio)
        index = round(logical_x / 100 * (len(self.points) - 1))
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
        value = round(self._value_for_x_ratio((x - rect.left()) / rect.width()))
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
            preview_pixel = self._x_for_value(rect, self.preview_x)
            if abs(event.position().x() - preview_pixel) <= 10:
                self.preview_dragging = True
                self.setCursor(Qt.ClosedHandCursor)
                return
        self.active_index = self._index_for_position(event.position())
        self.setCursor(Qt.ClosedHandCursor)
        self._set_point(self.active_index, self._value_for_y(event.position().y()))

    def mouseMoveEvent(self, event):
        if self.preview_dragging:
            self.preview_x = self._preview_value_for_x(event.position().x())
            self.update()
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
        available_sources=None,
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
        self.available_sources = set(available_sources or ("tray", "ambient", "daytime"))
        self.available_sources.add("tray")
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
        self.source_selector.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
        self._populate_source_selector()
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
        self.detail_row_icons = {}
        self.bc_link_bracket = LinkBracket(self.bg)
        self.bc_link_bracket.hide()
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
                if name in ("brightness", "contrast"):
                    self.detail_row_icons[name] = (icon_label, icon_path)

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
                QSlider::groove:horizontal:disabled {
                    background: #4a4a4a;
                }
                QSlider::handle:horizontal:disabled {
                    background: #8a8a8a;
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

        linked = not self._detail_rows_visible
        light_slider = self.sliders.get("light")
        if light_slider is not None:
            light_slider.setEnabled(linked)
        light_label = self.value_labels.get("light")
        if light_label is not None:
            light_label.setStyleSheet("""
                QLabel {
                    color: %s;
                }
                QLabel:hover {
                    color: #ffd166;
                }
            """ % ("white" if linked else "#8a8a8a"))

        for key in ("brightness", "contrast"):
            slider = self.sliders.get(key)
            if slider is not None:
                slider.setEnabled(not linked)
            value_label = self.value_labels.get(key)
            if value_label is not None:
                value_label.setEnabled(not linked)
                value_label.setStyleSheet("color: #8a8a8a;" if linked else "color: white;")
            icon_data = self.detail_row_icons.get(key)
            if icon_data is not None:
                icon_label, icon_path = icon_data
                icon_label.setText("")
                icon_label.setStyleSheet("")
                icon_label.setPixmap(QIcon(icon_path).pixmap(QSize(14, 14)))
            for widget in self.slider_rows.get(key, []):
                widget.setVisible(True)

        height = 270
        self.setFixedSize(280, height)
        self.bg.setGeometry(0, 0, 280, height)
        self._update_bc_link_bracket(linked)
        QTimer.singleShot(0, lambda: self._update_bc_link_bracket(linked))
        self.place_bottom_right()

    def _update_bc_link_bracket(self, visible):
        if not visible:
            self.bc_link_bracket.hide()
            return
        brightness_icon = self.detail_row_icons.get("brightness", (None, None))[0]
        contrast_icon = self.detail_row_icons.get("contrast", (None, None))[0]
        if brightness_icon is None or contrast_icon is None:
            self.bc_link_bracket.hide()
            return
        top_left = brightness_icon.mapTo(self.bg, brightness_icon.rect().topLeft())
        bottom_right = contrast_icon.mapTo(self.bg, contrast_icon.rect().bottomRight())
        x = max(0, top_left.x() - 9)
        y = top_left.y()
        height = max(18, bottom_right.y() - top_left.y())
        self.bc_link_bracket.setGeometry(x, y, 7, height)
        self.bc_link_bracket.show()
        self.bc_link_bracket.raise_()

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

    def _auto_curve_active(self):
        return self.light_mode and not self._detail_rows_visible

    def apply_light_value(self, value):
        value = max(0, min(100, int(value)))
        if not self.light_mode:
            return False
        self._set_slider_silent("light", value)
        if self._auto_curve_active():
            brightness, contrast = self._light_to_brightness_contrast(value)
            self._set_slider_silent("brightness", brightness)
            self._set_slider_silent("contrast", contrast)
            applied = self._safe_set_light_values(brightness, contrast)
        else:
            brightness = value
            self._set_slider_silent("brightness", brightness)
            submit_ddcci_command(
                "brightness",
                "Brightness set",
                lambda monitor=self.monitor, brightness=brightness: monitor.set_brightness(brightness),
            )
            applied = True
        if applied:
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
        dialog.setWindowTitle("B/C auto curve")
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

    def _build_smoothing_settings(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        def label(text, bold=False):
            item = QLabel(text)
            item.setStyleSheet("color: white;" + (" font-weight: bold;" if bold else ""))
            return item

        layout.addWidget(label("Smoothing", bold=True))

        field_style = "color: white; background: #333; border: 1px solid #555; border-radius: 4px; padding: 3px;"
        row_label_width = 130
        field_width = 95

        def add_combo_row(text, combo):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row_label = label(text)
            row_label.setFixedWidth(row_label_width)
            combo.setFixedWidth(field_width)
            combo.setStyleSheet(field_style)
            row.addWidget(row_label)
            row.addWidget(combo)
            row.addStretch()
            layout.addWidget(row_widget)
            return row_widget

        def add_edit_row(text, edit):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row_label = label(text)
            row_label.setFixedWidth(row_label_width)
            edit.setFixedWidth(field_width)
            edit.setStyleSheet(field_style)
            row.addWidget(row_label)
            row.addWidget(edit)
            row.addStretch()
            layout.addWidget(row_widget)
            return row_widget

        enabled_combo = QComboBox()
        enabled_combo.setInsertPolicy(QComboBox.NoInsert)
        enabled_combo.addItem("On", True)
        enabled_combo.addItem("Off", False)
        enabled_combo.setCurrentIndex(0 if bool(getattr(self.config, "AMBIENT_SMOOTHING_ENABLED", True)) else 1)
        add_combo_row("Smoothing", enabled_combo)

        mode_combo = QComboBox()
        mode_combo.setInsertPolicy(QComboBox.NoInsert)
        mode_combo.addItem("Steps", "steps")
        mode_combo.addItem("Time (s)", "time")
        mode = str(getattr(self.config, "AMBIENT_SMOOTHING_MODE", "steps"))
        mode_combo.setCurrentIndex(max(0, mode_combo.findData(mode if mode in ("steps", "time") else "steps")))
        mode_row = add_combo_row("Mode", mode_combo)

        steps_edit = QLineEdit(str(self._config_int("AMBIENT_SMOOTHING_STEPS", 4)))
        steps_row = add_edit_row("Steps", steps_edit)
        seconds_edit = QLineEdit(str(self._ambient_config_float("AMBIENT_SMOOTHING_SECONDS", 2.0, 0.05, 120.0)))
        seconds_row = add_edit_row("Time (s)", seconds_edit)
        layout.addStretch()

        updating = {"active": False}

        def update_visibility():
            enabled = bool(enabled_combo.currentData())
            time_mode = mode_combo.currentData() == "time"
            mode_row.setVisible(enabled)
            steps_row.setVisible(enabled and not time_mode)
            seconds_row.setVisible(enabled and time_mode)

        def save_settings():
            if updating["active"]:
                return
            enabled = bool(enabled_combo.currentData())
            mode = mode_combo.currentData() if mode_combo.currentData() in ("steps", "time") else "steps"
            try:
                steps = int(float(steps_edit.text().replace(",", ".")))
            except ValueError:
                steps = 4
            steps = max(1, min(100, steps))
            try:
                seconds = float(seconds_edit.text().replace(",", "."))
            except ValueError:
                seconds = 2.0
            seconds = max(0.05, min(120.0, seconds))
            updating["active"] = True
            steps_edit.setText(str(steps))
            seconds_edit.setText(f"{seconds:g}")
            update_visibility()
            updating["active"] = False
            self.config.set("AMBIENT_SMOOTHING_ENABLED", enabled)
            self.config.set("AMBIENT_SMOOTHING_MODE", mode)
            self.config.set("AMBIENT_SMOOTHING_STEPS", steps)
            self.config.set("AMBIENT_SMOOTHING_SECONDS", seconds)

        enabled_combo.currentIndexChanged.connect(lambda index: (update_visibility(), save_settings()))
        mode_combo.currentIndexChanged.connect(lambda index: (update_visibility(), save_settings()))
        steps_edit.editingFinished.connect(save_settings)
        seconds_edit.editingFinished.connect(save_settings)
        update_visibility()
        return {"save": save_settings}

    def _build_gamma_ramp_settings(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        general_label = QLabel("General")
        general_label.setStyleSheet("color: white; font-weight: bold;")
        general_label.setFixedHeight(18)
        layout.addWidget(general_label)

        reset_button = QPushButton("Reset gamma")
        reset_button.setFixedHeight(28)
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
        target_label.setFixedHeight(18)
        layout.addWidget(target_label)

        preview_button = QPushButton("Preview OFF")
        preview_button.setCheckable(True)
        preview_button.setFixedHeight(28)
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
        temperature_label.setFixedHeight(18)
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
        apply_button.setFixedHeight(28)
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
        root_layout = QVBoxLayout(parent)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
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
        main_tab = QWidget()
        advanced_tab = QWidget()
        layout = QVBoxLayout(main_tab)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(16, 14, 16, 14)
        advanced_layout.setSpacing(8)
        tabs.addTab(main_tab, "Main")
        tabs.addTab(advanced_tab, "Advanced")
        root_layout.addWidget(tabs)
        started_passive = {"value": False}

        def label(text, bold=False):
            item = QLabel(text)
            if bold:
                item.setStyleSheet("color: white; font-weight: bold;")
            else:
                item.setStyleSheet("color: white;")
            return item

        value_label_width = 145
        value_field_width = 90
        sensor_config_updating = {"active": False}
        field_style = "color: white; background: #333; border: 1px solid #555; border-radius: 4px; padding: 3px;"

        def add_value_row(text, edit, target_layout=None):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row_label = label(text)
            row_label.setFixedWidth(value_label_width)
            edit.setFixedWidth(value_field_width)
            edit.setStyleSheet(field_style)
            row.addWidget(row_label)
            row.addWidget(edit)
            row.addStretch()
            (target_layout or layout).addWidget(row_widget)
            return row_widget

        def add_combo_row(text, combo, target_layout=None):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row_label = label(text)
            row_label.setFixedWidth(value_label_width)
            combo.setFixedWidth(value_field_width)
            combo.setStyleSheet(field_style)
            row.addWidget(row_label)
            row.addWidget(combo)
            row.addStretch()
            (target_layout or layout).addWidget(row_widget)
            return row_widget

        sensor_config_label = label("Sensor runtime", bold=True)
        advanced_layout.addWidget(sensor_config_label)
        sensor_mode_combo = QComboBox()
        sensor_mode_combo.setInsertPolicy(QComboBox.NoInsert)
        sensor_mode_combo.addItem("Auto", "auto")
        sensor_mode_combo.addItem("Interval", "interval")
        sensor_mode = str(getattr(self.config, "AMBIENT_SENSOR_PUBLISH_MODE", "auto"))
        sensor_mode_combo.setCurrentIndex(max(0, sensor_mode_combo.findData(sensor_mode if sensor_mode in ("auto", "interval") else "auto")))
        add_combo_row("Push mode", sensor_mode_combo, advanced_layout)
        sensor_refresh_edit = QLineEdit(str(self._config_int("AMBIENT_SENSOR_REFRESH_MS", 100)))
        sensor_refresh_row = add_value_row("Read every ms", sensor_refresh_edit, advanced_layout)
        sensor_change_edit = QLineEdit(str(self._ambient_config_float("AMBIENT_SENSOR_PUBLISH_LUX_CHANGE_PERCENT", 1.0, 0.0, 100.0)))
        sensor_change_row = add_value_row("Push change %", sensor_change_edit, advanced_layout)
        sensor_interval_edit = QLineEdit(str(self._config_int("AMBIENT_SENSOR_PUBLISH_MAX_INTERVAL_SECONDS", 30)))
        sensor_interval_row = add_value_row("Max push interval s", sensor_interval_edit, advanced_layout)
        sensor_status_label = label("")
        advanced_layout.addWidget(sensor_status_label)
        advanced_layout.addStretch()
        sensor_config_last = {
            "values": {
                "refreshMs": self._config_int("AMBIENT_SENSOR_REFRESH_MS", 100),
                "publishLuxChangePercent": self._ambient_config_float("AMBIENT_SENSOR_PUBLISH_LUX_CHANGE_PERCENT", 1.0, 0.0, 100.0),
                "publishMaxIntervalSeconds": self._config_int("AMBIENT_SENSOR_PUBLISH_MAX_INTERVAL_SECONDS", 30),
                "publishMode": sensor_mode if sensor_mode in ("auto", "interval") else "auto",
            }
        }
        sensor_config_pending = {"values": None}

        min_lux = 0.1
        max_lux = 1000.0
        scale_note = label("Logarithmic lux scale: each interval = 10x")
        scale_note.setStyleSheet("color: #aaa;")
        layout.addWidget(scale_note)
        graph_row = QHBoxLayout()
        graph = AmbientLuxGraph()
        graph_row.addWidget(graph, 1)
        layout.addLayout(graph_row)

        ambient_curve_points = self._validated_curve_points(getattr(self.config, "AMBIENT_LIGHT_CURVE_POINTS", None))
        if ambient_curve_points is None:
            ambient_curve_points = [0, 17, 33, 50, 67, 83, 100]
        curve_label = label("Ambient lux -> screen light", bold=True)
        curve_editor = CurveEditor(
            ambient_curve_points,
            y_label="Screen light",
            y_tick_labels={0: "0%", 50: "50%", 100: "100%"},
            x_display_exponent=1.0,
            x_tick_labels={0: "0.1 lx", 25: "1 lx", 50: "10 lx", 75: "100 lx", 100: "1000 lx"},
        )
        curve_editor.setMinimumHeight(175)
        layout.addWidget(curve_label)
        layout.addWidget(curve_editor)
        layout.addStretch()

        def normalized_lux(lux, min_lux, max_lux):
            try:
                lux = float(lux)
            except (TypeError, ValueError):
                return None
            log_min = math.log10(max(0.001, min_lux))
            log_max = math.log10(max(min_lux + 0.001, max_lux))
            if log_max <= log_min:
                return None
            clamped_lux = max(min_lux, min(lux, max_lux))
            return (math.log10(clamped_lux) - log_min) / (log_max - log_min) * 100

        def update_curve_lux_labels(min_lux, max_lux):
            curve_editor.x_tick_labels = {
                0: "0.1 lx",
                25: "1 lx",
                50: "10 lx",
                75: "100 lx",
                100: "1000 lx",
            }
            curve_editor.update()

        def parse_float(edit, fallback, minimum, maximum):
            try:
                value = float(edit.text().replace(",", "."))
            except ValueError:
                value = fallback
            return max(minimum, min(maximum, value))

        def parse_int(edit, fallback, minimum, maximum):
            try:
                value = int(float(edit.text().replace(",", ".")))
            except ValueError:
                value = fallback
            return max(minimum, min(maximum, value))

        def sensor_config_values():
            mode = sensor_mode_combo.currentData() or "auto"
            if mode not in ("auto", "interval"):
                mode = "auto"
            return {
                "refreshMs": parse_int(sensor_refresh_edit, 100, 50, 60000),
                "publishLuxChangePercent": parse_float(sensor_change_edit, 1.0, 0.0, 100.0),
                "publishMaxIntervalSeconds": parse_int(sensor_interval_edit, 30, 1, 86400),
                "publishMode": mode,
            }

        def update_sensor_config_visibility():
            interval_mode = (sensor_mode_combo.currentData() or "auto") == "interval"
            sensor_change_row.setVisible(not interval_mode)
            sensor_interval_row.setVisible(True)
            sensor_refresh_row.setVisible(True)

        def set_sensor_config_fields(values):
            sensor_config_updating["active"] = True
            sensor_refresh_edit.setText(str(values["refreshMs"]))
            sensor_change_edit.setText(f"{float(values['publishLuxChangePercent']):g}")
            sensor_interval_edit.setText(str(values["publishMaxIntervalSeconds"]))
            index = sensor_mode_combo.findData(values["publishMode"])
            sensor_mode_combo.setCurrentIndex(index if index >= 0 else 0)
            update_sensor_config_visibility()
            sensor_config_updating["active"] = False

        def remember_sensor_config(values, save_file=True):
            sensor_config_last["values"] = dict(values)
            if save_file:
                self.config.set("AMBIENT_SENSOR_REFRESH_MS", values["refreshMs"])
                self.config.set("AMBIENT_SENSOR_PUBLISH_LUX_CHANGE_PERCENT", values["publishLuxChangePercent"])
                self.config.set("AMBIENT_SENSOR_PUBLISH_MAX_INTERVAL_SECONDS", values["publishMaxIntervalSeconds"])
                self.config.set("AMBIENT_SENSOR_PUBLISH_MODE", values["publishMode"])

        def save_sensor_config():
            if sensor_config_updating["active"]:
                return sensor_config_values()
            values = sensor_config_values()
            if self.ambient_source is None or not self.ambient_source.apply_sensor_config(values):
                set_sensor_config_fields(sensor_config_last["values"])
                sensor_status_label.setText("not connected")
                return sensor_config_last["values"]
            sensor_config_pending["values"] = dict(values)
            set_sensor_config_fields(values)
            sensor_status_label.setText("sent")
            return values

        def save_settings():
            self.config.set("AMBIENT_LIGHT_CURVE_POINTS", list(curve_editor.points))
            update_curve_lux_labels(min_lux, max_lux)

        def update_curve_live(points):
            points = list(points)
            self.config._data["AMBIENT_LIGHT_CURVE_POINTS"] = points
            self.config.AMBIENT_LIGHT_CURVE_POINTS = points

        def save_curve(points):
            update_curve_live(points)
            self.config.set("AMBIENT_LIGHT_CURVE_POINTS", list(points))

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
            runtime_config = status.get("sensor_config")
            if isinstance(runtime_config, dict):
                runtime_values = {
                    "refreshMs": int(runtime_config.get("refreshMs", sensor_config_last["values"]["refreshMs"])),
                    "publishLuxChangePercent": float(runtime_config.get("publishLuxChangePercent", sensor_config_last["values"]["publishLuxChangePercent"])),
                    "publishMaxIntervalSeconds": int(runtime_config.get("publishMaxIntervalSeconds", sensor_config_last["values"]["publishMaxIntervalSeconds"])),
                    "publishMode": runtime_config.get("publishMode") if runtime_config.get("publishMode") in ("auto", "interval") else sensor_config_last["values"]["publishMode"],
                }
                save_runtime = sensor_config_pending["values"] is not None
                remember_sensor_config(runtime_values, save_file=save_runtime)
                sensor_config_pending["values"] = None
                sensor_config_updating["active"] = True
                if not sensor_refresh_edit.hasFocus() and "refreshMs" in runtime_config:
                    sensor_refresh_edit.setText(str(runtime_config["refreshMs"]))
                if not sensor_change_edit.hasFocus() and "publishLuxChangePercent" in runtime_config:
                    sensor_change_edit.setText(f"{float(runtime_config['publishLuxChangePercent']):g}")
                if not sensor_interval_edit.hasFocus() and "publishMaxIntervalSeconds" in runtime_config:
                    sensor_interval_edit.setText(str(runtime_config["publishMaxIntervalSeconds"]))
                mode = runtime_config.get("publishMode")
                if mode in ("auto", "interval") and not sensor_mode_combo.hasFocus():
                    index = sensor_mode_combo.findData(mode)
                    if index >= 0:
                        sensor_mode_combo.setCurrentIndex(index)
                update_sensor_config_visibility()
                sensor_config_updating["active"] = False
                sensor_status_label.setText("sensor config ok")
            elif status.get("sensor_config_error"):
                sensor_config_pending["values"] = None
                set_sensor_config_fields(sensor_config_last["values"])
                sensor_status_label.setText(str(status.get("sensor_config_error")))
            current_x = normalized_lux(status.get("filtered_lux") or status.get("lux"), min_lux, max_lux)
            curve_editor.current_x = current_x
            if current_x is not None:
                curve_editor.current_y = self._curve_value_from_points(curve_editor.points, current_x)
            else:
                curve_editor.current_y = None
            curve_editor.update()
            graph.add_sample(status.get("lux"), status.get("filtered_lux"), status.get("saturated"))
        curve_editor.points_changed.connect(update_curve_live)
        curve_editor.point_edit_finished.connect(save_curve)
        sensor_refresh_edit.editingFinished.connect(save_sensor_config)
        sensor_change_edit.editingFinished.connect(save_sensor_config)
        sensor_interval_edit.editingFinished.connect(save_sensor_config)
        def sensor_mode_changed(index):
            update_sensor_config_visibility()
            save_sensor_config()

        sensor_mode_combo.currentIndexChanged.connect(sensor_mode_changed)
        update_sensor_config_visibility()

        status_timer = QTimer(parent)
        status_timer.timeout.connect(refresh_status)
        status_timer.start(100)
        save_settings()
        if self.ambient_source is not None:
            if not self.ambient_source.is_running():
                started_passive["value"] = bool(self.ambient_source.start_passive())
            else:
                status = self.ambient_source.status()
                started_passive["value"] = not bool(getattr(self.config, "AMBIENT_SOURCE_ENABLED", False))
                if status.get("lux") is None and status.get("filtered_lux") is None:
                    self.ambient_source.request_measurement(force=True)
            self.ambient_source.request_sensor_config()

        def cleanup():
            if (
                started_passive["value"]
                and self.ambient_source is not None
                and not bool(getattr(self.config, "AMBIENT_SOURCE_ENABLED", False))
            ):
                self.ambient_source.stop()

        refresh_status()
        return {"timer": status_timer, "save": save_settings, "cleanup": cleanup}

    def _build_daytime_settings(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        field_style = "color: white; background: #333; border: 1px solid #555; border-radius: 4px; padding: 3px;"

        def label(text, bold=False):
            item = QLabel(text)
            item.setStyleSheet("color: white;" + (" font-weight: bold;" if bold else ""))
            return item

        def config_float(name, default, minimum, maximum):
            try:
                value = float(getattr(self.config, name, default))
            except (TypeError, ValueError):
                value = default
            return max(minimum, min(maximum, value))

        def config_mode():
            mode = str(getattr(self.config, "DAYTIME_SOLAR_MODE", "auto"))
            return mode if mode in ("auto", "manual") else "auto"

        def current_location():
            latitude = config_float("DAYTIME_LATITUDE", 48.8566, -89.8, 89.8)
            longitude = config_float("DAYTIME_LONGITUDE", 2.3522, -180.0, 180.0)
            name = str(getattr(self.config, "DAYTIME_LOCATION_NAME", "France"))
            return name, latitude, longitude

        def sun_hours():
            try:
                return solar_hours(
                    datetime.datetime.now().astimezone(),
                    config_float("DAYTIME_LATITUDE", 48.8566, -89.8, 89.8),
                    config_float("DAYTIME_LONGITUDE", 2.3522, -180.0, 180.0),
                )
            except Exception:
                return 7.5, 18.5

        def current_position():
            sunrise, sunset = sun_hours()
            return daytime_position(datetime.datetime.now(), sunrise, sunset)

        def add_row(text, widget):
            row = QHBoxLayout()
            row_label = label(text)
            row_label.setFixedWidth(92)
            row.addWidget(row_label)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        mode_combo = QComboBox()
        mode_combo.setInsertPolicy(QComboBox.NoInsert)
        mode_combo.addItem("Auto", "auto")
        mode_combo.addItem("Manual country", "manual")
        mode_combo.setStyleSheet(field_style)
        mode_combo.setCurrentIndex(max(0, mode_combo.findData(config_mode())))

        location_name, latitude, longitude = current_location()
        location_combo = QComboBox()
        location_combo.setInsertPolicy(QComboBox.NoInsert)
        location_combo.addItems(sorted(DAYTIME_LOCATION_PRESETS.keys()))
        location_combo.setStyleSheet(field_style)
        preset_index = location_combo.findText(location_name, Qt.MatchFixedString)
        if preset_index >= 0:
            location_combo.setCurrentIndex(preset_index)
        else:
            location_combo.setCurrentIndex(max(0, location_combo.findText("France", Qt.MatchFixedString)))

        preview_button = QPushButton("Preview OFF")
        preview_button.setCheckable(True)
        preview_button.setFixedHeight(28)
        preview_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:checked {
                background-color: #4f6f42;
                border-color: #78a85f;
            }
        """)

        add_row("Zone", mode_combo)
        add_row("Country/region", location_combo)

        computed_label = label("")
        layout.addWidget(computed_label)

        light_points = self._validated_curve_points(getattr(self.config, "DAYTIME_LIGHT_CURVE_POINTS", None))
        if light_points is None:
            light_points = [18, 28, 55, 100, 55, 28, 18]
        color_points = self._validated_curve_points(getattr(self.config, "DAYTIME_COLOR_CURVE_POINTS", None))
        if color_points is None:
            color_points = [70, 50, 18, 0, 18, 50, 70]

        current_x = current_position()
        light_editor = CurveEditor(
            light_points,
            x_labels=("Sunrise", "Midday", "Sunset"),
            y_label="Screen light",
            y_tick_labels={0: "0%", 50: "50%", 100: "100%"},
            current_x=current_x,
            current_y=self._curve_value_from_points(light_points, current_x),
            preview_x=None,
        )
        color_editor = CurveEditor(
            color_points,
            x_labels=("Sunrise", "Midday", "Sunset"),
            y_label="Color",
            y_tick_labels={0: "cold", 50: "mid", 100: "warm"},
            current_x=current_x,
            current_y=self._curve_value_from_points(color_points, current_x),
            preview_x=None,
        )
        light_editor.setMinimumHeight(165)
        color_editor.setMinimumHeight(165)
        layout.addWidget(label("Daytime light", bold=True))
        layout.addWidget(preview_button)
        layout.addWidget(light_editor)
        layout.addWidget(label("Daytime color", bold=True))
        layout.addWidget(color_editor)
        layout.addStretch()
        preview_state = {"original": None}

        def update_field_visibility():
            manual = mode_combo.currentData() == "manual"
            location_combo.setEnabled(manual)

        def selected_location():
            text = location_combo.currentText().strip()
            preset = DAYTIME_LOCATION_PRESETS.get(text)
            if preset is not None:
                return text, preset[0], preset[1]
            return "France", DAYTIME_LOCATION_PRESETS["France"][0], DAYTIME_LOCATION_PRESETS["France"][1]

        def save_settings(refresh=True):
            mode = mode_combo.currentData() or "auto"
            location, latitude, longitude = selected_location()
            self.config.set("DAYTIME_SOLAR_MODE", mode)
            self.config.set("DAYTIME_LOCATION_NAME", location)
            self.config.set("DAYTIME_LATITUDE", latitude)
            self.config.set("DAYTIME_LONGITUDE", longitude)
            self.config.set("DAYTIME_LIGHT_CURVE_POINTS", list(light_editor.points))
            self.config.set("DAYTIME_COLOR_CURVE_POINTS", list(color_editor.points))
            if refresh:
                refresh_markers()

        def update_curve_live():
            self.config._data["DAYTIME_LIGHT_CURVE_POINTS"] = list(light_editor.points)
            self.config.DAYTIME_LIGHT_CURVE_POINTS = list(light_editor.points)
            self.config._data["DAYTIME_COLOR_CURVE_POINTS"] = list(color_editor.points)
            self.config.DAYTIME_COLOR_CURVE_POINTS = list(color_editor.points)
            refresh_markers()

        def save_curve():
            update_curve_live()
            self.config.set("DAYTIME_LIGHT_CURVE_POINTS", list(light_editor.points))
            self.config.set("DAYTIME_COLOR_CURVE_POINTS", list(color_editor.points))

        def set_preview_bar_visible(visible):
            x = current_position() if visible else None
            light_editor.preview_x = x
            color_editor.preview_x = x
            light_editor.update()
            color_editor.update()

        def restore_preview():
            original = preview_state["original"]
            preview_state["original"] = None
            if original is None:
                return
            if "light" in self.sliders:
                self._set_slider_silent("light", original["light"])
            self._set_slider_silent("brightness", original["brightness"])
            self._set_slider_silent("contrast", original["contrast"])
            self._set_slider_silent("nightlight", original["nightlight"])
            self.apply_light_value(original["light"])
            self._safe_set_nightlight_strength(original["nightlight"])
            self._remember_slider_values()

        def apply_preview(position):
            if not preview_button.isChecked():
                return
            position = max(0.0, min(float(position), 100.0))
            light = round(self._curve_value_from_points(light_editor.points, position))
            color = round(self._curve_value_from_points(color_editor.points, position))
            self.apply_light_value(light)
            self._set_slider_silent("nightlight", color)
            self._safe_set_nightlight_strength(color)

        def preview_toggled(checked):
            preview_button.setText("Preview ON" if checked else "Preview OFF")
            if checked:
                preview_state["original"] = {
                    "light": self.sliders["light"].value() if "light" in self.sliders else self.sliders["brightness"].value(),
                    "brightness": self.sliders["brightness"].value(),
                    "contrast": self.sliders["contrast"].value(),
                    "nightlight": self.sliders["nightlight"].value(),
                }
                set_preview_bar_visible(True)
                apply_preview(current_position())
            else:
                set_preview_bar_visible(False)
                restore_preview()

        def refresh_markers():
            sunrise, sunset = sun_hours()
            x = daytime_position(datetime.datetime.now(), sunrise, sunset)
            computed_label.setText(f"Today sunrise {format_hour(sunrise)}   Today sunset {format_hour(sunset)}")
            for editor in (light_editor, color_editor):
                editor.x_labels = ("Sunrise", "Midday", "Sunset")
                editor.current_x = x
                if preview_button.isChecked() and editor.preview_x is None:
                    editor.preview_x = x
            light_editor.current_y = self._curve_value_from_points(light_editor.points, x)
            color_editor.current_y = self._curve_value_from_points(color_editor.points, x)
            light_editor.update()
            color_editor.update()
            update_field_visibility()

        mode_combo.currentIndexChanged.connect(save_settings)
        location_combo.currentIndexChanged.connect(lambda index: save_settings())
        preview_button.toggled.connect(preview_toggled)
        light_editor.points_changed.connect(lambda points: update_curve_live())
        color_editor.points_changed.connect(lambda points: update_curve_live())
        light_editor.point_edit_finished.connect(lambda points: save_curve())
        color_editor.point_edit_finished.connect(lambda points: save_curve())
        light_editor.preview_changed.connect(apply_preview)
        color_editor.preview_changed.connect(apply_preview)

        refresh_timer = QTimer(parent)
        refresh_timer.timeout.connect(refresh_markers)
        refresh_timer.start(30000)
        refresh_markers()
        return {"timer": refresh_timer, "save": save_settings, "cleanup": restore_preview}

    def open_display_settings(self, initial_tab=None):
        dialog = QDialog(self)
        self._display_settings_dialog = dialog
        dialog.setWindowTitle("Display settings")
        dialog_width = 560
        min_settings_height = 585
        light_height = 620
        smoothing_height = 585
        daytime_height = 585
        nightlight_color_height = 405
        ambient_height = 665
        dialog.setFixedSize(dialog_width, light_height)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)

        page_list = QListWidget()
        page_list.setFixedWidth(170)
        page_list.setStyleSheet("""
            QListWidget {
                color: white;
                background: #2b2b2b;
                border: 1px solid #444;
            }
            QListWidget::item {
                background: #333;
                padding: 8px;
                border-bottom: 1px solid #3f3f3f;
            }
            QListWidget::item:selected {
                background: #444;
            }
            QListWidget::item:disabled {
                color: #9a9a9a;
                background: #262626;
            }
        """)
        page_stack = QStackedWidget()
        page_stack.setStyleSheet("QStackedWidget { border: 1px solid #444; }")

        light_tab = QWidget()
        self._build_light_curve_settings(light_tab, include_cancel=False)

        smoothing_tab = QWidget()
        smoothing_controls = self._build_smoothing_settings(smoothing_tab)

        daytime_tab = QWidget()
        daytime_controls = self._build_daytime_settings(daytime_tab)

        nightlight_color_tab = QWidget()
        nightlight_color_layout = QVBoxLayout(nightlight_color_tab)
        nightlight_color_layout.setContentsMargins(0, 0, 0, 0)
        nightlight_color_layout.setSpacing(0)
        nightlight_color_tabs = QTabWidget()
        nightlight_color_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
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
        color_tab = QWidget()
        color_controls = self._build_nightlight_color_settings(color_tab, include_cancel=False, preview_changes=False)

        gamma_tab = QWidget()
        gamma_controls = self._build_gamma_ramp_settings(gamma_tab)

        nightlight_curve_tab = QWidget()
        nightlight_curve_controls = self._build_light_linked_nightlight_settings(nightlight_curve_tab)

        nightlight_color_tabs.addTab(color_tab, "RGB")
        nightlight_color_tabs.addTab(gamma_tab, "Gamma ramp")
        nightlight_color_tabs.addTab(nightlight_curve_tab, "Light-color link")
        nightlight_color_layout.addWidget(nightlight_color_tabs)

        show_ambient = self.ambient_source is not None and "ambient" in self.available_sources
        ambient_tab = None
        if show_ambient:
            ambient_tab = QWidget()
            ambient_controls = self._build_ambient_sensor_settings(ambient_tab)
        else:
            ambient_controls = {"save": lambda: None, "cleanup": lambda: None}

        pages = []
        page_groups = [
            (
                "Main settings",
                [
                    ("light", "B/C auto curve", light_tab, light_height),
                    ("smoothing", "Smoothing", smoothing_tab, smoothing_height),
                    ("nightlight_color", "Nightlight color", nightlight_color_tab, nightlight_color_height),
                ],
            ),
            (
                "Control sources",
                [
                    ("daytime", "Daytime", daytime_tab, daytime_height),
                ] + (
                    [("ambient", "Light sensor", ambient_tab, ambient_height)] if show_ambient else []
                ),
            ),
        ]

        def add_page_header(text):
            item = QListWidgetItem(text)
            item.setFlags(Qt.NoItemFlags)
            page_list.addItem(item)

        def add_page_item(key, text, widget, height):
            page_index = len(pages)
            pages.append((key, text, widget, height))
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, page_index)
            item.setData(Qt.UserRole + 1, key)
            page_list.addItem(item)
            page_stack.addWidget(widget)

        for group_label, group_pages in page_groups:
            if not group_pages:
                continue
            add_page_header(group_label)
            for key, text, widget, height in group_pages:
                add_page_item(key, text, widget, height)

        settings_row.addWidget(page_list)
        settings_row.addWidget(page_stack, 1)
        layout.addLayout(settings_row)

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
            daytime_controls["cleanup"]()
            smoothing_controls["save"]()
            nightlight_curve_controls["save"]()
            daytime_controls["save"]()
            ambient_controls["save"]()
            ambient_controls["cleanup"]()

        def close_display_settings():
            cleanup_display_settings()
            dialog.accept()

        close_button.clicked.connect(close_display_settings)
        dialog.finished.connect(lambda result: cleanup_display_settings())
        dialog.finished.connect(lambda result: setattr(self, "_display_settings_dialog", None))
        dialog.finished.connect(lambda result: setattr(self, "_display_settings_set_source_available", None))

        def resize_for_page(index):
            if index < 0 or index >= len(pages):
                index = 0
            height = max(min_settings_height, pages[index][3])
            dialog.setFixedSize(dialog_width, height)

        def select_page(row):
            item = page_list.item(row)
            page_index = item.data(Qt.UserRole) if item is not None else None
            if page_index is None:
                for fallback_row in range(page_list.count()):
                    fallback_item = page_list.item(fallback_row)
                    fallback_index = fallback_item.data(Qt.UserRole) if fallback_item is not None else None
                    if fallback_index is not None:
                        page_list.setCurrentRow(fallback_row)
                        return
                return
            page_stack.setCurrentIndex(page_index)
            resize_for_page(page_index)

        def remove_page(key):
            removed_index = None
            removed_widget = None
            for index, (page_key, _, widget, _) in enumerate(pages):
                if page_key == key:
                    removed_index = index
                    removed_widget = widget
                    break
            if removed_index is None:
                return

            was_current = page_stack.currentWidget() is removed_widget
            page_stack.removeWidget(removed_widget)
            pages.pop(removed_index)

            for row in range(page_list.count() - 1, -1, -1):
                item = page_list.item(row)
                if item is not None and item.data(Qt.UserRole + 1) == key:
                    page_list.takeItem(row)
                    break

            for row in range(page_list.count()):
                item = page_list.item(row)
                page_key = item.data(Qt.UserRole + 1) if item is not None else None
                if page_key is None:
                    continue
                for index, (current_key, _, _, _) in enumerate(pages):
                    if current_key == page_key:
                        item.setData(Qt.UserRole, index)
                        break

            if was_current or page_list.currentItem() is None:
                for row in range(page_list.count()):
                    item = page_list.item(row)
                    if item is not None and item.data(Qt.UserRole) is not None:
                        page_list.setCurrentRow(row)
                        select_page(row)
                        break

        def update_display_source_available(source, available):
            if source == "ambient" and not available:
                remove_page("ambient")

        self._display_settings_set_source_available = update_display_source_available

        page_list.currentRowChanged.connect(select_page)
        initial_index = 0
        if initial_tab == "rgb":
            initial_tab = "nightlight_color"
            nightlight_color_tabs.setCurrentWidget(color_tab)
        elif initial_tab == "gamma":
            initial_tab = "nightlight_color"
            nightlight_color_tabs.setCurrentWidget(gamma_tab)
        elif initial_tab == "nightlight_curve":
            initial_tab = "nightlight_color"
            nightlight_color_tabs.setCurrentWidget(nightlight_curve_tab)
        for index, (key, _, _, _) in enumerate(pages):
            if key == initial_tab:
                initial_index = index
                break
        initial_row = 0
        for row in range(page_list.count()):
            item = page_list.item(row)
            if item is not None and item.data(Qt.UserRole) == initial_index:
                initial_row = row
                break
        page_list.setCurrentRow(initial_row)
        QTimer.singleShot(0, lambda: select_page(page_list.currentRow()))
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
        general_label.setFixedHeight(18)
        layout.addWidget(general_label)

        reset_rgb_button = QPushButton("Reset RGB monitor")
        reset_rgb_button.setFixedHeight(28)
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
        target_section_label.setFixedHeight(18)
        layout.addWidget(target_section_label)

        preview_button = QPushButton("Preview OFF")
        preview_button.setCheckable(True)
        preview_button.setFixedHeight(28)
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
        color_label.setFixedHeight(18)
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
        cancel_button.setFixedHeight(28)
        apply_button.setFixedHeight(28)
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
        source = source if source in ("tray", "ambient", "daytime") and source in self.available_sources else "tray"
        self.active_source = source
        if hasattr(self, "source_selector"):
            index = self.source_selector.findData(source)
            if index >= 0 and self.source_selector.currentIndex() != index:
                self._updating_source_selector = True
                self.source_selector.setCurrentIndex(index)
                self._updating_source_selector = False

    def set_source_available(self, source, available):
        if source not in ("ambient", "daytime"):
            return
        if available:
            self.available_sources.add(source)
        else:
            self.available_sources.discard(source)
            if self.active_source == source:
                self.active_source = "tray"
        self._populate_source_selector()
        self.set_source_control(self.active_source)
        updater = getattr(self, "_display_settings_set_source_available", None)
        if updater is not None:
            updater(source, available)

    def _populate_source_selector(self):
        if not hasattr(self, "source_selector"):
            return
        self._updating_source_selector = True
        current = self.active_source if self.active_source in self.available_sources else "tray"
        self.source_selector.clear()
        self.source_selector.addItem("Manual", "tray")
        if "ambient" in self.available_sources:
            self.source_selector.addItem("Sensor", "ambient")
        if "daytime" in self.available_sources:
            self.source_selector.addItem("Daytime", "daytime")
        index = self.source_selector.findData(current)
        self.source_selector.setCurrentIndex(index if index >= 0 else 0)
        self.active_source = self.source_selector.currentData() or "tray"
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
                value = self.sliders['light'].value()
                if self._auto_curve_active():
                    brightness, contrast = self._light_to_brightness_contrast(value)
                    self._set_slider_silent("brightness", brightness)
                    self._set_slider_silent("contrast", contrast)
                    self._safe_set_light_values(brightness, contrast)
                else:
                    brightness = value
                    self._set_slider_silent("brightness", brightness)
                    submit_ddcci_command(
                        "brightness",
                        "Brightness set",
                        lambda monitor=self.monitor, brightness=brightness: monitor.set_brightness(brightness),
                    )
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
    on_general_settings=None,
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
    general_action = QAction("General settings", tray_menu)
    if on_general_settings is not None:
        general_action.triggered.connect(on_general_settings)
    tray_menu.addAction(general_action)
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
