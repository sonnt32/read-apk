"""Open an APK / XAPK / APKS, detect the engine and extract code structure."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from .axml import parse_manifest
from .dex import parse_dex
from .il2cpp_metadata import MetadataError, TypeInfo, parse_metadata

METADATA_PATH = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
MANAGED_DIR = "assets/bin/Data/Managed/"
SCENE_RE = re.compile(rb"Assets/[\w\-/. ()]{1,200}?\.unity")

# Signatures to name SDKs found in the app (assembly, DEX package, .so name).
SDK_SIGNATURES = {
    "Firebase Analytics": ["Firebase.Analytics", "com.google.firebase.analytics"],
    "Firebase Remote Config": ["Firebase.RemoteConfig", "com.google.firebase.remoteconfig"],
    "Firebase Crashlytics": ["Firebase.Crashlytics", "com.google.firebase.crashlytics"],
    "AppsFlyer": ["AppsFlyer", "com.appsflyer"],
    "Adjust": ["com.adjust.sdk", "AdjustSdk"],
    "Facebook SDK": ["Facebook.Unity", "com.facebook.FacebookSdk"],
    "Google AdMob": ["GoogleMobileAds", "com.google.android.gms.ads"],
    "AppLovin MAX": ["MaxSdk", "com.applovin"],
    "IronSource / LevelPlay": ["IronSource", "com.ironsource", "com.unity3d.mediation"],
    "Unity Ads": ["UnityEngine.Advertisements", "com.unity3d.ads"],
    "Unity IAP": ["Unity.Purchasing", "UnityEngine.Purchasing"],
    "Google Play Billing": ["com.android.billingclient"],
    "GameAnalytics": ["GameAnalytics", "com.gameanalytics"],
    "SolarEngine": ["SolarEngine", "com.reyun.solar"],
    "Unity Analytics": ["Unity.Services.Analytics"],
    "Play Games Services": ["GooglePlayGames", "com.google.android.gms.games"],
}


@dataclass
class AppCode:
    source: str
    engine: str = "unknown"
    manifest: dict = field(default_factory=dict)
    types: list[TypeInfo] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    assemblies: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)
    sdks: list[str] = field(default_factory=list)
    metadata_version: int | None = None
    warnings: list[str] = field(default_factory=list)


def _open_all(path: str) -> list[zipfile.ZipFile]:
    """Return the APK zip(s). XAPK/APKS bundles contain several APKs."""
    outer = zipfile.ZipFile(path)
    inner = [n for n in outer.namelist() if n.lower().endswith(".apk")]
    if not inner:
        return [outer]
    zips = [zipfile.ZipFile(io.BytesIO(outer.read(n))) for n in inner]
    # base APK first
    zips.sort(key=lambda z: "AndroidManifest.xml" not in z.namelist() or
              not any(x.startswith("assets/") for x in z.namelist()))
    return zips


def _find(zips, name):
    for z in zips:
        if name in z.namelist():
            return z.read(name)
    return None


def _names(zips) -> list[str]:
    return [n for z in zips for n in z.namelist()]


def read_apk(path: str) -> AppCode:
    zips = _open_all(path)
    names = _names(zips)
    app = AppCode(source=path)

    man = _find(zips, "AndroidManifest.xml")
    if man:
        try:
            app.manifest = parse_manifest(man)
        except Exception as e:  # manifest is nice-to-have
            app.warnings.append(f"manifest: {e}")

    has = lambda pat: any(pat in n for n in names)
    if has("libil2cpp.so") or METADATA_PATH in names:
        app.engine = "unity-il2cpp"
    elif has(MANAGED_DIR + "Assembly-CSharp.dll"):
        app.engine = "unity-mono"
    elif has("libcocos"):
        app.engine = "cocos"
    elif has("libflutter.so"):
        app.engine = "flutter"
    elif has("libgodot"):
        app.engine = "godot"
    else:
        app.engine = "native-android"

    if app.engine == "unity-il2cpp":
        _read_il2cpp(zips, app)
    elif app.engine == "unity-mono":
        _read_mono(zips, names, app)
    else:
        _read_dex(zips, names, app)
        if app.engine in ("cocos", "flutter", "godot"):
            app.warnings.append(
                f"Engine {app.engine}: logic game nằm ngoài DEX (script/bytecode riêng), "
                "hiện mới đọc phần Java/Kotlin.")

    if app.engine.startswith("unity"):
        _read_scenes(zips, names, app)

    _detect_sdks(zips, names, app)
    return app


def _read_il2cpp(zips, app: AppCode):
    data = _find(zips, METADATA_PATH)
    if data is None:
        app.warnings.append("Không thấy global-metadata.dat (có thể bị đổi tên/ẩn).")
        return
    try:
        md = parse_metadata(data)
    except MetadataError as e:
        app.warnings.append(str(e))
        return
    app.metadata_version = md.version
    app.types = md.types
    app.string_literals = md.string_literals
    app.assemblies = md.assemblies
    app.warnings += md.warnings


def _read_mono(zips, names, app: AppCode):
    try:
        import dnfile  # optional dependency
    except ImportError:
        app.warnings.append("Game Unity Mono: cần `pip install dnfile` để đọc DLL.")
        return
    idx = 0
    for n in names:
        if not (n.startswith(MANAGED_DIR) and n.endswith(".dll")):
            continue
        asm = n.rsplit("/", 1)[-1]
        app.assemblies.append(asm)
        try:
            pe = dnfile.dnPE(data=_find(zips, n))
        except Exception as e:
            app.warnings.append(f"{asm}: {e}")
            continue
        tables = pe.net.mdtables if pe.net else None
        if not tables or not tables.TypeDef:
            continue
        for row in tables.TypeDef:
            t = TypeInfo(idx, str(row.TypeNamespace or ""), str(row.TypeName or ""), asm)
            t.fields = [str(f.row.Name) for f in (row.FieldList or []) if f.row]
            t.methods = [str(m.row.Name) for m in (row.MethodList or []) if m.row]
            app.types.append(t)
            idx += 1
        us = pe.net.user_strings if pe.net else None
        if us is not None and asm.startswith("Assembly-CSharp"):
            app.string_literals += _user_strings(getattr(us, "__data__", b"") or b"")


def _user_strings(heap: bytes) -> list[str]:
    """Decode the .NET #US heap: [compressed length][utf-16 bytes][1 flag byte]."""
    out, p = [], 1
    while p < len(heap):
        b = heap[p]
        if b & 0x80 == 0:
            n, p = b, p + 1
        elif b & 0xC0 == 0x80:
            n, p = ((b & 0x3F) << 8) | heap[p + 1], p + 2
        else:
            n = ((b & 0x1F) << 24) | (heap[p + 1] << 16) | (heap[p + 2] << 8) | heap[p + 3]
            p += 4
        if n == 0:
            continue
        s = heap[p : p + n - 1].decode("utf-16-le", "replace")
        if s:
            out.append(s)
        p += n
    return out


