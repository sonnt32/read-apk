"""Build the tracking-plan Excel for one game from the Data Foundation template.

Input:  plan JSON (gameplay design for this game, see prompts/gameplay_tracking_prompt.md)
        + Data Foundation xlsx (company master template)
Output: one .xlsx with a single sheet "Tracking Plan": event groups, user
        properties, and a notes section explaining every standard event that
        is not used (reason from plan["excluded_events"]). Lint goes to the console.

Lifecycle and Ads groups are always copied unchanged from the Foundation.
IAP group is added when the plan says the game has IAP.

Usage: python -m readapk.plan plan.json [-f "Data Foundation (1).xlsx"] [-o out.xlsx]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from dataclasses import dataclass, field

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

DEFAULT_FOUNDATION = "Data Foundation (1).xlsx"

# Fixes to the Foundation agreed with the DA team (applied when reading it).
EVENT_RENAMES = {"asset_equid": "asset_equip"}
PARAM_TYPE_FIXES = {("loading_completed", "duration"): "String"}

AUTO_EVENTS = {"first_open", "session_start", "screen_view", "ad_impression",
               "in_app_purchase", "app_remove", "user_engagement"}
DOUBLE_PARAMS = {"value", "value_in_usd", "price"}
VERB_FIRST = {"earn", "spend", "get", "click", "tap", "show", "open", "close", "start",
              "end", "complete", "fail", "win", "lose", "use", "buy", "unlock", "claim",
              "watch", "select", "enter", "exit", "view"}
POSITION_NAMES = {"position", "location", "pos", "place", "where", "from_screen", "source_screen"}

# Colors (Governance sheet rule + Foundation header style)
RED, YELLOW, GREEN = "FFF4CCCC", "FFFFF2CC", "FFD9EAD3"
STATUS_FILL = {"red": RED, "yellow": YELLOW, "green": GREEN,
               "Sai": RED, "Sửa": YELLOW, "Giữ": GREEN}
HEADER_FILL, GROUP_FILL, BLUE_HEADER = "FFC0504D", "FFF2DCDB", "FF1F4E79"
THIN = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


@dataclass
class Param:
    name: str
    type: str = "String"
    values: str = ""
    metric: str = ""


@dataclass
class Event:
    group: str
    tier: str
    event: str
    source: str = "CUSTOM"
    question: str = ""
    trigger: str = ""
    params: list[Param] = field(default_factory=list)
    code_location: str = ""
    priority: str = ""
    status: str = "Mới"  # Mới | Giữ | Sửa | Sai | Template
    note: str = ""


# ---------------------------------------------------------------- Foundation
def _s(v) -> str:
    return "" if v is None else str(v).strip()


def read_foundation_events(path: str) -> list[tuple[str, list[Event]]]:
    """Return [(group_title, [Event...])] from the Foundation 'Events' sheet."""
    ws = openpyxl.load_workbook(path, data_only=True)["Events"]
    groups: list[tuple[str, list[Event]]] = []
    cur_group_name, cur_tier = "", ""
    ev: Event | None = None
    for row in ws.iter_rows(min_row=3, max_col=10, values_only=True):
        a, b, c, d, e, f, g, h, i, j = (_s(x) for x in row)
        if a.upper().startswith("NHÓM"):
            groups.append((a, []))
            ev = None
            continue
        if not groups:
            continue
        if a:
            cur_group_name = a
        if b:
            cur_tier = b
        if c:
            name = EVENT_RENAMES.get(c, c)
            ev = Event(cur_group_name, cur_tier, name, d or "CUSTOM", e, f,
                       status="Template")
            groups[-1][1].append(ev)
        if ev is None:
            continue
        if g and g not in ("—", "-"):
            typ = PARAM_TYPE_FIXES.get((ev.event, g), h or "String")
            ev.params.append(Param(g, typ, i, j))
        elif not g and (i or j) and not ev.params:
            ev.note = "; ".join(x for x in (i, j) if x)
        elif ev.params and not g and (i or j):
            ev.params[-1].values += ("\n" + i) if i else ""
    return groups


def group_kind(title: str) -> str:
    t = title.upper()
    if "LIFECYCLE" in t:
        return "lifecycle"
    if "ADS" in t:
        return "ads"
    if "IAP" in t:
        return "iap"
    return "gameplay"


# ---------------------------------------------------------------- plan JSON
def _params(items) -> list[Param]:
    out = []
    for p in items or []:
        out.append(Param(p["name"], p.get("type", "String"), p.get("values", ""),
                         p.get("metric", "")))
    return out


MISSING_REASON = "CHƯA CÓ LÝ DO — DA cần bổ sung"


def merge_plan(foundation, plan: dict):
    """Combine Foundation groups with the game's plan.

    Returns (groups, excluded) where excluded = [(event, reason)] lists every
    standard gameplay/IAP event that is not used, with the reason from the plan.
    """
    std_by_name = {}
    for title, evs in foundation:
        for e in evs:
            std_by_name[e.event] = (title, e)

    chosen = {s["event"]: s for s in plan.get("standard_events", [])}
    unknown = [n for n in chosen if n not in std_by_name]
    if unknown:
        print("WARN: standard_events không có trong Foundation:", unknown, file=sys.stderr)
    reasons = plan.get("excluded_events", {})

    out: list[tuple[str, list[Event]]] = []
    excluded: list[tuple[str, str]] = []
    include_iap = plan.get("include_iap", False)
    for title, evs in foundation:
        kind = group_kind(title)
        if kind == "iap" and not include_iap:
            for e in evs:
                excluded.append((e.event, reasons.get(e.event) or reasons.get("iap")
                                 or "Game không có IAP"))
            continue
        rows = []
        for e in evs:
            if kind in ("lifecycle", "ads"):
                rows.append(copy.deepcopy(e))  # copied unchanged
                continue
            s = chosen.get(e.event)
            if kind == "iap" and s is None:
                s = {}
            if s is None:
                excluded.append((e.event, reasons.get(e.event, MISSING_REASON)))
                continue
            ne = copy.deepcopy(e)
            if e.source.upper().startswith("AUTO"):
                rows.append(ne)  # auto events stay as in the template
                continue
            overrides = s.get("param_values", {})
            for p in ne.params:
                names = re.split(r"\s*/\s*", p.name)
                for key, val in overrides.items():
                    if key in names:
                        p.values = val if len(names) == 1 else \
                            "\n".join(x for x in (p.values, f"{key}: {val}") if x)
            ne.params += _params(s.get("extra_params"))
            if s.get("trigger"):
                ne.trigger = s["trigger"]
            ne.code_location = s.get("code_location", "")
            ne.priority = s.get("priority", "")
            ne.status = s.get("status", "Mới")
            ne.note = "; ".join(x for x in (ne.note, s.get("note", "")) if x)
            rows.append(ne)
        if rows:
            out.append((title, rows))

    custom = [
        Event(c.get("group", "Game-specific"), c.get("tier", "T3"), c["event"], "CUSTOM",
              c.get("question", ""), c.get("trigger", ""), _params(c.get("params")),
              c.get("code_location", ""), c.get("priority", ""), c.get("status", "Mới"),
              c.get("note", ""))
        for c in plan.get("custom_events", [])
    ]
    if custom:
        out.append(("NHÓM 7 — GAME-SPECIFIC (TIER 3): event riêng của game này", custom))

    # Notes about events already in the game go into the matching event's note.
    by_name = {e.event: e for _, evs in out for e in evs}
    for m in plan.get("existing_mapping", []):
        targets = re.findall(r"[a-z][a-z0-9_]+", m.get("new_event", ""))
        msg = f"Đang có '{m.get('old_event')}': {m.get('note', '')}".strip()
        for t in targets:
            if t in by_name and msg not in by_name[t].note:
                by_name[t].note = "\n".join(x for x in (by_name[t].note, msg) if x)
    return out, excluded


# ---------------------------------------------------------------- lint
def lint(groups, plan: dict) -> list[tuple[str, str, str]]:
    """Check designed events against Governance rules. Returns (level, event, message)."""
    issues = []
    std_names = {e.event for _, evs in groups for e in evs if e.status == "Template"}
    for title, evs in groups:
        if group_kind(title) in ("lifecycle", "ads"):
            continue
        for e in evs:
            n = e.event
            if e.source.upper().startswith("AUTO"):
                continue  # auto events from the template (e.g. in_app_purchase)
            if not re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", n):
                issues.append(("Sai", n, "Tên event phải snake_case, chữ thường"))
            if len(n) > 40:
                issues.append(("Sai", n, "Tên event dài hơn 40 ký tự"))
            if n in AUTO_EVENTS:
                issues.append(("Sai", n, "Trùng tên auto event"))
            if n.split("_")[0] in VERB_FIRST:
                issues.append(("Sửa", n, "Nên đặt module trước, động từ sau (module_action)"))
            if re.search(r"_\d+(_|$)", n):
                issues.append(("Sửa", n, "Có số trong tên event — có thể đang hardcode nội dung, nên đưa vào param"))
            if e.status != "Template" and not e.question and group_kind(title) == "gameplay" \
                    and n not in std_names and e.tier == "T3":
                issues.append(("Sai", n, "Event Tier 3 thiếu 'Câu hỏi kinh doanh' (Nguyên tắc 1)"))
            if len(e.params) > 25:
                issues.append(("Sai", n, "Quá 25 param"))
            for p in e.params:
                names = re.split(r"\s*/\s*", p.name)
                types = re.split(r"\s*/\s*", p.type.lower())
                if len(types) != len(names):
                    types = [types[0]] * len(names)
                for pn, t in zip(names, types):
                    if pn in DOUBLE_PARAMS and t != "double":
                        issues.append(("Sai", n, f"Param {pn} là doanh thu → phải Double"))
                    elif pn not in DOUBLE_PARAMS and t not in ("string", "—", ""):
                        issues.append(("Sửa", n, f"Param {pn} kiểu {p.type} → event param nên là String"))
                    if pn in POSITION_NAMES:
                        issues.append(("Sửa", n, f"Param {pn} chỉ vị trí → đổi thành placement"))
                is_bool = re.match(r"\s*true\s*\|\s*false\b", p.values.lower())
                if "|" in p.values and "other" not in p.values.lower() and not is_bool:
                    issues.append(("Sửa", n, f"Enum của {p.name} thiếu giá trị 'other'"))
    for up in plan.get("user_properties", []):
        if up.get("type", "").lower() not in ("string", "int"):
            issues.append(("Sửa", up.get("property", "?"), "User property chỉ nên String hoặc Int"))
    return issues


# ---------------------------------------------------------------- writing
def _style_header(ws, row: int, ncol: int, color=HEADER_FILL):
    for c in range(1, ncol + 1):
        cell = ws.cell(row, c)
        cell.font = Font(bold=True, color="FFFFFFFF")
        cell.fill = PatternFill("solid", fgColor=color)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BORDER


def _title(ws, text: str, sub: str = ""):
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=14)
    if sub:
        ws["A2"] = sub
        ws["A2"].font = Font(italic=True, color="FF595959")


def write_tracking_plan(ws, groups):
    _title(ws, "TRACKING PLAN", "Nhóm 1–2 copy nguyên từ Data Foundation. Trạng thái: Template = chuẩn công ty | "
                                "Mới = cần implement | Giữ/Sửa/Sai = đối chiếu event đang có (xanh/vàng/đỏ).")
    headers = ["Nhóm", "Tier", "Event", "Nguồn", "Câu hỏi kinh doanh", "Trigger", "Param",
               "Data Type", "Values / Ý nghĩa", "Metric phụ thuộc", "Vị trí code (gợi ý)",
               "Ưu tiên", "Trạng thái", "Implemented?", "Android", "iOS", "Ghi chú"]
    widths = [18, 7, 26, 14, 42, 45, 30, 10, 50, 36, 34, 8, 11, 12, 9, 9, 36]
    hr = 3
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(hr, i, h)
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    _style_header(ws, hr, len(headers))
    ws.freeze_panes = "D4"
    r = hr + 1
    event_cols = (1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 16, 17)
    for title, evs in groups:
        ws.cell(r, 1, title)
        for c in range(1, len(headers) + 1):
            ws.cell(r, c).fill = PatternFill("solid", fgColor=GROUP_FILL)
            ws.cell(r, c).font = Font(bold=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        r += 1
        for e in evs:
            params = e.params or [Param("—", "—", "", "")]
            start = r
            vals = {1: e.group, 2: e.tier, 3: e.event, 4: e.source, 5: e.question,
                    6: e.trigger, 11: e.code_location, 12: e.priority, 13: e.status,
                    17: e.note}
            for c, v in vals.items():
                ws.cell(start, c, v)
            for p in params:
                ws.cell(r, 7, p.name)
                ws.cell(r, 8, p.type)
                ws.cell(r, 9, p.values)
                ws.cell(r, 10, p.metric)
                r += 1
            end = r - 1
            fill = STATUS_FILL.get(e.status)
            for rr in range(start, end + 1):
                for c in range(1, len(headers) + 1):
                    cell = ws.cell(rr, c)
                    cell.alignment = WRAP
                    cell.border = BORDER
                    if fill and c in (3, 13):
                        cell.fill = PatternFill("solid", fgColor=fill)
            ws.cell(start, 3).font = Font(bold=True)
            if end > start:
                for c in event_cols:
                    ws.merge_cells(start_row=start, start_column=c, end_row=end, end_column=c)


def user_property_rows(foundation_path: str, plan: dict) -> tuple[list[Event], list[tuple[str, str]]]:
    """User properties (Foundation standard + game-specific) as rows of the plan."""
    src = openpyxl.load_workbook(foundation_path, data_only=True)["User Properties"]
    reasons = plan.get("excluded_events", {})
    skip = set(plan.get("skip_user_properties", []))
    if not plan.get("level_based", True):
        skip.add("current_level")
    rows, excluded = [], []
    for tier, prop, typ, meaning, when, values, note in src.iter_rows(
            min_row=4, max_col=7, values_only=True):
        if not prop:
            continue
        if prop in skip:
            excluded.append((f"{prop} (user property)", reasons.get(prop, MISSING_REASON)))
            continue
        rows.append(Event("User Property", _s(tier), _s(prop), "USER PROPERTY", _s(meaning),
                          _s(when), [Param("—", _s(typ), _s(values), "")],
                          status="Template", note=_s(note)))
    for up in plan.get("user_properties", []):
        rows.append(Event("User Property", up.get("tier", "T3"), up["property"], "USER PROPERTY",
                          up.get("meaning", ""), up.get("update_when", ""),
                          [Param("—", up.get("type", "String"), up.get("values", ""), "")],
                          up.get("code_location", ""), up.get("priority", ""),
                          up.get("status", "Mới"), up.get("note", "")))
    return rows, excluded


def write_notes(ws, start_row: int, excluded: list[tuple[str, str]], ncol: int) -> int:
    """Section listing standard events / properties left out, with the reason."""
    r = start_row + 1
    ws.cell(r, 1, "GHI CHÚ — EVENT / USER PROPERTY CHUẨN KHÔNG ĐƯA VÀO TRACKING (và lý do)")
    for c in range(1, ncol + 1):
        ws.cell(r, c).fill = PatternFill("solid", fgColor=GROUP_FILL)
        ws.cell(r, c).font = Font(bold=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    r += 1
    for name, reason in excluded:
        ws.cell(r, 1, "Không áp dụng")
        ws.cell(r, 3, name).font = Font(bold=True)
        ws.cell(r, 5, reason)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=ncol)
        for c in range(1, ncol + 1):
            cell = ws.cell(r, c)
            cell.alignment = WRAP
            cell.border = BORDER
            cell.fill = PatternFill("solid", fgColor="FFEFEFEF")
        if reason == MISSING_REASON:
            ws.cell(r, 5).fill = PatternFill("solid", fgColor=YELLOW)
        r += 1
    return r


def build_plan_xlsx(plan: dict, foundation_path: str, out_path: str) -> list:
    foundation = read_foundation_events(foundation_path)
    groups, excluded = merge_plan(foundation, plan)
    issues = lint(groups, plan)
    up_rows, up_excluded = user_property_rows(foundation_path, plan)
    groups.append(("NHÓM 8 — USER PROPERTIES (tối đa 25 — giới hạn Firebase)", up_rows))
    excluded += up_excluded
    issues += [("Sửa", n, "Event chuẩn bị loại nhưng chưa ghi lý do (excluded_events)")
               for n, why in excluded if why == MISSING_REASON]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tracking Plan"
    write_tracking_plan(ws, groups)
    write_notes(ws, ws.max_row, excluded, 17)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    wb.save(out_path)
    return issues


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="readapk.plan")
    ap.add_argument("plan_json")
    ap.add_argument("-f", "--foundation", default=DEFAULT_FOUNDATION)
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    with open(args.plan_json, encoding="utf-8") as f:
        plan = json.load(f)
    out = args.out or os.path.join(os.path.dirname(args.plan_json),
                                   f"tracking_plan_{plan.get('game', {}).get('package', 'game')}.xlsx")
    issues = build_plan_xlsx(plan, args.foundation, out)
    print(f"Saved: {out}")
    print(f"Lint: {len(issues)} vấn đề")
    for lvl, ev, msg in issues:
        print(f"  [{lvl}] {ev}: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
