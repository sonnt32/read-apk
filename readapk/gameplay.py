"""Keep only the game's own gameplay code and group it by feature.

Ads are excluded on purpose: ad events come from a separate template.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .il2cpp_metadata import TypeInfo

# Assemblies that are engine / framework / third-party (not game code).
THIRD_PARTY_ASM = (
    "mscorlib", "netstandard", "System", "Mono.", "UnityEngine", "Unity.",
    "Newtonsoft", "DOTween", "DemiLib", "Facebook", "Firebase", "Google",
    "GoogleMobileAds", "AppsFlyer", "Adjust", "MaxSdk", "IronSource",
    "Sirenix", "UniTask", "UniRx", "Zenject", "Spine", "OSA.", "Lean",
    "SolarEngine", "GameAnalytics", "Astra.Ads", "Cinemachine", "Coffee.",
    "I18N", "Purchasing", "Assembly-CSharp-firstpass", "__Generated",
    "Febucci", "MoreMountains", "Obi", "PlayFab", "Photon", "Mirror",
    "Cysharp", "MessagePack", "Bolt", "Ludiq", "Rewired", "AmplifyShader",
    "Lofelt", "NiceVibrations", "Shapes", "Animancer", "Pathfinding",
    "AYellowpaper",
)
# Namespaces inside game assemblies that are still third-party.
THIRD_PARTY_NS = (
    "TMPro", "DG.", "Sirenix", "Spine", "Lean", "Firebase", "GoogleMobileAds",
    "AppsFlyerSDK", "Facebook", "IronSource", "Newtonsoft", "UnityEngine",
    "System", "Unity.", "Cysharp", "Zenject", "Coffee", "MoreMountains",
    "Lofelt", "Astra.Ads", "AmazonAds", "com.", "Google", "SolarEngine",
    "UnityStandardAssets", "Febucci", "IngameDebugConsole", "Kamgam",
    "EpicToonFX", "LayerLab", "AYellowpaper", "ETFX",
)
# Name tokens that mark ad / ad-mediation code (excluded from gameplay).
AD_TOKENS = {"ad", "ads", "banner", "interstitial", "inter", "appopen", "mrec",
             "mediation", "admob", "applovin", "ironsource", "levelplay",
             "ecpm", "waterfall", "adunit", "adsmanager", "native"}
ANALYTICS_RE = re.compile(r"analytic|tracking|tracker|telemetry|logevent|eventlog|"
                          r"firebase|appsflyer|solarengine|gameanalytics", re.I)
UNITY_LIFECYCLE = {"Awake", "Start", "Update", "LateUpdate", "FixedUpdate",
                   "OnEnable", "OnDisable", "OnDestroy", "OnValidate", "Reset",
                   "OnDrawGizmos", "OnDrawGizmosSelected", "Finalize",
                   "ToString", "GetHashCode", "Equals", "Invoke", "BeginInvoke",
                   "EndInvoke", "MoveNext", "Dispose"}

# Feature buckets: first match wins (order matters).
FEATURES = [
    ("Analytics (event có sẵn)", ANALYTICS_RE),
    ("Tutorial / Onboarding", re.compile(r"tutorial|onboard|guide|hint|tooltip|ftue", re.I)),
    ("Level / Progression", re.compile(r"level|stage|chapter|world|map|progress|unlock|star|wave|campaign|episode", re.I)),
    ("Booster / Item / Inventory", re.compile(r"booster|powerup|power_up|item|inventory|consumable|hammer|bomb|magnet|shuffle|undo|freeze", re.I)),
    ("Economy / Currency", re.compile(r"coin|gem|currency|wallet|gold|cash|diamond|energy|heart|live[s]?\b|stamina|economy|resource", re.I)),
    ("Shop / IAP", re.compile(r"shop|store|iap|purchase|offer|bundle|pack|price|vip|subscription|noads", re.I)),
    ("Reward / Retention", re.compile(r"reward|daily|streak|login|spin|wheel|chest|quest|mission|task|achievement|event|season|pass|calendar|gift|bonus", re.I)),
    ("Character / Skin / Upgrade", re.compile(r"skin|character|hero|avatar|outfit|weapon|upgrade|equip|pet|costume|collection", re.I)),
    ("Combat / Core loop", re.compile(r"combat|battle|enemy|boss|attack|damage|health|hp\b|kill|death|die|survive|spawn|player|board|grid|block|tile|piece|match|combo|score|move|puzzle|game(play)?|round|craft|build", re.I)),
    ("Win / Lose / Revive", re.compile(r"win|lose|fail|victory|defeat|revive|continue|gameover|game_over|complete|result", re.I)),
    ("Social / Leaderboard", re.compile(r"leaderboard|friend|social|share|rank|clan|guild|team|pvp|invite|chat", re.I)),
    ("UI / Popup / Screen", re.compile(r"popup|panel|screen|view|window|dialog|menu|hud|button|tab|ui\b|page", re.I)),
    ("Settings / Save / System", re.compile(r"setting|sound|music|vibrat|haptic|language|save|load|data|config|remote|user|profile|session|consent|privacy", re.I)),
]

ANALYTICS_HINT_RE = re.compile(
    r"analytic|\[firebase\]|logevent|log_event|track(ing|er)?\b|solarengine|appsflyer|"
    r"\[af\]|\[adjust\]|user ?property", re.I)
# Standard event / param names of Firebase (GA4), Facebook, IAP, billing SDKs.
SDK_STANDARD = set("""
access_token achievement_id action_type add_payment_info add_shipping_info add_to_cart
add_to_wishlist ad_impression ad_platform ad_source ad_format ad_unit_name app_id app_open
app_version auth_nonce auth_token_string begin_checkout callback_id campaign_details
campaign_id class_name content_description content_title content_type content_url context_id
context_token_id coupon creative_format creative_name creative_slot currency_code
declined_permissions developer_payload earn_virtual_currency end_date error_code error_message
event_name event_type expiration_timestamp flight_number free_trial generate_lead granted_permissions
graph_domain group_id image_uri in_app_purchase item_brand item_category item_category2
item_category3 item_category4 item_category5 item_id item_list_id item_list_name item_name
item_variant join_group level_up location_id marketing_tactic number_of_nights
number_of_passengers number_of_rooms object_id payment_type percent_complete photo_url
player_id post_id post_score price_amount price_amount_micros price_currency_code
product_id product_name promotion_id promotion_name public_profile purchase_platform
purchase_price purchase_time purchase_token quantity_max quantity_min referral_link
remove_from_cart request_id restore_transaction screen_class screen_name screen_view
search_term select_content select_item select_promotion shipping_tier sign_up sign_up_method
signed_request source_platform spend_virtual_currency start_date store_ids subscription_term
target_url transaction_id travel_class tutorial_begin tutorial_complete unlock_achievement
user_id video_id view_cart view_item view_item_list view_promotion view_search_results
virtual_currency_name total_ad_revenue end_time start_time is_unity sdk_type
""".split())
SDK_LIKE_RE = re.compile(
    r"sku|subscription|receipt|entitlement|introductory|payment|purchases?_|_purchase$|"
    r"promotion|permission|token|license|^etfx_|^navigation_|^ks_c|^shift_jis|^iso_|"
    r"^net_|_buffer$|^m_|lambda|_micros|^test_|tournament|^fetch_|^dequeue_|_error$|"
    r"^is_entitlement|^old_|^new_sku|^period_|graph|^context_|^auth_|^sub_lib", re.I)
EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+){1,6}$")
EVENT_IN_TEXT_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,5}\b")
UI_TEXT_RE = re.compile(r"^[A-Z][A-Za-z0-9 ,.!?'%+:\-]{2,60}$")
# Literals that look like event names but come from engines / SDKs.
NOISE_LITERAL = re.compile(
    r"^(unity|gl|vk|sk|unity_|android|com_|google|firebase|fb|af_|ga_|max_|ad_|ads_|"
    r"is_native|set_protocol|request_set|unload_burst|shader|tex|_main|ui_|tmp_|"
    r"dotween|newtonsoft|system_|ios_|webgl|mono|il2cpp|json|xml|utf|sha|md5)", re.I)


def _tokens(name: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", name)]


def is_ad_type(t: TypeInfo) -> bool:
    toks = set(_tokens(t.name)) | set(_tokens(t.namespace.replace(".", " ")))
    if toks & AD_TOKENS - {"native"}:
        return True
    if "native" in toks and ("ad" in toks or "ads" in toks):
        return True
    return "rewarded" in toks and bool(toks & {"video", "ad", "ads"})


def is_game_assembly(asm: str) -> bool:
    if not asm:
        return True
    a = asm[:-4] if asm.endswith(".dll") else asm
    if a.startswith("Assembly-CSharp") and a != "Assembly-CSharp-firstpass":
        return True
    return not any(a.startswith(p) for p in THIRD_PARTY_ASM)


@dataclass
class GameClass:
    full_name: str
    feature: str
    kind: str  # class | enum | interface
    fields: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)  # C# events (add_X/remove_X)


@dataclass
class GameplayView:
    classes: list[GameClass]
    ad_classes_skipped: list[str]
    events_confirmed: list[str]   # seen inside analytics log / doc strings
    events_likely_game: list[str]  # snake_case literals, not SDK-standard
    events_sdk_or_ads: list[str]   # SDK-standard or ad-related (ignored)
    analytics_text_hints: list[str]
    ui_texts: list[str]
    game_assemblies: list[str]


def _is_ad_name(s: str) -> bool:
    toks = set(s.split("_"))
    return bool(toks & (AD_TOKENS | {"inter", "rewarded", "reward_tracking"})) or "_ad" in s


def _clean_fields(fields: list[str]) -> list[str]:
    out = []
    for f in fields:
        m = re.fullmatch(r"<(.+)>k__BackingField", f)
        if m:
            f = m.group(1)
        if f.startswith("<") or f == "value__":
            continue
        if f not in out:
            out.append(f)
    return out


def _clean_methods(methods: list[str]) -> tuple[list[str], list[str]]:
    out, events = [], []
    for m in methods:
        if m.startswith(("<", ".")) or m in UNITY_LIFECYCLE:
            continue
        if "." in m:  # explicit interface implementation
            continue
        if m.startswith(("add_", "remove_")):
            ev = m.split("_", 1)[1]
            if ev not in events:
                events.append(ev)
            continue
        if m not in out:
            out.append(m)
    return out, events


def _feature_of(t: TypeInfo, methods: list[str]) -> str:
    text = f"{t.namespace} {t.name}"
    for name, rx in FEATURES:
        if rx.search(text):
            return name
    joined = " ".join(methods[:40])
    for name, rx in FEATURES[1:]:
        if rx.search(joined):
            return name
    return "Khác"


def build_view(types: list[TypeInfo], literals: list[str], package: str = "") -> GameplayView:
    classes, ads = [], []
    asms: list[str] = []
    # com.company.app -> com.company. (apps often split code across sub-packages)
    package_prefix = ".".join(package.split(".")[:2]) + "." if package.count(".") >= 1 else ""
    for t in types:
        if not is_game_assembly(t.assembly):
            continue
        if "<" in t.name or t.name in ("", "MonoScriptData") or t.name.startswith("UnitySourceGenerated"):
            continue
        is_dex = t.assembly.endswith(".dex")
        if is_dex:
            # native apps: keep only the app's own package (e.g. com.company.*)
            if not package_prefix or not t.full_name.startswith(package_prefix):
                continue
        elif t.namespace.startswith(THIRD_PARTY_NS):
            continue
        # asset-store demo / sample code shipped inside Assembly-CSharp
        if re.search(r"(^|\.)(\w*Demo\w*|\w*Example\w*|\w*Sample\w*|ETFX\w*)(\.|$)",
                     t.namespace) or re.search(r"(Demo|Example|Sample)", t.name):
            continue
        if is_ad_type(t):
            ads.append(t.full_name)
            continue
        if t.assembly and t.assembly not in asms:
            asms.append(t.assembly)
        is_enum = "value__" in t.fields
        methods, events = _clean_methods(t.methods)
        fields = [f for f in _clean_fields(t.fields)]
        if not is_enum and not methods and not fields and not events:
            continue
        kind = "enum" if is_enum else (
            "interface" if not t.fields and re.match(r"I[A-Z]", t.name) else "class")
        classes.append(GameClass(t.full_name, _feature_of(t, methods), kind,
                                 fields, methods, events))

    snake: list[str] = []
    hints: list[str] = []
    ui: list[str] = []
    for s in literals:
        s = s.strip()
        if not s:
            continue
        if EVENT_NAME_RE.match(s) and len(s) <= 40 and not NOISE_LITERAL.match(s):
            if s not in snake:
                snake.append(s)
        elif ANALYTICS_HINT_RE.search(s) and len(s) < 2000:
            if not s.startswith(("Firebase.", "UnityEngine.", "System.")) and s not in hints:
                hints.append(s)
        elif UI_TEXT_RE.match(s) and " " in s and len(ui) < 400:
            if any(rx.search(s) for _, rx in FEATURES[1:11]) and s not in ui:
                ui.append(s)

    # Event names mentioned inside analytics log/doc strings are confirmed.
    mentioned: set[str] = set()
    for h in hints:
        mentioned |= set(EVENT_IN_TEXT_RE.findall(h))
    confirmed, likely, sdk = [], [], []
    for s in snake:
        if _is_ad_name(s):
            sdk.append(s)
        elif s in mentioned:
            confirmed.append(s)
        elif s in SDK_STANDARD or SDK_LIKE_RE.search(s):
            sdk.append(s)
        else:
            likely.append(s)
    for s in sorted(mentioned - set(snake)):
        if not _is_ad_name(s) and not NOISE_LITERAL.match(s) and len(s) <= 40:
            confirmed.append(s)

    order = {name: i for i, (name, _) in enumerate(FEATURES)}
    order["Khác"] = len(order)
    classes.sort(key=lambda c: (order[c.feature], c.full_name))
    return GameplayView(classes, ads, confirmed, likely, sdk, hints, ui, asms)
