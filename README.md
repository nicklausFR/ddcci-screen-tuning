# DDC/CI Screen Tuning

Version 1.0.

Utility for adjusting monitor brightness, contrast, and DDC/CI RGB gains.

## Night Light

The Night Light control is one of the main features of the application. It warms the display by adjusting the monitor RGB gains through DDC/CI instead of applying a Windows color filter. At 0%, it restores the configured neutral RGB gains. At higher values, it moves progressively toward the selected warm target color while keeping perceived brightness as stable as possible.

## Requirements and technical notes

- UI: PySide6 / Qt.
- Monitor control: DDC/CI backend abstraction in `platform_backends/`.
- Implemented backend: Windows DDC/CI through Dxva2 APIs via `ctypes`.
- Current platform support: Windows only.
- Project structure is prepared so Linux or macOS DDC/CI support can be added through another backend.
- Control sources live in `control_sources/`; the tray menu is currently one control source among others that can be added later.

## Build executable

```powershell
pyinstaller main.py --onefile --windowed
```

MIDI control code exists in the repository as experimental work, but it is not wired into the tested v1.0 startup path.

## License

Copyright (C) 2026 nicklausFR.

This project is free software licensed under GPL-3.0-or-later. You may use, study, share, and modify it under the GPL terms. Redistribution of original or modified versions must preserve the copyright and license notices.
