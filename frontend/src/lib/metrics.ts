// Every number on the dashboard is computed here from the exported reviews, so the week picker
// and filters work without a server. Pure functions only; see metrics.test.ts.

import type { Filters, Rating, Review, ThemeMeta } from "./types";

export const OTHER = "other";
const DAY = 86_400_000;

// --- weeks ---------------------------------------------------------------------------------

function utc(date: string): Date {
  return new Date(`${date}T00:00:00Z`);
}

/** ISO 8601 week key of a YYYY-MM-DD date, e.g. "2026-W44". */
export function isoWeek(date: string): string {
  const d = utc(date);
  const day = (d.getUTCDay() + 6) % 7; // Monday = 0
  const thursday = new Date(d.getTime() + (3 - day) * DAY);
  const year = thursday.getUTCFullYear();
  const week = Math.floor((thursday.getTime() - Date.UTC(year, 0, 1)) / (7 * DAY)) + 1;
  return `${year}-W${String(week).padStart(2, "0")}`;
}

/** Monday and Sunday of an ISO week key. */
export function weekDates(key: string): { start: Date; end: Date } {
  const [year, w] = key.split("-W").map(Number);
  const jan4 = Date.UTC(year, 0, 4);
  const jan4Day = (new Date(jan4).getUTCDay() + 6) % 7;
  const start = new Date(jan4 - jan4Day * DAY + (w - 1) * 7 * DAY);
  return { start, end: new Date(start.getTime() + 6 * DAY) };
}

/** Every week from the first to the last review, oldest first, with no gaps. */
export function allWeeks(reviews: Review[]): string[] {
  if (!reviews.length) return [];
  const dates = reviews.map((r) => r.date).sort();
  const weeks: string[] = [];
  let t = weekDates(isoWeek(dates[0])).start.getTime();
  const last = isoWeek(dates[dates.length - 1]);
  for (;;) {
    const key = isoWeek(new Date(t).toISOString().slice(0, 10));
    weeks.push(key);
    if (key === last) return weeks;
    t += 7 * DAY;
  }
}

/** The `n` weeks ending at `week`, oldest first. */
export function lookbackWeeks(weeks: string[], week: string, n: number): string[] {
  const end = weeks.indexOf(week);
  if (end < 0) return weeks.slice(-n);
  return weeks.slice(Math.max(0, end - n + 1), end + 1);
}

export function previousWeek(weeks: string[], week: string): string | null {
  const i = weeks.indexOf(week);
  return i > 0 ? weeks[i - 1] : null;
}

// --- filtering -----------------------------------------------------------------------------

/** Rating, theme and version filters: the cohort every chart describes. */
export function cohort(reviews: Review[], f: Pick<Filters, "ratings" | "themes" | "versions">) {
  return reviews.filter(
    (r) =>
      (!f.ratings.length || f.ratings.includes(r.rating)) &&
      (!f.themes.length || f.themes.includes(r.theme)) &&
      (!f.versions.length || (r.version !== null && f.versions.includes(r.version))),
  );
}

export function inWeeks(reviews: Review[], weeks: string[]): Review[] {
  const set = new Set(weeks);
  return reviews.filter((r) => set.has(isoWeek(r.date)));
}

export function search(reviews: Review[], query: string): Review[] {
  const q = query.trim().toLowerCase();
  return q ? reviews.filter((r) => r.text.toLowerCase().includes(q)) : reviews;
}

export function sortReviews(reviews: Review[], sort: Filters["sort"]): Review[] {
  const out = [...reviews];
  const byDate = (a: Review, b: Review) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id);
  if (sort === "newest") out.sort(byDate);
  if (sort === "oldest") out.sort((a, b) => -byDate(a, b));
  if (sort === "lowest") out.sort((a, b) => a.rating - b.rating || byDate(a, b));
  if (sort === "highest") out.sort((a, b) => b.rating - a.rating || byDate(a, b));
  return out;
}

// --- summaries -----------------------------------------------------------------------------

export type Sentiment = "negative" | "neutral" | "positive";

/** 1-2 stars negative, 3 neutral, 4-5 positive: the rating already carries sentiment. */
export function sentiment(rating: number): Sentiment {
  return rating <= 2 ? "negative" : rating === 3 ? "neutral" : "positive";
}

export interface Summary {
  count: number;
  avg: number | null;
  negative: number; // shares, 0-1
  neutral: number;
  positive: number;
}

export function summarize(reviews: Review[]): Summary {
  const n = reviews.length;
  if (!n) return { count: 0, avg: null, negative: 0, neutral: 0, positive: 0 };
  const tally = { negative: 0, neutral: 0, positive: 0 };
  let sum = 0;
  for (const r of reviews) {
    sum += r.rating;
    tally[sentiment(r.rating)] += 1;
  }
  return {
    count: n,
    avg: sum / n,
    negative: tally.negative / n,
    neutral: tally.neutral / n,
    positive: tally.positive / n,
  };
}

export interface WeekPoint extends Summary {
  week: string;
}

export function weekly(reviews: Review[], weeks: string[]): WeekPoint[] {
  const by = new Map<string, Review[]>(weeks.map((w) => [w, []]));
  for (const r of reviews) by.get(isoWeek(r.date))?.push(r);
  return weeks.map((week) => ({ week, ...summarize(by.get(week)!) }));
}

