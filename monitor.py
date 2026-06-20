import math

from platform_backends import load_monitor_backend
from screen_tuning import config


NIGHTLIGHT_WHITE_KELVIN = 6500
DEFAULT_NIGHTLIGHT_TARGET_RGB = (100, 85, 5)
DEFAULT_NIGHTLIGHT_NEUTRAL_RGB = (50, 50, 50)
DEFAULT_READ_CACHE_TTL = 0.15

_BACKEND = None


def _monitor_backend():
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = load_monitor_backend()
    return _BACKEND


class _NightlightColor:
    def __init__(self):
        self.neutral_rgb = self._read_rgb_config(
            "NIGHTLIGHT_NEUTRAL_RGB",
            DEFAULT_NIGHTLIGHT_NEUTRAL_RGB,
        )
        self.target_rgb = self._read_target_rgb()
        self.rgb = self.neutral_rgb
        self.kelvin = None
        self.strength = 0

    def set_rgb(self, r, g, b):
        self.rgb = (int(r), int(g), int(b))
        self.kelvin = None
        self._update_strength()

    def set_current_rgb(self, r, g, b):
        self.rgb = (
            max(0, min(100, int(r))),
            max(0, min(100, int(g))),
            max(0, min(100, int(b))),
        )
        self.kelvin = None
        self._update_strength()

    def set_neutral_rgb(self, r, g, b):
        self.neutral_rgb = (
            max(0, min(100, int(r))),
            max(0, min(100, int(g))),
            max(0, min(100, int(b))),
        )
        if self.strength == 0:
            self.rgb = self.neutral_rgb

    def set_target_rgb(self, r, g, b):
        self.target_rgb = (
            max(0, min(100, int(r))),
            max(0, min(100, int(g))),
            max(0, min(100, int(b))),
        )
        self.rgb = self._strength_to_rgb(self.strength)

    def set_kelvin(self, kelvin):
        self.kelvin = kelvin
        self.rgb = self._kelvin_to_relative_rgb(kelvin, 1.0)
        self._update_strength()

    def _strength_to_rgb(self, strength):
        t = max(0, min(strength, 100)) / 100.0
        neutral_r, neutral_g, neutral_b = self.neutral_rgb
        target_r, target_g, target_b = self.target_rgb

        raw_r = neutral_r + (target_r - neutral_r) * t
        raw_g = neutral_g + (target_g - neutral_g) * t
        raw_b = neutral_b + (target_b - neutral_b) * t

        neutral_luma = self._relative_luma(neutral_r, neutral_g, neutral_b)
        raw_luma = self._relative_luma(raw_r, raw_g, raw_b)
        scale = neutral_luma / raw_luma if raw_luma > 0 else 1.0

        return (
            round(max(0, min(100, raw_r * scale))),
            round(max(0, min(100, raw_g * scale))),
            round(max(0, min(100, raw_b * scale))),
        )

    def set_strength(self, percent):
        self.strength = max(0, min(percent, 100))
        self.rgb = self._strength_to_rgb(self.strength)
        self.kelvin = None

    def _update_strength(self):
        r, g, b = self.rgb

        best_strength = 0
        best_err = float("inf")

        for strength in range(101):
            r_test, g_test, b_test = self._strength_to_rgb(strength)
            err = abs(r - r_test) + abs(g - g_test) + abs(b - b_test)

            if err < best_err:
                best_err = err
                best_strength = strength

        self.strength = best_strength

    @staticmethod
    def _relative_luma(r, g, b):
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @staticmethod
    def _read_rgb_config(name, default):
        value = getattr(config, name, default)
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return default
        return tuple(max(0, min(100, int(channel))) for channel in value)

    @classmethod
    def _read_target_rgb(cls):
        return cls._read_rgb_config("NIGHTLIGHT_TARGET_RGB", DEFAULT_NIGHTLIGHT_TARGET_RGB)

    @classmethod
    def _kelvin_to_relative_rgb(cls, kelvin, strength):
        white = cls._kelvin_to_rgb_gains(NIGHTLIGHT_WHITE_KELVIN)
        warm = cls._kelvin_to_rgb_gains(kelvin)

        relative = []
        for warm_channel, white_channel in zip(warm, white):
            if white_channel <= 0:
                relative.append(0.0)
            else:
                relative.append(min(1.0, warm_channel / white_channel))

        t = max(0.0, min(float(strength), 1.0))
        return tuple((1.0 - t) + t * channel for channel in relative)

    @staticmethod
    def _kelvin_to_rgb_gains(temp_k):
        temp = temp_k / 100.0
        r = g = b = 0

        if temp <= 66:
            r = 255
        else:
            r = 329.698727446 * ((temp - 60) ** -0.1332047592)
            r = max(0, min(r, 255))

        if temp <= 66:
            g = 99.4708025861 * math.log(temp) - 161.1195681661
        else:
            g = 288.1221695283 * ((temp - 60) ** -0.0755148492)
        g += 3
        g = max(0, min(g, 255))

        if temp >= 66:
            b = 255
        elif temp <= 19:
            b = 0
        else:
            b = 138.5177312231 * math.log(temp - 10) - 305.0447927307
        b = max(0, min(b, 255))

        return round(r / 255 * 100), round(g / 255 * 100), round(b / 255 * 100)


