from gui import (
    LIGHT_CURVE_POINT_COUNT,
    NIGHTLIGHT_BACKEND_DDCCI,
    NIGHTLIGHT_BACKEND_GAMMA,
    CurveEditor,
    PopupPanel,
    create_tray_icon,
)
from monitor import DDCCI_Monitor, ddc_ci_monitors_list
from ddcci_screen_tuning import config
from ddcci_command_queue import submit_ddcci_command, submit_light_values
from daytime import daytime_position, solar_hours
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
import datetime
import math
import platform

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


class _AmbientSignals(QObject):
    unavailable = Signal(object)


class TrayControlSource:
    def __init__(self, ambient_source=None):
        self.ambient_source = ambient_source
        self.panel = None
        self.tray_icon = None
        self.daytime_monitor = None
        self.daytime_timer = QTimer()
        self.daytime_timer.timeout.connect(self.apply_daytime)
        self.auto_nightlight_timer = QTimer()
        self.auto_nightlight_timer.timeout.connect(self._apply_auto_nightlight)
        self.ambient_availability_timer = QTimer()
        self.ambient_availability_timer.timeout.connect(self._poll_ambient_availability)
        self._last_auto_nightlight = None
        self._last_ambient_available = None
        self._ambient_seen_at_start = False
        self._ambient_watch_enabled = False
        self._ambient_signals = _AmbientSignals()
        self._ambient_signals.unavailable.connect(self._ambient_source_unavailable)
        if self.ambient_source is not None:
            self.ambient_source.set_unavailable_callback(lambda exc: self._ambient_signals.unavailable.emit(exc))

    def start(self):
        daytime_enabled = bool(getattr(config, "DAYTIME_SOURCE_ENABLED", False))
        ambient_enabled = bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False))
        startup_ambient_available = self.ambient_source is not None and self.ambient_source.is_available()
        self._ambient_seen_at_start = startup_ambient_available
        self._ambient_watch_enabled = startup_ambient_available
        self.tray_icon = create_tray_icon(
            self.show_active_source_window,
            self.open_configuration,
            self.open_daytime_settings,
            self.select_source,
            self._active_source_name(),
            self.select_nightlight_backend,
            self._nightlight_backend(),
        )
        if ambient_enabled and startup_ambient_available and self.ambient_source is not None:
            self.set_daytime_enabled(False)
            if not self.ambient_source.start():
                self._sync_tray_source_menu("tray")
                self._sync_source_availability()
                self.apply_tray_values()
        elif daytime_enabled:
            self.set_daytime_enabled(True)
        self._sync_source_availability()
        self._update_auto_nightlight_timer()
        if self.ambient_source is not None and self._ambient_watch_enabled:
            self.ambient_availability_timer.start(2000)
        QTimer.singleShot(0, self._restore_gamma_nightlight)
        return self.tray_icon

    def select_source(self, source):
        if source == "ambient":
            self.set_daytime_enabled(False)
            if self.ambient_source is not None and self.ambient_source.set_enabled(True):
                self._ambient_watch_enabled = True
                if not self.ambient_availability_timer.isActive():
                    self.ambient_availability_timer.start(2000)
                self._sync_tray_source_menu("ambient")
                self._sync_source_availability()
                self._update_auto_nightlight_timer()
                return
            self._sync_tray_source_menu("tray")
            self._sync_source_availability()
            self._update_auto_nightlight_timer()
            self.apply_tray_values()
        elif source == "daytime":
            self._set_ambient_enabled(False)
            self.set_daytime_enabled(True)
            self._update_auto_nightlight_timer()
        else:
            self._set_ambient_enabled(False)
            self.set_daytime_enabled(False)
            self._update_auto_nightlight_timer()
            self.apply_tray_values()

    def _active_source_name(self):
        if (
            bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False))
            and self.ambient_source is not None
            and self.ambient_source.is_available()
        ):
            return "ambient"
        if bool(getattr(config, "DAYTIME_SOURCE_ENABLED", False)):
            return "daytime"
        return "tray"

    def _sync_tray_source_menu(self, source=None):
        if source is None:
            source = self._active_source_name()
        if self.tray_icon is not None and hasattr(self.tray_icon, "set_source_control"):
            self.tray_icon.set_source_control(source)
        if self.panel is not None and hasattr(self.panel, "set_source_control"):
            self.panel.set_source_control(source)

    def _sync_source_availability(self):
        ambient_available = (
            self.ambient_source is not None
            and self._ambient_watch_enabled
            and self.ambient_source.is_available()
        )
        self._last_ambient_available = ambient_available
        if self.panel is not None and hasattr(self.panel, "set_source_available"):
            self.panel.set_source_available("ambient", ambient_available)

    def _poll_ambient_availability(self):
        if self.ambient_source is None:
            return
        if not self._ambient_watch_enabled:
            return
        ambient_requested = bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False))
        if ambient_requested and not self.ambient_source.is_running():
            if self.ambient_source.start():
                self._sync_tray_source_menu("ambient")
                self._update_auto_nightlight_timer()
                self._sync_source_availability()
                return
        ambient_available = self.ambient_source.is_available()
        if ambient_available == self._last_ambient_available:
            return
        self._last_ambient_available = ambient_available
        if ambient_available and ambient_requested:
            self.set_daytime_enabled(False)
            if self.ambient_source.start():
                self._sync_tray_source_menu("ambient")
                self._update_auto_nightlight_timer()
            ambient_available = self.ambient_source.is_available()
            self._last_ambient_available = ambient_available
        if self.panel is not None and hasattr(self.panel, "set_source_available"):
            self.panel.set_source_available("ambient", ambient_available)

    def _ambient_source_unavailable(self, exc):
        print("[WARN] Ambient source unavailable, switching to manual:", exc)
        if bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False)):
            self.set_daytime_enabled(False)
            self._sync_tray_source_menu("tray")
            self.apply_tray_values()
        self._sync_source_availability()
        self._update_auto_nightlight_timer()

    def _nightlight_source(self):
        source = str(getattr(config, "NIGHTLIGHT_SOURCE", "manual"))
        if source not in ("manual", "daytime", "light_linked"):
            source = "manual"
        return source

    def select_nightlight_source(self, source):
        if source not in ("manual", "daytime", "light_linked"):
            source = "manual"
        config.set("NIGHTLIGHT_SOURCE", source)
        self._sync_panel_nightlight_source_menu(source)
        self._last_auto_nightlight = None
        self._update_auto_nightlight_timer()
        if self._active_source_name() == "daytime":
            self.apply_daytime()
        elif self._active_source_name() == "ambient":
            self._apply_auto_nightlight()
        else:
            self.apply_tray_values()

    def _sync_panel_nightlight_source_menu(self, source=None):
        if source is None:
            source = self._nightlight_source()
        if self.panel is not None and hasattr(self.panel, "set_nightlight_source_control"):
            self.panel.set_nightlight_source_control(source)

    def _update_auto_nightlight_timer(self):
        if self._active_source_name() != "daytime" and self._nightlight_source() != "manual":
            self.auto_nightlight_timer.start(500)
        else:
            self.auto_nightlight_timer.stop()

    def _set_ambient_enabled(self, enabled):
        if self.ambient_source is not None:
            self.ambient_source.set_enabled(enabled)
        else:
            config.set("AMBIENT_SOURCE_ENABLED", bool(enabled))
        self._sync_source_availability()

    def select_nightlight_backend(self, backend):
        if backend not in (NIGHTLIGHT_BACKEND_DDCCI, NIGHTLIGHT_BACKEND_GAMMA):
            backend = NIGHTLIGHT_BACKEND_DDCCI
        self._sync_tray_nightlight_backend_menu(backend)
        if self.panel is not None and self.panel.isVisible():
            self.panel._set_nightlight_backend(backend)
            return
        self.panel = None
        previous_backend = self._nightlight_backend()
        config.set("NIGHTLIGHT_BACKEND", backend)
        if previous_backend == NIGHTLIGHT_BACKEND_GAMMA and backend != NIGHTLIGHT_BACKEND_GAMMA and reset_gamma is not None:
            try:
                reset_gamma()
            except Exception as e:
                print("[WARN] Gamma ramp reset failed:", e)
        if previous_backend != NIGHTLIGHT_BACKEND_GAMMA and backend == NIGHTLIGHT_BACKEND_GAMMA and self.panel is None:
            try:
                monitor = self._monitor_for_daytime()
                submit_ddcci_command(
                    "nightlight",
                    "Nightlight RGB off",
                    lambda monitor=monitor: monitor.nightlight_set_strength(0),
                )
            except Exception as e:
                print("[WARN] Failed to turn off DDC/CI RGB Night Light:", e)
        if bool(getattr(config, "DAYTIME_SOURCE_ENABLED", False)):
            self.apply_daytime()
        else:
            self.apply_tray_values()

    def _sync_tray_nightlight_backend_menu(self, backend=None):
        if backend is None:
            backend = self._nightlight_backend()
        if self.tray_icon is not None and hasattr(self.tray_icon, "set_nightlight_backend"):
            self.tray_icon.set_nightlight_backend(backend)

    def _nightlight_backend(self):
        backend = str(getattr(config, "NIGHTLIGHT_BACKEND", NIGHTLIGHT_BACKEND_DDCCI))
        if backend == NIGHTLIGHT_BACKEND_GAMMA:
            return NIGHTLIGHT_BACKEND_GAMMA
        return NIGHTLIGHT_BACKEND_DDCCI

    def _gamma_warm_kelvin(self):
        try:
            kelvin = int(getattr(config, "GAMMA_RAMP_WARM_KELVIN", 5000))
        except (TypeError, ValueError):
            kelvin = 5000
        return max(1000, min(5000, kelvin))

    def _apply_gamma_nightlight(self, strength):
        if apply_strength is None or reset_gamma is None:
            print("[WARN] Gamma ramp backend unavailable on this system.")
            return False
        strength = max(0, min(100, int(strength)))
        if strength <= 0:
            reset_gamma()
        else:
            apply_strength(self._gamma_warm_kelvin(), strength)
        return True

    def _current_nightlight_value(self):
        return self._nightlight_value_for_source(self._current_light_value())

    def _restore_gamma_nightlight(self):
        if self._nightlight_backend() != NIGHTLIGHT_BACKEND_GAMMA:
            return
        try:
            nightlight = self._current_nightlight_value()
            self._apply_gamma_nightlight(nightlight)
            config.set("LAST_NIGHTLIGHT", nightlight)
            if self.panel is not None and self.panel.isVisible():
                self.panel._set_slider_silent("nightlight", nightlight)
        except Exception as e:
            print("[WARN] Failed to restore Gamma ramp Night Light:", e)

    def _apply_nightlight(self, monitor, value, label):
        if self._nightlight_backend() == NIGHTLIGHT_BACKEND_GAMMA:
            self._apply_gamma_nightlight(value)
            return
        submit_ddcci_command(
            "nightlight",
            label,
            lambda monitor=monitor, value=value: monitor.nightlight_set_strength(value),
        )

    def show_active_source_window(self):
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
                self.panel = PopupPanel(
                    monitor,
                    monitor_names,
                    index,
                    on_nightlight_backend_changed=self._sync_tray_nightlight_backend_menu,
                    ambient_source=self.ambient_source,
                    on_source_selected=self.select_source,
                    active_source=self._active_source_name(),
                    available_sources=self._available_sources(),
                    on_nightlight_source_selected=self.select_nightlight_source,
                    active_nightlight_source=self._nightlight_source(),
                )
            except Exception as e:
                print("[WARN] Failed to open panel:", e)
                return None
        return self.panel

    def _available_sources(self):
        sources = {"tray", "daytime"}
        if (
            self.ambient_source is not None
            and self._ambient_watch_enabled
            and self.ambient_source.is_available()
        ):
            sources.add("ambient")
        return sources

    def show_panel(self):
        if self._ensure_panel() is None:
            return
        self.panel.place_bottom_right()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()
        QTimer.singleShot(0, self._restore_gamma_nightlight)

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
        initial_tab = "ambient" if bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False)) else None
        panel.open_display_settings(initial_tab=initial_tab)

    def set_daytime_enabled(self, enabled):
        config.set("DAYTIME_SOURCE_ENABLED", bool(enabled))
        if enabled:
            config.set("AMBIENT_SOURCE_ENABLED", False)
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
            light = getattr(config, "TRAY_LIGHT", getattr(config, "LAST_LIGHT", 50))
            nightlight = self._nightlight_value_for_source(light)

            if self.panel is not None and self.panel.isVisible():
                self.panel._set_slider_silent("brightness", brightness)
                self.panel._set_slider_silent("contrast", contrast)
                self.panel._set_slider_silent("nightlight", nightlight)
                if self.panel.light_mode:
                    self.panel._set_slider_silent("light", light)
                submit_light_values(self.panel.monitor, brightness, contrast, "Tray light")
                self.panel._safe_set_nightlight_strength(nightlight)
            else:
                monitor = self._monitor_for_daytime()
                submit_light_values(monitor, brightness, contrast, "Tray light")
                self._apply_nightlight(monitor, nightlight, "Tray nightlight")
            config.set("LAST_BRIGHTNESS", brightness)
            config.set("LAST_CONTRAST", contrast)
            config.set("LAST_NIGHTLIGHT", nightlight)
            if hasattr(config, "TRAY_LIGHT"):
                config.set("LAST_LIGHT", getattr(config, "TRAY_LIGHT"))
        except Exception as e:
            print("[WARN] Failed to apply Tray values:", e)

    def _daytime_light_value(self, now=None):
        daytime_position = self._daytime_position(now)
        curve = self._curve_points(
            "DAYTIME_LIGHT_CURVE_POINTS",
            [18, 28, 55, 100, 55, 28, 18],
        )
        return round(self._curve_value(curve, daytime_position))

    def _daytime_color_value(self, now=None):
        daytime_position = self._daytime_position(now)
        curve = self._curve_points(
            "DAYTIME_COLOR_CURVE_POINTS",
            [70, 50, 18, 0, 18, 50, 70],
        )
        return round(self._curve_value(curve, daytime_position))

    def _light_linked_nightlight_value(self, light=None):
        if light is None:
            light = getattr(config, "LAST_LIGHT", getattr(config, "TRAY_LIGHT", 50))
        curve = self._curve_points(
            "LIGHT_NIGHTLIGHT_CURVE_POINTS",
            [80, 65, 45, 25, 12, 4, 0],
        )
        return max(0, min(100, round(self._curve_value(curve, light))))

    def _nightlight_value_for_source(self, light=None):
        source = self._nightlight_source()
        if source == "daytime":
            return self._daytime_color_value()
        if source == "light_linked":
            return self._light_linked_nightlight_value(light)
        return max(0, min(100, int(getattr(config, "TRAY_NIGHTLIGHT", getattr(config, "LAST_NIGHTLIGHT", 0)))))

    def _current_light_value(self):
        if self._active_source_name() == "ambient" and self.ambient_source is not None:
            status = self.ambient_source.status()
            light = status.get("light")
            if light is not None:
                return light
        if self.panel is not None and self.panel.isVisible() and "light" in getattr(self.panel, "sliders", {}):
            return self.panel.sliders["light"].value()
        if self._active_source_name() == "daytime":
            return self._daytime_light_value()
        return getattr(config, "TRAY_LIGHT", getattr(config, "LAST_LIGHT", 50))

    def _apply_auto_nightlight(self):
        if self._nightlight_source() == "manual":
            return
        light = self._current_light_value()
        nightlight = self._nightlight_value_for_source(light)
        if self._last_auto_nightlight == nightlight:
            return
        try:
            if self.panel is not None and self.panel.isVisible():
                self.panel._set_slider_silent("nightlight", nightlight)
                self.panel._safe_set_nightlight_strength(nightlight)
            else:
                monitor = self._monitor_for_daytime()
                self._apply_nightlight(monitor, nightlight, "Auto nightlight")
            config.set("LAST_NIGHTLIGHT", nightlight)
            self._last_auto_nightlight = nightlight
        except Exception as e:
            print("[WARN] Auto Nightlight failed:", e)

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
        sunrise, sunset = self._daytime_sun_hours(now)
        return daytime_position(now, sunrise, sunset)

    def _daytime_sun_hours(self, now=None):
        now = now or datetime.datetime.now().astimezone()
        latitude = getattr(config, "DAYTIME_LATITUDE", 48.8566)
        longitude = getattr(config, "DAYTIME_LONGITUDE", 2.3522)
        try:
            return solar_hours(now, latitude, longitude)
        except Exception as e:
            print("[WARN] Daytime solar calculation failed:", e)
            return 7.5, 18.5

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

    def _auto_curve_active(self):
        return bool(getattr(config, "LIGHT_MODE", False)) and not bool(getattr(config, "DETAIL_ROWS_VISIBLE", True))

    def apply_daytime(self):
        if not bool(getattr(config, "LIGHT_MODE", False)):
            return
        light = self._daytime_light_value()
        color = self._nightlight_value_for_source(light)
        try:
            if self.panel is not None and self.panel.isVisible():
                if self._auto_curve_active():
                    self.panel.apply_light_value(light)
                else:
                    self.panel._set_slider_silent("light", light)
                    self.panel._set_slider_silent("brightness", light)
                    submit_ddcci_command(
                        "brightness",
                        "Daytime brightness",
                        lambda monitor=self.panel.monitor, light=light: monitor.set_brightness(light),
                    )
                self.panel._set_slider_silent("nightlight", color)
                self.panel._safe_set_nightlight_strength(color)
                self.panel._remember_slider_values()
            else:
                monitor = self._monitor_for_daytime()
                if self._auto_curve_active():
                    brightness, contrast = self._light_to_brightness_contrast(light)
                    submit_light_values(monitor, brightness, contrast, "Daytime light")
                    config.set("LAST_CONTRAST", contrast)
                else:
                    brightness = light
                    submit_ddcci_command(
                        "brightness",
                        "Daytime brightness",
                        lambda monitor=monitor, brightness=brightness: monitor.set_brightness(brightness),
                    )
                self._apply_nightlight(monitor, color, "Daytime nightlight")
                config.set("LAST_LIGHT", light)
                config.set("LAST_BRIGHTNESS", brightness)
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
