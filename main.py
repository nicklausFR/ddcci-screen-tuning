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


_instance_mutex_handle = None
_instance_lock = None


def acquire_single_instance():
    global _instance_mutex_handle, _instance_lock

    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            ctypes.wintypes.BOOL,
            ctypes.wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (ctypes.wintypes.HANDLE,)
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(
            None,
            False,
            "Local\\ddcci-screen-tuning-single-instance",
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _instance_mutex_handle = handle
        return True

    _instance_lock = QLockFile(
        str(Path(tempfile.gettempdir()) / "ddcci-screen-tuning.lock")
    )
    return _instance_lock.tryLock(0)


if not acquire_single_instance():
    print("[WARN] ddcci-screen-tuning is already running.")
    sys.exit(0)

from control_sources import AmbientSensorControlSource, TrayControlSource


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


def stop_ambient_source():
    try:
        ambient_source.stop()
    except Exception as exc:
        print("[WARN] Ambient BLE shutdown failed:", exc)


app.aboutToQuit.connect(stop_ambient_source)
atexit.register(stop_ambient_source)

tray_source = TrayControlSource(ambient_source=ambient_source)
tray_icon = tray_source.start()
sys.exit(app.exec())
