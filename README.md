# DDC/CI Screen Tuning

Daily-use utility for display tuning from the Windows tray.

The project started as a small Windows tray tool for DDC/CI monitor control, and is evolving toward multiple control sources, different controllers, and different display backends.

## Features

- Tray panel for quick brightness, contrast, and night light control.
- Single auto light slider that can drive brightness and contrast together.
- Fine night light color configuration.
- Windows gamma ramp backend for software night light when DDC/CI RGB is not suitable.
- Source-based control model.

## Control Sources

Current and planned control sources are handled as separate modules:

- Manual tray control.
- Daytime control based on sunrise, sunset, and location.
- Ambient light sensor control, with firmware in [nicklausFR/ddcci-screen-tuning-tsl2591](https://github.com/nicklausFR/ddcci-screen-tuning-tsl2591).
- Extensible path for other controllers later.

## Display Control

Current implementation focuses on Windows and DDC/CI:

- Brightness.
- Contrast.
- Monitor RGB gains for night light.
- Optional Windows gamma ramp night light.

The codebase is structured so other platforms or monitor backends can be added later.

## Requirements

- Windows.
- Python.
- PySide6.
- A DDC/CI-capable monitor for hardware brightness/contrast/RGB control.

## Build

```powershell
pyinstaller main.py --onefile --windowed --name ddcci-screen-tuning
```

## License

Copyright (C) 2026 nicklausFR.

GPL-3.0-or-later.
