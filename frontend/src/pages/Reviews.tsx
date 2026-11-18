import { ShieldCheck, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { ReviewCard } from "../components/cards";
import { Empty, Pagination, RatingChip, shade, tint } from "../components/ui";
import { num, weekLabel, weekShort } from "../lib/format";
import { inWeeks, pct, ratingCounts, search, sortReviews, summarize, themeStats } from "../lib/metrics";
import { useStore } from "../lib/store";
import type { Rating, Sort } from "../lib/types";

const PAGE = 10;
const SORTS: { value: Sort; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "lowest", label: "Lowest rating" },
  { value: "highest", label: "Highest rating" },
];

export function Reviews() {
  const { data, filters, setFilters, resetFilters, all, window, windowWeeks, theme } = useStore();
  // "" = every week in the lookback window; otherwise one week.
  const [scope, setScope] = useState<string>(filters.week);
  const [page, setPage] = useState(1);
  const scoped = scope ? inWeeks(all, [scope]) : window;
  const results = useMemo(
    () => sortReviews(search(scoped, filters.search), filters.sort),
    [scoped, filters.search, filters.sort],
  );
  const pages = Math.max(1, Math.ceil(results.length / PAGE));
  const current = Math.min(page, pages);
  const s = summarize(results);
  const mix = themeStats(results, data.themes).filter((x) => x.count > 0);
  const counts = ratingCounts(results);
  const maxCount = Math.max(...Object.values(counts), 1);
  const set = (patch: Parameters<typeof setFilters>[0]) => {
    setFilters(patch);
    setPage(1);
  };
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const active: { label: string; clear: () => void }[] = [
    ...(filters.search ? [{ label: `“${filters.search}”`, clear: () => set({ search: "" }) }] : []),
    ...filters.ratings.map((r) => ({ label: `${r}★`, clear: () => set({ ratings: filters.ratings.filter((x) => x !== r) }) })),
    ...filters.themes.map((k) => ({ label: theme(k).label, clear: () => set({ themes: filters.themes.filter((x) => x !== k) }) })),
    ...filters.versions.map((v) => ({ label: `v${v}`, clear: () => set({ versions: filters.versions.filter((x) => x !== v) }) })),
  ];

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-label-sm font-semibold text-emerald-800">
            <ShieldCheck size={12} /> PII scrubbed before analysis
          </span>
          <h1 className="mt-2 font-display text-headline-xl font-bold tracking-tight text-ink">Reviews explorer</h1>
          <p className="text-body-md text-muted">
            Every {data.store} review in the window, PII-scrubbed and tagged with its theme by the clustering model.
          </p>
        </div>
      </div>

      <div className="card mt-6 p-5">
        <div className="flex flex-col gap-3 lg:flex-row">
          <label className="relative flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={filters.search}
              onChange={(e) => set({ search: e.target.value })}
              placeholder="Search review text, e.g. withdrawal, chart, brokerage…"
              className="h-11 w-full rounded-xl bg-slate-50 pl-10 pr-4 text-body-md placeholder:text-slate-400 focus:bg-white focus:outline-2 focus:outline-primary-container"
            />
          </label>
          <select
            value={scope}
            onChange={(e) => {
              setScope(e.target.value);
              setPage(1);
            }}
            aria-label="Weeks"
            className="h-11 rounded-xl bg-slate-50 px-3 text-body-md"
          >
            <option value="">All {windowWeeks.length} weeks ({weekShort(windowWeeks[0] ?? "")}–{weekShort(filters.week)})</option>
            {[...windowWeeks].reverse().map((w) => (
              <option key={w} value={w}>
                {weekShort(w)} · {weekLabel(w)}
              </option>
            ))}
          </select>
          <select
            value={filters.sort}
            onChange={(e) => set({ sort: e.target.value as Sort })}
            aria-label="Sort"
            className="h-11 rounded-xl bg-slate-50 px-3 text-body-md"
          >
            {SORTS.map((o) => (
              <option key={o.value} value={o.value}>
                Sort: {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-label-sm font-bold uppercase tracking-wider text-muted">Rating</span>
            {([1, 2, 3, 4, 5] as Rating[]).map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={filters.ratings.includes(r)}
                onClick={() => set({ ratings: toggle(filters.ratings, r) })}
                className={`tactile rounded-full ring-2 ${filters.ratings.includes(r) ? "ring-primary-container" : "ring-transparent opacity-80 hover:opacity-100"}`}
              >
                <RatingChip rating={r} />
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-label-sm font-bold uppercase tracking-wider text-muted">Themes</span>
            {data.themes.map((t) => {
              const on = filters.themes.includes(t.key);
              return (
                <button
                  key={t.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set({ themes: toggle(filters.themes, t.key) })}
                  className="tactile inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-label-sm font-semibold"
                  style={
                    on
                      ? { backgroundColor: t.color, color: "#fff", boxShadow: `0 4px 12px ${tint(t.color, 0.35)}` }
                      : { backgroundColor: tint(t.color, 0.1), color: shade(t.color) }
                  }
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: on ? "#fff" : t.color }} />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-label-md font-semibold text-on-surface">Showing</span>
        <span className="tnum rounded-full bg-violet-100 px-2.5 py-0.5 text-label-md font-bold text-primary">{num(results.length)} reviews</span>
        <span className="rounded-full bg-white px-2.5 py-0.5 text-label-md text-slate-600 shadow-sm">
          {scope ? weekShort(scope) : `${windowWeeks.length} weeks`}
        </span>
        {active.map((a) => (
          <button
            key={a.label}
            type="button"
            onClick={a.clear}
            className="tactile inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-label-md text-slate-600 shadow-sm hover:text-rose-600"
          >
            {a.label} <X size={12} />
          </button>
        ))}
        {active.length > 0 && (
          <button
            type="button"
            onClick={() => {
              resetFilters();
              setPage(1);
            }}
            className="text-label-md font-semibold text-primary hover:underline"
          >
            Reset all
          </button>
        )}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          {results.slice((current - 1) * PAGE, current * PAGE).map((r) => (
            <ReviewCard key={r.id} review={r} />
          ))}
          {!results.length && (
            <div className="card">
              <Empty title="No reviews match these filters" hint="Clear a filter, widen the weeks, or try a different search term." />
            </div>
          )}
          <Pagination
            page={current}
            pages={pages}
            total={results.length}
            size={PAGE}
            onPage={(p) => {
              setPage(p);
              globalThis.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <div className="card p-6">
            <p className="text-label-sm font-bold uppercase tracking-wider text-muted">Cohort summary</p>
            <p className="mt-1 font-display text-title-md font-bold text-ink">{num(results.length)} reviews</p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-rose-100 bg-rose-50/60 p-3">
                <p className="text-label-sm text-muted">Negative share</p>
                <p className="tnum font-display text-metric-md font-bold text-rose-600">{results.length ? pct(s.negative) : "–"}</p>
              </div>
              <div className="rounded-xl border border-amber-100 bg-amber-50/60 p-3">
                <p className="text-label-sm text-muted">Avg rating</p>
                <p className="tnum font-display text-metric-md font-bold text-ink">
                  {s.avg?.toFixed(2) ?? "–"} <span className="text-amber-500">★</span>
                </p>
              </div>
            </div>

            <p className="mb-2 mt-6 text-label-md font-semibold text-on-surface">Theme composition</p>
            <div className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-slate-100">
              {mix.map((m) => (
                <div key={m.theme.key} style={{ width: `${m.share * 100}%`, backgroundColor: m.theme.color }} title={`${m.theme.label}: ${pct(m.share)}`} />
              ))}
            </div>
            <div className="mt-3 flex flex-col gap-1.5">
              {mix.map((m) => (
                <div key={m.theme.key} className="flex items-center justify-between text-label-md">
                  <span className="flex items-center gap-2 text-slate-600">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: m.theme.color }} />
                    {m.theme.label}
                  </span>
                  <span className="tnum text-slate-600">
                    {pct(m.share)} <span className="text-muted">({m.count})</span>
                  </span>
                </div>
              ))}
            </div>

            <p className="mb-2 mt-6 text-label-md font-semibold text-on-surface">Rating distribution</p>
            <div className="flex flex-col gap-1.5">
              {([1, 2, 3, 4, 5] as Rating[]).map((r) => (
                <div key={r} className="flex items-center gap-2 text-label-md">
                  <span className="tnum w-5 text-slate-600">{r}★</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${(counts[r] / maxCount) * 100}%`, backgroundColor: r <= 2 ? "#E11D48" : r === 3 ? "#94A3B8" : "#10B981" }}
                    />
                  </div>
                  <span className="tnum w-8 text-right text-muted">{counts[r]}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}
