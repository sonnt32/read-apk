"""Usage: python -m readapk <file.apk|.xapk|.apks> [-o OUT_DIR]"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .apk import read_apk
from .gameplay import build_view
from .report import write_reports


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="readapk", description="Đọc APK và trích xuất code gameplay.")
    ap.add_argument("apk")
    ap.add_argument("-o", "--out", help="thư mục output (mặc định: out/<tên apk>)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    t0 = time.time()
    app = read_apk(args.apk)
    pkg = app.manifest.get("package", "") if app.engine == "native-android" else ""
    view = build_view(app.types, app.string_literals, pkg)
    stem = os.path.splitext(os.path.basename(args.apk))[0]
    out = args.out or os.path.join("out", stem)
    paths = write_reports(app, view, out)

    print(f"Engine: {app.engine}  package: {app.manifest.get('package', '?')}")
    print(f"Types: {len(app.types)}  gameplay classes: {len(view.classes)}  "
          f"ad classes skipped: {len(view.ad_classes_skipped)}")
    print(f"Existing events: {len(view.events_confirmed)} confirmed, "
          f"{len(view.events_likely_game)} likely game, "
          f"{len(view.events_sdk_or_ads)} SDK/ads skipped")
    print(f"SDKs: {', '.join(app.sdks) or '-'}")
    for wmsg in app.warnings:
        print("WARN:", wmsg)
    for k, p in paths.items():
        print(f"{k}: {p}")
    print(f"Done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
