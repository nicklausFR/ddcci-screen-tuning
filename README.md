# DDC/CI Screen Tuning

Version 1.0.

Utility for adjusting monitor brightness, contrast, and DDC/CI RGB gains.

## Changes since v1.0

- Added a richer tray control panel with monitor selection, presets, Light mode, Night Light controls, and direct access to display settings.
- Added editable Light curves for mapping a single intensity slider to brightness and contrast.
- Added Night Light target color controls with warmth, amber/yellow, tint, preview, and saved target RGB settings.
- Added Daytime source mode with time-based light and color curves, curve templates, and a periodic timer.
- Added separate Tray and Daytime control sources so manual tray values and automatic daytime values can coexist.
- Improved window behavior for tray use: the panel is reopened instead of toggled blindly, settings dialogs stay visible, and the panel is placed on the screen where the cursor is.
- Added resilient startup behavior when DDC/CI reads fail, so the panel can open using cached values instead of blocking.
- Added serialized DDC/CI command handling so brightness, contrast, and Night Light writes do not flood monitors during slider interaction.
- Updated the Windows executable build flow and PyInstaller name.

## Night Light

The Night Light control is one of the main features of the application. It warms the display by adjusting the monitor RGB gains through DDC/CI instead of applying a Windows color filter. At 0%, it restores the configured neutral RGB gains. At higher values, it moves progressively toward the selected warm target color while keeping perceived brightness as stable as possible.

## Requirements and technical notes

- UI: PySide6 / Qt.
- Monitor control: DDC/CI backend abstraction in `platform_backends/`.
- Implemented backend: Windows DDC/CI through Dxva2 APIs via `ctypes`.
- Current platform support: Windows only.
- Project structure is prepared so Linux or macOS DDC/CI support can be added through another backend.
- Control sources live in `control_sources/`; the tray menu is currently one control source among others that can be added later.
- DDC/CI writes are serialized through `ddcci_command_queue.py`. This avoids sending brightness and contrast at the same time and keeps the UI responsive while a monitor processes VCP commands.

## DDC/CI command behavior

Some monitors fail or ignore VCP commands when values are sent continuously during a slider drag. The UI therefore updates slider labels while dragging, then sends the final value when the slider is released. Auto/Light mode writes brightness first, waits for `DDCCI_COMMAND_DELAY`, and then writes contrast.

If a monitor does not expose a VCP value reliably at startup, the panel keeps the last cached value instead of blocking the window. Failed queued writes are warning-rate-limited so repeated monitor errors do not flood the console.

## Build executable

```powershell
pyinstaller main.py --onefile --windowed --name ddcci-screen-tuning
```

MIDI control code exists in the repository as experimental work, but it is not wired into the tested v1.0 startup path.

## License

Copyright (C) 2026 nicklausFR.

This project is free software licensed under GPL-3.0-or-later. You may use, study, share, and modify it under the GPL terms. Redistribution of original or modified versions must preserve the copyright and license notices.
