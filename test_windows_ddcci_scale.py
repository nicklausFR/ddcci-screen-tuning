import unittest

from platform_backends.windows_ddcci import VCP_BRIGHTNESS, WindowsDDCIMonitor


class WindowsDDCCIScaleTests(unittest.TestCase):
    def test_brightness_uses_monitor_advertised_range(self):
        monitor = WindowsDDCIMonitor.__new__(WindowsDDCIMonitor)
        monitor.get_vcp = lambda code, **_kwargs: (128, 255)
        writes = []
        monitor.set_vcp = lambda code, value: writes.append((code, value))

        self.assertEqual(monitor.get_brightness(), 50)
        monitor.set_brightness(100)

        self.assertEqual(writes, [(VCP_BRIGHTNESS, 255)])


if __name__ == "__main__":
    unittest.main()
