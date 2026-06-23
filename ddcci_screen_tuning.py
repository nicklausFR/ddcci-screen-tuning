import os

import yaml


DEFAULT_CONFIG = {
    "SLIDER_DEBOUNCE": 0.1,
    "DDCCI_COMMAND_DELAY": 0.15,
    "BRIGHTNESS_RANGE": [0, 100],
    "CONTRAST_RANGE": [0, 100],
    "NIGHTLIGHT_RANGE": [0, 100],
    "NIGHTLIGHT_NEUTRAL_RGB": [50, 50, 50],
    "NIGHTLIGHT_TARGET_RGB": [100, 13, 0],
    "NIGHTLIGHT_TARGET_COLOR": 100,
    "NIGHTLIGHT_TARGET_AMBER": 0,
    "NIGHTLIGHT_TARGET_TINT": 0,
    "NIGHTLIGHT_COLOR_CURVE_POINTS": [0, 17, 33, 50, 67, 83, 100],
    "LIGHT_MODE": True,
    "LIGHT_CURVE": 0.75,
    "LIGHT_CURVE_POINTS": [0, 34, 55, 68, 78, 88, 100],
    "LIGHT_BRIGHTNESS_CURVE_POINTS": [0, 34, 55, 68, 78, 88, 100],
    "LIGHT_CONTRAST_CURVE_POINTS": [0, 18, 31, 42, 55, 74, 100],
    "LIGHT_BRIGHTNESS_RANGE": [0, 100],
    "LIGHT_CONTRAST_RANGE": [0, 100],
    "DAYTIME_SOURCE_ENABLED": False,
    "DAYTIME_UPDATE_SECONDS": 300,
    "DAYTIME_MIN_LIGHT": 18,
    "DAYTIME_MAX_LIGHT": 88,
    "DAYTIME_LIGHT_CURVE_POINTS": [18, 28, 55, 100, 55, 28, 18],
    "DAYTIME_COLOR_CURVE_POINTS": [70, 50, 18, 0, 18, 50, 70],
    "LAST_BRIGHTNESS": 49,
    "LAST_CONTRAST": 49,
    "LAST_NIGHTLIGHT": 0,
    "LAST_LIGHT": 50,
    "TRAY_BRIGHTNESS": 49,
    "TRAY_CONTRAST": 49,
    "TRAY_NIGHTLIGHT": 0,
    "TRAY_LIGHT": 50,
    "DETAIL_ROWS_VISIBLE": True,
    "SELECTED_MONITOR_INDEX": 0,
}


class Config:
    def __init__(self, path="config.yaml"):
        self._path = path
        data = dict(DEFAULT_CONFIG)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                data.update(loaded)
        self._data = data
        self.__dict__.update(data)

    def set(self, name, value):
        self._data[name] = value
        setattr(self, name, value)
        self._save_value(name, value)

    def _save_value(self, name, value):
        dumped = yaml.safe_dump(
            value,
            allow_unicode=True,
            default_flow_style=True,
            sort_keys=False,
        ).strip()
        if "\n" in dumped:
            dumped = dumped.splitlines()[0]

        line = f"{name}: {dumped}\n"
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

        prefix = f"{name}:"
        for index, current in enumerate(lines):
            if current.lstrip().startswith(prefix):
                indent = current[:len(current) - len(current.lstrip())]
                lines[index] = indent + line
                break
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(line)

        with open(self._path, "w", encoding="utf-8") as f:
            f.writelines(lines)


config = Config()


class PresetManager:
    def __init__(self, filepath="presets.yaml"):
        self.filepath = filepath
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.presets = yaml.safe_load(f) or {}
        else:
            self.presets = {}

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.presets, f, allow_unicode=True, sort_keys=False)

    def get_all_names(self):
        return list(self.presets.keys())

    def get(self, name):
        return self.presets.get(name, {})

    def set(self, name, data):
        self.presets[name] = data
        self.save()

    def delete(self, name):
        if name in self.presets:
            del self.presets[name]
            self.save()

    def exists(self, name):
        return name in self.presets
