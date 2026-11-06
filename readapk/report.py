"""Write the extracted game structure as Markdown (for Claude / humans) + JSON."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import asdict

from .apk import AppCode
from .gameplay import GameplayView

MAX_METHODS = 60
MAX_FIELDS = 40


def _cap(items: list[str], n: int) -> str:
    s = ", ".join(items[:n])
    return s + (f", … (+{len(items) - n})" if len(items) > n else "")


def write_reports(app: AppCode, view: GameplayView, out_dir: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    m = app.manifest or {}
    L: list[str] = []
    w = L.append

    w(f"# Game profile: {m.get('package') or os.path.basename(app.source)}")
    w("")
    w(f"- File: `{os.path.basename(app.source)}`")
    w(f"- Package: `{m.get('package', '?')}` — version {m.get('versionName', '?')} ({m.get('versionCode', '?')})")
    w(f"- Engine: **{app.engine}**" + (f" (IL2CPP metadata v{app.metadata_version})" if app.metadata_version else ""))
    w(f"- SDK phát hiện: {', '.join(app.sdks) or '—'}")
    w(f"- Assembly của game: {', '.join(view.game_assemblies) or '—'}")
    w(f"- Số class gameplay: {len(view.classes)} (đã bỏ {len(view.ad_classes_skipped)} class quảng cáo)")
    if app.warnings:
        w(f"- Cảnh báo: " + "; ".join(app.warnings))
    w("")

    if app.scenes:
        w("## Scenes")
        for s in app.scenes:
            w(f"- `{s}`")
        w("")

    w("## Event / parameter có sẵn trong code")
    w("")
    w("### Đã xác nhận (xuất hiện trong log/ghi chú analytics)")
    w(", ".join(f"`{e}`" for e in view.events_confirmed) or "—")
    w("")
    w("### Nhiều khả năng của game (snake_case, không phải tên chuẩn của SDK)")
    w("Gồm cả tên event, tên parameter, key PlayerPrefs/Remote Config — cần đối chiếu.")
    w("")
    w(", ".join(f"`{e}`" for e in view.events_likely_game) or "—")
    w("")
    if view.analytics_text_hints:
        w("### Chuỗi log / ghi chú analytics trong code")
        for h in view.analytics_text_hints[:150]:
            w(f"- {h.replace(chr(10), ' ')}")
        w("")

    by_feature: dict[str, list] = defaultdict(list)
    for c in view.classes:
        by_feature[c.feature].append(c)

    w("## Code gameplay theo tính năng")
    for feature, classes in by_feature.items():
        w("")
        w(f"### {feature} ({len(classes)})")
        enums = [c for c in classes if c.kind == "enum"]
        for c in classes:
            if c.kind == "enum":
                continue
            w(f"- **{c.full_name}**" + (" _(interface)_" if c.kind == "interface" else ""))
            if c.events:
                w(f"  - C# events: {_cap(c.events, MAX_METHODS)}")
            if c.methods:
                w(f"  - methods: {_cap(c.methods, MAX_METHODS)}")
            if c.fields:
                w(f"  - fields: {_cap(c.fields, MAX_FIELDS)}")
        if enums:
            w(f"- Enums:")
            for c in enums:
                w(f"  - **{c.full_name}**: {_cap(c.fields, MAX_FIELDS)}")

    if view.ad_classes_skipped:
        w("")
        w("## Class quảng cáo đã bỏ qua")
        w(_cap(view.ad_classes_skipped, 200))
    if view.events_sdk_or_ads:
        w("")
        w("## Tên chuẩn SDK / ads đã bỏ qua")
        w(", ".join(f"`{e}`" for e in view.events_sdk_or_ads))

    md_path = os.path.join(out_dir, "game_profile.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    json_path = os.path.join(out_dir, "game_structure.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": os.path.basename(app.source),
            "engine": app.engine,
            "metadata_version": app.metadata_version,
            "manifest": m,
            "sdks": app.sdks,
            "scenes": app.scenes,
            "warnings": app.warnings,
            "events_confirmed": view.events_confirmed,
            "events_likely_game": view.events_likely_game,
            "events_sdk_or_ads": view.events_sdk_or_ads,
            "analytics_text_hints": view.analytics_text_hints,
            "classes": [asdict(c) for c in view.classes],
            "ad_classes_skipped": view.ad_classes_skipped,
        }, f, ensure_ascii=False, indent=1)

    lit_path = os.path.join(out_dir, "all_string_literals.txt")
    with open(lit_path, "w", encoding="utf-8") as f:
        for s in app.string_literals:
            f.write(s.replace("\n", "\\n") + "\n")

    return {"profile": md_path, "json": json_path, "literals": lit_path}
