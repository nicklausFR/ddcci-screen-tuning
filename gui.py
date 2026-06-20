from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QPushButton, QComboBox, QSystemTrayIcon, QMenu, QDialog)
from PySide6.QtGui import QIcon, QFont, QAction, QColor, QPainter, QPen, QBrush, QPalette
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from monitor import DDCCI_Monitor
from ddcci_screen_tuning import PresetManager, config
import sys
import math
import platform
from midi_qt_signals import bus


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

    def __init__(self, points):
        super().__init__()
        self.points = [max(0, min(100, int(point))) for point in points]
        self.active_index = None
        self.setMinimumSize(260, 160)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(14, 10, -14, -18)
        painter.fillRect(self.rect(), QColor(38, 38, 38))

        grid_pen = QPen(QColor(75, 75, 75), 1)
        painter.setPen(grid_pen)
        for i in range(6):
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(rect.left(), round(y), rect.right(), round(y))
        for i in range(11):
            x = rect.left() + rect.width() * i / 10
            painter.drawLine(round(x), rect.top(), round(x), rect.bottom())

        curve_points = []
        for i, value in enumerate(self.points):
            x = rect.left() + rect.width() * i / (len(self.points) - 1)
            y = rect.bottom() - rect.height() * value / 100
            curve_points.append((round(x), round(y)))

        painter.setPen(QPen(QColor(0, 170, 255), 2))
        for left, right in zip(curve_points, curve_points[1:]):
            painter.drawLine(left[0], left[1], right[0], right[1])

        painter.setBrush(QBrush(QColor(245, 245, 245)))
        painter.setPen(QPen(QColor(25, 25, 25), 1))
        for i, point in enumerate(curve_points):
            radius = 5 if i != self.active_index else 7
            painter.drawEllipse(point[0] - radius, point[1] - radius, radius * 2, radius * 2)

    def _index_for_x(self, x):
        rect = self.rect().adjusted(14, 10, -14, -18)
        if rect.width() <= 0:
            return 0
        index = round((x - rect.left()) / rect.width() * (len(self.points) - 1))
        return max(0, min(len(self.points) - 1, index))

    def _value_for_y(self, y):
        rect = self.rect().adjusted(14, 10, -14, -18)
        if rect.height() <= 0:
            return 0
        value = round((rect.bottom() - y) / rect.height() * 100)
        return max(0, min(100, value))

    def _set_point(self, index, value):
        left = self.points[index - 1] if index > 0 else 0
        right = self.points[index + 1] if index < len(self.points) - 1 else 100
        self.points[index] = max(left, min(right, value))
        self.update()
        self.points_changed.emit(list(self.points))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.active_index = self._index_for_x(event.position().x())
        self._set_point(self.active_index, self._value_for_y(event.position().y()))

    def mouseMoveEvent(self, event):
        if self.active_index is not None:
            self._set_point(self.active_index, self._value_for_y(event.position().y()))

    def mouseReleaseEvent(self, event):
        self.active_index = None
        self.update()

