import asyncio
import json
import math
import re
import struct
import sys
import threading
import time
from pathlib import Path

from ddcci_command_queue import submit_ddcci_command, submit_light_values
from ddcci_screen_tuning import config
from monitor import DDCCI_Monitor, ddc_ci_monitors_list


class AmbientLightController:
    def __init__(self):
        self.monitor = None
        self.apply_enabled = False
        self._last_applied_light = None
        self._last_light = None
        self._filtered_lux = None
        self._filtered_at = None
        self._last_measurement_at = None
        self._last_raw_lux = None
        self._last_visible = None
        self._last_ir = None
        self._last_full = None
        self._last_saturated = None
        self._last_quality = None
        self._last_range = None
        self._last_brightness = None
        self._last_contrast = None
        self._lock = threading.Lock()

    def on_measurement(self, lux, visible=None, ir=None, full=None, saturated=None, quality=None, range_id=None):
        quality = self._optional_int(quality)
        saturated_value = self._optional_bool(saturated)
        saturated = bool(saturated_value) or bool(quality is not None and quality & 1)
        lux_was_invalid = False
        try:
            lux = max(0.0, float(lux))
        except (TypeError, ValueError):
            if not saturated:
                return
            lux_was_invalid = True
            lux = 10000.0
        if saturated and lux_was_invalid:
            lux = max(lux, 10000.0)

        with self._lock:
            self._last_measurement_at = time.monotonic()
            self._last_raw_lux = lux
            self._last_visible = visible
            self._last_ir = ir
            self._last_full = full
            self._last_saturated = saturated
            self._last_quality = quality
            self._last_range = range_id
            self._filtered_lux = self._smooth_lux(lux)
            light = self._lux_to_light(self._filtered_lux)
            if self._auto_curve_active():
                brightness, contrast = self._light_to_brightness_contrast(light)
            else:
                brightness = light
                contrast = self._last_contrast
            self._last_light = light
            self._last_brightness = brightness
            self._last_contrast = contrast
            if self.apply_enabled and self._should_apply(light):
                self._apply_light(light, brightness, contrast)

    def status(self):
        with self._lock:
            self._settle_filtered_lux()
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
                "quality": self._last_quality,
                "range": self._last_range,
                "age": age,
                "light": self._last_light,
                "brightness": self._last_brightness,
                "contrast": self._last_contrast,
            }

    def recalculate_current(self):
        with self._lock:
            lux = self._filtered_lux if self._filtered_lux is not None else self._last_raw_lux
            if lux is None:
                return False
            self._update_light_from_lux(lux)
            return True

    def force_next_apply(self):
        with self._lock:
            self._last_applied_light = None

    def close(self):
        if self.monitor is not None:
            try:
                self.monitor.close()
            finally:
                self.monitor = None

    def _smooth_lux(self, lux):
        if not bool(getattr(config, "AMBIENT_SMOOTHING_ENABLED", True)):
            self._filtered_at = time.monotonic()
            return lux
        mode = str(getattr(config, "AMBIENT_SMOOTHING_MODE", "steps"))
        if mode == "time":
            now = time.monotonic()
            smoothing_seconds = self._config_float("AMBIENT_SMOOTHING_SECONDS", 2.0, 0.05, 120.0)
            if self._filtered_lux is None or self._filtered_at is None:
                self._filtered_at = now
                return lux
            elapsed = max(0.001, now - self._filtered_at)
            self._filtered_at = now
            alpha = 1.0 - math.exp(-elapsed / smoothing_seconds)
            return self._filtered_lux + (lux - self._filtered_lux) * alpha
        smoothing_steps = self._config_int("AMBIENT_SMOOTHING_STEPS", 4, 1, 100)
        self._filtered_at = time.monotonic()
        if self._filtered_lux is None or smoothing_steps <= 1:
            return lux
        return self._filtered_lux + (lux - self._filtered_lux) / smoothing_steps

    def _settle_filtered_lux(self):
        if self._last_raw_lux is None or self._filtered_lux is None:
            return
        if not bool(getattr(config, "AMBIENT_SMOOTHING_ENABLED", True)):
            if self._filtered_lux != self._last_raw_lux:
                self._filtered_lux = self._last_raw_lux
                self._update_light_from_lux(self._filtered_lux)
            self._filtered_at = time.monotonic()
            return

        now = time.monotonic()
        if self._filtered_at is None:
            self._filtered_at = now
            return
        elapsed = now - self._filtered_at
        if elapsed <= 0:
            return

        previous = self._filtered_lux
        mode = str(getattr(config, "AMBIENT_SMOOTHING_MODE", "steps"))
        if mode == "time":
            smoothing_seconds = self._config_float("AMBIENT_SMOOTHING_SECONDS", 2.0, 0.05, 120.0)
            alpha = 1.0 - math.exp(-elapsed / smoothing_seconds)
            self._filtered_lux += (self._last_raw_lux - self._filtered_lux) * alpha
            self._filtered_at = now
        else:
            refresh_seconds = self._config_float("AMBIENT_SENSOR_REFRESH_MS", 100, 50, 60000) / 1000.0
            smoothing_steps = self._config_int("AMBIENT_SMOOTHING_STEPS", 4, 1, 100)
            if smoothing_steps <= 1:
                self._filtered_lux = self._last_raw_lux
                self._filtered_at = now
            else:
                virtual_steps = max(0.0, elapsed / refresh_seconds)
                alpha = 1.0 - ((smoothing_steps - 1.0) / smoothing_steps) ** virtual_steps
                self._filtered_lux += (self._last_raw_lux - self._filtered_lux) * alpha
                self._filtered_at = now

        if abs(self._filtered_lux - self._last_raw_lux) < 0.001:
            self._filtered_lux = self._last_raw_lux
        if self._filtered_lux != previous:
            self._update_light_from_lux(self._filtered_lux)

    def _update_light_from_lux(self, lux):
        light = self._lux_to_light(lux)
        if self._auto_curve_active():
            brightness, contrast = self._light_to_brightness_contrast(light)
        else:
            brightness = light
            contrast = self._last_contrast
        self._last_light = light
        self._last_brightness = brightness
        self._last_contrast = contrast
        if self.apply_enabled and self._should_apply(light):
            self._apply_light(light, brightness, contrast)

    def _lux_to_light(self, lux):
        min_lux = 0.1
        max_lux = 10000.0

        log_min = math.log10(min_lux)
        log_max = math.log10(max_lux)
        position = (math.log10(max(min_lux, min(lux, max_lux))) - log_min) / (log_max - log_min)
        normalized = 100 * position
        points = self._curve_points(
            "AMBIENT_LIGHT_CURVE_POINTS",
            [0, 17, 33, 50, 67, 83, 100],
        )
        return round(self._curve_value(points, normalized))

    def _should_apply(self, light):
        threshold = self._config_int("AMBIENT_APPLY_THRESHOLD", 2, 0, 100)
        if self._last_applied_light is None:
            return True
        return abs(light - self._last_applied_light) >= threshold

    def _apply_light(self, light, brightness=None, contrast=None):
        monitor = self._monitor()
        auto_curve_active = self._auto_curve_active()
        if auto_curve_active and (brightness is None or contrast is None):
            brightness, contrast = self._light_to_brightness_contrast(light)
        if auto_curve_active:
            submit_light_values(monitor, brightness, contrast, "Ambient sensor light")
        else:
            brightness = max(0, min(100, round(light)))
            submit_ddcci_command(
                "brightness",
                "Ambient sensor brightness",
                lambda monitor=monitor, brightness=brightness: monitor.set_brightness(brightness),
            )
            contrast = self._last_contrast
        self._last_applied_light = light
        config.set("LAST_LIGHT", light)
        config.set("LAST_BRIGHTNESS", brightness)
        if contrast is not None:
            config.set("LAST_CONTRAST", contrast)

    def _auto_curve_active(self):
        return bool(getattr(config, "LIGHT_MODE", False)) and not bool(getattr(config, "DETAIL_ROWS_VISIBLE", True))

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

    def _optional_int(self, value):
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _optional_bool(self, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on", "sat", "saturated", "overflow"):
            return True
        if text in ("0", "false", "no", "n", "off", "ok", "valid", "none"):
            return False
        return None


class UsbSerialAmbientReader:
    def __init__(self, controller):
        self.controller = controller
        self.running = False
        self.available = False
        self.last_error = None
        self.on_unavailable = None
        self.thread = None
        self.serial_port = None
        self.port_name = None
        self._last_request_at = 0.0
        self._last_config = None
        self._last_config_at = None
        self._last_config_cmd = None
        self._last_config_error = None
        self._write_lock = threading.Lock()

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
            self.available = False
            self.last_error = str(exc)
            print(f"[WARN] Ambient USB source failed to open {port}:", exc)
            return False

        self.available = True
        self.last_error = None
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        self.apply_saved_config()
        self.request_measurement(force=True)
        print(f"Ambient USB source connected on {port}.")
        return True

    def is_port_available(self):
        try:
            import serial
        except ImportError:
            return False

        port = str(getattr(config, "AMBIENT_USB_PORT", "") or "").strip()
        if not port:
            return self._auto_detect_port(serial, verbose=False) is not None

        try:
            try:
                ports = list(serial.tools.list_ports.comports())
            except AttributeError:
                from serial.tools import list_ports
                ports = list(list_ports.comports())
        except Exception:
            return True

        return any(str(getattr(item, "device", "")).lower() == port.lower() for item in ports)

    def _auto_detect_port(self, serial_module, verbose=True):
        if not bool(getattr(config, "AMBIENT_USB_AUTO_DETECT", True)):
            if verbose:
                print("[WARN] Ambient USB source enabled but AMBIENT_USB_PORT is empty.")
            return None

        try:
            ports = list(serial_module.tools.list_ports.comports())
        except AttributeError:
            try:
                from serial.tools import list_ports
                ports = list(list_ports.comports())
            except Exception as exc:
                if verbose:
                    print("[WARN] Ambient USB auto-detect failed:", exc)
                return None

        if not ports:
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
            if verbose:
                print(f"Ambient USB auto-detected {device}.")
            return device

        if len(matches) > 1:
            devices = ", ".join(port.device for port in matches)
            if verbose:
                print(f"[WARN] Ambient USB auto-detect matched multiple ports: {devices}. Set AMBIENT_USB_PORT.")
            return None

        if len(ports) == 1:
            device = ports[0].device
            if verbose:
                print(f"Ambient USB auto-detected the only serial port: {device}.")
            return device

        devices = ", ".join(port.device for port in ports)
        if verbose:
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

    def mark_unavailable(self, exc):
        if not self.running and self.serial_port is None:
            return
        self.last_error = str(exc)
        self.available = False
        self.stop()
        if self.on_unavailable is not None:
            try:
                self.on_unavailable(exc)
            except Exception as callback_exc:
                print("[WARN] Ambient USB unavailable callback failed:", callback_exc)

    def request_measurement(self, force=False):
        if self.serial_port is None:
            return False
        now = time.monotonic()
        if not force and now - self._last_request_at < 1.0:
            return False
        try:
            self._write_json({"cmd": "get"})
            self._last_request_at = now
            return True
        except Exception as exc:
            print("[WARN] Ambient USB request failed:", exc)
            return False

    def request_config(self):
        try:
            return self._write_json({"cmd": "config.get"})
        except Exception as exc:
            print("[WARN] Ambient USB config request failed:", exc)
            return False

    def apply_config(self, values):
        payload = {"cmd": "config.set"}
        payload.update(values)
        try:
            return self._write_json(payload)
        except Exception as exc:
            print("[WARN] Ambient USB config set failed:", exc)
            return False

    def reset_config(self):
        try:
            return self._write_json({"cmd": "config.reset"})
        except Exception as exc:
            print("[WARN] Ambient USB config reset failed:", exc)
            return False

    def apply_saved_config(self):
        values = {
            "refreshMs": self._config_int("AMBIENT_SENSOR_REFRESH_MS", 100, 50, 60000),
            "publishLuxChangePercent": self._config_float("AMBIENT_SENSOR_PUBLISH_LUX_CHANGE_PERCENT", 1.0, 0.0, 100.0),
            "publishMaxIntervalSeconds": self._config_int("AMBIENT_SENSOR_PUBLISH_MAX_INTERVAL_SECONDS", 30, 1, 86400),
            "publishMode": self._config_publish_mode("AMBIENT_SENSOR_PUBLISH_MODE", "auto"),
        }
        return self.apply_config(values)

    def _write_json(self, payload):
        if self.serial_port is None:
            return False
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._write_lock:
            self.serial_port.write(line)
            self.serial_port.flush()
        return True

    def _read_loop(self):
        while self.running:
            try:
                line = self.serial_port.readline()
            except Exception as exc:
                print("[WARN] Ambient USB read failed:", exc)
                self.mark_unavailable(exc)
                break
            if not line:
                continue
            try:
                payload = self._parse_line(line.decode("utf-8", errors="replace").strip())
                if payload is not None:
                    self.controller.on_measurement(**payload)
            except Exception as exc:
                print("[WARN] Ambient USB line ignored:", exc)

    def _parse_line(self, line):
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            cleaned_line = re.sub(
                r"(:\s*)([-+]?inf(?:inity)?|nan)(?=\s*[,}])",
                r"\1null",
                line,
                flags=re.IGNORECASE,
            )
            if cleaned_line != line:
                try:
                    return self._payload_from_json_data(json.loads(cleaned_line))
                except json.JSONDecodeError:
                    pass
            try:
                return {"lux": float(line)}
            except ValueError:
                payload = self._parse_key_value_line(line) or self._parse_csv_line(line)
                if payload is None:
                    print("[WARN] Ambient USB ignored line:", line)
                return payload

        return self._payload_from_json_data(data)

    def _payload_from_json_data(self, data):
        if isinstance(data, (int, float)):
            return {"lux": float(data)}
        if isinstance(data, str):
            try:
                return {"lux": float(data)}
            except ValueError:
                return None
        if isinstance(data, (list, tuple)):
            return self._payload_from_sequence(data)
        if not isinstance(data, dict):
            return None

        if self._handle_response(data):
            return None
        data = self._flatten_measurement_dict(data)
        return self._payload_from_dict(data)

    def _handle_response(self, data):
        if data.get("type") != "response":
            return False
        cmd = data.get("cmd")
        if data.get("ok") is False:
            self._last_config_error = data.get("error") or "command_failed"
            return True
        if cmd in ("config.get", "config.set", "config.reset") and isinstance(data.get("config"), dict):
            self._last_config = dict(data["config"])
            self._last_config_at = time.monotonic()
            self._last_config_cmd = cmd
            self._last_config_error = None
            self._sync_runtime_config(self._last_config)
        return True

    def _sync_runtime_config(self, runtime_config):
        mapping = {
            "refreshMs": "AMBIENT_SENSOR_REFRESH_MS",
            "publishLuxChangePercent": "AMBIENT_SENSOR_PUBLISH_LUX_CHANGE_PERCENT",
            "publishMaxIntervalSeconds": "AMBIENT_SENSOR_PUBLISH_MAX_INTERVAL_SECONDS",
            "publishMode": "AMBIENT_SENSOR_PUBLISH_MODE",
        }
        for source, target in mapping.items():
            if source in runtime_config:
                config._data[target] = runtime_config[source]
                setattr(config, target, runtime_config[source])

    def _flatten_measurement_dict(self, data):
        for name in ("ambient", "als", "light", "sensor", "tsl", "tsl2591", "measurement", "m"):
            nested = data.get(name)
            if isinstance(nested, dict):
                merged = dict(data)
                merged.pop(name, None)
                merged.update(nested)
                return merged
        return data

    def _payload_from_dict(self, data):
        if not isinstance(data, dict):
            return None

        def first(*names):
            for name in names:
                if name in data:
                    return data.get(name)
            return None

        lux = first("lux", "lx", "l", "illuminance", "illum", "ambient_lux")
        if lux is None:
            lux_x100 = first("lux_x100", "lx100", "l100")
            if lux_x100 is not None:
                try:
                    lux = float(lux_x100) / 100.0
                except (TypeError, ValueError):
                    lux = None
        quality = first("q", "quality", "status", "flags", "flag")
        if quality is None:
            quality = self._quality_from_flags(data)
        saturated = first("saturated", "sat", "overflow", "ovf", "clipped", "adcOverRange", "adc_over_range")
        if saturated is None and quality is not None:
            try:
                saturated = bool(int(quality) & 1)
            except (TypeError, ValueError):
                saturated = False

        if lux is None and not saturated:
            return None

        return {
            "lux": lux,
            "visible": first("visible", "vis", "v", "raw_visible", "ch_visible"),
            "ir": first("ir", "i", "ch1", "raw_ir", "infrared"),
            "full": first("full", "f", "ch0", "raw_full", "clear", "broadband"),
            "saturated": saturated,
            "quality": quality,
            "range_id": first("r", "range", "range_id", "gain", "g", "cal", "calibration", "profile"),
        }

    def _quality_from_flags(self, data):
        quality = 0
        for bit, names in (
            (0, ("saturated", "sat", "overflow", "ovf", "clipped", "adcOverRange", "adc_over_range")),
            (1, ("spectral", "spectralOverload", "spectral_overload")),
            (2, ("held", "hold")),
            (3, ("estimated", "estimate", "estimatedLux")),
        ):
            if any(self._optional_bool(data.get(name)) for name in names if name in data):
                quality |= 1 << bit
        return quality if quality else None

    def _payload_from_sequence(self, values):
        if not values:
            return None
        if len(values) == 1:
            return {"lux": values[0]}
        if len(values) == 2:
            return {"lux": values[0], "quality": values[1]}
        if len(values) == 3:
            return {"lux": values[0], "quality": values[1], "range_id": values[2]}
        return {
            "lux": values[0],
            "visible": values[1],
            "ir": values[2],
            "full": values[3],
            "quality": values[4] if len(values) > 4 else None,
            "range_id": values[5] if len(values) > 5 else None,
        }

    def _parse_key_value_line(self, line):
        tokens = line.replace(",", " ").replace(";", " ").split()
        data = {}
        for token in tokens:
            if "=" in token:
                key, value = token.split("=", 1)
            elif ":" in token:
                key, value = token.split(":", 1)
            else:
                continue
            key = key.strip().lower()
            value = value.strip()
            if key:
                data[key] = value
        if not data:
            return None
        return self._payload_from_dict(data)

    def _parse_csv_line(self, line):
        if "," not in line and ";" not in line:
            return None
        separator = "," if "," in line else ";"
        parts = [part.strip() for part in line.split(separator)]
        try:
            values = [float(part) for part in parts if part]
        except ValueError:
            return None
        return self._payload_from_sequence(values)

    def _optional_bool(self, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on", "sat", "saturated", "overflow"):
            return True
        if text in ("0", "false", "no", "n", "off", "ok", "valid", "none", "null"):
            return False
        return None

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

    def _config_publish_mode(self, name, default):
        value = str(getattr(config, name, default))
        return value if value in ("auto", "interval") else default


class BleNusAmbientReader(UsbSerialAmbientReader):
    """Ambient sensor transport over Nordic UART Service."""

    NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    MEASUREMENT_PACKET = struct.Struct("<2sBBfHHHB")
    GAIN_NAMES = ("low", "med", "high", "max")

    def __init__(self, controller):
        super().__init__(controller)
        self.client = None
        self.event_loop = None
        self._ble_task = None
        self._ble_write_lock = None
        self._rx_buffer = bytearray()
        self._logged_first_measurement = False

    def _log(self, message):
        print(message)
        if not getattr(sys, "frozen", False):
            return
        try:
            log_path = Path(sys.executable).resolve().parent / "ambient_ble.log"
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{timestamp} {message}\n")
        except Exception:
            pass

    def start(self):
        if self.running:
            return True
        try:
            import bleak  # noqa: F401
        except ImportError as exc:
            self.last_error = f"bleak import failed: {exc}"
            self._log(f"[WARN] Ambient BLE source requires bleak: {exc}")
            return False

        self.running = True
        self.available = False
        self.last_error = None
        self._rx_buffer.clear()
        self._logged_first_measurement = False
        self.port_name = str(
            getattr(config, "AMBIENT_BLE_NAME", "LuxSensor") or "LuxSensor"
        ).strip()
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()
        self._log(f"Ambient BLE source is looking for {self.port_name!r}.")
        return True

    def is_port_available(self):
        try:
            import bleak  # noqa: F401
        except ImportError as exc:
            self.last_error = f"bleak import failed: {exc}"
            self._log(f"[WARN] Ambient BLE availability check failed: {exc}")
            return False
        return True

    def stop(self):
        was_active = self.running or self.available or self.client is not None
        if was_active:
            self._log("Ambient BLE source is stopping.")
        self.running = False
        loop = self.event_loop
        client = self.client
        ble_task = self._ble_task
        if loop is not None and client is not None and client.is_connected:
            try:
                disconnect = asyncio.run_coroutine_threadsafe(
                    client.disconnect(), loop
                )
                disconnect.result(timeout=5.0)
            except Exception as exc:
                self._log(
                    f"[WARN] Ambient BLE graceful disconnect failed: {exc}"
                )
        # A client is only published after BleakClient.connect() completes.
        # Cancelling the owning task is therefore essential when shutdown
        # happens during scanning, GATT connection, or service discovery.
        if loop is not None and ble_task is not None and not ble_task.done():
            try:
                loop.call_soon_threadsafe(ble_task.cancel)
            except RuntimeError:
                pass
        thread = self.thread
        if (
            thread is not None
            and thread is not threading.current_thread()
            and thread.is_alive()
        ):
            thread.join(timeout=8.0)
            if thread.is_alive():
                self._log(
                    "[WARN] Ambient BLE worker did not stop before shutdown."
                )
        self.thread = None
        self.client = None
        self.available = False
        self.port_name = None
        self.controller.close()
        if was_active:
            self._log("Ambient BLE source stopped.")

    def request_measurement(self, force=False):
        if not self.available:
            return False
        now = time.monotonic()
        if not force and now - self._last_request_at < 1.0:
            return False
        if self._write_json({"cmd": "get"}):
            self._last_request_at = now
            return True
        return False

    def _write_json(self, payload):
        loop = self.event_loop
        client = self.client
        if (
            loop is None
            or client is None
            or not client.is_connected
            or not self.running
        ):
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                self._write_json_async(payload), loop
            )
            return True
        except Exception:
            return False

    async def _write_json_async(self, payload):
        write_lock = self._ble_write_lock
        if write_lock is None:
            return False
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        async with write_lock:
            client = self.client
            if client is None or not client.is_connected:
                return False
            characteristic = client.services.get_characteristic(
                self.NUS_RX_UUID
            )
            chunk_size = max(
                20,
                characteristic.max_write_without_response_size,
            )
            for offset in range(0, len(line), chunk_size):
                await client.write_gatt_char(
                    self.NUS_RX_UUID,
                    line[offset : offset + chunk_size],
                    response=False,
                )
                if offset + chunk_size < len(line):
                    await asyncio.sleep(0.1)
        return True

    def _saved_config_values(self):
        return {
            "cmd": "config.set",
            "refreshMs": self._config_int(
                "AMBIENT_SENSOR_REFRESH_MS", 100, 50, 60000
            ),
            "publishLuxChangePercent": self._config_float(
                "AMBIENT_SENSOR_PUBLISH_LUX_CHANGE_PERCENT",
                1.0,
                0.0,
                100.0,
            ),
            "publishMaxIntervalSeconds": self._config_int(
                "AMBIENT_SENSOR_PUBLISH_MAX_INTERVAL_SECONDS",
                30,
                1,
                86400,
            ),
            "publishMode": self._config_publish_mode(
                "AMBIENT_SENSOR_PUBLISH_MODE", "auto"
            ),
        }

    def _thread_main(self):
        try:
            asyncio.run(self._run_ble())
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"[WARN] Ambient BLE worker stopped: {exc}")
        finally:
            self.event_loop = None
            self._ble_task = None
            self._ble_write_lock = None
            self.client = None
            self.available = False
            if self.running:
                self.running = False
                if self.on_unavailable is not None:
                    try:
                        self.on_unavailable(RuntimeError(self.last_error or "BLE stopped"))
                    except Exception as callback_exc:
                        self._log(
                            f"[WARN] Ambient BLE unavailable callback failed: "
                            f"{callback_exc}"
                        )

    async def _run_ble(self):
        self.event_loop = asyncio.get_running_loop()
        self._ble_task = asyncio.current_task()
        self._ble_write_lock = asyncio.Lock()
        reconnect_seconds = self._config_float(
            "AMBIENT_BLE_RECONNECT_SECONDS", 3.0, 0.5, 60.0
        )
        while self.running:
            try:
                client, device, disconnected = await self._connect_once()
                self.client = client
                await client.start_notify(self.NUS_TX_UUID, self._on_notification)
                self.last_error = None
                self.port_name = device.address
                await self._write_json_async({"cmd": "get"})
                await self._write_json_async(self._saved_config_values())
                self.available = True
                self._log(
                    f"Ambient BLE source connected to "
                    f"{device.name or device.address} ({device.address})."
                )
                next_heartbeat = asyncio.get_running_loop().time() + 30.0

                while (
                    self.running
                    and client.is_connected
                    and not disconnected.is_set()
                ):
                    await asyncio.sleep(0.25)
                    now = asyncio.get_running_loop().time()
                    if now >= next_heartbeat:
                        await self._write_json_async({"cmd": "ping"})
                        next_heartbeat = now + 30.0
            except Exception as exc:
                detail = str(exc).strip() or type(exc).__name__
                self.last_error = detail
                self._log(
                    f"[WARN] Ambient BLE connection failed "
                    f"({type(exc).__name__}): {detail}"
                )
            finally:
                self.available = False
                client = self.client
                self.client = None
                if client is not None and client.is_connected:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

            if self.running:
                await asyncio.sleep(reconnect_seconds)

    async def _connect_once(self):
        from bleak import BleakClient, BleakScanner

        loop = asyncio.get_running_loop()
        disconnected = asyncio.Event()
        wanted_name = str(
            getattr(config, "AMBIENT_BLE_NAME", "LuxSensor") or "LuxSensor"
        ).strip()
        wanted_address = str(
            getattr(config, "AMBIENT_BLE_ADDRESS", "") or ""
        ).strip().lower()

        def matches_device(device, advertisement_data):
            advertised_name = advertisement_data.local_name or device.name or ""
            name_matches = advertised_name == wanted_name
            address_matches = (
                bool(wanted_address)
                and str(device.address).strip().lower() == wanted_address
            )
            return name_matches or address_matches

        def on_disconnect(_client):
            loop.call_soon_threadsafe(disconnected.set)

        timeout = self._config_float(
            "AMBIENT_BLE_SCAN_TIMEOUT", 20.0, 2.0, 120.0
        )
        client = None
        try:
            device = await BleakScanner.find_device_by_filter(
                matches_device,
                timeout=timeout,
            )
            if device is None:
                raise RuntimeError(
                    f"{wanted_name!r} introuvable après {timeout:g} s; "
                    "il est peut-être déjà connecté à une autre instance."
                )
            client = BleakClient(
                device,
                disconnected_callback=on_disconnect,
                timeout=30.0,
                winrt={
                    "address_type": "random",
                    "use_cached_services": True,
                },
            )
            try:
                await client.connect()
            except TimeoutError as exc:
                raise RuntimeError(
                    f"délai dépassé pendant la connexion Windows à "
                    f"{wanted_name!r}"
                ) from exc
            return client, device, disconnected
        except BaseException:
            if client is not None and client.is_connected:
                await client.disconnect()
            raise

    def _on_notification(self, _sender, data):
        if (
            len(data) == self.MEASUREMENT_PACKET.size
            and data[:2] == b"LT"
        ):
            (
                _magic,
                version,
                quality,
                lux,
                visible,
                infrared,
                full,
                gain_index,
            ) = self.MEASUREMENT_PACKET.unpack(data)
            if version != 1:
                self._log(
                    f"[WARN] Ambient BLE measurement version "
                    f"{version} is unsupported."
                )
                return
            if not self._logged_first_measurement:
                self._logged_first_measurement = True
                self._log(
                    f"Ambient BLE first measurement received: "
                    f"lux={lux:.3f}, visible={visible}, quality=0x{quality:02x}."
                )
            self.controller.on_measurement(
                lux=None if math.isnan(lux) else lux,
                visible=visible,
                ir=infrared,
                full=full,
                saturated=bool(quality & 1),
                quality=quality,
                range_id=(
                    self.GAIN_NAMES[gain_index]
                    if gain_index < len(self.GAIN_NAMES)
                    else gain_index
                ),
            )
            return

        self._rx_buffer.extend(data)
        while b"\n" in self._rx_buffer:
            raw_line, _, remainder = self._rx_buffer.partition(b"\n")
            self._rx_buffer = bytearray(remainder)
            line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = self._parse_line(line)
                if payload is not None:
                    self.controller.on_measurement(**payload)
            except Exception as exc:
                self._log(f"[WARN] Ambient BLE line ignored: {exc}")


