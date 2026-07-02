import mido
import threading
import time
from monitor import DDCCI_Monitor
from ddcci_screen_tuning import config
from midi_qt_signals import bus

class MidiController:
    def __init__(self, monitor):
        self.monitor = monitor
        self.port_prefix = config.MidiDeviceName
        self.cc_number = config.MidiCCNumber
        self.inport = None
        self.outport = None
        self.running = True
        self.midi_thread = None
        self.port_watcher_thread = threading.Thread(target=self._watch_ports, daemon=True)

        self.midi_debounce = float(getattr(config, "MIDI_DEBOUNCE", 0.1))
        self.debounce_timers = {}
        self.last_values = {"brightness": None, "contrast": None, "nightlight": None}

    def run(self):
        print("MIDI controller initialized.")
        self.port_watcher_thread.start()

    def _watch_ports(self):
        last_in, last_out = None, None
        while self.running:
            try:
                in_ports = [p for p in mido.get_input_names()
                            if self.port_prefix.lower() in p.lower() and "loopback" not in p.lower()]
                current_in = in_ports[0] if in_ports else None

                current_out = None
                if getattr(config, "LOOPBACK", False):
                    out_ports = [p for p in mido.get_output_names()
                                 if self.port_prefix.lower() in p.lower() and "loopback" in p.lower()]
                    current_out = out_ports[0] if out_ports else None

                if current_in != last_in:
                    if self.inport:
                        print(f"MIDI IN disconnected: {self.inport.name}")
                        self.inport.close()
                        self.inport = None
                    if current_in:
                        try:
                            self.inport = mido.open_input(current_in)
                            print(f"MIDI IN connected: {current_in}")
                            if not self.midi_thread or not self.midi_thread.is_alive():
                                self.midi_thread = threading.Thread(target=self._midi_loop, daemon=True)
                                self.midi_thread.start()
                        except Exception as e:
                            print(f"MIDI IN open error: {e}")
                    last_in = current_in

                if getattr(config, "LOOPBACK", False):
                    if current_in and current_out and current_out != last_out:
                        if self.outport:
                            print(f"🔌 Fermeture LoopBack : {self.outport.name}")
                            self.outport.close()
                        try:
                            self.outport = mido.open_output(current_out)
                            print(f"LoopBack enabled: {current_out}")
                        except Exception as e:
                            print(f"MIDI OUT open error: {e}")
                        last_out = current_out
                    elif (not current_in or not current_out) and self.outport:
                        print("LoopBack disabled")
                        self.outport.close()
                        self.outport = None
                        last_out = None

            except Exception as e:
                print(f"[WATCH_PORTS] Error: {e}")
            time.sleep(getattr(config, "PORT_WATCH_INTERVAL", 1.0))

    def _midi_loop(self):
        while self.running:
            try:
                if not self.inport:
                    time.sleep(0.1)
                    continue
                msg = self.inport.poll()
                if msg is None:
                    time.sleep(0.01)
                    continue

                if msg.type == 'control_change' and msg.control == self.cc_number:
                    value = self._scale_value(msg.value)
                    self._handle_control(msg.channel, value)
                    if getattr(config, "LOOPBACK", False) and self.outport and msg.channel in config.MidiRedirectPorts:
                        self.outport.send(msg)

            except Exception as e:
                print(f"[MIDI_LOOP] Error: {e}")
                time.sleep(0.1)

    def _scale_value(self, raw):
        raw = max(0, min(127, raw))
        return int((raw / 127) * 100)

    def _auto_curve_active(self):
        return bool(getattr(config, "LIGHT_MODE", False)) and not bool(getattr(config, "DETAIL_ROWS_VISIBLE", True))

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

    def _handle_control(self, channel, value):
        mapping = {
            config.MidiBrightnessChannel: ("brightness", self.monitor.set_brightness),
            config.MidiContrastChannel: ("contrast", self.monitor.set_contrast),
            config.MidiNightlightIntensity: ("nightlight", self.monitor.nightlight_set_strength)
        }

        if channel in mapping:
            key, action = mapping[channel]
            self.last_values[key] = value

            def apply():
                try:
                    emit_key = key
                    if key == "brightness" and self._auto_curve_active():
                        brightness, contrast = self._light_to_brightness_contrast(value)
                        self.monitor.set_light_values(brightness, contrast)
                        emit_key = "light"
                    else:
                        action(value)
                    bus.midi_update.emit(emit_key, value)
                except Exception as e:
                    print(f"[MIDI_ACTION] Channel {channel} error: {e}")

            if key in self.debounce_timers and self.debounce_timers[key]:
                self.debounce_timers[key].cancel()

            timer = threading.Timer(self.midi_debounce, apply)
            timer.daemon = True
            self.debounce_timers[key] = timer
            timer.start()

    def quit(self):
        self.running = False
        if self.inport:
            self.inport.close()
        if self.outport:
            self.outport.close()
        print("MIDI controller stopped cleanly.")
