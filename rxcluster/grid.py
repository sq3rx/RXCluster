"""Maidenhead grid helpers and great-circle distance."""

from __future__ import annotations

import math
import re

_EARTH_RADIUS_KM = 6371.0

# Maidenhead locator: two A-R fields, two digits, optional two A-X subsquares.
_GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$")


def is_valid_grid(grid: str) -> bool:
    """Return whether ``grid`` is a well-formed 4- or 6-character locator."""
    return bool(_GRID_RE.match(grid.strip().upper()))


def latlon_to_grid(lat: float, lon: float, precision: int = 4) -> str:
    """Convert latitude/longitude to a Maidenhead locator (default 4 chars)."""
    lon = lon + 180.0
    lat = lat + 90.0
    field_lon = int(lon // 20)
    field_lat = int(lat // 10)
    square_lon = int((lon % 20) // 2)
    square_lat = int(lat % 10)
    grid = (
        chr(ord("A") + field_lon)
        + chr(ord("A") + field_lat)
        + str(square_lon)
        + str(square_lat)
    )
    if precision >= 6:
        subsquare_lon = int(((lon % 2) / 2) * 24)
        subsquare_lat = int(((lat % 1) / 1) * 24)
        grid += chr(ord("A") + subsquare_lon) + chr(ord("A") + subsquare_lat)
    return grid


def grid_to_latlon(grid: str) -> tuple[float, float] | None:
    """Convert a Maidenhead locator (>= 4 chars) to the center lat/lon."""
    g = grid.strip().upper()
    if len(g) < 4:
        return None
    try:
        lon = (ord(g[0]) - ord("A")) * 20 - 180
        lat = (ord(g[1]) - ord("A")) * 10 - 90
        lon += int(g[2]) * 2
        lat += int(g[3])
        if len(g) >= 6:
            lon += (ord(g[4]) - ord("A")) * (2 / 24)
            lat += (ord(g[5]) - ord("A")) * (1 / 24)
            lon += 1 / 24
            lat += 1 / 48
        else:
            lon += 1
            lat += 0.5
    except (ValueError, IndexError):
        return None
    return lat, lon


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers (haversine)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def grid_distance_km(grid1: str, grid2: str) -> float | None:
    p1 = grid_to_latlon(grid1)
    p2 = grid_to_latlon(grid2)
    if p1 is None or p2 is None:
        return None
    return distance_km(p1[0], p1[1], p2[0], p2[1])