class AmbientSensorControlSource:
    def __init__(self):
        self.controller = AmbientLightController()
        transport = str(
            getattr(config, "AMBIENT_SENSOR_TRANSPORT", "ble") or "ble"
        ).strip().lower()
        if transport == "usb":
            self.reader = UsbSerialAmbientReader(self.controller)
        else:
            self.reader = BleNusAmbientReader(self.controller)

    def set_unavailable_callback(self, callback):
        self.reader.on_unavailable = callback

    def start(self):
        if not bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False)):
            return None
        self.controller.apply_enabled = True
        return self.reader.start()

    def start_passive(self):
        self.controller.apply_enabled = bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False))
        return self.reader.start()

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        config.set("AMBIENT_SOURCE_ENABLED", enabled)
        self.controller.apply_enabled = enabled
        if enabled:
            self.controller.force_next_apply()
            return self.reader.start()
        self.controller.close()
        return True

    def stop(self):
        self.controller.apply_enabled = False
        self.reader.stop()

    def request_measurement(self, force=False):
        if not self.reader.running:
            if bool(getattr(config, "AMBIENT_SOURCE_ENABLED", False)):
                return self.start()
            return self.start_passive()
        return self.reader.request_measurement(force=force)

    def request_sensor_config(self):
        if not self.reader.running:
            if not self.start_passive():
                return False
        return self.reader.request_config()

    def apply_sensor_config(self, values):
        if not self.reader.running:
            if not self.start_passive():
                return False
        return self.reader.apply_config(values)

    def reset_sensor_config(self):
        if not self.reader.running:
            if not self.start_passive():
                return False
        return self.reader.reset_config()

    def is_running(self):
        return self.reader.running

    def recalculate_current(self):
        return self.controller.recalculate_current()

    def is_available(self):
        if self.reader.running or self.reader.available:
            return True
        if self.reader.last_error:
            return False
        return self.reader.is_port_available()

    def status(self):
        data = self.controller.status()
        data["running"] = self.reader.running
        data["port"] = self.reader.port_name
        data["available"] = self.reader.available or self.reader.running
        data["error"] = self.reader.last_error
        data["sensor_config"] = self.reader._last_config
        data["sensor_config_age"] = None if self.reader._last_config_at is None else time.monotonic() - self.reader._last_config_at
        data["sensor_config_received_at"] = self.reader._last_config_at
        data["sensor_config_error"] = self.reader._last_config_error
        return data
