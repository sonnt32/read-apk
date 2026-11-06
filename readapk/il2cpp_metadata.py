"""Read Unity IL2CPP global-metadata.dat without external tools.

Struct layouts change between Unity versions (v24..v39+, and v38+ uses
variable-width indices), so instead of hard-coding layouts we read only the
fields we need and detect columns by checking the data is consistent.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

SANITY = 0xFAB11BAF

# Section order in the metadata header (stable from v24 to v39).
SEC_STRING_LITERAL = 0
SEC_STRING_LITERAL_DATA = 1
SEC_STRING = 2
SEC_PROPERTIES = 4
SEC_METHODS = 5
SEC_FIELDS = 11
SEC_TYPE_DEFINITIONS = 19
SEC_IMAGES = 20


class MetadataError(Exception):
    pass


@dataclass
class TypeInfo:
    index: int
    namespace: str
    name: str
    assembly: str = ""
    fields: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


@dataclass
class Metadata:
    version: int
    types: list[TypeInfo]
    string_literals: list[str]
    assemblies: list[str]
    warnings: list[str]


@dataclass
class Section:
    offset: int
    size: int
    count: int | None  # only present in v38+


def _read_cstr(buf: bytes, off: int) -> str:
    end = buf.find(b"\0", off)
    if end < 0:
        end = len(buf)
    return buf[off:end].decode("utf-8", "replace")


def _col(data: bytes, entry: int, n: int, off: int, width: int) -> list[int]:
    """Read one column (unsigned) from a table of n fixed-size entries."""
    fmt = {1: "B", 2: "H", 4: "I"}[width]
    out = []
    for i in range(n):
        out.append(struct.unpack_from("<" + fmt, data, i * entry + off)[0])
    return out


def _sentinel(width: int) -> int:
    return (1 << (8 * width)) - 1


class _Parser:
    def __init__(self, data: bytes):
        self.d = data
        if len(data) < 64:
            raise MetadataError("file too small")
        sanity, self.version = struct.unpack_from("<Ii", data, 0)
        if sanity != SANITY:
            raise MetadataError(
                "global-metadata.dat bị mã hóa hoặc bị sửa header "
                f"(sanity=0x{sanity:08X}). Cần giải mã trước khi đọc."
            )
        self.warnings: list[str] = []
        self.sections = self._read_header()
        s = self.sections[SEC_STRING]
        self.strings = data[s.offset : s.offset + s.size]

    # ---------- header ----------
    def _read_header(self) -> list[Section]:
        triples = self.version >= 38
        step = 12 if triples else 8
        header_end = struct.unpack_from("<I", self.d, 8)[0]  # first section offset
        n = (header_end - 8) // step
        secs = []
        for i in range(n):
            base = 8 + i * step
            if triples:
                o, sz, c = struct.unpack_from("<iii", self.d, base)
                secs.append(Section(o, sz, c))
            else:
                o, sz = struct.unpack_from("<ii", self.d, base)
                secs.append(Section(o, sz, None))
        return secs

    def sec(self, i: int) -> bytes:
        s = self.sections[i]
        return self.d[s.offset : s.offset + s.size]

    # ---------- helpers ----------
    def is_str_start(self, idx: int) -> bool:
        return 0 <= idx < len(self.strings) and (idx == 0 or self.strings[idx - 1] == 0)

    def name(self, idx: int) -> str:
        return _read_cstr(self.strings, idx)

    def _entry_sizes(self, sec_i: int, candidates: range, validate) -> list[int]:
        """All record sizes that pass validation (v38+ stores the count)."""
        s = self.sections[sec_i]
        if s.count:
            return [s.size // s.count]
        sizes = [sz for sz in candidates
                 if s.size % sz == 0 and validate(sz, s.size // sz)]
        if not sizes:
            raise MetadataError(f"không dò được kích thước bản ghi của section {sec_i}")
        return sizes

    def _entry_size(self, sec_i: int, candidates: range, validate) -> int:
        return self._entry_sizes(sec_i, candidates, validate)[0]

    def _names_ok(self, data: bytes, size: int, n: int, offs: tuple[int, ...]) -> bool:
        step = max(1, n // 200)
        for i in range(0, n, step):
            for o in offs:
                if not self.is_str_start(struct.unpack_from("<I", data, i * size + o)[0]):
                    return False
        return True

    # ---------- string literals ----------
    def string_literals(self) -> list[str]:
        tbl = self.sec(SEC_STRING_LITERAL)
        blob = self.sec(SEC_STRING_LITERAL_DATA)
        s = self.sections[SEC_STRING_LITERAL]
        out: list[str] = []
        entry = s.size // s.count if s.count else 8
        if entry == 8:  # {uint32 length, int32 dataIndex}
            for i in range(len(tbl) // 8):
                ln, idx = struct.unpack_from("<Ii", tbl, i * 8)
                out.append(blob[idx : idx + ln].decode("utf-8", "replace"))
        else:  # v31+/v38+: only dataIndex, length = next index - this index
            idxs = _col(tbl, entry, len(tbl) // entry, 0, entry)
            for i, idx in enumerate(idxs):
                end = idxs[i + 1] if i + 1 < len(idxs) else len(blob)
                out.append(blob[idx:end].decode("utf-8", "replace"))
        return out

    # ---------- type definitions ----------
    def type_table(self) -> tuple[bytes, int, int]:
        data = self.sec(SEC_TYPE_DEFINITIONS)
        size = self._entry_size(
            SEC_TYPE_DEFINITIONS, range(48, 160, 4),
            lambda sz, n: self._names_ok(data, sz, n, (0, 4)),
        )
        return data, size, len(data) // size

    # ---------- generic "start/count" column finder ----------
    def find_range_columns(self, data: bytes, entry: int, n: int, total: int,
                           skip: set[int] = frozenset()):
        """Find (start_col, count_col) such that the entries' [start, start+count)
        ranges exactly cover 0..total without overlap (in any order).
        Returns ((off,w),(off,w)) or None."""
        cols = {}
        for w in (4, 2):
            for off in range(0, entry - w + 1, 2 if w == 2 else 4):
                if off in skip:
                    continue
                cols[(off, w)] = _col(data, entry, n, off, w)
        counts = [k for k, v in cols.items() if sum(v) == total]
        for ck in counts:
            cv = cols[ck]
            for sk, sv in cols.items():
                if sk[0] == ck[0] or sk[1] < ck[1]:
                    continue
                ranges = sorted((st, c) for st, c in zip(sv, cv) if c)
                pos = 0
                for st, c in ranges:
                    if st != pos:
                        break
                    pos += c
                else:
                    if pos == total:
                        return sk, ck
        return None

    def table_candidates(self, sec_i: int, candidates=range(8, 64, 2)):
        """Possible (data, entry_size, count) for a table whose records start
        with a name index. The caller picks the one that fits the type table."""
        data = self.sec(sec_i)
        sizes = self._entry_sizes(
            sec_i, candidates, lambda sz, n: self._names_ok(data, sz, n, (0,)))
        return [(data, sz, len(data) // sz) for sz in sizes]

    def match_table(self, sec_i, owner: bytes, owner_size: int, owner_count: int,
                    skip: set[int], candidates=range(8, 64, 2)):
        """Find the entry size of table sec_i and the owner's start/count columns."""
        for data, size, count in self.table_candidates(sec_i, candidates):
            if count == 0:
                continue
            cols = self.find_range_columns(owner, owner_size, owner_count, count, skip)
            if cols:
                return data, size, count, cols
        return None


