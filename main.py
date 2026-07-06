import signal
import sys
import platform
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from control_sources import AmbientSensorControlSource, TrayControlSource


instance_lock = QLockFile(str(Path(tempfile.gettempdir()) / "ddcci-screen-tuning.lock"))
if not instance_lock.tryLock(0):
    print("[WARN] ddcci-screen-tuning is already running.")
    sys.exit(0)

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


ambient_source = AmbientSensorControlSource()
tray_source = TrayControlSource(ambient_source=ambient_source)
tray_icon = tray_source.start()
sys.exit(app.exec())
