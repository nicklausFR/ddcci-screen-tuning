import ctypes
import ctypes.wintypes
import threading
import time


PHYSICAL_MONITOR_DESCRIPTION_SIZE = 128
VCP_BRIGHTNESS = 0x10
VCP_CONTRAST = 0x12
VCP_GAIN_R = 0x16
VCP_GAIN_G = 0x18
VCP_GAIN_B = 0x1A
DEFAULT_READ_CACHE_TTL = 0.15

VCP_LOCK = threading.Lock()


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", ctypes.wintypes.HANDLE),
        ("szPhysicalMonitorDescription", ctypes.wintypes.WCHAR * PHYSICAL_MONITOR_DESCRIPTION_SIZE),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
dxva2 = ctypes.WinDLL("Dxva2", use_last_error=True)

user32.EnumDisplayMonitors.restype = ctypes.wintypes.BOOL
user32.EnumDisplayMonitors.argtypes = [
    ctypes.wintypes.HDC,
    ctypes.wintypes.LPRECT,
    ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HMONITOR,
        ctypes.wintypes.HDC,
        ctypes.POINTER(ctypes.wintypes.RECT),
        ctypes.wintypes.LPARAM,
    ),
    ctypes.wintypes.LPARAM,
]

dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = ctypes.wintypes.BOOL
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
    ctypes.wintypes.HMONITOR,
    ctypes.POINTER(ctypes.wintypes.DWORD),
]

dxva2.GetPhysicalMonitorsFromHMONITOR.restype = ctypes.wintypes.BOOL
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    ctypes.wintypes.HMONITOR,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(PHYSICAL_MONITOR),
]

dxva2.DestroyPhysicalMonitor.restype = ctypes.wintypes.BOOL
dxva2.DestroyPhysicalMonitor.argtypes = [ctypes.wintypes.HANDLE]

dxva2.GetVCPFeatureAndVCPFeatureReply.restype = ctypes.wintypes.BOOL
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.BYTE,
    ctypes.POINTER(ctypes.wintypes.DWORD),
    ctypes.POINTER(ctypes.wintypes.DWORD),
    ctypes.POINTER(ctypes.wintypes.DWORD),
]

dxva2.SetVCPFeature.restype = ctypes.wintypes.BOOL
dxva2.SetVCPFeature.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.BYTE,
    ctypes.wintypes.DWORD,
]


class WindowsDDCCIBackend:
    def list_monitors(self):
        monitors = []

        def callback(hMonitor, hdc, lprc, lparam):
            count = ctypes.wintypes.DWORD()
            if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hMonitor, ctypes.byref(count)):
                physical_array = (PHYSICAL_MONITOR * count.value)()
                if dxva2.GetPhysicalMonitorsFromHMONITOR(hMonitor, count, physical_array):
                    for i in range(count.value):
                        name = physical_array[i].szPhysicalMonitorDescription.strip()
                        monitors.append(name)
                        dxva2.DestroyPhysicalMonitor(physical_array[i].hPhysicalMonitor)
            return True

        self._enum_display_monitors(callback)
        return monitors

    def open_monitor(self, index, cache_ttl=DEFAULT_READ_CACHE_TTL):
        return WindowsDDCIMonitor(index=index, cache_ttl=cache_ttl)

    @staticmethod
    def _enum_display_monitors(callback):
        monitor_enum_proc = ctypes.WINFUNCTYPE(
            ctypes.wintypes.BOOL,
            ctypes.wintypes.HMONITOR,
            ctypes.wintypes.HDC,
            ctypes.POINTER(ctypes.wintypes.RECT),
            ctypes.wintypes.LPARAM,
        )
        cb = monitor_enum_proc(callback)
        user32.EnumDisplayMonitors(None, None, cb, 0)


