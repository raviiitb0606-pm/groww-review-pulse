import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { dateLabel } from "../lib/format";
import { sentiment } from "../lib/metrics";
import { go } from "../lib/router";
import { useStore } from "../lib/store";
import type { Rating, Review } from "../lib/types";
import { RatingChip, ReviewText, SentimentTag, Tag, ThemeChip } from "./ui";

const EDGE = { negative: "border-l-rose-500", neutral: "border-l-amber-400", positive: "border-l-emerald-500" };

export function QuoteCard({
  text,
  rating,
  theme,
  meta,
}: {
  text: string;
  rating: Rating;
  theme: string | null;
  meta?: string;
}) {
  const { data, theme: themeOf } = useStore();
  const t = theme ? themeOf(theme) : null;
  return (
    <figure className={`card flex h-full flex-col gap-4 border-l-4 p-6 ${EDGE[sentiment(rating)]}`}>
      <div className="flex items-center justify-between gap-2">
        <RatingChip rating={rating} />
        <Tag className="bg-slate-100 text-slate-500">{meta ?? data.store}</Tag>
      </div>
      <blockquote className="relative flex-1 pl-5 text-body-md italic leading-relaxed text-slate-700">
        <span className="absolute -top-1 left-0 font-display text-2xl not-italic leading-none text-violet-300" aria-hidden>
          “
        </span>
        <ReviewText text={text} />
      </blockquote>
      {t && (
        <figcaption>
          <ThemeChip theme={t} onClick={() => go({ page: "themes", theme: t.key })} />
        </figcaption>
      )}
    </figure>
  );
}

export function ReviewCard({ review, showTheme = true }: { review: Review; showTheme?: boolean }) {
  const { theme } = useStore();
  const [open, setOpen] = useState(false);
  const long = review.text.length > 240;
  const t = theme(review.theme);
  return (
    <article className="card group p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <RatingChip rating={review.rating} />
        <span className="tnum text-label-md text-muted">{dateLabel(review.date)}</span>
        {review.version && (
          <Tag className="tnum bg-violet-50 font-mono text-violet-700">v{review.version}</Tag>
        )}
        {showTheme && <ThemeChip theme={t} onClick={() => go({ page: "themes", theme: t.key })} />}
        <span className="ml-auto">
          <SentimentTag rating={review.rating} />
        </span>
      </div>
      <p className={`mt-3 text-body-md leading-relaxed text-slate-700 ${!open && long ? "line-clamp-3" : ""}`}>
        <ReviewText text={review.text} />
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {long && (
          <button type="button" onClick={() => setOpen(!open)} className="text-label-md font-semibold text-primary hover:underline">
            {open ? "Show less" : "Show more"}
          </button>
        )}
        <Tag
          className={
            review.confidence === "high" ? "bg-emerald-500/10 text-emerald-700" : "bg-amber-500/10 text-amber-700"
          }
        >
          <ShieldCheck size={12} /> {review.confidence === "high" ? "High" : "Low"} theme confidence
        </Tag>
        {review.quote_eligible && <Tag className="bg-violet-500/10 text-violet-700">Quote-eligible</Tag>}
      </div>
    </article>
  );
}
