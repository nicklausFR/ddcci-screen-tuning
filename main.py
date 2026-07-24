import atexit
import ctypes
import ctypes.wintypes
import signal
import sys
import platform
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QWidget

from control_sources import AmbientSensorControlSource, TrayControlSource


instance_lock = QLockFile(str(Path(tempfile.gettempdir()) / "ddcci-screen-tuning.lock"))
if not instance_lock.tryLock(0):
    print("[WARN] ddcci-screen-tuning is already running.")
    sys.exit(0)

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from gui import apply_windows_app_theme

apply_windows_app_theme(app)

_shutdown_reset_done = False


def reset_displays_before_exit():
    global _shutdown_reset_done
    if _shutdown_reset_done:
        return

    try:
        from ddcci_screen_tuning import config

        if not bool(getattr(config, "RESET_DISPLAYS_ON_EXIT", False)):
            return
    except Exception as e:
        print("[WARN] Failed to read shutdown reset setting:", e)
        return

    _shutdown_reset_done = True

    try:
        from ddcci_command_queue import clear_pending_ddcci_commands

        clear_pending_ddcci_commands()
    except Exception as e:
        print("[WARN] Failed to clear pending DDC/CI commands:", e)

    if platform.system() == "Windows":
        try:
            from gamma_ramp import reset_gamma

            reset_gamma()
        except Exception as e:
            print("[WARN] Windows gamma reset failed:", e)

    try:
        from monitor import reset_all_monitors_to_neutral

        reset_all_monitors_to_neutral()
    except Exception as e:
        print("[WARN] DDC/CI shutdown reset failed:", e)


def quit_application(*_):
    app.quit()


signal.signal(signal.SIGINT, quit_application)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, quit_application)
app.aboutToQuit.connect(reset_displays_before_exit)
atexit.register(reset_displays_before_exit)

if platform.system() == "Windows":
    try:
        from gamma_ramp import reset_gamma

        reset_gamma()
    except Exception as e:
        print("[WARN] Windows gamma reset failed:", e)

    CTRL_CLOSE_EVENT = 2
    CTRL_LOGOFF_EVENT = 5
    CTRL_SHUTDOWN_EVENT = 6

    def _windows_console_handler(ctrl_type):
        if ctrl_type in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
            reset_displays_before_exit()
        return False

    try:
        _console_handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        _console_handler = _console_handler_type(_windows_console_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)
    except Exception as e:
        print("[WARN] Windows shutdown handler unavailable:", e)

    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016

    class _WindowsShutdownWindow(QWidget):
        def nativeEvent(self, event_type, message):
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
            except Exception:
                return False, 0
            if msg.message == WM_QUERYENDSESSION:
                reset_displays_before_exit()
                return True, 1
            if msg.message == WM_ENDSESSION and msg.wParam:
                reset_displays_before_exit()
            return False, 0

    _shutdown_window = _WindowsShutdownWindow()
    _shutdown_window.setWindowTitle("ddcci-screen-tuning shutdown handler")
    _shutdown_window.winId()

if hasattr(app, "commitDataRequest"):
    app.commitDataRequest.connect(lambda _manager: reset_displays_before_exit())


# MIDI control is experimental and not wired into the tested v1.0 startup path.


ambient_source = AmbientSensorControlSource()
tray_source = TrayControlSource(ambient_source=ambient_source)
tray_icon = tray_source.start()
sys.exit(app.exec())