class WindowsDDCIMonitor:
    def __init__(self, index=0, cache_ttl=DEFAULT_READ_CACHE_TTL):
        self._handle = None
        self._closed = False
        self._vcp_lock = threading.RLock()
        self._vcp_cache = {}
        self._cache_ttl = max(0, float(cache_ttl))
        self._monitor_name = None
        self._get_monitor_by_index(index)

    def _get_monitor_by_index(self, target_index):
        self._handle = None
        self._closed = False
        found_monitors = []

        def callback(hMonitor, hdc, lprc, lparam):
            count = ctypes.wintypes.DWORD()
            if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hMonitor, ctypes.byref(count)):
                physical_array = (PHYSICAL_MONITOR * count.value)()
                if dxva2.GetPhysicalMonitorsFromHMONITOR(hMonitor, count, physical_array):
                    for i in range(count.value):
                        found_monitors.append((
                            physical_array[i].hPhysicalMonitor,
                            physical_array[i].szPhysicalMonitorDescription.strip(),
                        ))
            return True

        WindowsDDCCIBackend._enum_display_monitors(callback)

        if target_index < 0 or target_index >= len(found_monitors):
            for handle, _ in found_monitors:
                dxva2.DestroyPhysicalMonitor(handle)
            raise RuntimeError(f"No monitor found at index {target_index}.")

        self._handle, self._monitor_name = found_monitors[target_index]
        for i, (handle, _) in enumerate(found_monitors):
            if i != target_index:
                dxva2.DestroyPhysicalMonitor(handle)

    def name(self):
        return self._monitor_name

    def close(self):
        if not self._closed:
            dxva2.DestroyPhysicalMonitor(self._handle)
            self._closed = True
            self._vcp_cache.clear()

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("DDC/CI monitor is closed or unavailable.")

    def _get_cached_vcp(self, code):
        if self._cache_ttl <= 0:
            return None

        cached = self._vcp_cache.get(code)
        if cached is None:
            return None

        cached_at, current_value, maximum_value = cached
        if time.monotonic() - cached_at <= self._cache_ttl:
            return current_value, maximum_value

        return None

    def _cache_vcp(self, code, current_value, maximum_value):
        self._vcp_cache[code] = (
            time.monotonic(),
            int(current_value),
            int(maximum_value),
        )

    def get_vcp(self, code, max_attempts=5, delay=0.03, use_cache=True):
        with self._vcp_lock:
            self._ensure_open()
            if use_cache:
                cached = self._get_cached_vcp(code)
                if cached is not None:
                    return cached

            last_error = 0
            for attempt in range(1, max_attempts + 1):
                current_value = ctypes.wintypes.DWORD()
                maximum_value = ctypes.wintypes.DWORD()
                type_code = ctypes.wintypes.DWORD()

                with VCP_LOCK:
                    success = dxva2.GetVCPFeatureAndVCPFeatureReply(
                        self._handle,
                        code,
                        ctypes.byref(type_code),
                        ctypes.byref(current_value),
                        ctypes.byref(maximum_value),
                    )

                if success:
                    if attempt > 1:
                        print(f"  VCP 0x{code:02X} succeeded on attempt {attempt}")
                    self._cache_vcp(code, current_value.value, maximum_value.value)
                    return current_value.value, maximum_value.value

                last_error = ctypes.get_last_error()
                time.sleep(delay)

        raise RuntimeError(
            f"VCP 0x{code:02X} read failed after {max_attempts} attempts "
            f"(GetLastError={last_error})"
        )

    def set_vcp(self, code, value, max_attempts=3, delay=0.03):
        value = int(value)
        with self._vcp_lock:
            self._ensure_open()
            cached = self._get_cached_vcp(code)
            if cached is not None and cached[0] == value:
                return

            maximum_value = cached[1] if cached is not None else 100
            last_error = 0
            for attempt in range(1, max_attempts + 1):
                with VCP_LOCK:
                    success = dxva2.SetVCPFeature(self._handle, code, ctypes.wintypes.DWORD(value))
                if success:
                    if attempt > 1:
                        print(f"  VCP 0x{code:02X} written successfully on attempt {attempt}")
                    self._cache_vcp(code, value, maximum_value)
                    return
                last_error = ctypes.get_last_error()
                time.sleep(delay)

        raise RuntimeError(
            f"VCP 0x{code:02X} write failed after {max_attempts} attempts "
            f"(GetLastError={last_error})"
        )

    def get_brightness(self):
        return self.get_vcp(VCP_BRIGHTNESS)[0]

    def set_brightness(self, value):
        self.set_vcp(VCP_BRIGHTNESS, max(0, min(100, round(value))))

    def get_contrast(self):
        return self.get_vcp(VCP_CONTRAST)[0]

    def set_contrast(self, value):
        self.set_vcp(VCP_CONTRAST, max(0, min(100, round(value))))

    def get_rgb(self):
        return (
            self.get_vcp(VCP_GAIN_R)[0],
            self.get_vcp(VCP_GAIN_G)[0],
            self.get_vcp(VCP_GAIN_B)[0],
        )

    def set_rgb(self, r, g, b):
        self.set_vcp(VCP_GAIN_R, max(0, min(100, int(r))))
        self.set_vcp(VCP_GAIN_G, max(0, min(100, int(g))))
        self.set_vcp(VCP_GAIN_B, max(0, min(100, int(b))))
