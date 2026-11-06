"""Minimal reader for Android binary XML (AndroidManifest.xml)."""
from __future__ import annotations

import struct

RES_STRING_POOL = 0x0001
RES_XML_START_ELEMENT = 0x0102
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10


def _string_pool(d: bytes, off: int) -> list[str]:
    _, hsize, _ = struct.unpack_from("<HHI", d, off)
    count, _, flags, str_start, _ = struct.unpack_from("<IIIII", d, off + 8)
    utf8 = bool(flags & 0x100)
    offs = struct.unpack_from(f"<{count}I", d, off + hsize)
    base = off + str_start
    out = []
    for o in offs:
        p = base + o
        if utf8:
            n = d[p]
            p += 2 if n & 0x80 else 1  # utf16 length
            n = d[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | d[p + 1]
                p += 2
            else:
                p += 1
            out.append(d[p : p + n].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", d, p)[0]
            p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, p)[0]
                p += 2
            out.append(d[p : p + n * 2].decode("utf-16-le", "replace"))
    return out


def parse_manifest(d: bytes) -> dict:
    """Return package, versionName, versionCode, activities, permissions."""
    info = {"package": "", "versionName": "", "versionCode": "",
            "activities": [], "permissions": [], "launcher_activity": ""}
    strings: list[str] = []
    off = 8
    last_activity = ""
    while off + 8 <= len(d):
        ctype, hsize, csize = struct.unpack_from("<HHI", d, off)
        if csize == 0:
            break
        if ctype == RES_STRING_POOL:
            strings = _string_pool(d, off)
        elif ctype == RES_XML_START_ELEMENT:
            ext = off + hsize
            _, name_i, attr_start, attr_size, attr_count = struct.unpack_from("<iiHHH", d, ext)
            tag = strings[name_i] if 0 <= name_i < len(strings) else ""
            attrs = {}
            for k in range(attr_count):
                a = ext + attr_start + k * attr_size
                _, an, raw, _, _, dtype, data = struct.unpack_from("<iiiHBBI", d, a)
                key = strings[an] if 0 <= an < len(strings) else ""
                if raw >= 0 and raw < len(strings):
                    attrs[key] = strings[raw]
                elif dtype == TYPE_STRING and data < len(strings):
                    attrs[key] = strings[data]
                elif dtype == TYPE_INT_DEC:
                    attrs[key] = str(data)
            if tag == "manifest":
                info["package"] = attrs.get("package", "")
                info["versionName"] = attrs.get("versionName", "")
                info["versionCode"] = attrs.get("versionCode", "")
            elif tag in ("activity", "activity-alias"):
                last_activity = attrs.get("name", "")
                info["activities"].append(last_activity)
            elif tag == "uses-permission":
                info["permissions"].append(attrs.get("name", ""))
            elif tag == "category" and attrs.get("name") == "android.intent.category.LAUNCHER":
                info["launcher_activity"] = info["launcher_activity"] or last_activity
        off += csize
    return info
