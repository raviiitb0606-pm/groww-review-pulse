import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, CheckCircle2, FileText, Frown, MessageSquareText, Star, TrendingUp, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { BarRow, LineChart, SentimentBar } from "../components/charts";
import { QuoteCard } from "../components/cards";
import { CardTitle, ChangePill, Empty, Section, Tag, ThemeChip, shade, tint } from "../components/ui";
import { num, signed, stamp, weekShort, weekTitle } from "../lib/format";
import {
  OTHER,
  change,
  headline,
  movers,
  pct,
  ratingCounts,
  representative,
  summarize,
  themeStats,
  topPain,
  versionStats,
  weekly,
} from "../lib/metrics";
import { go } from "../lib/router";
import { useStore } from "../lib/store";
import type { Rating } from "../lib/types";

function Kpi({
  label,
  icon,
  accent,
  children,
  pill,
}: {
  label: string;
  icon: ReactNode;
  accent: string;
  children: ReactNode;
  pill?: ReactNode;
}) {
  return (
    <div className="kpi-card group relative flex flex-col justify-between gap-3 overflow-hidden p-6">
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r opacity-80 transition-all group-hover:h-1.5 ${accent}`} />
      <div className="flex items-center justify-between">
        <span className="text-body-sm font-semibold tracking-wide text-slate-500">{label}</span>
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50 transition-transform group-hover:scale-110">{icon}</span>
      </div>
      <div className="flex items-baseline justify-between gap-2 pt-1">{children}</div>
      {pill}
    </div>
  );
}

export function Overview() {
  const { data, filters, week, prev, prevWeek, window, windowWeeks, all, theme } = useStore();
  const now = summarize(week);
  const before = summarize(prev);
  const stats = themeStats(window, data.themes);
  const pain = topPain(stats);
  const moves = movers(all, data.themes, filters.week, prevWeek);
  const series = weekly(window, windowWeeks);
  const hi = windowWeeks.indexOf(filters.week);
  const isPulseWeek = filters.week === data.run_id && data.pulse !== null;
  const weekThemes = themeStats(week, data.themes).filter((s) => s.theme.key !== OTHER && s.count > 0).slice(0, 3);
  const prevShares = new Map(themeStats(prev, data.themes).map((s) => [s.theme.key, s.share]));

  const volumeChange = change(now.count, before.count);
  const avgDelta = now.avg !== null && before.avg !== null ? now.avg - before.avg : null;
  const negDelta = before.count ? now.negative - before.negative : null;
  const windowAvg = summarize(window).avg;

  const avgs = series.map((p) => p.avg).filter((v): v is number => v !== null);
  const trendTakeaway =
    avgs.length && now.avg !== null && windowAvg !== null
      ? `Average rating ranged ${Math.min(...avgs).toFixed(1)}–${Math.max(...avgs).toFixed(1)}★ over ${windowWeeks.length} weeks; ${weekShort(
          filters.week,
        )} is ${now.avg.toFixed(2)}★, ${now.avg >= windowAvg ? "above" : "below"} the ${windowAvg.toFixed(2)}★ average.`
      : "No reviews in this selection.";

  const versions = versionStats(window, 20);
  const [latest, baseline] = versions;

  const counts = ratingCounts(week);
  const quotes = isPulseWeek
    ? data.pulse!.quotes.map((q) => ({ ...q, meta: data.store }))
    : representative(week.length >= 3 ? week : window, 3).map((r) => ({ text: r.text, rating: r.rating, theme: r.theme, meta: data.store }));

  return (
    <>
      {/* FIRST FOLD: hero + 4 KPIs + top 3 themes */}
      <section className="relative">
        <div className="relative overflow-hidden rounded-3xl border border-violet-400/20 bg-gradient-to-br from-[#1E1B4B] via-[#4C1D95] to-[#2E1065] px-6 pb-20 pt-7 shadow-[0_16px_40px_-10px_rgba(76,29,149,0.35)] sm:px-8 sm:pt-8">
          <div className="pointer-events-none absolute -right-16 -top-24 h-96 w-96 rounded-full bg-gradient-to-br from-emerald-400/25 via-teal-300/15 to-transparent blur-3xl" />
          <div className="pointer-events-none absolute -left-20 top-1/2 h-80 w-80 rounded-full bg-gradient-to-tr from-fuchsia-500/20 via-violet-400/15 to-transparent blur-3xl" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(255,255,255,0.12),transparent_70%)]" />
          <div className="relative z-10 flex flex-col gap-3">
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-label-sm font-bold uppercase tracking-widest text-purple-200/90 backdrop-blur-md">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
              {weekTitle(filters.week)}
            </span>
            <h1 className="max-w-4xl font-display text-[22px] font-extrabold leading-snug tracking-tight text-white drop-shadow-sm sm:text-headline-xl">
              {headline(pain, moves[0] ?? null)}
            </h1>
          </div>
          <div className="relative z-10 mt-6 flex flex-wrap items-center justify-between gap-3">
            <a
              href={isPulseWeek ? "#pulse" : "#/reviews"}
              onClick={(e) => {
                if (!isPulseWeek) return;
                e.preventDefault();
                document.getElementById("pulse")?.scrollIntoView({ behavior: "smooth" });
              }}
              className="tactile group inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-label-md font-semibold text-primary-fixed backdrop-blur-md hover:border-white/30 hover:bg-white/20 hover:text-white"
            >
              {isPulseWeek ? "View full pulse" : "Explore this week's reviews"}
              <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
            </a>
            {data.publish?.email_at && (
              <span className="hidden items-center gap-2.5 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-label-sm font-medium tracking-wide text-white/90 backdrop-blur-md md:flex">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
                </span>
                {weekShort(data.run_id)} pulse emailed {stamp(data.publish.email_at)}
              </span>
            )}
          </div>
        </div>

        <div className="relative z-20 -mt-12 px-2 sm:px-6">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Reviews this week" icon={<MessageSquareText size={15} className="text-violet-600" />} accent="from-violet-500 to-indigo-500">
              <span className="tnum font-display text-metric-xl font-extrabold text-slate-900">{num(now.count)}</span>
              {volumeChange !== null && <ChangePill good={null}>{signed(volumeChange * 100, 0, "%")}</ChangePill>}
            </Kpi>
            <Kpi label="Average rating" icon={<Star size={15} className="text-amber-500" />} accent="from-amber-400 to-emerald-500">
              <span className="flex items-baseline gap-1">
                <span className="tnum font-display text-metric-xl font-extrabold text-slate-900">{now.avg?.toFixed(1) ?? "–"}</span>
                <span className="text-xl font-bold text-amber-500">★</span>
              </span>
              {avgDelta !== null && <ChangePill good={Math.abs(avgDelta) < 0.05 ? null : avgDelta > 0}>{signed(avgDelta, 1)}</ChangePill>}
            </Kpi>
            <Kpi label="Negative reviews (1–2★)" icon={<Frown size={15} className="text-rose-500" />} accent="from-rose-500 to-amber-500">
              <span className="tnum font-display text-metric-xl font-extrabold text-slate-900">{now.count ? pct(now.negative) : "–"}</span>
              {negDelta !== null && now.count > 0 && (
                <ChangePill good={Math.abs(negDelta) < 0.005 ? null : negDelta < 0}>{signed(negDelta * 100, 0, " pts")}</ChangePill>
              )}
            </Kpi>
            <Kpi label="Top pain point" icon={<AlertTriangle size={15} className="text-purple-600" />} accent="from-purple-600 to-pink-500">
              {pain ? (
                <button type="button" onClick={() => go({ page: "themes", theme: pain.theme.key })} className="text-left">
                  <span className="block font-display text-title-md font-bold text-ink hover:text-primary">{pain.theme.label}</span>
                  <span
                    className="mt-2 inline-flex rounded-full px-2.5 py-0.5 text-label-sm font-semibold"
                    style={{ backgroundColor: tint(pain.theme.color, 0.12), color: shade(pain.theme.color) }}
                  >
                    {pct(pain.share)} of volume · {pct(pain.negative)} negative
                  </span>
                </button>
              ) : (
                <span className="text-muted">–</span>
              )}
            </Kpi>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
            {weekThemes.map((s) => {
              const before = prevShares.get(s.theme.key) ?? 0;
              const up = s.share > before;
              return (
                <button
                  key={s.theme.key}
                  type="button"
                  onClick={() => go({ page: "themes", theme: s.theme.key })}
                  className="card tactile flex items-center justify-between gap-3 px-5 py-4 text-left transition-transform hover:-translate-y-0.5"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: s.theme.color, boxShadow: `0 0 0 4px ${tint(s.theme.color, 0.15)}` }} />
                    <span className="truncate font-display text-body-lg font-semibold" style={{ color: shade(s.theme.color, 0.2) }}>
                      {s.theme.label}
                    </span>
                  </span>
                  <span
                    className="tnum inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-label-md font-bold"
                    style={{ backgroundColor: tint(s.theme.color, 0.12), color: shade(s.theme.color) }}
                    title={`Share of this week's reviews; ${weekShort(prevWeek ?? "")} was ${pct(before)}`}
                  >
                    {pct(s.share)} {prevWeek && (up ? <ArrowUp size={13} /> : <ArrowDown size={13} />)}
                  </span>
                </button>
              );
            })}
            {!weekThemes.length && <p className="text-body-sm text-muted">No themed reviews this week.</p>}
          </div>
        </div>
      </section>

      <Section title="Volume & rating trend" takeaway={trendTakeaway}>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="card p-6">
            <CardTitle right={<Tag className="bg-slate-100 text-slate-500">{weekShort(windowWeeks[0] ?? "")} – {weekShort(filters.week)}</Tag>}>
              Weekly review volume
            </CardTitle>
            <LineChart
              labels={windowWeeks.map(weekShort)}
              series={[{ name: "Reviews", color: "#7C3AED", values: series.map((p) => p.count), fill: true }]}
              domain={[0, Math.max(...series.map((p) => p.count), 1) * 1.15]}
              format={(v) => String(Math.round(v))}
              highlight={hi}
              footer={(i) => (
                <>
                  <div className={`tnum text-label-md font-bold ${i === hi ? "text-primary" : "text-on-surface"}`}>{series[i].count}</div>
                  <div className="text-[10px] text-muted">{weekShort(windowWeeks[i])}</div>
                </>
              )}
            />
          </div>
          <div className="card p-6">
            <CardTitle
              right={
                avgDelta !== null && (
                  <Tag className={avgDelta >= 0 ? "bg-emerald-500/12 text-emerald-700" : "bg-rose-500/12 text-rose-700"}>
                    <TrendingUp size={12} className={avgDelta < 0 ? "rotate-180" : ""} /> {signed(avgDelta, 1)} vs last week
                  </Tag>
                )
              }
            >
              Weekly average rating
            </CardTitle>
            <LineChart
              labels={windowWeeks.map(weekShort)}
              series={[{ name: "Avg rating", color: "#10B981", values: series.map((p) => p.avg) }]}
              domain={[Math.max(1, Math.min(...avgs, 5) - 0.4), Math.min(5, Math.max(...avgs, 1) + 0.4)]}
              format={(v) => `${v.toFixed(2)}★`}
              highlight={hi}
              footer={(i) => {
                const a = series[i].avg;
                const low = a !== null && windowAvg !== null && a < windowAvg;
                return (
                  <>
                    <div className={`tnum text-label-md font-bold ${low ? "text-rose-600" : "text-emerald-700"}`}>{a?.toFixed(1) ?? "–"}</div>
                    <div className="text-[10px] text-muted">{weekShort(windowWeeks[i])}</div>
                  </>
                );
              }}
            />
          </div>
        </div>
      </Section>

      <Section
        title="Themes breakdown"
        takeaway={
          stats[0]?.count
            ? `${stats[0].theme.label} accounts for ${pct(stats[0].share)} of feedback over ${windowWeeks.length} weeks; click a theme to drill in.`
            : undefined
        }
      >
        {window.length === 0 ? (
          <div className="card">
            <Empty title="No reviews match these filters" hint="Widen the lookback or reset the filters." />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="card p-6">
              <CardTitle right={<span className="tnum text-label-sm text-muted">{num(window.length)} reviews</span>}>Feedback distribution by theme</CardTitle>
              <div className="flex flex-col gap-3">
                {stats.map((s) => (
                  <BarRow
                    key={s.theme.key}
                    label={
                      <>
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.theme.color }} />
                        {s.theme.label}
                      </>
                    }
                    value={s.share}
                    max={stats[0].share}
                    color={s.theme.color}
                    right={pct(s.share)}
                    onClick={s.theme.key === OTHER ? undefined : () => go({ page: "themes", theme: s.theme.key })}
                  />
                ))}
              </div>
            </div>
            <div className="card p-6">
              <CardTitle
                right={
                  <span className="flex items-center gap-3 text-label-sm text-muted">
                    <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" />Positive</span>
                    <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" />Neutral</span>
                    <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-rose-500" />Negative</span>
                  </span>
                }
              >
                Sentiment split by theme
              </CardTitle>
              <div className="flex flex-col gap-4">
                {stats.map((s) => {
                  const lead =
                    s.negative >= 0.5
                      ? { t: `${pct(s.negative)} neg`, c: "bg-rose-500/12 text-rose-700" }
                      : s.positive >= 0.5
                        ? { t: `${pct(s.positive)} pos`, c: "bg-emerald-500/12 text-emerald-700" }
                        : { t: "Mixed", c: "bg-slate-100 text-slate-600" };
                  return (
                    <div key={s.theme.key}>
                      <div className="mb-1.5 flex items-center justify-between text-body-sm">
                        <span className="text-on-surface">{s.theme.label}</span>
                        <span className="flex items-center gap-2">
                          <span className="tnum text-label-sm text-muted">avg {s.avg?.toFixed(2) ?? "–"}★</span>
                          <Tag className={lead.c}>{lead.t}</Tag>
                        </span>
                      </div>
                      <SentimentBar negative={s.negative} neutral={s.neutral} positive={s.positive} />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </Section>

      <Section
        id="pulse"
        title="What users said"
        takeaway={
          isPulseWeek
            ? `The verbatim quotes chosen for the published ${weekShort(data.run_id)} pulse.`
            : `Short, clearly themed reviews from ${weekShort(filters.week)}, mixing ratings. Pulse quotes are shown for ${weekShort(data.run_id)}.`
        }
      >
        {quotes.length ? (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {quotes.map((q, i) => (
              <QuoteCard key={i} text={q.text} rating={q.rating} theme={q.theme} meta={q.meta} />
            ))}
          </div>
        ) : (
          <div className="card">
            <Empty title="No quotable reviews in this selection" />
          </div>
        )}
      </Section>

      {data.pulse && (
        <Section
          title="Action ideas"
          takeaway={`From the ${weekShort(data.run_id)} pulse: one next step for each top theme, grounded in its reviews.`}
          action={
            data.publish?.doc_url && (
              <a href={data.publish.doc_url} target="_blank" rel="noreferrer" className="glass-btn">
                <FileText size={15} className="text-primary" /> Open Google Doc
              </a>
            )
          }
        >
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {data.pulse.actions.map((a, i) => {
              const t = a.theme ? theme(a.theme) : null;
              const summary = data.pulse!.themes.find((s) => s.theme === a.theme)?.summary;
              return (
                <article key={i} className="card relative flex flex-col gap-3 overflow-hidden p-6">
                  {t && <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full blur-2xl" style={{ backgroundColor: tint(t.color, 0.18) }} />}
                  <div className="relative flex items-center justify-between gap-2">
                    <Tag className="bg-gradient-to-r from-primary-container to-primary text-white">
                      <Zap size={11} /> Action {i + 1}
                    </Tag>
                    {t && <ThemeChip theme={t} onClick={() => go({ page: "themes", theme: t.key })} />}
                  </div>
                  <h3 className="relative font-display text-title-md font-bold leading-snug text-ink">{a.text}</h3>
                  {summary && <p className="relative text-body-sm text-muted">Why: {summary}.</p>}
                </article>
              );
            })}
          </div>
        </Section>
      )}

      <Section
        title="Release watch & rating distribution"
        takeaway={
          latest && baseline && latest.avg !== null && baseline.avg !== null
            ? `v${latest.version} averages ${latest.avg.toFixed(2)}★ vs ${baseline.avg.toFixed(2)}★ on v${baseline.version} (versions with 20+ reviews in the window).`
            : "Not enough reviews per version in this window to compare releases."
        }
      >
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="card p-6">
            <CardTitle right={latest && baseline && <Tag className="bg-slate-100 font-mono text-slate-500">v{latest.version} vs v{baseline.version}</Tag>}>
              Version comparison
            </CardTitle>
            {latest && baseline ? (
              <div className="flex flex-col gap-3">
                {[latest, baseline].map((v, i) => {
                  const worse = i === 0 && v.avg! < baseline.avg! - 0.1;
                  return (
                    <div
                      key={v.version}
                      className={`flex items-center justify-between rounded-2xl border p-4 ${
                        worse ? "border-rose-200 bg-rose-50/60" : "border-emerald-200 bg-emerald-50/50"
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-body-lg font-bold text-ink">v{v.version}</span>
                          <Tag className={i === 0 ? "bg-violet-500/12 text-violet-700" : "bg-emerald-500/12 text-emerald-700"}>
                            {i === 0 ? "Latest" : "Previous"}
                          </Tag>
                        </div>
                        <span className="tnum text-label-md text-muted">{num(v.count)} reviews</span>
                      </div>
                      <div className="text-right">
                        <div className={`tnum font-display text-metric-md font-bold ${worse ? "text-rose-600" : "text-emerald-700"}`}>
                          {v.avg!.toFixed(1)} <span className="text-amber-500">★</span>
                        </div>
                        <span className="tnum text-label-sm text-muted">{pct(v.negative)} negative</span>
                      </div>
                    </div>
                  );
                })}
                {(() => {
                  const gap = latest.avg! - baseline.avg!;
                  const negGap = (latest.negative - baseline.negative) * 100;
                  const bad = gap < -0.1;
                  return (
                    <div
                      className={`flex items-start gap-2 rounded-xl border p-3 text-label-md ${
                        bad ? "border-amber-200 bg-amber-50 text-amber-800" : "border-slate-200 bg-slate-50 text-slate-600"
                      }`}
                    >
                      {bad ? <AlertTriangle size={15} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" />}
                      <span>
                        Rating {signed(gap, 2)}★ and negative share {signed(negGap, 0, " pts")} on v{latest.version}
                        {bad ? ": worth checking what changed in this release." : ": no regression signal."}
                      </span>
                    </div>
                  );
                })()}
                <div className="mt-2 flex flex-col gap-2">
                  {versions.slice(2, 6).map((v) => (
                    <div key={v.version} className="flex items-center justify-between text-body-sm">
                      <span className="font-mono text-slate-600">v{v.version}</span>
                      <span className="tnum text-muted">
                        {num(v.count)} reviews · {v.avg!.toFixed(2)}★ · {pct(v.negative)} neg
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <Empty title="Not enough data per version" hint="Each version needs 20+ reviews in the lookback window." />
            )}
          </div>
          <div className="card p-6">
            <CardTitle right={<span className="tnum text-label-sm text-muted">{num(now.count)} reviews · {weekShort(filters.week)}</span>}>
              Star rating breakdown
            </CardTitle>
            <div className="flex flex-col gap-3">
              {([5, 4, 3, 2, 1] as Rating[]).map((r) => {
                const share = now.count ? counts[r] / now.count : 0;
                const color = r >= 4 ? (r === 5 ? "#10B981" : "#34D399") : r === 3 ? "#94A3B8" : r === 2 ? "#FB7185" : "#E11D48";
                return (
                  <div key={r} className="flex items-center gap-3">
                    <span className="tnum w-6 text-label-md font-semibold text-slate-600">{r}★</span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${share * 100}%`, backgroundColor: color }} />
                    </div>
                    <span className="tnum w-20 text-right text-label-md text-slate-600">
                      {pct(share)} <span className="text-muted">({counts[r]})</span>
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="mt-6 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
              <Tag className="bg-rose-500/10 text-rose-700">{pct(now.negative)} negative (1–2★)</Tag>
              <Tag className="bg-slate-100 text-slate-600">{pct(now.neutral)} neutral (3★)</Tag>
              <Tag className="bg-emerald-500/10 text-emerald-700">{pct(now.positive)} positive (4–5★)</Tag>
            </div>
          </div>
        </div>
      </Section>
    </>
  );
}
