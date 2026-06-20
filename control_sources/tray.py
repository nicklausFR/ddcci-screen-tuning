from gui import PopupPanel, create_tray_icon
from monitor import DDCCI_Monitor, ddc_ci_monitors_list
from ddcci_screen_tuning import config


class TrayControlSource:
    def __init__(self):
        self.panel = None
        self.tray_icon = None

    def start(self):
        self.tray_icon = create_tray_icon(self.toggle_panel)
        return self.tray_icon

    def selected_monitor_index(self, monitors):
        if not monitors:
            raise RuntimeError("No DDC/CI monitor detected.")
        try:
            index = int(getattr(config, "SELECTED_MONITOR_INDEX", 0))
        except (TypeError, ValueError):
            index = 0
        return max(0, min(index, len(monitors) - 1))

    def toggle_panel(self):
        if self.panel is None or not self.panel.isVisible():
            try:
                monitor_names = ddc_ci_monitors_list()
                index = self.selected_monitor_index(monitor_names)
                monitor = DDCCI_Monitor(index=index)
                self.panel = PopupPanel(monitor, monitor_names, index)
            except Exception as e:
                print("[WARN] Failed to open panel:", e)
                return
            self.panel.show()
        else:
            self.panel.close()
