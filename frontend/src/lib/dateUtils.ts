export function parseIsoDate(value?: string | null): Date | null {
  if (!value) return null;
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    return d;
  } catch {
    return null;
  }
}

export function formatDateTimeLocal(
  value?: string | null,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!value) return "-";
  const d = parseIsoDate(value);
  if (!d) return value ?? "";
  const fmt = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...options,
  });
  return fmt.format(d);
}

export function formatTimeLocal(value?: string | null): string {
  if (!value) return "-";
  const d = parseIsoDate(value);
  if (!d) return value ?? "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(d);
}

export function formatDateLocal(value?: string | null): string {
  if (!value) return "-";
  const d = parseIsoDate(value);
  if (!d) return value ?? "";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(d);
}

/**
 * Format a timestamp as a short relative time helper next to an absolute date.
 *
 * Examples: "just now", "2m ago", "3h ago", "yesterday", "5d ago", "in 3m".
 */
export function formatRelativeTime(value?: string | null, now: Date = new Date()): string {
  const d = parseIsoDate(value ?? undefined);
  if (!d) return "";

  const diffMs = d.getTime() - now.getTime();
  const past = diffMs <= 0;
  const absMs = Math.abs(diffMs);
  const sec = Math.round(absMs / 1000);
  const min = Math.round(sec / 60);
  const hr = Math.round(min / 60);
  const day = Math.round(hr / 24);

  const suffix = past ? "ago" : "";
  const prefix = past ? "" : "in ";

  if (sec < 45) return past ? "just now" : "in seconds";
  if (sec < 90) return past ? "1m ago" : "in 1m";
  if (min < 45) return `${prefix}${min}m${suffix}`.trim();
  if (min < 90) return past ? "1h ago" : "in 1h";
  if (hr < 24) return `${prefix}${hr}h${suffix}`.trim();
  if (hr < 36) return past ? "yesterday" : "tomorrow";
  if (day < 90) return `${prefix}${day}d${suffix}`.trim();
  // For very long ranges, fall back to empty helper and let the absolute date speak for itself.
  return "";
}
