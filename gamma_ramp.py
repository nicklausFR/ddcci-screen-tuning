import argparse
import ctypes
import ctypes.wintypes
import math


GAMMA_POINTS = 256
MAX_GAMMA_VALUE = 65535

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

user32.GetDC.restype = ctypes.wintypes.HDC
user32.GetDC.argtypes = [ctypes.wintypes.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]

gdi32.SetDeviceGammaRamp.restype = ctypes.wintypes.BOOL
gdi32.SetDeviceGammaRamp.argtypes = [ctypes.wintypes.HDC, ctypes.c_void_p]


class GammaRampError(RuntimeError):
    pass


def _raise_last_error(message):
    err = ctypes.get_last_error()
    raise GammaRampError(f"{message} (GetLastError={err})")


def _get_screen_dc():
    hdc = user32.GetDC(None)
    if not hdc:
        _raise_last_error("Impossible d'obtenir le device context ecran")
    return hdc


def _release_screen_dc(hdc):
    user32.ReleaseDC(None, hdc)


def _make_ramp(red_gamma=1.0, green_gamma=1.0, blue_gamma=1.0):
    ramp = (ctypes.c_ushort * (GAMMA_POINTS * 3))()
    gammas = (
        max(0.25, float(red_gamma)),
        max(0.25, float(green_gamma)),
        max(0.25, float(blue_gamma)),
    )

    for channel, gamma in enumerate(gammas):
        offset = channel * GAMMA_POINTS
        for i in range(GAMMA_POINTS):
            x = i / (GAMMA_POINTS - 1)
            y = math.pow(x, 1.0 / gamma)
            ramp[offset + i] = round(max(0.0, min(1.0, y)) * MAX_GAMMA_VALUE)

    return ramp


def _set_ramp(ramp):
    hdc = _get_screen_dc()
    try:
        if not gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
            _raise_last_error("SetDeviceGammaRamp failed")
    finally:
        _release_screen_dc(hdc)


def reset_gamma():
    _set_ramp(_make_ramp())


def apply_warmth(strength):
    strength = max(0, min(int(strength), 100)) / 100.0

    # Driver-compatible tint: keep black/white endpoints intact and shift
    # mostly midtones. Some drivers reject ramps that lower channel maxima.
    red_gamma = 1.0 + 0.10 * strength
    green_gamma = 1.0 - 0.10 * strength
    blue_gamma = 1.0 - 0.55 * strength

    _set_ramp(_make_ramp(red_gamma, green_gamma, blue_gamma))


def main():
    parser = argparse.ArgumentParser(description="Test Windows gamma ramp color warmth.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    warm = subparsers.add_parser("warm", help="Apply a warm gamma ramp.")
    warm.add_argument("strength", nargs="?", type=int, default=50, help="Warmth from 0 to 100.")

    subparsers.add_parser("reset", help="Reset to a linear gamma ramp.")

    args = parser.parse_args()
    if args.command == "warm":
        apply_warmth(args.strength)
        print(f"Gamma ramp warmth applied: {max(0, min(args.strength, 100))}%")
    elif args.command == "reset":
        reset_gamma()
        print("Gamma ramp reset.")


if __name__ == "__main__":
    main()