class DDCCI_Monitor:
    def __init__(self, index=0, cache_ttl=DEFAULT_READ_CACHE_TTL):
        self._monitor = _monitor_backend().open_monitor(index=index, cache_ttl=cache_ttl)
        self._nightlight_color = _NightlightColor()
        self._sync_nightlight_color()

    def name(self):
        return self._monitor.name()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._monitor.close()

    def get_vcp(self, code, max_attempts=5, delay=0.03, use_cache=True):
        return self._monitor.get_vcp(
            code,
            max_attempts=max_attempts,
            delay=delay,
            use_cache=use_cache,
        )

    def set_vcp(self, code, value, max_attempts=3, delay=0.03):
        self._monitor.set_vcp(
            code,
            value,
            max_attempts=max_attempts,
            delay=delay,
        )

    def get_brightness(self):
        return self._monitor.get_brightness()

    def set_brightness(self, value):
        self._monitor.set_brightness(value)

    def get_contrast(self):
        return self._monitor.get_contrast()

    def set_contrast(self, value):
        self._monitor.set_contrast(value)

    def get_rgb(self):
        return self._monitor.get_rgb()

    def set_rgb(self, r, g, b):
        self._monitor.set_rgb(r, g, b)

    def _sync_nightlight_color(self):
        r, g, b = self.get_rgb()
        self._nightlight_color.set_current_rgb(r, g, b)

    def nightlight_set_strength(self, percent):
        percent = max(0, min(int(percent), 100))
        self._nightlight_color.set_strength(percent)
        self.set_rgb(*self._nightlight_color.rgb)

    def nightlight_set_target_rgb(self, r, g, b, apply_current=True):
        self._nightlight_color.set_target_rgb(r, g, b)
        if apply_current:
            self.nightlight_set_strength(self._nightlight_color.strength)

    def nightlight_get_target_rgb(self):
        return self._nightlight_color.target_rgb

    def nightlight_set_neutral_rgb(self, r, g, b, apply_current=True):
        self._nightlight_color.set_neutral_rgb(r, g, b)
        if apply_current:
            self.nightlight_set_strength(self._nightlight_color.strength)

    def nightlight_get_neutral_rgb(self):
        return self._nightlight_color.neutral_rgb

    def nightlight_get_strength(self):
        r, g, b = self.get_rgb()
        self._nightlight_color.set_current_rgb(r, g, b)
        return self._nightlight_color.strength


def ddc_ci_monitors_list():
    return _monitor_backend().list_monitors()


def _print_monitor_diagnostics():
    monitors = ddc_ci_monitors_list()
    if not monitors:
        print("No DDC/CI monitor detected.")
        return

    print(f"{len(monitors)} DDC/CI monitor(s) detected:")
    for index, name in enumerate(monitors):
        print(f"\n[{index}] {name}")
        try:
            with DDCCI_Monitor(index=index) as monitor:
                print(f"  Brightness : {monitor.get_brightness()}")
                print(f"  Contrast   : {monitor.get_contrast()}")
                print(f"  RGB gains  : {monitor.get_rgb()}")
                print(f"  Nightlight : {monitor.nightlight_get_strength()}%")
        except Exception as exc:
            print(f"  Read error: {exc}")


if __name__ == "__main__":
    _print_monitor_diagnostics()
