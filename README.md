# DDC/CI Screen Tuning

Daily-use Windows tray utility for tuning monitors manually, according to the
time of day, or automatically from an ambient light sensor.

## Features

- Quick brightness, contrast, combined light, and night-light controls.
- DDC/CI monitor control with an optional Windows gamma-ramp night-light
  backend.
- Manual, daytime, and ambient-light control sources.
- Configurable curves linking ambient lux or daytime position to display
  settings.
- Bluetooth Low Energy (BLE) ambient sensor transport with automatic scanning,
  configuration, heartbeat, and reconnection.
- Sensor diagnostics, live lux graph, and a force-reconnect action in the
  configuration window.
- Automatic Windows light/dark theme and single-instance protection.

## Ambient light sensor over BLE

The ambient source now uses BLE by default instead of a USB serial connection.
It communicates with the sensor through the Nordic UART Service (NUS). The
matching TSL2591 sensor firmware is maintained in
[nicklausFR/ddcci-screen-tuning-tsl2591](https://github.com/nicklausFR/ddcci-screen-tuning-tsl2591).

The application:

- discovers the peripheral by its advertised name or an optional fixed address;
- sends the saved sampling and publishing configuration after connecting;
- waits for the sensor to confirm that configuration before applying readings;
- receives binary lux measurements and maps the 0.1–20,000 lx range to the
  configured display-light curve;
- keeps the connection alive and automatically scans again after a disconnect
  or stale session.

To use the sensor:

1. Enable Bluetooth in Windows and power the BLE sensor.
2. Install the `bleak` dependency.
3. Set the ambient options in `config.yaml`:

   ```yaml
   AMBIENT_SOURCE_ENABLED: true
   AMBIENT_SENSOR_TRANSPORT: ble
   AMBIENT_BLE_NAME: LuxSensor
   AMBIENT_BLE_ADDRESS: '' # Optional; name discovery is used when empty
   AMBIENT_BLE_SCAN_TIMEOUT: 20.0
   AMBIENT_BLE_RECONNECT_SECONDS: 3.0
   ```

4. Start the application and open **Configuration > Light sensor** to tune the
   light curve, smoothing, sensor refresh interval, and publishing mode.

Only one application instance can own the BLE peripheral. If a connection is
stuck, close any other instance and use **Force reconnect**. Packaged builds
also write BLE connection details to `ambient_ble.log` next to the executable.

The previous USB serial reader remains available as a compatibility fallback:

```yaml
AMBIENT_SENSOR_TRANSPORT: usb
```

It requires `pyserial` and uses the existing `AMBIENT_USB_*` settings.

## Other control sources

- **Manual tray:** direct brightness, contrast, combined light, and night-light
  control.
- **Daytime:** automatic control based on sunrise, sunset, and location.
- **Ambient:** automatic display adjustment from the BLE lux sensor.

## Requirements

- Windows with Bluetooth support for the ambient BLE source.
- A recent Python 3 version.
- A DDC/CI-capable monitor for hardware brightness, contrast, and RGB control.
- Python packages:

  ```powershell
  python -m pip install PySide6 PyYAML bleak
  ```

  Install `pyserial` as well only when using the legacy USB transport.

## Run

```powershell
python main.py
```

## Build

```powershell
python -m pip install pyinstaller
pyinstaller main.py --onefile --windowed --name ddcci-screen-tuning
```

Keep `config.yaml` next to the generated executable to override the built-in
defaults.

## License

Copyright (C) 2026 nicklausFR.

GPL-3.0-or-later.
