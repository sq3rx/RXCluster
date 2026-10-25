"""Sunrise / sunset computation (NOAA sunrise equation).

Used by the ``SH/SUN`` command (DX Spider / N1MM) to report the sunrise and
sunset times for a DXCC entity or grid locator. Times are UTC and may be
``None`` during polar day/night.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time

# Official zenith for sunrise/sunset (accounts for refraction + solar radius).
_ZENITH_DEG = 90.833


def _sun_event_utc(lat: float, lon: float, day: date, rising: bool) -> datetime | None:
    """Return the sunrise (``rising``) or sunset UTC datetime, or ``None``."""
    n = day.timetuple().tm_yday
    lng_hour = lon / 15.0

    t = n + ((6.0 if rising else 18.0) - lng_hour) / 24.0
    mean_anomaly = 0.9856 * t - 3.289
    true_long = (
        mean_anomaly
        + 1.916 * math.sin(math.radians(mean_anomaly))
        + 0.020 * math.sin(math.radians(2 * mean_anomaly))
        + 282.634
    ) % 360.0

    right_ascension = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_long))))
    right_ascension %= 360.0
    # Move the RA into the same quadrant as the true longitude.
    l_quadrant = (math.floor(true_long / 90.0)) * 90.0
    ra_quadrant = (math.floor(right_ascension / 90.0)) * 90.0
    right_ascension += l_quadrant - ra_quadrant
    right_ascension /= 15.0

    sin_decl = 0.39782 * math.sin(math.radians(true_long))
    cos_decl = math.cos(math.asin(sin_decl))

    cos_hour = (math.cos(math.radians(_ZENITH_DEG)) - sin_decl * math.sin(math.radians(lat))) / (
        cos_decl * math.cos(math.radians(lat))
    )
    if cos_hour > 1.0 or cos_hour < -1.0:
        return None  # polar night or midnight sun

    hour_angle = (360.0 - math.degrees(math.acos(cos_hour))) if rising else math.degrees(
        math.acos(cos_hour)
    )
    hour_angle /= 15.0

    local_time = hour_angle + right_ascension - 0.06571 * t - 6.622
    utc_hours = (local_time - lng_hour) % 24.0

    hours = int(utc_hours)
    minutes = int(round((utc_hours - hours) * 60.0))
    if minutes == 60:
        hours = (hours + 1) % 24
        minutes = 0
    return datetime.combine(day, time(hour=hours, minute=minutes), tzinfo=UTC)


def sunrise_sunset(
    lat: float, lon: float, day: date | None = None
) -> tuple[datetime | None, datetime | None]:
    """Return ``(sunrise, sunset)`` in UTC for ``lat``/``lon`` (east-positive)."""
    when = day or datetime.now(UTC).date()
    return _sun_event_utc(lat, lon, when, True), _sun_event_utc(lat, lon, when, False)
