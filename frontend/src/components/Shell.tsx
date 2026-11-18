import {
  CalendarDays,
  Check,
  ChevronDown,
  FileText,
  LayoutDashboard,
  Link2,
  MessageSquareText,
  Printer,
  Share2,
  Shapes,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { stamp, weekLabel, weekShort } from "../lib/format";
import { topVersions } from "../lib/metrics";
import { href, useRoute, type Route } from "../lib/router";
import { activeFilterCount, LOOKBACKS, useStore } from "../lib/store";
import type { Rating } from "../lib/types";
import { RatingChip, Segmented, tint } from "./ui";

const NAV: { route: Route; label: string; icon: typeof LayoutDashboard }[] = [
  { route: { page: "overview" }, label: "Overview", icon: LayoutDashboard },
  { route: { page: "themes", theme: null }, label: "Themes", icon: Shapes },
  { route: { page: "reviews" }, label: "Reviews", icon: MessageSquareText },
];

function Sidebar() {
  const route = useRoute();
  return (
    <aside className="group fixed left-0 top-0 z-50 hidden h-full w-16 flex-col overflow-hidden border-r border-slate-200/70 bg-white/80 shadow-[2px_0_16px_rgba(30,27,75,0.03)] backdrop-blur-xl transition-[width] duration-300 ease-out hover:w-60 sm:flex">
      <div className="flex h-16 items-center gap-3 border-b border-slate-100/80 px-4">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-primary to-primary-container text-white shadow-[0_4px_12px_rgba(109,40,217,0.35)] ring-1 ring-white/30">
          <Sparkles size={17} />
        </span>
        <span className="whitespace-nowrap font-display text-title-md font-extrabold tracking-tight text-on-surface opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          Review Pulse
        </span>
      </div>
      <nav className="mt-3 flex flex-col gap-1.5 px-2.5" aria-label="Main">
        {NAV.map(({ route: r, label, icon: Icon }) => {
          const active = route.page === r.page;
          return (
            <a
              key={label}
              href={href(r)}
              aria-current={active ? "page" : undefined}
              className={`tactile flex h-10 items-center gap-3 overflow-hidden rounded-xl px-2.5 ${
                active
                  ? "bg-gradient-to-r from-primary-container to-primary font-medium text-white shadow-[0_4px_14px_rgba(109,40,217,0.3)]"
                  : "text-slate-500 hover:bg-violet-50 hover:text-primary"
              }`}
            >
              <Icon size={19} className="shrink-0" />
              <span className="whitespace-nowrap text-body-md font-semibold opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                {label}
              </span>
            </a>
          );
        })}
      </nav>
    </aside>
  );
}

function MobileNav() {
  const route = useRoute();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-50 flex justify-around border-t border-slate-200/70 bg-white/90 py-2 backdrop-blur-xl sm:hidden"
    >
      {NAV.map(({ route: r, label, icon: Icon }) => (
        <a
          key={label}
          href={href(r)}
          className={`flex flex-col items-center gap-0.5 px-4 text-label-sm ${
            route.page === r.page ? "text-primary" : "text-slate-500"
          }`}
        >
          <Icon size={20} />
          {label}
        </a>
      ))}
    </nav>
  );
}

