import math
import unittest
from unittest.mock import Mock, patch

from control_sources.ambient_sensor import (
    AmbientLightController,
    AmbientSensorControlSource,
    BleNusAmbientReader,
    UsbSerialAmbientReader,
)


class AmbientLightControllerMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.controller = AmbientLightController()

    def test_rejects_positive_infinity_without_saturation(self):
        accepted = self.controller.on_measurement(
            math.inf,
            visible=0,
            ir=42,
            full=0,
            quality=0x04,
        )

        self.assertFalse(accepted)
        self.assertIsNone(self.controller.status()["lux"])

    def test_accepts_zero_as_a_real_dark_measurement(self):
        accepted = self.controller.on_measurement(
            0.0,
            visible=0,
            ir=0,
            full=0,
            quality=0,
        )

        self.assertTrue(accepted)
        self.assertEqual(self.controller.status()["lux"], 0.0)

    def test_invalid_saturated_measurement_maps_to_sensor_maximum(self):
        accepted = self.controller.on_measurement(
            math.nan,
            visible=0,
            ir=65535,
            full=65535,
            quality=0x01,
        )

        self.assertTrue(accepted)
        self.assertEqual(self.controller.status()["lux"], 20000.0)

    def test_enabling_sensor_reapplies_cached_measurement(self):
        source = AmbientSensorControlSource.__new__(AmbientSensorControlSource)
        source.controller = Mock()
        source.reader = Mock()
        source.reader.start.return_value = True

        class FakeConfig:
            def set(self, _name, _value):
                pass

        with patch("control_sources.ambient_sensor.config", FakeConfig()):
            self.assertTrue(source.set_enabled(True))

        source.controller.force_next_apply.assert_called_once_with()
        source.controller.recalculate_current.assert_called_once_with()
        source.reader.start.assert_called_once_with()


class BleDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_exposes_connection_event_history(self):
        reader = BleNusAmbientReader(AmbientLightController())
        reader._record_diagnostic("scanning", "Searching for LuxSensor")

        diagnostics = reader.diagnostics()

        self.assertEqual(diagnostics["state"], "scanning")
        self.assertEqual(diagnostics["events"][-1]["detail"], "Searching for LuxSensor")


class AutomaticTransportTests(unittest.TestCase):
    class AutoConfig:
        AMBIENT_SENSOR_TRANSPORT = "auto"

    def test_auto_uses_ble_when_usb_is_absent(self):
        with (
            patch("control_sources.ambient_sensor.config", self.AutoConfig()),
            patch.object(UsbSerialAmbientReader, "is_port_available", return_value=False),
        ):
            source = AmbientSensorControlSource()

        self.assertIs(type(source.reader), BleNusAmbientReader)

    def test_auto_switches_from_usb_to_ble_after_unplug(self):
        with (
            patch("control_sources.ambient_sensor.config", self.AutoConfig()),
            patch.object(UsbSerialAmbientReader, "is_port_available", return_value=True),
        ):
            source = AmbientSensorControlSource()
        self.assertIs(type(source.reader), UsbSerialAmbientReader)

        with (
            patch("control_sources.ambient_sensor.config", self.AutoConfig()),
            patch.object(UsbSerialAmbientReader, "is_port_available", return_value=False),
        ):
            source._ensure_preferred_reader()

        self.assertIs(type(source.reader), BleNusAmbientReader)

    def test_auto_keeps_sensor_available_during_handover_grace(self):
        callback = Mock()
        with (
            patch("control_sources.ambient_sensor.config", self.AutoConfig()),
            patch.object(UsbSerialAmbientReader, "is_port_available", return_value=True),
        ):
            source = AmbientSensorControlSource()
            source.set_unavailable_callback(callback)
            source._reader_unavailable(PermissionError("USB unplugged"))

            self.assertTrue(source.is_handover_pending())
            self.assertTrue(source.is_available())
            callback.assert_called_once()

    def test_auto_proactively_switches_from_ble_to_new_usb_port(self):
        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        with (
            patch("control_sources.ambient_sensor.config", self.AutoConfig()),
            patch.object(UsbSerialAmbientReader, "is_port_available", return_value=False),
        ):
            source = AmbientSensorControlSource()
        self.assertIs(type(source.reader), BleNusAmbientReader)

        with (
            patch("control_sources.ambient_sensor.config", self.AutoConfig()),
            patch.object(UsbSerialAmbientReader, "is_port_available", return_value=True),
            patch.object(UsbSerialAmbientReader, "start", return_value=True),
            patch("control_sources.ambient_sensor.threading.Thread", ImmediateThread),
        ):
            self.assertTrue(source.switch_to_preferred_transport())

        self.assertIs(type(source.reader), UsbSerialAmbientReader)
        self.assertTrue(source.controller.status()["usb_connected"])


if __name__ == "__main__":
    unittest.main()
