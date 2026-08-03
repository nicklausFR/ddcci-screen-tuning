import math
import unittest
from unittest.mock import Mock, patch

from control_sources.ambient_sensor import AmbientLightController, AmbientSensorControlSource


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


if __name__ == "__main__":
    unittest.main()