def parse_metadata(data: bytes) -> Metadata:
    p = _Parser(data)

    tdata, tsize, tcount = p.type_table()
    types = [
        TypeInfo(i, p.name(struct.unpack_from("<I", tdata, i * tsize + 4)[0]),
                 p.name(struct.unpack_from("<I", tdata, i * tsize)[0]))
        for i in range(tcount)
    ]

    # Members: methods and fields. Each typedef has start/count columns
    # pointing into these tables; detect them by consistency.
    # (Properties are skipped: their get_X/set_X methods already show them.)
    used: set[int] = {0, 4}
    for sec_i, attr in ((SEC_METHODS, "methods"), (SEC_FIELDS, "fields")):
        try:
            found = p.match_table(sec_i, tdata, tsize, tcount, used)
        except MetadataError as e:
            p.warnings.append(f"{attr}: {e}")
            continue
        if not found:
            p.warnings.append(f"{attr}: không ghép được với type")
            continue
        mdata, msize, _mcount, ((so, sw), (co, cw)) = found
        used |= {so, co}
        starts = _col(tdata, tsize, tcount, so, sw)
        counts = _col(tdata, tsize, tcount, co, cw)
        for t, st, c in zip(types, starts, counts):
            names = getattr(t, attr)
            for j in range(st, st + c):
                names.append(p.name(struct.unpack_from("<I", mdata, j * msize)[0]))

    # Images (assemblies): typeStart/typeCount ranges over the type table.
    assemblies: list[str] = []
    try:
        cols = None
        for idata, isize, icount in p.table_candidates(SEC_IMAGES, range(16, 64, 2)):
            cols = p.find_range_columns(idata, isize, icount, tcount, skip={0})
            if cols:
                break
        if cols:
            (so, sw), (co, cw) = cols
            starts = _col(idata, isize, icount, so, sw)
            counts = _col(idata, isize, icount, co, cw)
            for i in range(icount):
                asm = p.name(struct.unpack_from("<I", idata, i * isize)[0])
                assemblies.append(asm)
                for t in types[starts[i] : starts[i] + counts[i]]:
                    t.assembly = asm
        else:
            p.warnings.append("images: không ghép được với type")
    except MetadataError as e:
        p.warnings.append(f"images: {e}")

    return Metadata(p.version, types, p.string_literals(), assemblies, p.warnings)