class PopupPanel(QWidget):
    def __init__(self, monitor, monitor_names=None, selected_monitor_index=0):
        super().__init__()
        self.config = config
        self.monitor = monitor
        self.monitor_names = monitor_names or [self.monitor.name()]
        self.selected_monitor_index = selected_monitor_index
        self._panel_closed = False
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
        self.setFixedSize(280, 270 if self.light_mode else 240)

        self.bg = QWidget(self)
        self.bg.setStyleSheet("background-color: rgba(45, 45, 45, 230); border-radius: 12px;")
        self.bg.setGeometry(0, 0, 280, 270 if self.light_mode else 240)

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
        layout.setSpacing(12)

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
                    value_label.clicked.connect(self.choose_nightlight_target_color)
            else:
                value_label = QLabel("49")
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                value_label.setFixedWidth(24)
                value_label.setStyleSheet("color: white;")
            self.value_labels[name] = value_label
            row_widgets.append(value_label)
            def on_slider_change(val, lbl=value_label, k=name):
                lbl.setText(str(val))
                delay = self.slider_debounce_delay
                self.debounce_timers[k].start(delay)

            slider.valueChanged.connect(lambda val, lbl=value_label, k=name: on_slider_change(val, lbl, k))

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

        def apply_preset(name):
            if preset_combo.isEditable() and preset_combo.lineEdit().hasFocus():
                return
            if name == "New preset":
                return
            values = self.preset_manager.get(name)
            for timer in self.debounce_timers.values():
                timer.stop()

            if 'light_curve_points' in values:
                points = values['light_curve_points']
                if isinstance(points, (list, tuple)) and len(points) == 11:
                    self.config.set("LIGHT_CURVE_POINTS", list(points))
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
            if 'nightlight_target_rgb' in values:
                target = values['nightlight_target_rgb']
                if isinstance(target, (list, tuple)) and len(target) == 3:
                    self.config.set("NIGHTLIGHT_TARGET_RGB", list(target))
                    self.monitor.nightlight_set_target_rgb(*target, apply_current=False)
            if 'nightlight' in values:
                nightlight = max(0, min(100, int(values['nightlight'])))
                self._set_slider_silent("nightlight", nightlight)
                self.monitor.nightlight_set_strength(nightlight)

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
            }
            if self.light_mode:
                values["light"] = self._brightness_to_light(values["brightness"])
                values["light_curve_points"] = self._light_curve_points()
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

        try:
            brightness = self.monitor.get_brightness()
            self._set_slider_silent("brightness", brightness)
        except Exception as e:
            print("[WARN] Brightness unavailable, retrying in 1 s:", e)
            QTimer.singleShot(1000, self._load_monitor_values)
            return

        try:
            contrast = self.monitor.get_contrast()
            self._set_slider_silent("contrast", contrast)
        except Exception as e:
            print("[WARN] Contrast unavailable, retrying in 1 s:", e)
            QTimer.singleShot(1000, self._load_monitor_values)
            return

        if self.light_mode:
            light = self._brightness_to_light(brightness)
            self._set_slider_silent("light", light)
            self._set_slider_silent("brightness", brightness)
            self._set_slider_silent("contrast", contrast)

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

    def _light_curve_points(self):
        points = getattr(self.config, "LIGHT_CURVE_POINTS", None)
        if isinstance(points, (list, tuple)) and len(points) == 11:
            try:
                values = [max(0, min(100, int(point))) for point in points]
            except (TypeError, ValueError):
                values = None
            if values is not None:
                values[0] = 0
                values[-1] = 100
                for i in range(1, len(values)):
                    values[i] = max(values[i - 1], values[i])
                return values

        curve = max(0.1, float(getattr(self.config, "LIGHT_CURVE", 0.75)))
        return [round(100 * math.pow(i / 10, curve)) for i in range(11)]

    def _curve_value(self, x):
        x = max(0.0, min(float(x), 100.0))
        points = self._light_curve_points()
        left_index = min(9, int(x // 10))
        right_index = left_index + 1
        t = (x - left_index * 10) / 10.0
        return points[left_index] + (points[right_index] - points[left_index]) * t

    def _light_to_brightness_contrast(self, value):
        y = self._curve_value(value) / 100.0

        b_min, b_max = self._config_range("LIGHT_BRIGHTNESS_RANGE", (0, 100))
        c_min, c_max = self._config_range("LIGHT_CONTRAST_RANGE", (35, 75))

        brightness = b_min + (b_max - b_min) * y
        contrast = c_min + (c_max - c_min) * math.sqrt(y)
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
            error = abs(self._curve_value(value) - target)
            if error < best_error:
                best_error = error
                best_value = value
        return best_value

    def _safe_set_nightlight_target(self, target):
        if self._panel_closed:
            return False
        try:
            self.monitor.nightlight_set_target_rgb(*target)
            return True
        except Exception as e:
            print("[WARN] Failed to apply target color:", e)
            return False

    def _safe_set_light_values(self, brightness, contrast):
        if self._panel_closed:
            return False
        try:
            self.monitor.set_brightness(brightness)
            self.monitor.set_contrast(contrast)
            return True
        except Exception as e:
            print("[WARN] Failed to apply Auto curve:", e)
            return False

    def choose_light_curve(self):
        original_points = self._light_curve_points()
        original_light = self.sliders["light"].value()
        original_brightness = self.sliders["brightness"].value()
        original_contrast = self.sliders["contrast"].value()

        dialog = QDialog(self)
        self._light_curve_dialog = dialog
        dialog.setWindowTitle("Auto Curve")
        dialog.setFixedSize(310, 225)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        editor = CurveEditor(original_points)
        layout.addWidget(editor)

        button_row = QHBoxLayout()
        reset_button = QPushButton("Reset")
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("OK")
        button_row.addWidget(reset_button)
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(ok_button)
        layout.addLayout(button_row)

        def apply_points(points):
            self.config.set("LIGHT_CURVE_POINTS", list(points))
            brightness, contrast = self._light_to_brightness_contrast(original_light)
            self._set_slider_silent("brightness", brightness)
            self._set_slider_silent("contrast", contrast)
            self._safe_set_light_values(brightness, contrast)

        def reset_points():
            editor.points = [0, 18, 30, 41, 50, 59, 68, 77, 85, 92, 100]
            editor.update()
            apply_points(editor.points)

        editor.points_changed.connect(apply_points)
        reset_button.clicked.connect(reset_points)
        cancel_button.clicked.connect(dialog.reject)
        ok_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.Accepted:
            self.config.set("LIGHT_CURVE_POINTS", original_points)
            self._set_slider_silent("light", original_light)
            self._set_slider_silent("brightness", original_brightness)
            self._set_slider_silent("contrast", original_contrast)
            self._safe_set_light_values(original_brightness, original_contrast)
            self._light_curve_dialog = None
            return

        self.config.set("LIGHT_CURVE_POINTS", list(editor.points))
        self._remember_slider_values()
        self._light_curve_dialog = None

    def handle_nightlight_click(self):
        try:
            current = self.monitor.nightlight_get_strength()
        except Exception as e:
            print("[WARN] Failed to read Night Light:", e)
            return

        if current > 0:
            self._last_nightlight_strength = current
            self.monitor.nightlight_set_strength(0)
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
            self.monitor.nightlight_set_strength(self._last_nightlight_strength)
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
        dialog.setWindowTitle("Target Color")
        dialog.setFixedSize(260, 82)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setFixedHeight(20)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0.00 #ffff00,
                    stop: 0.35 #ffd12a,
                    stop: 0.68 #ff8a1c,
                    stop: 1.00 #ff0000
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
        slider.setValue(self._nightlight_target_to_warmth(self.monitor.nightlight_get_target_rgb()))
        layout.addWidget(slider)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("OK")
        cancel_button.clicked.connect(dialog.reject)
        ok_button.clicked.connect(dialog.accept)
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(ok_button)
        layout.addLayout(button_row)

        def apply_target(value):
            self._safe_set_nightlight_target(self._warmth_to_nightlight_target(value))

        slider.valueChanged.connect(apply_target)
        apply_target(slider.value())

        if dialog.exec() != QDialog.Accepted:
            self._safe_set_nightlight_target(original_target)
            self._nightlight_target_dialog = None
            return

        target = self._warmth_to_nightlight_target(slider.value())
        self.config.set("NIGHTLIGHT_TARGET_RGB", target)
        self._safe_set_nightlight_target(target)
        self._nightlight_target_dialog = None

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

    def send_debounced(self, key):
        try:
            if key == "light":
                brightness, contrast = self._light_to_brightness_contrast(self.sliders['light'].value())
                self._set_slider_silent("brightness", brightness)
                self._set_slider_silent("contrast", contrast)
                self._safe_set_light_values(brightness, contrast)
            elif key == "brightness":
                self.monitor.set_brightness(self.sliders['brightness'].value())
            elif key == "contrast":
                self.monitor.set_contrast(self.sliders['contrast'].value())
            elif key == "nightlight":
                self.monitor.nightlight_set_strength(self.sliders['nightlight'].value())
            self._remember_slider_values()
        except Exception as e:
            print(f"[WARN] {key} set failed:", e)

    def place_bottom_right(self):
        screen_rect = QApplication.primaryScreen().availableGeometry()
        x = screen_rect.right() - self.width() - 10
        y = screen_rect.bottom() - self.height() - 10
        self.move(x, y)

    def _has_visible_child_dialog(self):
        for dialog_name in ("_nightlight_target_dialog", "_light_curve_dialog"):
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
        for dialog_name in ("_nightlight_target_dialog", "_light_curve_dialog"):
            dialog = getattr(self, dialog_name, None)
            if dialog is not None:
                dialog.reject()
                setattr(self, dialog_name, None)
        try:
            self.monitor.close()
        except Exception as e:
            print("[WARN] Failed to close monitor:", e)
        super().closeEvent(event)

def create_tray_icon(on_triggered):
    tray_icon = QSystemTrayIcon()
    tray_icon.setIcon(QIcon(tray_icon_path()))
    tray_menu = QMenu()
    source_menu = tray_menu.addMenu("Source control")
    tray_source_action = QAction("Tray", source_menu)
    tray_source_action.setCheckable(True)
    tray_source_action.setChecked(True)
    tray_source_action.setEnabled(False)
    source_menu.addAction(tray_source_action)
    tray_menu.addSeparator()
    quit_action = QAction("Quit", tray_menu)
    quit_action.triggered.connect(QApplication.instance().quit)
    tray_menu.addAction(quit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.tray_menu = tray_menu
    def handle_activation(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            on_triggered()
    tray_icon.activated.connect(handle_activation)
    QTimer.singleShot(100, tray_icon.show)
    return tray_icon