/** Closes a popover on an outside click or Escape. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

function WeekPicker() {
  const { weeks, filters, setFilters, data } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  return (
    <div ref={ref} className="relative">
      <button type="button" className="glass-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        <CalendarDays size={15} className="text-primary" />
        <span className="hidden md:inline">
          Week {Number(filters.week.slice(6))} ({weekLabel(filters.week)})
        </span>
        <span className="md:hidden">{weekShort(filters.week)}</span>
        <ChevronDown size={15} className="text-slate-400" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1.5 max-h-96 w-72 overflow-y-auto rounded-2xl border border-slate-200/80 bg-white/95 p-1.5 shadow-[0_20px_48px_-8px_rgba(30,27,75,0.12)] backdrop-blur-xl">
          {[...weeks].reverse().map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => {
                setFilters({ week: w });
                setOpen(false);
              }}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-label-md ${
                w === filters.week ? "bg-violet-50 text-primary" : "text-on-surface hover:bg-slate-50"
              }`}
            >
              <span>
                <span className="font-bold">{weekShort(w)}</span>
                <span className="ml-2 text-muted">{weekLabel(w)}</span>
              </span>
              {w === data.run_id ? (
                <span className="rounded-full bg-primary-fixed px-2 py-0.5 text-label-sm text-primary">Pulse</span>
              ) : (
                w === filters.week && <Check size={14} />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ShareMenu() {
  const { data } = useStore();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  const item = "flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-label-md font-medium text-slate-600 hover:bg-violet-50 hover:text-primary";
  return (
    <div ref={ref} className="relative">
      <button type="button" className="glass-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        <Share2 size={15} className="text-slate-500" />
        <span className="hidden md:inline">Share</span>
        <ChevronDown size={15} className="text-slate-400" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1.5 w-56 rounded-2xl border border-slate-200/80 bg-white/95 p-1.5 shadow-[0_20px_48px_-8px_rgba(30,27,75,0.12)] backdrop-blur-xl">
          {data.publish?.doc_url && (
            <a className={item} href={data.publish.doc_url} target="_blank" rel="noreferrer">
              <FileText size={16} className="text-primary" /> Open Google Doc
            </a>
          )}
          <button
            type="button"
            className={item}
            onClick={() => {
              setOpen(false);
              setTimeout(() => window.print(), 50);
            }}
          >
            <Printer size={16} className="text-rose-600" /> Export PDF
          </button>
          <button
            type="button"
            className={item}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(window.location.href);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              } catch {
                /* clipboard blocked: nothing to do */
              }
            }}
          >
            <Link2 size={16} className="text-slate-500" /> {copied ? "Link copied" : "Copy link"}
          </button>
        </div>
      )}
    </div>
  );
}

