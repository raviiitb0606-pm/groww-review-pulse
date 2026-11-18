import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** The element's content width, kept current, so charts draw at real pixels. */
function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** A smooth path through the points (Catmull-Rom as cubic Béziers). */
function smooth(pts: [number, number][]): string {
  if (pts.length < 2) return pts.length ? `M${pts[0][0]},${pts[0][1]}` : "";
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const [p0, p1, p2, p3] = [pts[i - 1] ?? pts[i], pts[i], pts[i + 1], pts[i + 2] ?? pts[i + 1]];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${p2[0]},${p2[1]}`;
  }
  return d;
}

export interface Series {
  name: string;
  color: string;
  values: (number | null)[];
  dashed?: boolean;
  fill?: boolean;
}

interface LineChartProps {
  labels: string[];
  series: Series[];
  domain: [number, number];
  format: (v: number) => string;
  height?: number;
  ticks?: number[]; // gridlines with axis labels; omit for none
  highlight?: number; // index of the emphasised point (the selected week)
  footer?: (i: number) => ReactNode; // per-point caption under the plot
}

export function LineChart({
  labels,
  series,
  domain,
  format,
  height = 180,
  ticks,
  highlight,
  footer,
}: LineChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const gid = useId().replace(/:/g, "");
  const pad = { l: ticks ? 36 : 14, r: 14, t: 16, b: 8 };
  const n = labels.length;
  const w = Math.max(width - pad.l - pad.r, 1);
  const h = height - pad.t - pad.b;
  const x = (i: number) => pad.l + (n > 1 ? (i * w) / (n - 1) : w / 2);
  const y = (v: number) => pad.t + h - ((v - domain[0]) / (domain[1] - domain[0] || 1)) * h;

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={series.map((s) => s.name).join(", ")}>
          <defs>
            {series.map((s, si) => (
              <linearGradient key={si} id={`${gid}-${si}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={s.color} stopOpacity="0.28" />
                <stop offset="1" stopColor={s.color} stopOpacity="0" />
              </linearGradient>
            ))}
          </defs>
          {ticks?.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke="#e2e8f0" strokeDasharray="3 4" />
              <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="fill-slate-400 text-[10px]">
                {format(t)}
              </text>
            </g>
          ))}
          {!ticks &&
            [0.25, 0.5, 0.75].map((f) => (
              <line key={f} x1={pad.l} x2={width - pad.r} y1={pad.t + h * f} y2={pad.t + h * f} stroke="#f1f5f9" />
            ))}
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + h} stroke="#c4b5fd" strokeDasharray="3 3" />
          )}
          {series.map((s, si) => {
            const pts = s.values
              .map((v, i) => (v === null ? null : ([x(i), y(v)] as [number, number])))
              .filter((p): p is [number, number] => p !== null);
            const line = smooth(pts);
            return (
              <g key={si}>
                {s.fill && pts.length > 1 && (
                  <path
                    d={`${line} L${pts[pts.length - 1][0]},${pad.t + h} L${pts[0][0]},${pad.t + h} Z`}
                    fill={`url(#${gid}-${si})`}
                  />
                )}
                <path
                  d={line}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeDasharray={s.dashed ? "6 5" : undefined}
                />
                {s.values.map((v, i) =>
                  v === null ? null : (
                    <circle
                      key={i}
                      cx={x(i)}
                      cy={y(v)}
                      r={i === highlight || i === hover ? 6 : 3.5}
                      fill={i === highlight ? "#fff" : s.color}
                      stroke={s.color}
                      strokeWidth={i === highlight ? 3 : 2}
                      style={{
                        transition: "r 0.2s cubic-bezier(0.16,1,0.3,1)",
                        filter: i === hover ? `drop-shadow(0 0 6px ${s.color})` : undefined,
                      }}
                    />
                  ),
                )}
              </g>
            );
          })}
          {labels.map((_, i) => (
            <rect
              key={i}
              x={x(i) - w / Math.max(n - 1, 1) / 2}
              y={0}
              width={w / Math.max(n - 1, 1)}
              height={height}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </svg>
      )}
      {hover !== null && width > 0 && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-xl bg-ink px-3 py-2 text-label-sm text-white shadow-lg"
          style={{
            left: Math.min(Math.max(x(hover), 70), width - 70),
            top: Math.min(...series.map((s) => (s.values[hover] === null ? height : y(s.values[hover]!)))) - 10,
          }}
        >
          <div className="mb-0.5 font-bold text-violet-200">{labels[hover]}</div>
          {series.map((s) => (
            <div key={s.name} className="flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s.color }} />
              {s.name}: <span className="tnum font-bold">{s.values[hover] === null ? "–" : format(s.values[hover]!)}</span>
            </div>
          ))}
        </div>
      )}
      {footer && width > 0 && (
        <div className="relative mt-3 h-10">
          {labels.map((label, i) => (
            // Captions need ~36px each; on narrow charts show every other one (and the highlight).
            (w / Math.max(n - 1, 1) >= 36 || i % 2 === (n - 1) % 2 || i === highlight) && (
            <div
              key={label}
              className={`absolute -translate-x-1/2 rounded-lg px-1.5 py-0.5 text-center ${
                i === highlight ? "bg-violet-50" : ""
              }`}
              style={{ left: x(i) }}
            >
              {footer(i)}
            </div>
            )
          ))}
        </div>
      )}
    </div>
  );
}

export function Donut({
  segments,
  center,
  size = 120,
}: {
  segments: { value: number; color: string; label: string }[];
  center: ReactNode;
  size?: number;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f1f5f9" strokeWidth={14} />
        {segments.map((s) => {
          const len = (s.value / total) * c;
          const el = (
            <circle
              key={s.label}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={14}
              strokeDasharray={`${Math.max(len - 2, 0)} ${c}`}
              strokeDashoffset={-offset}
            >
              <title>{s.label}</title>
            </circle>
          );
          offset += len;
          return el;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{center}</div>
    </div>
  );
}

/** A labelled progress bar row. */
export function BarRow({
  label,
  value,
  max = 1,
  color,
  right,
  onClick,
}: {
  label: ReactNode;
  value: number;
  max?: number;
  color: string;
  right: ReactNode;
  onClick?: () => void;
}) {
  const body = (
    <>
      <div className="mb-1.5 flex items-center justify-between gap-3 text-body-sm">
        <span className="flex min-w-0 items-center gap-2 font-medium text-on-surface">{label}</span>
        <span className="tnum shrink-0 font-semibold text-on-surface">{right}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out group-hover:brightness-110"
          style={{ width: `${Math.max((value / (max || 1)) * 100, value > 0 ? 2 : 0)}%`, backgroundColor: color }}
        />
      </div>
    </>
  );
  const cls = "group -mx-2 block w-[calc(100%+1rem)] rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-slate-50";
  return onClick ? (
    <button type="button" onClick={onClick} className={`tactile ${cls}`}>
      {body}
    </button>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** Negative / neutral / positive shares as one stacked bar. */
export function SentimentBar({ negative, neutral, positive }: { negative: number; neutral: number; positive: number }) {
  return (
    <div className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-slate-100">
      <div className="bg-rose-500" style={{ width: `${negative * 100}%` }} title={`Negative ${(negative * 100).toFixed(0)}%`} />
      <div className="bg-amber-400" style={{ width: `${neutral * 100}%` }} title={`Neutral ${(neutral * 100).toFixed(0)}%`} />
      <div className="bg-emerald-500" style={{ width: `${positive * 100}%` }} title={`Positive ${(positive * 100).toFixed(0)}%`} />
    </div>
  );
}
