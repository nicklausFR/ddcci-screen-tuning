import platform


def load_monitor_backend():
    system = platform.system()
    if system == "Windows":
        from .windows_ddcci import WindowsDDCCIBackend

        return WindowsDDCCIBackend()
    raise NotImplementedError(f"DDC/CI backend is not implemented for {system}.")