function FilterDrawer({ onClose }: { onClose: () => void }) {
  const { data, filters, setFilters, resetFilters } = useStore();
  const versions = topVersions(data.reviews, 12);
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const group = "border-b border-slate-100 py-5";
  const heading = "mb-3 text-label-sm font-bold uppercase tracking-wider text-muted";
  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Filters">
      <button type="button" aria-label="Close filters" className="absolute inset-0 bg-ink/20 backdrop-blur-[2px]" onClick={onClose} />
      <div className="absolute right-0 top-0 flex h-full w-full max-w-sm flex-col bg-white shadow-[0_20px_48px_-8px_rgba(30,27,75,0.25)]">
        <div className="flex h-16 items-center justify-between border-b border-slate-100 px-6">
          <h2 className="font-display text-title-md font-bold text-ink">Filters</h2>
          <button type="button" onClick={onClose} className="tactile rounded-lg p-1.5 text-muted hover:bg-slate-100" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6">
          <div className={group}>
            <p className={heading}>Lookback</p>
            <Segmented
              label="Lookback"
              value={filters.lookback}
              onChange={(lookback) => setFilters({ lookback })}
              options={LOOKBACKS.map((n) => ({ value: n, label: `${n} weeks` }))}
            />
            <p className="mt-2 text-body-sm text-muted">Trends, themes and distributions cover this many weeks.</p>
          </div>
          <div className={group}>
            <p className={heading}>Store</p>
            <div className="flex gap-2">
              <span className="rounded-lg bg-violet-50 px-3 py-1.5 text-label-md font-semibold text-primary">{data.store}</span>
              <span className="rounded-lg bg-slate-50 px-3 py-1.5 text-label-md text-slate-400">App Store · coming soon</span>
            </div>
          </div>
          <div className={group}>
            <p className={heading}>Rating</p>
            <div className="flex flex-wrap gap-2">
              {([1, 2, 3, 4, 5] as Rating[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  aria-pressed={filters.ratings.includes(r)}
                  onClick={() => setFilters({ ratings: toggle(filters.ratings, r) })}
                  className={`tactile rounded-full ring-2 ${filters.ratings.includes(r) ? "ring-primary-container" : "ring-transparent"}`}
                >
                  <RatingChip rating={r} />
                </button>
              ))}
            </div>
          </div>
          <div className={group}>
            <p className={heading}>Theme</p>
            <div className="flex flex-col gap-1">
              {data.themes.map((t) => {
                const on = filters.themes.includes(t.key);
                return (
                  <label key={t.key} className="flex cursor-pointer items-center gap-3 rounded-xl px-2 py-2 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => setFilters({ themes: toggle(filters.themes, t.key) })}
                      className="h-4 w-4 accent-primary-container"
                    />
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: t.color, boxShadow: `0 0 0 3px ${tint(t.color, 0.15)}` }} />
                    <span className="text-body-md text-on-surface">{t.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
          <div className={group}>
            <p className={heading}>App version (most reviewed)</p>
            <div className="flex flex-wrap gap-2">
              {versions.map((v) => {
                const on = filters.versions.includes(v.version);
                return (
                  <button
                    key={v.version}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setFilters({ versions: toggle(filters.versions, v.version) })}
                    className={`tactile tnum rounded-lg px-2.5 py-1 text-label-md font-semibold ${
                      on ? "bg-primary-container text-white" : "bg-slate-100 text-slate-600 hover:bg-violet-50"
                    }`}
                  >
                    {v.version}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-6 py-4">
          <button type="button" onClick={resetFilters} className="tactile text-label-md font-semibold text-primary hover:underline">
            Reset filters
          </button>
          <button
            type="button"
            onClick={onClose}
            className="tactile h-10 rounded-xl bg-gradient-to-r from-primary-container to-primary px-5 text-label-md font-semibold text-white shadow-[0_4px_14px_rgba(109,40,217,0.3)]"
          >
            Show results
          </button>
        </div>
      </div>
    </div>
  );
}

function TopBar({ onFilters }: { onFilters: () => void }) {
  const { data, filters } = useStore();
  const count = activeFilterCount(filters);
  const published = data.publish?.email_status === "done" || Boolean(data.publish?.doc_url);
  return (
    <header className="fixed left-0 right-0 top-0 z-40 h-16 border-b border-slate-200/60 bg-white/80 shadow-[0_2px_12px_rgba(0,0,0,0.03)] backdrop-blur-xl sm:left-16 print:hidden">
      <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-display text-title-md font-bold tracking-tight text-on-surface">
            {data.app} Review Pulse
          </span>
          {published && (
            <span className="ml-1 hidden items-center gap-1.5 rounded-full border border-emerald-500/20 bg-gradient-to-r from-emerald-500/10 to-teal-500/15 px-2.5 py-0.5 text-label-sm font-semibold text-emerald-800 lg:inline-flex">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              {weekShort(data.run_id)} pulse published
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <WeekPicker />
          <ShareMenu />
          <button
            type="button"
            onClick={onFilters}
            className="tactile flex h-9 items-center gap-2 rounded-xl bg-gradient-to-r from-primary-container to-primary px-3.5 text-label-md font-semibold text-white shadow-[0_4px_14px_rgba(109,40,217,0.3)] hover:brightness-110"
          >
            <SlidersHorizontal size={15} />
            <span className="hidden sm:inline">Filters</span>
            {count > 0 && (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/25 text-label-sm font-bold">{count}</span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { data } = useStore();
  const [filtersOpen, setFiltersOpen] = useState(false);
  return (
    <div className="relative min-h-screen">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden print:hidden" aria-hidden>
        <div className="absolute -top-32 left-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-br from-purple-200/40 via-violet-100/20 to-transparent blur-3xl" />
        <div className="absolute right-0 top-[45%] h-[550px] w-[550px] rounded-full bg-gradient-to-bl from-indigo-100/30 via-sky-100/20 to-transparent blur-3xl" />
        <div className="absolute bottom-10 left-10 h-[500px] w-[500px] rounded-full bg-gradient-to-tr from-emerald-100/25 via-teal-50/15 to-transparent blur-3xl" />
      </div>
      <span className="print:hidden">
        <Sidebar />
      </span>
      <TopBar onFilters={() => setFiltersOpen(true)} />
      <div className="relative z-10 flex min-h-screen flex-col sm:pl-16 print:pl-0">
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 pb-24 pt-20 sm:px-8 sm:pb-12 print:pt-4">{children}</main>
        <footer className="mx-auto flex w-full max-w-[1440px] flex-wrap items-center justify-between gap-2 px-4 pb-20 pt-4 text-label-sm text-muted sm:px-8 sm:pb-6">
          <span>
            Data as of {stamp(data.generated_at)} · {data.store} · PII scrubbed &amp; anonymised
          </span>
          <span>Theme clustering: TF-IDF + NMF · summaries by LLM, quotes verbatim</span>
        </footer>
      </div>
      <span className="print:hidden">
        <MobileNav />
      </span>
      {filtersOpen && <FilterDrawer onClose={() => setFiltersOpen(false)} />}
    </div>
  );
}
