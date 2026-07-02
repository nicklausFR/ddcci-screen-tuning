import datetime
import math


def parse_hour(value, fallback):
    try:
        if isinstance(value, str) and ":" in value:
            parts = value.strip().split(":")
            hour = float(parts[0])
            minute = float(parts[1]) if len(parts) > 1 else 0.0
            return max(0.0, min(23.999, hour + minute / 60.0))
        return max(0.0, min(23.999, float(value)))
    except (TypeError, ValueError):
        return fallback


def format_hour(value):
    value = max(0.0, min(23.999, float(value)))
    hour = int(value)
    minute = int(round((value - hour) * 60))
    if minute >= 60:
        hour = min(23, hour + 1)
        minute = 0
    return f"{hour:02d}:{minute:02d}"


def solar_hours(now=None, latitude=48.8566, longitude=2.3522):
    now = now or datetime.datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    day_of_year = now.timetuple().tm_yday
    offset_hours = now.utcoffset().total_seconds() / 3600.0
    latitude = max(-89.8, min(89.8, float(latitude)))
    longitude = max(-180.0, min(180.0, float(longitude)))

    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1)
    equation = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )

    zenith = math.radians(90.833)
    lat_rad = math.radians(latitude)
    cos_hour_angle = (
        math.cos(zenith) / (math.cos(lat_rad) * math.cos(declination))
        - math.tan(lat_rad) * math.tan(declination)
    )
    if cos_hour_angle <= -1.0:
        return 0.0, 23.999
    if cos_hour_angle >= 1.0:
        return 12.0, 12.0

    hour_angle = math.degrees(math.acos(cos_hour_angle))
    solar_noon = (720.0 - 4.0 * longitude - equation + offset_hours * 60.0) / 60.0
    sunrise = (solar_noon * 60.0 - hour_angle * 4.0) / 60.0
    sunset = (solar_noon * 60.0 + hour_angle * 4.0) / 60.0
    return max(0.0, min(23.999, sunrise)), max(0.0, min(23.999, sunset))


def daytime_position(now=None, sunrise=7.5, sunset=18.5):
    now = now or datetime.datetime.now()
    hour = now.hour + now.minute / 60.0 + now.second / 3600.0
    if sunset <= sunrise:
        return 50.0
    return max(0.0, min(1.0, (hour - sunrise) / (sunset - sunrise))) * 100.0
