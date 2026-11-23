const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/;
const beijingTimeZone = "Asia/Shanghai";
const beijingDateTimeOptions: Intl.DateTimeFormatOptions = {
  timeZone: beijingTimeZone,
  hour12: false,
  hourCycle: "h23",
};

/** Parse API timestamps without letting a browser's local timezone decide. */
export function parseApiDate(value: string): Date {
  return new Date(hasTimezone.test(value) ? value : `${value}Z`);
}

/** Format server lifecycle timestamps as China business time. */
export function formatBeijingTime(value?: string | null, withYear = false): string {
  if (!value) return "—";
  return parseApiDate(value).toLocaleString("zh-CN", {
    ...beijingDateTimeOptions,
    ...(withYear ? { year: "numeric" as const, month: "2-digit" as const, day: "2-digit" as const, hour: "2-digit" as const, minute: "2-digit" as const, second: "2-digit" as const } : { month: "2-digit" as const, day: "2-digit" as const, hour: "2-digit" as const, minute: "2-digit" as const }),
  });
}

/** Parse a timestamp whose naive value is an ABC/business wall-clock time. */
function parseBusinessDate(value: string): Date {
  return new Date(hasTimezone.test(value) ? value : `${value}+08:00`);
}

/** Format ABC/business timestamps as Beijing time with an explicit 24-hour clock. */
export function formatBusinessDateTime24h(value?: string | null, withYear = false): string {
  if (!value) return "—";
  return parseBusinessDate(value).toLocaleString("zh-CN", {
    ...beijingDateTimeOptions,
    ...(withYear ? { year: "numeric" as const, month: "2-digit" as const, day: "2-digit" as const, hour: "2-digit" as const, minute: "2-digit" as const, second: "2-digit" as const } : { month: "2-digit" as const, day: "2-digit" as const, hour: "2-digit" as const, minute: "2-digit" as const }),
  });
}

/** Format a date-only value in Beijing time without a 12-hour suffix. */
export function formatBusinessDate24h(value?: string | null): string {
  if (!value) return "—";
  return parseBusinessDate(value).toLocaleString("zh-CN", {
    ...beijingDateTimeOptions,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}
