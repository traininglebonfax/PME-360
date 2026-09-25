"""Identifiants UUID v7 : triables dans le temps et non devinables (Document 3, § 1)."""

import secrets
import time
import uuid


def uuid7() -> uuid.UUID:
    if hasattr(uuid, "uuid7"):  # Python ≥ 3.14
        return uuid.uuid7()
    timestamp_ms = time.time_ns() // 1_000_000
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (timestamp_ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return uuid.UUID(int=value)
