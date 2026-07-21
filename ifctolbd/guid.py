"""IFC compressed GUID codec, ported from ``GuidCompressor.java``."""

from __future__ import annotations

import uuid

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def compress(value: str | uuid.UUID) -> str:
    number = (value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))).int
    result = []
    for _ in range(22):
        result.append(_CHARS[number & 63])
        number >>= 6
    return "".join(reversed(result))


def expand(value: str) -> uuid.UUID:
    if len(value) != 22 or any(c not in _CHARS for c in value):
        raise ValueError("An IFC GUID must contain 22 base-64 characters")
    number = 0
    for char in value:
        number = (number << 6) | _CHARS.index(char)
    if number >= 1 << 128:
        raise ValueError("IFC GUID is outside the UUID range")
    return uuid.UUID(int=number)

