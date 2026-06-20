import os

import yaml


class Config:
    def __init__(self, path="config.yaml"):
        self._path = path
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
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
