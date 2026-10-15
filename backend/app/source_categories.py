from typing import Final


SOURCE_LEVEL_1_CODES: Final[tuple[str, ...]] = (
    "field_sales",
    "online",
    "offline",
    "event",
    "referral",
    "other",
)

SOURCE_LEVEL_1_LABELS: Final[dict[str, str]] = {
    "field_sales": "地推",
    "online": "线上",
    "offline": "线下",
    "event": "活动",
    "referral": "转介绍",
    "other": "其他",
}

SOURCE_LEVEL_2_OPTIONS: Final[dict[str, list[dict[str, str]]]] = {
    "field_sales": [
        {"code": "field_sales_group_1", "name": "地推一组"},
        {"code": "field_sales_group_2", "name": "地推二组"},
        {"code": "field_sales_other", "name": "其他地推"},
    ],
    "online": [
        {"code": "wechat", "name": "微信"},
        {"code": "xiaohongshu", "name": "小红书"},
        {"code": "douyin", "name": "抖音"},
        {"code": "online_other", "name": "其他线上"},
    ],
    "offline": [
        {"code": "store_visit", "name": "门店到访"},
        {"code": "community_promotion", "name": "社区推广"},
        {"code": "offline_other", "name": "其他线下"},
    ],
    "event": [
        {"code": "free_clinic", "name": "义诊"},
        {"code": "health_lecture", "name": "健康讲座"},
        {"code": "event_other", "name": "其他活动"},
    ],
    "referral": [
        {"code": "patient_referral", "name": "老患者转介绍"},
        {"code": "doctor_referral", "name": "医生转介绍"},
        {"code": "partner_referral", "name": "合作机构转介绍"},
    ],
    "other": [
        {"code": "unknown", "name": "来源不明"},
        {"code": "custom", "name": "自定义"},
    ],
}

SOURCE_LEVEL_1_OPTIONS: Final[list[dict[str, str]]] = [
    {"code": code, "name": SOURCE_LEVEL_1_LABELS[code]}
    for code in SOURCE_LEVEL_1_CODES
]

# Existing callers use this name. It now represents first-level options.
SOURCE_CATEGORY_OPTIONS = SOURCE_LEVEL_1_OPTIONS

SOURCE_CATEGORY_LABELS: Final[dict[str, str]] = {
    **SOURCE_LEVEL_1_LABELS,
    "third_party_referral": "转介绍",
    "external": "其他",
}

_LEGACY_SOURCE_MAP: dict[str, str] = {
    "地推": "field_sales", "field_sales": "field_sales",
    "线上": "online", "online": "online", "小红书": "online", "抖音": "online", "公众号": "online", "企业微信": "online",
    "线下": "offline", "offline": "offline", "自然到店": "offline", "到店": "offline", "线下到店": "offline",
    "活动": "event", "event": "event",
    "第三方转介绍": "referral", "third_party_referral": "referral", "老客转介绍": "referral", "转介绍": "referral",
    "外部来源": "other", "external": "other",
    "其它": "other", "其他": "other", "other": "other",
}


def normalize_source_level_1(value: str | None) -> str:
    if not value:
        return "other"
    raw = value.strip()
    return _LEGACY_SOURCE_MAP.get(raw) or _LEGACY_SOURCE_MAP.get(raw.lower(), "other")


def normalize_source_category(value: str | None) -> str:
    """Legacy helper retained for old integrations."""
    level_1 = normalize_source_level_1(value)
    return {"referral": "third_party_referral"}.get(level_1, level_1)


def legacy_source_category(level_1: str | None) -> str:
    return {"referral": "third_party_referral"}.get(level_1 or "other", level_1 or "other")


def source_level_2_is_valid(level_1: str | None, level_2: str | None) -> bool:
    if not level_1 or not level_2:
        return False
    return any(item["code"] == level_2 for item in SOURCE_LEVEL_2_OPTIONS.get(level_1, []))
