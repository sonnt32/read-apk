"""Minimal DEX reader: class names, method names, string constants.

Used for native Android (Java/Kotlin) apps. Unity games keep their gameplay
code in IL2CPP/Mono, so for them DEX only shows SDKs.
"""
from __future__ import annotations

import struct
from collections import defaultdict


def _uleb(d: bytes, p: int) -> tuple[int, int]:
    r = s = 0
    while True:
        b = d[p]
        p += 1
        r |= (b & 0x7F) << s
        if b < 0x80:
            return r, p
        s += 7


def _mutf8(d: bytes, p: int) -> str:
    _, p = _uleb(d, p)
    end = d.index(b"\0", p)
    return d[p:end].decode("utf-8", "replace")


def parse_dex(d: bytes) -> tuple[dict[str, list[str]], list[str]]:
    """Return ({class_name: [method names]}, all strings)."""
    if not d.startswith(b"dex\n"):
        return {}, []
    (str_n, str_off, type_n, type_off, _proto_n, _proto_off, _field_n, _field_off,
     meth_n, meth_off) = struct.unpack_from("<10I", d, 0x38)
    offs = struct.unpack_from(f"<{str_n}I", d, str_off)
    strings = [_mutf8(d, o) for o in offs]
    types = [strings[i] for i in struct.unpack_from(f"<{type_n}I", d, type_off)]
    classes: dict[str, list[str]] = defaultdict(list)
    for i in range(meth_n):
        cls, _, name = struct.unpack_from("<HHI", d, meth_off + i * 8)
        t = types[cls]
        if t.startswith("L") and t.endswith(";"):
            t = t[1:-1].replace("/", ".")
        classes[t].append(strings[name])
    return dict(classes), strings
