import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { sentiment, type Sentiment } from "../lib/metrics";
import type { Rating, ThemeMeta } from "../lib/types";

export function tint(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export const SENTIMENT_STYLE: Record<Sentiment, { bg: string; text: string; bar: string; label: string }> = {
  negative: { bg: "bg-rose-500/12", text: "text-rose-700", bar: "bg-rose-500", label: "Negative" },
  neutral: { bg: "bg-amber-500/12", text: "text-amber-700", bar: "bg-amber-400", label: "Neutral" },
  positive: { bg: "bg-emerald-500/12", text: "text-emerald-700", bar: "bg-emerald-500", label: "Positive" },
};

export function Section({
  id,
  title,
  takeaway,
  children,
  action,
}: {
  id?: string;
  title: string;
  takeaway?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section id={id} className="mt-10 scroll-mt-24">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 font-display text-title-md font-bold text-ink">
            {title}
            <span className="h-1.5 w-1.5 rounded-full bg-violet-400" />
          </h2>
          {takeaway && <p className="mt-0.5 text-body-sm text-muted">{takeaway}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function CardTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-5 flex items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-label-md font-semibold text-on-surface">
        <span className="h-1.5 w-1.5 rounded-full bg-primary-container" />
        {children}
      </h3>
      {right}
    </div>
  );
}

export function Tag({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-label-sm font-semibold ${className}`}
    >
      {children}
    </span>
  );
}

/** The colour mixed toward black, for text on a light tint of the same colour. */
export function shade(hex: string, amount = 0.35): string {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.round(v * (1 - amount)));
  return `rgb(${c.join(", ")})`;
}

export function ThemeChip({ theme, onClick }: { theme: ThemeMeta; onClick?: () => void }) {
  const style = { backgroundColor: tint(theme.color, 0.12), color: shade(theme.color) };
  const className =
    "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-label-sm font-semibold";
  const inner = (
    <>
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: theme.color }} />
      {theme.label}
    </>
  );
  return onClick ? (
    <button type="button" onClick={onClick} className={`tactile hover:brightness-95 ${className}`} style={style}>
      {inner}
    </button>
  ) : (
    <span className={className} style={style}>
      {inner}
    </span>
  );
}

export function RatingChip({ rating }: { rating: Rating }) {
  const s = SENTIMENT_STYLE[sentiment(rating)];
  return (
    <Tag className={`${s.bg} ${s.text} tnum`}>
      {rating}
      <span aria-hidden>★</span>
      <span className="sr-only"> stars</span>
    </Tag>
  );
}

export function SentimentTag({ rating }: { rating: Rating }) {
  const s = SENTIMENT_STYLE[sentiment(rating)];
  return <Tag className={`${s.bg} ${s.text}`}>{s.label}</Tag>;
}

/** A change pill. `good` says whether this change is good news, which sets its colour. */
export function ChangePill({ children, good }: { children: ReactNode; good: boolean | null }) {
  const tone =
    good === null
      ? "bg-slate-500/10 border-slate-500/20 text-slate-600"
      : good
        ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-700 shadow-[0_2px_8px_rgba(16,185,129,0.2)]"
        : "bg-rose-500/12 border-rose-500/25 text-rose-700 shadow-[0_2px_8px_rgba(225,29,72,0.15)]";
  return (
    <span
      className={`tnum inline-flex items-center gap-0.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-label-md font-bold ${tone}`}
    >
      {children}
    </span>
  );
}

/** Review text with the scrubber's redaction tokens shown as grey pills. */
export function ReviewText({ text }: { text: string }) {
  const parts = text.split(/(\[redacted\]|\[name\])/g);
  return (
    <>
      {parts.map((part, i) =>
        part === "[redacted]" || part === "[name]" ? (
          <span
            key={i}
            title="Personal data removed before analysis"
            className="mx-0.5 inline-flex items-center rounded-md bg-slate-200/70 px-1.5 font-mono text-[11px] font-semibold text-slate-600"
          >
            {part.slice(1, -1)}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-violet-50 text-violet-500">
        <Inbox size={20} />
      </span>
      <p className="font-display text-body-md font-semibold text-ink">{title}</p>
      {hint && <p className="max-w-sm text-body-sm text-muted">{hint}</p>}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  size,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  size: number;
  onPage: (p: number) => void;
}) {
  if (total === 0) return null;
  const from = (page - 1) * size + 1;
  const to = Math.min(page * size, total);
  const shown = [...new Set([1, page - 1, page, page + 1, pages])].filter((p) => p >= 1 && p <= pages);
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
      <p className="text-body-sm text-muted">
        Showing {from}–{to} of {total.toLocaleString("en-IN")} reviews
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={page === 1}
          onClick={() => onPage(page - 1)}
          className="tactile flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-violet-50 disabled:opacity-30"
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </button>
        {shown.map((p, i) => (
          <span key={p} className="flex items-center gap-1.5">
            {i > 0 && p - shown[i - 1] > 1 && <span className="text-muted">…</span>}
            <button
              type="button"
              onClick={() => onPage(p)}
              aria-current={p === page ? "page" : undefined}
              className={`tactile tnum h-8 min-w-8 rounded-lg px-2 text-label-md font-semibold ${
                p === page
                  ? "bg-gradient-to-r from-primary-container to-primary text-white shadow-[0_4px_12px_rgba(109,40,217,0.3)]"
                  : "text-on-surface hover:bg-violet-50"
              }`}
            >
              {p}
            </button>
          </span>
        ))}
        <button
          type="button"
          disabled={page === pages}
          onClick={() => onPage(page + 1)}
          className="tactile flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-violet-50 disabled:opacity-30"
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-xl bg-slate-100/80 p-1">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`tactile rounded-lg px-3 py-1.5 text-label-md font-semibold ${
            o.value === value ? "bg-white text-primary shadow-sm" : "text-muted hover:text-on-surface"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