export function ratingCounts(reviews: Review[]): Record<Rating, number> {
  const counts: Record<Rating, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  for (const r of reviews) counts[r.rating] += 1;
  return counts;
}

// --- themes --------------------------------------------------------------------------------

export interface ThemeStat extends Summary {
  theme: ThemeMeta;
  share: number; // of the reviews passed in
  negativeCount: number;
}

/** Per-theme stats, largest first, with `other` always last. */
export function themeStats(reviews: Review[], themes: ThemeMeta[]): ThemeStat[] {
  const by = new Map<string, Review[]>(themes.map((t) => [t.key, []]));
  for (const r of reviews) by.get(r.theme)?.push(r);
  const total = reviews.length || 1;
  return themes
    .map((theme) => {
      const rows = by.get(theme.key)!;
      const s = summarize(rows);
      return { theme, ...s, share: rows.length / total, negativeCount: Math.round(s.negative * s.count) };
    })
    .sort((a, b) => Number(a.theme.key === OTHER) - Number(b.theme.key === OTHER) || b.count - a.count);
}

/** The named theme with the most negative reviews. */
export function topPain(stats: ThemeStat[]): ThemeStat | null {
  const named = stats.filter((s) => s.theme.key !== OTHER && s.count > 0);
  return named.sort((a, b) => b.negativeCount - a.negativeCount)[0] ?? null;
}

export interface Mover {
  theme: ThemeMeta;
  previous: number;
  current: number;
  change: number; // relative, e.g. -0.69
}

/**
 * Week-over-week change in review count per named theme, biggest swing first. A theme needs at
 * least `minBase` reviews across both weeks, so 1 → 3 does not read as +200%.
 */
export function movers(
  reviews: Review[],
  themes: ThemeMeta[],
  week: string,
  prev: string | null,
  minBase = 10,
): Mover[] {
  if (!prev) return [];
  const count = (key: string, w: string) =>
    reviews.filter((r) => r.theme === key && isoWeek(r.date) === w).length;
  return themes
    .filter((t) => t.key !== OTHER)
    .map((theme) => {
      const previous = count(theme.key, prev);
      const current = count(theme.key, week);
      return { theme, previous, current, change: previous ? (current - previous) / previous : 0 };
    })
    .filter((m) => m.previous > 0 && m.previous + m.current >= minBase)
    .sort((a, b) => Math.abs(b.current - b.previous) - Math.abs(a.current - a.previous));
}

/** The hero sentence: the biggest pain point, then the biggest weekly swing. */
export function headline(pain: ThemeStat | null, mover: Mover | null): string {
  const parts: string[] = [];
  if (pain) {
    parts.push(`${pain.theme.label} is the #1 complaint area, ${pct(pain.negative)} negative.`);
  }
  if (mover && mover.change !== 0) {
    const verb = mover.change > 0 ? "rose" : "fell";
    parts.push(`${mover.theme.label} mentions ${verb} ${pct(Math.abs(mover.change))} this week.`);
  }
  return parts.join(" ") || "Not enough reviews in this selection for a headline.";
}

// --- versions ------------------------------------------------------------------------------

export interface VersionStat extends Summary {
  version: string;
}

function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d) return d;
  }
  return 0;
}

/** Versions with at least `minCount` reviews, newest first. Unknown versions are left out. */
export function versionStats(reviews: Review[], minCount = 1): VersionStat[] {
  const by = new Map<string, Review[]>();
  for (const r of reviews) {
    if (r.version) by.set(r.version, [...(by.get(r.version) ?? []), r]);
  }
  return [...by.entries()]
    .map(([version, rows]) => ({ version, ...summarize(rows) }))
    .filter((v) => v.count >= minCount)
    .sort((a, b) => compareVersions(b.version, a.version));
}

/** Versions by review count, most reviewed first. */
export function topVersions(reviews: Review[], n: number): VersionStat[] {
  return versionStats(reviews).sort((a, b) => b.count - a.count).slice(0, n);
}

// --- quotes and terms ----------------------------------------------------------------------

/**
 * Short, clearly themed reviews for quote cards: quote-eligible, high confidence, 40-220
 * characters, newest first, cycling through ratings so the cards mix complaints and praise.
 */
export function representative(reviews: Review[], n: number): Review[] {
  const pool = sortReviews(
    reviews.filter(
      (r) => r.quote_eligible && r.confidence === "high" && r.text.length >= 40 && r.text.length <= 220,
    ),
    "newest",
  );
  const order: Rating[] = [1, 5, 2, 3, 4];
  const picked: Review[] = [];
  for (let round = 0; picked.length < n && round < pool.length; round++) {
    let added = false;
    for (const rating of order) {
      const r = pool.find((x) => x.rating === rating && !picked.includes(x));
      if (r && picked.length < n) {
        picked.push(r);
        added = true;
      }
    }
    if (!added) break;
  }
  return picked;
}

/** How many reviews contain each term as a word (case-insensitive). */
export function termCounts(reviews: Review[], terms: string[]): { term: string; count: number }[] {
  return terms.map((term) => {
    const re = new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "i");
    return { term, count: reviews.filter((r) => re.test(r.text)).length };
  });
}

// --- formatting ----------------------------------------------------------------------------

export function pct(share: number, digits = 0): string {
  return `${(share * 100).toFixed(digits)}%`;
}

export function change(current: number, previous: number): number | null {
  return previous ? (current - previous) / previous : null;
}
