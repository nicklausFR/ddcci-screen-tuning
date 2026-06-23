import signal
import sys
import platform

from PySide6.QtWidgets import QApplication

from control_sources import TrayControlSource


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
signal.signal(signal.SIGINT, lambda *_: app.quit())

if platform.system() == "Windows":
    try:
        from gamma_ramp import reset_gamma

        reset_gamma()
    except Exception as e:
        print("[WARN] Windows gamma reset failed:", e)


# MIDI control is experimental and not wired into the tested v1.0 startup path.


tray_source = TrayControlSource()
tray_icon = tray_source.start()
sys.exit(app.exec())
