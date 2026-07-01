import json
import math
import threading
import time

from ddcci_command_queue import submit_light_values
from ddcci_screen_tuning import config
from monitor import DDCCI_Monitor, ddc_ci_monitors_list


class AmbientLightController:
    def __init__(self):
        self.monitor = None
        self._last_applied_light = None
        self._last_light = None
        self._filtered_lux = None
        self._last_measurement_at = None
        self._filtered_at = None
        self._last_raw_lux = None
        self._last_visible = None
        self._last_ir = None
        self._last_full = None
        self._last_saturated = None
        self._last_brightness = None
        self._last_contrast = None
        self._lock = threading.Lock()

    def on_measurement(self, lux, visible=None, ir=None, full=None, saturated=None):
        saturated = bool(saturated)
        try:
            lux = max(0.0, float(lux))
        except (TypeError, ValueError):
            if not saturated:
                return
            lux = self._config_float("AMBIENT_MAX_LUX", 500.0, 0.001, 100000.0)
        if saturated:
            lux = max(lux, self._config_float("AMBIENT_MAX_LUX", 500.0, 0.001, 100000.0))

        with self._lock:
            self._last_measurement_at = time.monotonic()
            self._last_raw_lux = lux
            self._last_visible = visible
            self._last_ir = ir
            self._last_full = full
            self._last_saturated = saturated
            self._filtered_lux = self._smooth_lux(lux)
            light = self._lux_to_light(self._filtered_lux)
            brightness, contrast = self._light_to_brightness_contrast(light)
            self._last_light = light
            self._last_brightness = brightness
            self._last_contrast = contrast
            if self._should_apply(light):
                self._apply_light(light, brightness, contrast)

    def status(self):
        with self._lock:
            age = None
            if self._last_measurement_at is not None:
                age = time.monotonic() - self._last_measurement_at
            return {
                "lux": self._last_raw_lux,
                "filtered_lux": self._filtered_lux,
                "visible": self._last_visible,
                "ir": self._last_ir,
                "full": self._last_full,
                "saturated": self._last_saturated,
                "age": age,
                "light": self._last_light,
                "brightness": self._last_brightness,
                "contrast": self._last_contrast,
            }

    def close(self):
        if self.monitor is not None:
            try:
                self.monitor.close()
            finally:
                self.monitor = None

    def _smooth_lux(self, lux):
        now = time.monotonic()
        smoothing_seconds = self._config_float("AMBIENT_SMOOTHING_SECONDS", 2.0, 0.0, 60.0)
        if self._filtered_lux is None or self._filtered_at is None or smoothing_seconds <= 0:
            self._filtered_at = now
            return lux
        elapsed = max(0.001, now - self._filtered_at)
        self._filtered_at = now
        alpha = 1.0 - math.exp(-elapsed / smoothing_seconds)
        return self._filtered_lux + (lux - self._filtered_lux) * alpha

    def _lux_to_light(self, lux):
        min_lux = self._config_float("AMBIENT_MIN_LUX", 5.0, 0.001, 100000.0)
        max_lux = self._config_float("AMBIENT_MAX_LUX", 500.0, min_lux + 0.001, 100000.0)

        log_min = math.log10(min_lux)
        log_max = math.log10(max_lux)
        position = (math.log10(max(min_lux, min(lux, max_lux))) - log_min) / (log_max - log_min)
        return round(100 * position)

    def _should_apply(self, light):
        threshold = self._config_int("AMBIENT_APPLY_THRESHOLD", 2, 0, 100)
        if self._last_applied_light is None:
            return True
        return abs(light - self._last_applied_light) >= threshold

    def _apply_light(self, light, brightness=None, contrast=None):
        monitor = self._monitor()
        if brightness is None or contrast is None:
            brightness, contrast = self._light_to_brightness_contrast(light)
        submit_light_values(monitor, brightness, contrast, "Ambient sensor light")
        self._last_applied_light = light
        config.set("LAST_LIGHT", light)
        config.set("LAST_BRIGHTNESS", brightness)
        config.set("LAST_CONTRAST", contrast)

    def _monitor(self):
        if self.monitor is None:
            monitor_names = ddc_ci_monitors_list()
            if not monitor_names:
                raise RuntimeError("No DDC/CI monitor detected.")
            index = self._config_int("SELECTED_MONITOR_INDEX", 0, 0, len(monitor_names) - 1)
            self.monitor = DDCCI_Monitor(index=index)
        return self.monitor

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

    def _curve_points(self, name, fallback):
        points = getattr(config, name, None)
        if not isinstance(points, (list, tuple)) or len(points) != 7:
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
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return default

    def _config_float(self, name, default, minimum, maximum):
        try:
            value = float(getattr(config, name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _config_int(self, name, default, minimum, maximum):
        try:
            value = int(getattr(config, name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))


class UsbSerialAmbientReader:
    def __init__(self, controller):
        self.controller = controller
        self.running = False
        self.thread = None
        self.serial_port = None
        self.port_name = None

    def start(self):
        if self.running:
            return True
        try:
            import serial
        except ImportError:
            print("[WARN] Ambient USB source requires pyserial.")
            return False

        port = str(getattr(config, "AMBIENT_USB_PORT", "") or "").strip()
        if not port:
            port = self._auto_detect_port(serial)
            if not port:
                return False

        baudrate = self._config_int("AMBIENT_USB_BAUDRATE", 115200, 1200, 1000000)
        timeout = self._config_float("AMBIENT_USB_TIMEOUT", 1.0, 0.05, 10.0)

        try:
            self.serial_port = serial.Serial(port, baudrate=baudrate, timeout=timeout)
            self.port_name = port
        except Exception as exc:
            print(f"[WARN] Ambient USB source failed to open {port}:", exc)
            return False

        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        print(f"Ambient USB source connected on {port}.")
        return True

    def _auto_detect_port(self, serial_module):
        if not bool(getattr(config, "AMBIENT_USB_AUTO_DETECT", True)):
            print("[WARN] Ambient USB source enabled but AMBIENT_USB_PORT is empty.")
            return None

        try:
            ports = list(serial_module.tools.list_ports.comports())
        except AttributeError:
            try:
                from serial.tools import list_ports
                ports = list(list_ports.comports())
            except Exception as exc:
                print("[WARN] Ambient USB auto-detect failed:", exc)
                return None

        if not ports:
            print("[WARN] Ambient USB auto-detect found no serial ports.")
            return None

        hints = getattr(config, "AMBIENT_USB_PORT_HINTS", [])
        if not isinstance(hints, (list, tuple)):
            hints = []
        hints = [str(hint).lower() for hint in hints]

        def port_text(port):
            fields = [
                getattr(port, "device", ""),
                getattr(port, "name", ""),
                getattr(port, "description", ""),
                getattr(port, "manufacturer", ""),
                getattr(port, "product", ""),
                getattr(port, "hwid", ""),
            ]
            return " ".join(str(field).lower() for field in fields if field)

        matches = [port for port in ports if any(hint in port_text(port) for hint in hints)]
        if len(matches) == 1:
            device = matches[0].device
            print(f"Ambient USB auto-detected {device}.")
            return device

        if len(matches) > 1:
            devices = ", ".join(port.device for port in matches)
            print(f"[WARN] Ambient USB auto-detect matched multiple ports: {devices}. Set AMBIENT_USB_PORT.")
            return None

        if len(ports) == 1:
            device = ports[0].device
            print(f"Ambient USB auto-detected the only serial port: {device}.")
            return device

        devices = ", ".join(port.device for port in ports)
        print(f"[WARN] Ambient USB auto-detect found multiple ports: {devices}. Set AMBIENT_USB_PORT.")
        return None

    def stop(self):
        self.running = False
        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None
            self.port_name = None
        self.controller.close()

    def _read_loop(self):
        while self.running:
            try:
                line = self.serial_port.readline()
                if not line:
                    continue
                payload = self._parse_line(line.decode("utf-8", errors="replace").strip())
                if payload is not None:
                    self.controller.on_measurement(**payload)
            except Exception as exc:
                print("[WARN] Ambient USB read failed:", exc)
                time.sleep(1.0)

    def _parse_line(self, line):
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            try:
                return {"lux": float(line)}
            except ValueError:
                print("[WARN] Ambient USB ignored line:", line)
                return None

        if not isinstance(data, dict) or "lux" not in data:
            return None
        return {
            "lux": data.get("lux"),
            "visible": data.get("visible"),
            "ir": data.get("ir"),
            "full": data.get("full"),
            "saturated": data.get("saturated"),
        }

    def _config_float(self, name, default, minimum, maximum):
        try:
            value = float(getattr(config, name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _config_int(self, name, default, minimum, maximum):
        try:
            value = int(getattr(config, name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))


class AmbientSensorControlSource:
    def __init__(self):
        self.controller = AmbientLightController()
        self.reader = UsbSerialAmbientReader(self.controller)

    def start(self):
        if not bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False)):
            return None
        return self.reader.start()

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        config.set("AMBIENT_SOURCE_ENABLED", enabled)
        if enabled:
            return self.reader.start()
        self.stop()
        return True

    def stop(self):
        self.reader.stop()

    def is_running(self):
        return self.reader.running

    def status(self):
        data = self.controller.status()
        data["running"] = self.reader.running
        data["port"] = self.reader.port_name
        return data
