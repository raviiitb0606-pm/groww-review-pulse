import { weekDates } from "./metrics";

const short = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const full = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "26 Oct – 1 Nov 2026" */
export function weekLabel(key: string): string {
  const { start, end } = weekDates(key);
  return `${short.format(start)} – ${full.format(end)}`;
}

/** "W44" */
export function weekShort(key: string): string {
  return key.slice(5);
}

/** "Week 44 · 26 Oct – 1 Nov 2026" */
export function weekTitle(key: string): string {
  return `Week ${Number(key.slice(6))} · ${weekLabel(key)}`;
}

export function dateLabel(date: string): string {
  return full.format(new Date(`${date}T00:00:00Z`));
}

/** "8 Nov 2026, 16:26 IST" for an ISO timestamp with an IST offset. */
export function stamp(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const day = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }).format(d);
  return `${day} IST`;
}

export function num(n: number): string {
  return n.toLocaleString("en-IN");
}

export function signed(n: number, digits = 0, suffix = ""): string {
  const s = Math.abs(n).toFixed(digits);
  if (Number(s) === 0) return `±0${suffix}`;
  return `${n > 0 ? "+" : "−"}${s}${suffix}`;
}
