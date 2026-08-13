import unittest
from unittest.mock import Mock, patch

from control_sources.tray import TrayControlSource


class PassiveAmbientTransportTests(unittest.TestCase):
    def test_manual_mode_still_switches_passive_reader_to_usb(self):
        ambient_source = Mock()
        ambient_source.switch_to_preferred_transport.return_value = True

        source = TrayControlSource.__new__(TrayControlSource)
        source.ambient_source = ambient_source
        source._ambient_watch_enabled = True
        source._sync_tray_source_menu = Mock()
        source._sync_source_availability = Mock()

        class ManualConfig:
            AMBIENT_SOURCE_ENABLED = False

        with patch("control_sources.tray.config", ManualConfig()):
            source._poll_ambient_availability()

        ambient_source.switch_to_preferred_transport.assert_called_once_with()
        source._sync_tray_source_menu.assert_not_called()
        source._sync_source_availability.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
