import argparse
import ctypes
import ctypes.wintypes
import math


GAMMA_POINTS = 256
MAX_GAMMA_VALUE = 65535
DEFAULT_WHITE_KELVIN = 6500
DEFAULT_WARM_KELVIN = 1900
LUMA_WEIGHTS = (0.2126, 0.7152, 0.0722)
SAFE_MAX_GAMMA_STRENGTH = 95.0

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


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _kelvin_to_rgb(temp_k):
    temp = _clamp(float(temp_k), 1000.0, 40000.0) / 100.0

    if temp <= 66:
        red = 255
        green = 99.4708025861 * math.log(temp) - 161.1195681661
        blue = 0 if temp <= 19 else 138.5177312231 * math.log(temp - 10) - 305.0447927307
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
        blue = 255

    return tuple(_clamp(channel, 0.0, 255.0) for channel in (red, green, blue))


def _kelvin_to_channel_scales(temp_k, white_k=DEFAULT_WHITE_KELVIN):
    target = _kelvin_to_rgb(temp_k)
    white = _kelvin_to_rgb(white_k)
    return tuple(
        0.0 if white_channel <= 0 else _clamp(target_channel / white_channel, 0.0, 1.0)
        for target_channel, white_channel in zip(target, white)
    )


def _make_ramp(red_gamma=1.0, green_gamma=1.0, blue_gamma=1.0, scales=(1.0, 1.0, 1.0)):
    ramp = (ctypes.c_ushort * (GAMMA_POINTS * 3))()
    gammas = (
        max(0.25, float(red_gamma)),
        max(0.25, float(green_gamma)),
        max(0.25, float(blue_gamma)),
    )
    scales = tuple(_clamp(float(scale), 0.0, 1.0) for scale in scales)

    for channel, (gamma, scale) in enumerate(zip(gammas, scales)):
        offset = channel * GAMMA_POINTS
        for i in range(GAMMA_POINTS):
            x = i / (GAMMA_POINTS - 1)
            y = math.pow(x, 1.0 / gamma)
            ramp[offset + i] = round(_clamp(y * scale, 0.0, 1.0) * MAX_GAMMA_VALUE)

    return ramp


def _relative_luma(channels):
    return sum(channel * weight for channel, weight in zip(channels, LUMA_WEIGHTS))


def _luma_compensated_scales(channel_scales):
    channel_scales = tuple(_clamp(float(scale), 0.0, 1.0) for scale in channel_scales)
    luma = _relative_luma(channel_scales)
    scale = 1.0 / luma if luma > 0 else 1.0
    return tuple(_clamp(channel * scale, 0.0, 1.0) for channel in channel_scales)


def _make_luma_preserving_ramp(channel_scales, brightness=1.0):
    ramp = (ctypes.c_ushort * (GAMMA_POINTS * 3))()
    target_scales = _luma_compensated_scales(channel_scales)
    brightness = _clamp(float(brightness), 0.01, 1.0)

    for i in range(GAMMA_POINTS):
        x = i / (GAMMA_POINTS - 1)
        highlight_restore = x ** 4
        channels = [
            x * brightness * (scale * (1.0 - highlight_restore) + highlight_restore)
            for scale in target_scales
        ]
        for channel, value in enumerate(channels):
            ramp[channel * GAMMA_POINTS + i] = round(_clamp(value, 0.0, 1.0) * MAX_GAMMA_VALUE)

    return ramp


def _make_kelvin_ramp(kelvin, brightness=100, scale_max=False, preserve_luma=True):
    brightness = _clamp(float(brightness), 1.0, 100.0) / 100.0
    channel_scales = _kelvin_to_channel_scales(kelvin)

    if preserve_luma:
        return _make_luma_preserving_ramp(channel_scales, brightness)

    if scale_max:
        scales = tuple(scale * brightness for scale in channel_scales)
        return _make_ramp(scales=scales)

    gammas = tuple(_clamp(scale * brightness, 0.25, 1.0) for scale in channel_scales)
    return _make_ramp(*gammas)


def _blend_ramps(left, right, mix):
    mix = _clamp(float(mix), 0.0, 1.0)
    ramp = (ctypes.c_ushort * (GAMMA_POINTS * 3))()
    for index in range(GAMMA_POINTS * 3):
        ramp[index] = round(left[index] + (right[index] - left[index]) * mix)
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


def apply_kelvin(kelvin, brightness=100, scale_max=False, preserve_luma=True):
    _set_ramp(_make_kelvin_ramp(kelvin, brightness, scale_max, preserve_luma))


def apply_strength(kelvin, strength, brightness=100, scale_max=False, preserve_luma=True):
    requested_strength = _clamp(float(strength), 0.0, 100.0)
    if requested_strength <= 0:
        reset_gamma()
        return

    effective_strength = min(requested_strength, SAFE_MAX_GAMMA_STRENGTH)
    neutral = _make_ramp()
    target = _make_kelvin_ramp(kelvin, brightness, scale_max, preserve_luma)
    last_error = None
    retry_strengths = [effective_strength]
    retry_strengths.extend(
        value
        for value in range(int(effective_strength) - 5, 0, -5)
        if value not in retry_strengths
    )
    for retry_strength in retry_strengths:
        try:
            _set_ramp(_blend_ramps(neutral, target, retry_strength / 100.0))
            return
        except GammaRampError as exc:
            last_error = exc
    raise last_error


def apply_warmth(strength):
    strength = _clamp(float(strength), 0.0, 100.0) / 100.0
    apply_strength(DEFAULT_WARM_KELVIN, strength * 100)
    return DEFAULT_WARM_KELVIN


def main():
    parser = argparse.ArgumentParser(description="Test Windows gamma ramp color warmth.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    warm = subparsers.add_parser("warm", help="Apply a Kelvin-based warm gamma ramp.")
    warm.add_argument("strength", nargs="?", type=int, default=50, help="Warmth from 0 to 100.")

    kelvin = subparsers.add_parser("kelvin", help="Apply an exact color temperature.")
    kelvin.add_argument("temperature", type=int, help="Color temperature in Kelvin.")
    kelvin.add_argument("--brightness", type=float, default=100, help="Software brightness from 1 to 100.")
    kelvin.add_argument(
        "--scale-max",
        action="store_true",
        help="Lower channel maxima for a stronger effect. Some Windows drivers reject this.",
    )

    subparsers.add_parser("reset", help="Reset to a linear gamma ramp.")

    args = parser.parse_args()
    if args.command == "warm":
        kelvin = apply_warmth(args.strength)
        print(f"Gamma ramp warmth applied: {max(0, min(args.strength, 100))}% ({kelvin}K)")
    elif args.command == "kelvin":
        apply_kelvin(args.temperature, args.brightness, args.scale_max)
        print(f"Gamma ramp color temperature applied: {args.temperature}K, brightness {args.brightness:g}%")
    elif args.command == "reset":
        reset_gamma()
        print("Gamma ramp reset.")


if __name__ == "__main__":
    main()
