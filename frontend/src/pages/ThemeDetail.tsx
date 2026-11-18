import { ArrowLeft, Frown, Gauge, MessageSquareText, Search, Shapes, Star, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { BarRow, Donut, LineChart } from "../components/charts";
import { QuoteCard, ReviewCard } from "../components/cards";
import { CardTitle, ChangePill, Empty, Pagination, Section, Tag, shade, tint } from "../components/ui";
import { dateLabel, num, signed, weekShort } from "../lib/format";
import {
  OTHER,
  cohort,
  inWeeks,
  isoWeek,
  pct,
  ratingCounts,
  representative,
  search,
  sentiment,
  sortReviews,
  summarize,
  termCounts,
  themeStats,
  topPain,
  topVersions,
  type Sentiment,
} from "../lib/metrics";
import { go } from "../lib/router";
import { useStore } from "../lib/store";
import type { Rating } from "../lib/types";

const PAGE = 8;
const RATING_COLORS: Record<Rating, string> = { 1: "#E11D48", 2: "#FB7185", 3: "#94A3B8", 4: "#34D399", 5: "#10B981" };

export function ThemeDetail({ themeKey }: { themeKey: string | null }) {
  const { data, filters, setFilters, windowWeeks, prevWeek } = useStore();
  // The page is about one theme, so the global theme filter does not apply here.
  const base = useMemo(() => cohort(data.reviews, { ...filters, themes: [] }), [data, filters]);
  const window = useMemo(() => inWeeks(base, windowWeeks), [base, windowWeeks]);
  const stats = themeStats(window, data.themes);
  const pain = topPain(stats);
  const key = themeKey ?? pain?.theme.key ?? data.themes[0].key;
  const stat = stats.find((s) => s.theme.key === key) ?? stats[0];
  const t = stat.theme;
  const rows = useMemo(() => window.filter((r) => r.theme === t.key), [window, t.key]);

  const [tab, setTab] = useState<"all" | Sentiment>("all");
  const [query, setQuery] = useState("");
  const [version, setVersion] = useState("");
  const [page, setPage] = useState(1);

  const overall = summarize(window);
  const thisWeek = rows.filter((r) => isoWeek(r.date) === filters.week).length;
  const lastWeek = prevWeek ? base.filter((r) => r.theme === t.key && isoWeek(r.date) === prevWeek).length : 0;
  const named = stats.filter((s) => s.theme.key !== OTHER && s.count > 0);
  const rank = [...named].sort((a, b) => (a.avg ?? 5) - (b.avg ?? 5)).findIndex((s) => s.theme.key === t.key);

  const trend = windowWeeks.map((w) => {
    const all = window.filter((r) => isoWeek(r.date) === w);
    const mine = all.filter((r) => r.theme === t.key);
    return {
      share: all.length ? mine.length / all.length : null,
      negative: mine.length ? summarize(mine).negative : null,
    };
  });
  const peak = Math.max(0.2, ...trend.flatMap((p) => [p.share ?? 0, p.negative ?? 0]));
  const top = Math.min(1, Math.ceil((peak + 0.05) * 10) / 10);
  const counts = ratingCounts(rows);
  const versions = topVersions(rows, 4);
  const terms = termCounts(rows, t.terms)
    .filter((x) => x.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
  const quotes = representative(rows, 4);
  const pulseIdx = data.pulse?.actions.findIndex((a) => a.theme === t.key) ?? -1;
  const action = pulseIdx >= 0 ? data.pulse!.actions[pulseIdx] : null;
  const summary = data.pulse?.themes.find((s) => s.theme === t.key)?.summary;

  const bySentiment = { negative: 0, neutral: 0, positive: 0 };
  for (const r of rows) bySentiment[sentiment(r.rating)] += 1;
  const feed = sortReviews(
    search(rows, query).filter((r) => (tab === "all" || sentiment(r.rating) === tab) && (!version || r.version === version)),
    filters.sort,
  );
  const pages = Math.max(1, Math.ceil(feed.length / PAGE));
  const current = Math.min(page, pages);

  const tabs: { id: "all" | Sentiment; label: string; n: number; on: string }[] = [
    { id: "all", label: "All", n: rows.length, on: "bg-gradient-to-r from-primary-container to-primary text-white" },
    { id: "negative", label: "Negative", n: bySentiment.negative, on: "bg-rose-600 text-white" },
    { id: "neutral", label: "Neutral", n: bySentiment.neutral, on: "bg-amber-500 text-white" },
    { id: "positive", label: "Positive", n: bySentiment.positive, on: "bg-emerald-600 text-white" },
  ];

  return (
    <>
      <nav aria-label="Themes" className="-mx-1 mb-6 flex gap-2 overflow-x-auto px-1 pb-1">
        {stats.map((s) => {
          const on = s.theme.key === t.key;
          return (
            <button
              key={s.theme.key}
              type="button"
              onClick={() => {
                setPage(1);
                go({ page: "themes", theme: s.theme.key });
              }}
              className={`tactile flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-label-md font-semibold ${
                on ? "bg-white text-ink shadow-[0_4px_14px_rgba(30,27,75,0.08)]" : "text-slate-500 hover:bg-white/70"
              }`}
              style={on ? { boxShadow: `inset 0 -2px 0 ${s.theme.color}, 0 4px 14px rgba(30,27,75,0.08)` } : undefined}
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.theme.color }} />
              {s.theme.label}
              <span className="tnum text-muted">{pct(s.share)}</span>
            </button>
          );
        })}
      </nav>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-label-md text-muted">
            <Shapes size={13} /> Themes <span className="text-slate-300">/</span>
            <span className="font-semibold text-on-surface">{t.label}</span>
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className="flex h-11 w-11 items-center justify-center rounded-2xl text-white shadow-lg"
              style={{ background: `linear-gradient(135deg, ${t.color}, ${shade(t.color, 0.3)})`, boxShadow: `0 8px 20px ${tint(t.color, 0.35)}` }}
            >
              <Shapes size={20} />
            </span>
            <h1 className="font-display text-headline-xl font-bold tracking-tight text-ink">{t.label}</h1>
            {pain?.theme.key === t.key ? (
              <Tag className="bg-rose-500/12 text-rose-700">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500" /> Primary friction point · {pct(stat.share)} share
              </Tag>
            ) : (
              <Tag className="bg-slate-100 text-slate-600">{pct(stat.share)} share</Tag>
            )}
          </div>
          {terms.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-label-sm font-bold uppercase tracking-wider text-muted">Top terms</span>
              {terms.map((x) => (
                <span key={x.term} className="rounded-full bg-white px-2.5 py-1 text-label-md text-slate-600 shadow-sm">
                  {x.term} <span className="tnum text-muted">({x.count})</span>
                </span>
              ))}
            </div>
          )}
          {t.key !== OTHER && (
            <p className="mt-2 text-label-sm text-muted">
              Clustered by the pipeline as “{t.name}”.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="glass-btn" onClick={() => go({ page: "overview" })}>
            <ArrowLeft size={15} /> Back to overview
          </button>
          <button
            type="button"
            onClick={() => {
              setFilters({ themes: [t.key], search: "" });
              go({ page: "reviews" });
            }}
            className="tactile flex h-9 items-center gap-2 rounded-xl bg-gradient-to-r from-primary-container to-primary px-4 text-label-md font-semibold text-white shadow-[0_4px_14px_rgba(109,40,217,0.3)]"
          >
            <Search size={15} /> Explore in Reviews
          </button>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: "Total reviews",
            icon: <MessageSquareText size={15} className="text-violet-600" />,
            accent: t.color,
            value: num(stat.count),
            pill: <ChangePill good={null}>{pct(stat.share)} of feedback</ChangePill>,
            note: `${windowWeeks.length}-week window`,
          },
          {
            label: "Average rating",
            icon: <Star size={15} className="text-amber-500" />,
            accent: "#F59E0B",
            value: stat.avg ? `${stat.avg.toFixed(2)}★` : "–",
            pill:
              stat.avg !== null && overall.avg !== null ? (
                <ChangePill good={stat.avg >= overall.avg}>{signed(stat.avg - overall.avg, 1)} vs avg</ChangePill>
              ) : null,
            note: rank >= 0 && t.key !== OTHER ? `${rank === 0 ? "Lowest" : `#${rank + 1} lowest`} rated of ${named.length} themes` : "",
          },
          {
            label: "Negative sentiment",
            icon: <Frown size={15} className="text-rose-500" />,
            accent: "#E11D48",
            value: pct(stat.negative),
            pill:
              stat.negative >= 0.5 ? (
                <ChangePill good={false}>High urgency</ChangePill>
              ) : (
                <ChangePill good={null}>{stat.negative >= 0.3 ? "Watch" : "Low"}</ChangePill>
              ),
            note: `${num(stat.negativeCount)} negative of ${num(stat.count)} reviews`,
          },
          {
            label: "This week",
            icon: <Gauge size={15} className="text-indigo-500" />,
            accent: "#6366F1",
            value: num(thisWeek),
            pill: prevWeek ? (
              <ChangePill good={null}>
                {thisWeek >= lastWeek ? "▲" : "▼"} from {lastWeek} in {weekShort(prevWeek)}
              </ChangePill>
            ) : null,
            note: `${weekShort(filters.week)} reviews in this theme`,
          },
        ].map((k) => (
          <div key={k.label} className="kpi-card relative flex flex-col gap-3 overflow-hidden p-6">
            <div className="absolute inset-x-0 top-0 h-1" style={{ background: `linear-gradient(90deg, ${k.accent}, ${tint(k.accent, 0.4)})` }} />
            <div className="flex items-center justify-between">
              <span className="text-body-sm font-semibold text-slate-500">{k.label}</span>
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50">{k.icon}</span>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="tnum font-display text-metric-xl font-extrabold text-slate-900">{k.value}</span>
              {k.pill}
            </div>
            <span className="text-label-sm text-muted">{k.note}</span>
          </div>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="card p-6 lg:col-span-3">
          <CardTitle
            right={
              <span className="flex flex-wrap items-center gap-3 text-label-sm text-muted">
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: t.color }} />Theme share</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-rose-500" />Negative within theme</span>
              </span>
            }
          >
            Weekly trend ({weekShort(windowWeeks[0] ?? "")}–{weekShort(filters.week)})
          </CardTitle>
          <LineChart
            labels={windowWeeks.map(weekShort)}
            series={[
              { name: "Theme share", color: t.color, values: trend.map((p) => p.share), fill: true },
              { name: "Negative within theme", color: "#E11D48", values: trend.map((p) => p.negative), dashed: true },
            ]}
            domain={[0, top]}
            ticks={[0, top / 2, top].map((v) => Math.round(v * 100) / 100)}
            format={(v) => pct(v)}
            height={220}
            highlight={windowWeeks.indexOf(filters.week)}
          />
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-label-md text-slate-600">
            <Zap size={14} className="mt-0.5 shrink-0 text-primary" />
            Share is this theme's slice of each week's reviews; the dashed line is how many of its own reviews were 1–2★.
          </div>
        </div>
        <div className="card p-6 lg:col-span-2">
          <CardTitle right={<Tag className="bg-slate-100 text-slate-500">N = {num(rows.length)}</Tag>}>Rating split</CardTitle>
          <div className="flex items-center gap-6">
            <Donut
              segments={([1, 2, 3, 4, 5] as Rating[]).map((r) => ({ value: counts[r], color: RATING_COLORS[r], label: `${r}★: ${counts[r]}` }))}
              center={
                <>
                  <span className="tnum font-display text-title-md font-bold text-ink">{stat.avg?.toFixed(2) ?? "–"}★</span>
                  <span className="text-label-sm text-muted">Mean</span>
                </>
              }
            />
            <div className="flex flex-1 flex-col gap-1.5">
              {([1, 2, 3, 4, 5] as Rating[]).map((r) => (
                <div key={r} className="flex items-center justify-between text-label-md">
                  <span className="flex items-center gap-2 text-slate-600">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: RATING_COLORS[r] }} />
                    {r}★
                  </span>
                  <span className="tnum font-semibold text-on-surface">
                    {rows.length ? pct(counts[r] / rows.length) : "–"} <span className="font-normal text-muted">({counts[r]})</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
          <h4 className="mb-3 mt-8 font-display text-body-md font-bold text-ink">Top app versions</h4>
          <div className="flex flex-col gap-2">
            {versions.map((v, i) => (
              <BarRow
                key={v.version}
                label={<span className="font-mono">v{v.version}</span>}
                value={v.count}
                max={versions[0].count}
                color={i === 0 ? t.color : "#94A3B8"}
                right={
                  <span className="text-label-md">
                    {v.count} · {v.avg!.toFixed(1)}★
                  </span>
                }
              />
            ))}
            {!versions.length && <p className="text-body-sm text-muted">No version data.</p>}
          </div>
        </div>
      </div>

      {quotes.length > 0 && (
        <Section title="Representative quotes" takeaway="Short, high-confidence reviews from this theme, mixing ratings.">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {quotes.map((r) => (
              <QuoteCard key={r.id} text={r.text} rating={r.rating} theme={null} meta={`${dateLabel(r.date)}${r.version ? ` · v${r.version}` : ""}`} />
            ))}
          </div>
        </Section>
      )}

      {action && (
        <section
          className="card relative mt-10 overflow-hidden p-6 sm:p-8"
          style={{ background: `linear-gradient(135deg, #fff 60%, ${tint(t.color, 0.08)})` }}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Tag className="bg-gradient-to-r from-primary-container to-primary text-white">
              <Zap size={11} /> Action idea · {weekShort(data.run_id)} pulse
            </Tag>
          </div>
          <h3 className="mt-3 font-display text-headline-lg font-bold text-ink">{action.text}</h3>
          {summary && <p className="mt-2 max-w-3xl text-body-md text-slate-600">What reviewers say: {summary}.</p>}
        </section>
      )}

      <section className="card mt-10 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-title-md font-bold text-ink">Feedback feed</h2>
            <p className="text-body-sm text-muted">Every review in this theme for the selected weeks.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {tabs.map((x) => (
              <button
                key={x.id}
                type="button"
                aria-pressed={tab === x.id}
                onClick={() => {
                  setTab(x.id);
                  setPage(1);
                }}
                className={`tactile tnum rounded-full px-3.5 py-1.5 text-label-md font-semibold ${
                  tab === x.id ? x.on : "bg-slate-100 text-slate-600 hover:bg-slate-200/70"
                }`}
              >
                {x.label} ({x.n})
              </button>
            ))}
          </div>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <label className="relative flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder={`Search this theme (e.g. ${t.terms.slice(0, 2).join(", ") || "keyword"})…`}
              className="h-11 w-full rounded-xl bg-slate-50 pl-10 pr-4 text-body-md placeholder:text-slate-400 focus:bg-white focus:outline-2 focus:outline-primary-container"
            />
          </label>
          <select
            value={version}
            onChange={(e) => {
              setVersion(e.target.value);
              setPage(1);
            }}
            className="h-11 rounded-xl bg-slate-50 px-3 text-body-md text-on-surface"
            aria-label="App version"
          >
            <option value="">All versions</option>
            {topVersions(rows, 15).map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version} ({v.count})
              </option>
            ))}
          </select>
        </div>
        <div className="mt-5 flex flex-col gap-3">
          {feed.slice((current - 1) * PAGE, current * PAGE).map((r) => (
            <ReviewCard key={r.id} review={r} showTheme={false} />
          ))}
          {!feed.length && <Empty title="No reviews match" hint="Try another sentiment tab, version or search term." />}
        </div>
        <Pagination page={current} pages={pages} total={feed.length} size={PAGE} onPage={setPage} />
      </section>
    </>
  );
}