def _read_dex(zips, names, app: AppCode):
    idx = 0
    for z in zips:
        for n in z.namelist():
            if not re.fullmatch(r"classes\d*\.dex", n):
                continue
            classes, strings = parse_dex(z.read(n))
            app.string_literals += strings
            for cname, methods in classes.items():
                ns, _, short = cname.rpartition(".")
                t = TypeInfo(idx, ns, short, n)
                t.methods = methods
                app.types.append(t)
                idx += 1


def _read_scenes(zips, names, app: AppCode):
    found: list[str] = []
    for n in names:
        if n.startswith("assets/bin/Data/") and (
            n.endswith("globalgamemanagers") or n.endswith("data.unity3d")
            or n.endswith("mainData")):
            for m in SCENE_RE.findall(_find(zips, n) or b""):
                s = m.decode("utf-8", "replace")
                if s not in found:
                    found.append(s)
    app.scenes = found


def _detect_sdks(zips, names, app: AppCode):
    hay = set(app.assemblies) | {t.namespace for t in app.types}
    hay |= {n.rsplit("/", 1)[-1] for n in names if n.endswith(".so")}
    # Unity games: Java SDK packages live in DEX, scan class names cheaply.
    dex_pkgs: set[str] = set()
    if app.engine.startswith("unity"):
        for z in zips:
            for n in z.namelist():
                if re.fullmatch(r"classes\d*\.dex", n):
                    d = z.read(n)
                    for sig in SDK_SIGNATURES.values():
                        for s in sig:
                            if "." in s and ("L" + s.replace(".", "/")).encode() in d:
                                dex_pkgs.add(s)
    for sdk, sigs in SDK_SIGNATURES.items():
        if any(s in dex_pkgs or any(h.startswith(s) or s in h for h in hay) for s in sigs):
            app.sdks.append(sdk)
