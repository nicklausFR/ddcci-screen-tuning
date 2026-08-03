import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QPushButton,
    QSlider,
    QWidget,
)

from gui import PopupPanel


class FakeConfig:
    def __init__(self):
        self._data = {}
        self.LIGHT_MODE = True
        self.DETAIL_ROWS_VISIBLE = False
        self.LAST_LIGHT = 50
        self.LAST_NIGHTLIGHT = 25

    def set(self, name, value):
        self._data[name] = value
        setattr(self, name, value)


class FakeMonitor:
    def nightlight_get_target_rgb(self):
        return 100, 40, 8

    def nightlight_get_neutral_rgb(self):
        return 50, 50, 50

    def nightlight_get_strength(self):
        return 25


class SettingsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = PopupPanel.__new__(PopupPanel)
        QWidget.__init__(self.panel)
        self.panel.config = FakeConfig()
        self.panel.monitor = FakeMonitor()
        self.panel.ambient_source = None
        self.panel.light_mode = True
        self.panel._detail_rows_visible = False
        self.panel._panel_closed = False
        self.panel.on_nightlight_source_selected = None
        self.panel.sliders = {}
        for name, value in (
            ("light", 50),
            ("brightness", 50),
            ("contrast", 50),
            ("nightlight", 25),
        ):
            slider = QSlider()
            slider.setRange(0, 100)
            slider.setValue(value)
            self.panel.sliders[name] = slider
        self.panel._safe_set_light_values = lambda *args: True
        self.panel._safe_set_nightlight_strength = lambda *args: True
        self.panel._safe_apply_nightlight_target_and_strength = lambda *args: True
        self.panel._safe_restore_nightlight_state = lambda *args, **kwargs: True
        self.panel._remember_slider_values = lambda: None
        self.panel.apply_light_value = lambda value: True
        self.panel.set_nightlight_source_control = lambda source: None
        self.panel._nightlight_backend = lambda: "gamma_ramp"
        self.panel._set_slider_silent = (
            lambda name, value: self.panel.sliders[name].setValue(round(value))
        )

    def test_settings_pages_have_no_apply_button(self):
        builders = (
            lambda page: self.panel._build_light_curve_settings(page, include_close=False),
            self.panel._build_smoothing_settings,
            self.panel._build_gamma_ramp_settings,
            self.panel._build_light_linked_nightlight_settings,
            lambda page: self.panel._build_nightlight_color_settings(
                page,
                include_close=False,
                preview_changes=False,
            ),
            self.panel._build_daytime_settings,
            self.panel._build_ambient_sensor_settings,
        )

        pages = []
        for builder in builders:
            page = QWidget()
            pages.append(page)
            builder(page)

        button_texts = {
            button.text()
            for page in pages
            for button in page.findChildren(QPushButton)
        }
        self.assertNotIn("Apply", button_texts)

    def test_representative_controls_save_immediately(self):
        light_page = QWidget()
        self.panel._build_light_curve_settings(light_page, include_close=False)
        template_combo = light_page.findChild(QComboBox)
        template_combo.setCurrentText("Office")
        self.assertIn("LIGHT_BRIGHTNESS_CURVE_POINTS", self.panel.config._data)
        self.assertIn("LIGHT_CONTRAST_CURVE_POINTS", self.panel.config._data)

        gamma_page = QWidget()
        self.panel._build_gamma_ramp_settings(gamma_page)
        temperature_slider = gamma_page.findChild(QSlider)
        temperature_slider.setValue(2200)
        temperature_slider.sliderReleased.emit()
        self.assertEqual(self.panel.config.GAMMA_RAMP_WARM_KELVIN, 2200)

        link_page = QWidget()
        self.panel._build_light_linked_nightlight_settings(link_page)
        source_combo = link_page.findChild(QComboBox)
        source_combo.setCurrentIndex(source_combo.findData("light_linked"))
        self.assertEqual(self.panel.config.NIGHTLIGHT_SOURCE, "light_linked")

        rgb_page = QWidget()
        self.panel._build_nightlight_color_settings(
            rgb_page,
            include_close=False,
            preview_changes=False,
        )
        color_slider = next(
            slider
            for slider in rgb_page.findChildren(QSlider)
            if slider.minimum() == 0 and slider.maximum() == 100
        )
        color_slider.setValue(80)
        color_slider.sliderReleased.emit()
        self.assertEqual(self.panel.config.NIGHTLIGHT_TARGET_COLOR, 80)

    def test_automatic_source_locks_light_sliders(self):
        self.panel.active_source = "ambient"
        self.panel._update_light_controls_enabled()

        for key in ("light", "brightness", "contrast"):
            self.assertFalse(self.panel.sliders[key].isEnabled())

        self.panel.active_source = "tray"
        self.panel._detail_rows_visible = True
        self.panel._update_light_controls_enabled()

        for key in ("light", "brightness", "contrast"):
            self.assertTrue(self.panel.sliders[key].isEnabled())


if __name__ == "__main__":
    unittest.main()
