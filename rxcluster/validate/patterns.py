"""Callsign shape validation.

Shape validation is the cheapest rejection filter. It runs before any database
lookup and catches obvious noise (too short, no digit, too many repeated
characters). Prefix/country validation is delegated to :mod:`cty` and
existence validation to :mod:`scp`.
"""

from __future__ import annotations

import re

# Portable/other suffixes that are stripped before shape/SCP checks.
_MODIFIER_RE = re.compile(r"/(P|M|MM|AM|QRP|A|LH|R|T|B|#\d*)$", re.IGNORECASE)
# Leading country/region prefix separated by "/", e.g. "3D2/R" or "VP8/G".
_PREFIX_SLASH_RE = re.compile(r"^[A-Z0-9]{1,4}/")

_SHAPE_RE = re.compile(r"^[A-Z0-9]{3,14}$")
_REPEAT_RE = re.compile(r"(.)\1\1")


def base_call(call: str) -> str:
    """Strip portable modifiers and return the core callsign (uppercase)."""
    c = call.strip().upper()
    c = _MODIFIER_RE.sub("", c)
    # If a slash remains, keep the longest component (heuristic).
    if "/" in c:
        parts = [p for p in c.split("/") if p]
        if parts:
            c = max(parts, key=len)
    return c


def is_valid_shape(call: str) -> bool:
    """Return ``True`` if ``call`` looks structurally like a callsign."""
    c = base_call(call)
    if not _SHAPE_RE.match(c):
        return False
    if not any(ch.isdigit() for ch in c):
        return False
    if not any(ch.isalpha() for ch in c):
        return False
    # Reject three or more identical consecutive characters (e.g. "AAAA").
    if _REPEAT_RE.search(c):
        return False
    return True


def strip_hash(call: str) -> str:
    return call.rstrip("#").upper()