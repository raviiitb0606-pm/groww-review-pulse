// Shape of public/dashboard.json, written by `pulse dashboard` (src/pulse/dashboard.py).

export type Rating = 1 | 2 | 3 | 4 | 5;

export interface ThemeMeta {
  key: string; // "t1".."t5", or "other"
  name: string; // the pipeline's theme name, e.g. "Update / Chart / Option"
  label: string; // display label from config, e.g. "App updates & charts"
  color: string;
  terms: string[]; // top terms of the topic, strongest first
}

export interface Review {
  id: string;
  date: string; // YYYY-MM-DD, IST
  rating: Rating;
  version: string | null;
  theme: string;
  confidence: "high" | "low";
  quote_eligible: boolean;
  text: string; // PII-scrubbed: redactions appear as [redacted] and [name]
}

export interface Pulse {
  title: string;
  themes: { theme: string | null; summary: string }[];
  quotes: { theme: string | null; rating: Rating; text: string }[];
  actions: { theme: string | null; text: string }[];
}

export interface Publish {
  doc_url: string | null;
  doc_at: string | null;
  email_status: string | null;
  email_at: string | null;
}

export interface Dashboard {
  app: string;
  run_id: string; // ISO week of the published pulse, e.g. "2026-W44"
  store: string;
  generated_at: string;
  window: { start: string; end: string };
  themes: ThemeMeta[];
  reviews: Review[];
  pulse: Pulse | null;
  publish: Publish | null;
}

export type Sort = "newest" | "oldest" | "lowest" | "highest";

export interface Filters {
  week: string; // the week the KPIs describe
  lookback: number; // weeks of history behind trends, themes and distributions
  ratings: Rating[]; // empty = all
  themes: string[];
  versions: string[];
  search: string;
  sort: Sort;
}
