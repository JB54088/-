export type SourceLevel1Code = "field_sales" | "online" | "offline" | "event" | "referral" | "other";
export type SourceLevel2Code =
  | "field_sales_group_1" | "field_sales_group_2" | "field_sales_other"
  | "wechat" | "xiaohongshu" | "douyin" | "online_other"
  | "store_visit" | "community_promotion" | "offline_other"
  | "free_clinic" | "health_lecture" | "event_other"
  | "patient_referral" | "doctor_referral" | "partner_referral"
  | "unknown" | "custom";

export const SOURCE_LEVEL_1_OPTIONS = [
  { code: "field_sales", name: "地推" },
  { code: "online", name: "线上" },
  { code: "offline", name: "线下" },
  { code: "event", name: "活动" },
  { code: "referral", name: "转介绍" },
  { code: "other", name: "其他" },
] as const;

export const SOURCE_LEVEL_2_OPTIONS: Record<SourceLevel1Code, readonly { code: SourceLevel2Code; name: string }[]> = {
  field_sales: [
    { code: "field_sales_group_1", name: "地推一组" },
    { code: "field_sales_group_2", name: "地推二组" },
    { code: "field_sales_other", name: "其他地推" },
  ],
  online: [
    { code: "wechat", name: "微信" },
    { code: "xiaohongshu", name: "小红书" },
    { code: "douyin", name: "抖音" },
    { code: "online_other", name: "其他线上" },
  ],
  offline: [
    { code: "store_visit", name: "门店到访" },
    { code: "community_promotion", name: "社区推广" },
    { code: "offline_other", name: "其他线下" },
  ],
  event: [
    { code: "free_clinic", name: "义诊" },
    { code: "health_lecture", name: "健康讲座" },
    { code: "event_other", name: "其他活动" },
  ],
  referral: [
    { code: "patient_referral", name: "老患者转介绍" },
    { code: "doctor_referral", name: "医生转介绍" },
    { code: "partner_referral", name: "合作机构转介绍" },
  ],
  other: [
    { code: "unknown", name: "来源不明" },
    { code: "custom", name: "自定义" },
  ],
};

export const SOURCE_LEVEL_1_LABELS: Record<string, string> = Object.fromEntries(
  SOURCE_LEVEL_1_OPTIONS.map((item) => [item.code, item.name]),
);
export const SOURCE_LEVEL_2_LABELS: Record<string, string> = Object.fromEntries(
  Object.values(SOURCE_LEVEL_2_OPTIONS).flat().map((item) => [item.code, item.name]),
);

// 兼容旧接口和历史数据读取，新的页面统一使用一级/二级来源字段。
export const SOURCE_CATEGORY_OPTIONS = SOURCE_LEVEL_1_OPTIONS;
export const SOURCE_CATEGORY_LABELS: Record<string, string> = {
  ...SOURCE_LEVEL_1_LABELS,
  third_party_referral: "第三方转介绍",
  external: "外部来源",
};

export function formatSourceCategory(level1?: string | null, level2?: string | null, customName?: string | null, legacy?: string | null) {
  if (level1) {
    const level1Name = SOURCE_LEVEL_1_LABELS[level1] || level1;
    const level2Name = level2 === "custom" && customName ? customName : SOURCE_LEVEL_2_LABELS[level2 || ""];
    return level2Name ? `${level1Name} / ${level2Name}` : level1Name;
  }
  return legacy ? SOURCE_CATEGORY_LABELS[legacy] || legacy : "待主管归档";
}
