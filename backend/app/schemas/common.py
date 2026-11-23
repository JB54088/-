from typing import Literal

LeadStatus = Literal["pending", "reviewed", "unassigned", "assigned", "approved", "converted", "rejected"]
SourceCategory = Literal["field_sales", "online", "offline", "event", "third_party_referral", "external", "other"]
SourceLevel1 = Literal["field_sales", "online", "offline", "event", "referral", "other"]
SourceLevel2 = Literal[
    "field_sales_group_1", "field_sales_group_2", "field_sales_other",
    "wechat", "xiaohongshu", "douyin", "online_other",
    "store_visit", "community_promotion", "offline_other",
    "free_clinic", "health_lecture", "event_other",
    "patient_referral", "doctor_referral", "partner_referral",
    "unknown", "custom",
]
PoolMatchStatus = Literal["pending", "matched", "conflict", "manual_required"]
