from gui import LIGHT_CURVE_POINT_COUNT, CurveEditor, PopupPanel, create_tray_icon
from monitor import DDCCI_Monitor, ddc_ci_monitors_list
from ddcci_screen_tuning import config
from ddcci_command_queue import submit_ddcci_command, submit_light_values
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
import datetime
import math


class TrayControlSource:
    def __init__(self):
        self.panel = None
        self.tray_icon = None
        self.daytime_monitor = None
        self.daytime_timer = QTimer()
        self.daytime_timer.timeout.connect(self.apply_daytime)

    def start(self):
        daytime_enabled = bool(getattr(config, "DAYTIME_SOURCE_ENABLED", False))
        self.tray_icon = create_tray_icon(
            self.show_active_source_window,
            self.open_configuration,
            self.open_daytime_settings,
            self.select_source,
            "daytime" if daytime_enabled else "tray",
        )
        if daytime_enabled:
            self.set_daytime_enabled(True)
        return self.tray_icon

    def select_source(self, source):
        if source == "daytime":
            self.set_daytime_enabled(True)
        else:
            self.set_daytime_enabled(False)
            self.apply_tray_values()

    def show_active_source_window(self):
        if bool(getattr(config, "DAYTIME_SOURCE_ENABLED", False)):
            self.open_daytime_settings()
        else:
            self.show_panel()

    def selected_monitor_index(self, monitors):
        if not monitors:
            raise RuntimeError("No DDC/CI monitor detected.")
        try:
            index = int(getattr(config, "SELECTED_MONITOR_INDEX", 0))
        except (TypeError, ValueError):
            index = 0
        return max(0, min(index, len(monitors) - 1))

    def _ensure_panel(self):
        if self.panel is None or not self.panel.isVisible():
            try:
                monitor_names = ddc_ci_monitors_list()
                index = self.selected_monitor_index(monitor_names)
                monitor = DDCCI_Monitor(index=index)
                self.panel = PopupPanel(monitor, monitor_names, index)
            except Exception as e:
                print("[WARN] Failed to open panel:", e)
                return None
        return self.panel

    def show_panel(self):
        if self._ensure_panel() is None:
            return
        self.panel.place_bottom_right()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def open_configuration(self):
        QTimer.singleShot(0, self._open_configuration_now)

    def _open_configuration_now(self):
        panel = self._ensure_panel()
        if panel is None:
            return
        panel.place_bottom_right()
        panel.show()
        panel.raise_()
        panel.activateWindow()
        panel.open_display_settings()

    def set_daytime_enabled(self, enabled):
        config.set("DAYTIME_SOURCE_ENABLED", bool(enabled))
        if enabled:
            self.apply_daytime()
            interval = int(float(getattr(config, "DAYTIME_UPDATE_SECONDS", 300)) * 1000)
            self.daytime_timer.start(max(10000, interval))
        else:
            self.daytime_timer.stop()
            if self.daytime_monitor is not None:
                try:
                    self.daytime_monitor.close()
                except Exception as e:
                    print("[WARN] Failed to close Daytime monitor:", e)
                self.daytime_monitor = None

    def apply_tray_values(self):
        try:
            brightness = max(0, min(100, int(getattr(config, "TRAY_BRIGHTNESS", getattr(config, "LAST_BRIGHTNESS", 49)))))
            contrast = max(0, min(100, int(getattr(config, "TRAY_CONTRAST", getattr(config, "LAST_CONTRAST", 49)))))
            nightlight = max(0, min(100, int(getattr(config, "TRAY_NIGHTLIGHT", getattr(config, "LAST_NIGHTLIGHT", 0)))))

            if self.panel is not None and self.panel.isVisible():
                self.panel._set_slider_silent("brightness", brightness)
                self.panel._set_slider_silent("contrast", contrast)
                self.panel._set_slider_silent("nightlight", nightlight)
                if self.panel.light_mode:
                    light = getattr(config, "TRAY_LIGHT", getattr(config, "LAST_LIGHT", self.panel._brightness_to_light(brightness)))
                    self.panel._set_slider_silent("light", light)
                submit_light_values(self.panel.monitor, brightness, contrast, "Tray light")
                submit_ddcci_command(
                    "nightlight",
                    "Tray nightlight",
                    lambda monitor=self.panel.monitor, value=nightlight: monitor.nightlight_set_strength(value),
                )
            else:
                monitor = self._monitor_for_daytime()
                submit_light_values(monitor, brightness, contrast, "Tray light")
                submit_ddcci_command(
                    "nightlight",
                    "Tray nightlight",
                    lambda monitor=monitor, value=nightlight: monitor.nightlight_set_strength(value),
                )
            config.set("LAST_BRIGHTNESS", brightness)
            config.set("LAST_CONTRAST", contrast)
            config.set("LAST_NIGHTLIGHT", nightlight)
            if hasattr(config, "TRAY_LIGHT"):
                config.set("LAST_LIGHT", getattr(config, "TRAY_LIGHT"))
        except Exception as e:
            print("[WARN] Failed to apply Tray values:", e)

    def _daytime_light_value(self, now=None):
        min_light = int(getattr(config, "DAYTIME_MIN_LIGHT", 18))
        max_light = int(getattr(config, "DAYTIME_MAX_LIGHT", 88))
        min_light = max(0, min(100, min_light))
        max_light = max(min_light, min(100, max_light))
        daytime_position = self._daytime_position(now)
        curve = self._curve_points(
            "DAYTIME_LIGHT_CURVE_POINTS",
            [18, 28, 55, 100, 55, 28, 18],
        )
        curved_position = self._curve_value(curve, daytime_position) / 100.0
        return round(min_light + (max_light - min_light) * curved_position)

    def _daytime_color_value(self, now=None):
        daytime_position = self._daytime_position(now)
        curve = self._curve_points(
            "DAYTIME_COLOR_CURVE_POINTS",
            [70, 50, 18, 0, 18, 50, 70],
        )
        return round(self._curve_value(curve, daytime_position))

    def _config_rgb(self, name, default):
        value = getattr(config, name, default)
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return default
        try:
            return [max(0, min(100, int(channel))) for channel in value]
        except (TypeError, ValueError):
            return default

    def _nightlight_rgb_for_strength(self, strength):
        neutral = self._config_rgb("NIGHTLIGHT_NEUTRAL_RGB", [50, 50, 50])
        target = self._config_rgb("NIGHTLIGHT_TARGET_RGB", [100, 40, 8])
        t = max(0.0, min(float(strength), 100.0)) / 100.0
        return [
            neutral[channel] + (target[channel] - neutral[channel]) * t
            for channel in range(3)
        ]

    def _kelvin_for_nightlight_strength(self, strength):
        r, g, b = [channel / 100.0 for channel in self._nightlight_rgb_for_strength(strength)]

        def linear(channel):
            if channel <= 0.04045:
                return channel / 12.92
            return ((channel + 0.055) / 1.055) ** 2.4

        r, g, b = linear(r), linear(g), linear(b)
        x = r * 0.4124 + g * 0.3576 + b * 0.1805
        y = r * 0.2126 + g * 0.7152 + b * 0.0722
        z = r * 0.0193 + g * 0.1192 + b * 0.9505
        total = x + y + z
        if total <= 0:
            return 6500
        chroma_x = x / total
        chroma_y = y / total
        if chroma_y == 0.1858:
            return 6500
        n = (chroma_x - 0.3320) / (chroma_y - 0.1858)
        kelvin = -449 * n ** 3 + 3525 * n ** 2 - 6823.3 * n + 5520.33
        return round(max(1000, min(12000, kelvin)), -2)

    def _kelvin_tick_labels(self):
        return {
            0: f"{self._kelvin_for_nightlight_strength(0)}K",
            50: f"{self._kelvin_for_nightlight_strength(50)}K",
            100: f"{self._kelvin_for_nightlight_strength(100)}K",
        }

    def _daytime_position(self, now=None):
        now = now or datetime.datetime.now()
        day_of_year = now.timetuple().tm_yday
        seasonal = math.cos(2 * math.pi * (day_of_year - 172) / 365.0)
        sunrise = 7.5 - 1.6 * seasonal
        sunset = 18.5 + 2.0 * seasonal
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0

        if sunset <= sunrise:
            return 50.0
        position = (hour - sunrise) / (sunset - sunrise)
        return max(0.0, min(1.0, position)) * 100

    def _monitor_for_daytime(self):
        if self.panel is not None and self.panel.isVisible():
            return self.panel.monitor
        if self.daytime_monitor is None:
            monitor_names = ddc_ci_monitors_list()
            index = self.selected_monitor_index(monitor_names)
            self.daytime_monitor = DDCCI_Monitor(index=index)
        return self.daytime_monitor

    def _curve_points(self, name, fallback):
        points = getattr(config, name, None)
        if not isinstance(points, (list, tuple)) or len(points) != LIGHT_CURVE_POINT_COUNT:
            return fallback
        try:
            return [max(0, min(100, int(point))) for point in points]
        except (TypeError, ValueError):
            return fallback

    def _curve_value(self, points, x):
        values = [float(point) for point in points]
        t = max(0.0, min(float(x), 100.0)) / 100.0
        while len(values) > 1:
            values = [
                values[index] + (values[index + 1] - values[index]) * t
                for index in range(len(values) - 1)
            ]
        return values[0]

    def _config_range(self, name, default):
        value = getattr(config, name, default)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return default
        return float(value[0]), float(value[1])

    def _light_to_brightness_contrast(self, value):
        brightness_points = self._curve_points(
            "LIGHT_BRIGHTNESS_CURVE_POINTS",
            [0, 34, 55, 68, 78, 88, 100],
        )
        contrast_points = self._curve_points(
            "LIGHT_CONTRAST_CURVE_POINTS",
            [0, 18, 31, 42, 55, 74, 100],
        )
        brightness_y = self._curve_value(brightness_points, value) / 100.0
        contrast_y = self._curve_value(contrast_points, value) / 100.0
        b_min, b_max = self._config_range("LIGHT_BRIGHTNESS_RANGE", (0, 100))
        c_min, c_max = self._config_range("LIGHT_CONTRAST_RANGE", (35, 100))
        brightness = b_min + (b_max - b_min) * brightness_y
        contrast = c_min + (c_max - c_min) * contrast_y
        return round(brightness), round(contrast)

    def apply_daytime(self):
        if not bool(getattr(config, "LIGHT_MODE", False)):
            return
        light = self._daytime_light_value()
        color = self._daytime_color_value()
        try:
            if self.panel is not None and self.panel.isVisible():
                self.panel.apply_light_value(light)
                self.panel._set_slider_silent("nightlight", color)
                submit_ddcci_command(
                    "nightlight",
                    "Daytime nightlight",
                    lambda monitor=self.panel.monitor, value=color: monitor.nightlight_set_strength(value),
                )
                self.panel._remember_slider_values()
            else:
                monitor = self._monitor_for_daytime()
                brightness, contrast = self._light_to_brightness_contrast(light)
                submit_light_values(monitor, brightness, contrast, "Daytime light")
                submit_ddcci_command(
                    "nightlight",
                    "Daytime nightlight",
                    lambda monitor=monitor, value=color: monitor.nightlight_set_strength(value),
                )
                config.set("LAST_LIGHT", light)
                config.set("LAST_BRIGHTNESS", brightness)
                config.set("LAST_CONTRAST", contrast)
                config.set("LAST_NIGHTLIGHT", color)
        except Exception as e:
            print("[WARN] Daytime source failed:", e)

    def open_daytime_settings(self):
        original_light_points = self._curve_points(
            "DAYTIME_LIGHT_CURVE_POINTS",
            [18, 28, 55, 100, 55, 28, 18],
        )
        original_color_points = self._curve_points(
            "DAYTIME_COLOR_CURVE_POINTS",
            [70, 50, 18, 0, 18, 50, 70],
        )
        current_x = self._daytime_position()
        current_light_y = self._curve_value(original_light_points, current_x)
        current_color_y = self._curve_value(original_color_points, current_x)
        curve_templates = {
            "Natural daylight": {
                "light": [18, 28, 55, 100, 55, 28, 18],
                "color": [70, 50, 18, 0, 18, 50, 70],
            },
            "Office focus": {
                "light": [35, 55, 82, 100, 82, 55, 35],
                "color": [35, 18, 5, 0, 5, 18, 35],
            },
            "Soft reading": {
                "light": [12, 20, 38, 62, 38, 20, 12],
                "color": [78, 68, 48, 22, 48, 68, 78],
            },
            "Low glare": {
                "light": [10, 16, 30, 50, 30, 16, 10],
                "color": [65, 58, 42, 24, 42, 58, 65],
            },
            "Stable workday": {
                "light": [42, 55, 68, 78, 68, 55, 42],
                "color": [28, 14, 4, 0, 4, 14, 28],
            },
            "Warm all day": {
                "light": [16, 24, 42, 66, 42, 24, 16],
                "color": [82, 72, 58, 42, 58, 72, 82],
            },
        }

        dialog = QDialog()
        dialog.setWindowTitle("Daytime settings")
        dialog.setFixedSize(330, 540)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)

        template_combo = QComboBox()
        template_combo.setInsertPolicy(QComboBox.NoInsert)
        template_combo.addItem("Custom")
        template_combo.addItems(curve_templates.keys())
        template_combo.setStyleSheet("color: white; background-color: #333; border-radius: 4px; padding: 2px;")
        layout.addWidget(template_combo)

        light_label = QLabel("Auto intensity")
        light_label.setStyleSheet("color: white;")
        light_editor = CurveEditor(
            original_light_points,
            x_labels=("Sunrise", "Midday", "Sunset"),
            y_label="Brightness (%)",
            y_tick_labels={0: "0%", 50: "50%", 100: "100%"},
            current_x=current_x,
            current_y=current_light_y,
        )
        color_label = QLabel("Color")
        color_label.setStyleSheet("color: white;")
        color_editor = CurveEditor(
            original_color_points,
            x_labels=("Sunrise", "Midday", "Sunset"),
            y_label="Color temperature",
            y_tick_labels=self._kelvin_tick_labels(),
            current_x=current_x,
            current_y=current_color_y,
        )
        layout.addWidget(light_label)
        layout.addWidget(light_editor)
        layout.addWidget(color_label)
        layout.addWidget(color_editor)

        button_row = QHBoxLayout()
        reset_button = QPushButton("Reset")
        cancel_button = QPushButton("Cancel")
        apply_button = QPushButton("Apply")
        button_row.addWidget(reset_button)
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(apply_button)
        layout.addLayout(button_row)

        def refresh_current_markers():
            light_editor.current_y = self._curve_value(light_editor.points, current_x)
            color_editor.current_y = self._curve_value(color_editor.points, current_x)

        def set_editor_points(light_points, color_points):
            light_editor.points = list(light_points)
            color_editor.points = list(color_points)
            refresh_current_markers()
            light_editor.update()
            color_editor.update()

        def reset_points():
            set_editor_points(
                [18, 28, 55, 100, 55, 28, 18],
                [70, 50, 18, 0, 18, 50, 70],
            )

        def apply_template(name):
            template = curve_templates.get(name)
            if template is None:
                return
            set_editor_points(template["light"], template["color"])

        template_combo.currentTextChanged.connect(apply_template)
        reset_button.clicked.connect(reset_points)
        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.Accepted:
            return

        config.set("DAYTIME_LIGHT_CURVE_POINTS", list(light_editor.points))
        config.set("DAYTIME_COLOR_CURVE_POINTS", list(color_editor.points))
        if bool(getattr(config, "DAYTIME_SOURCE_ENABLED", False)):
            self.apply_daytime()
