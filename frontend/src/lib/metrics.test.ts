import { describe, expect, it } from "vitest";
import {
  allWeeks,
  cohort,
  headline,
  isoWeek,
  lookbackWeeks,
  movers,
  previousWeek,
  representative,
  search,
  sortReviews,
  summarize,
  termCounts,
  themeStats,
  topPain,
  versionStats,
  weekDates,
  weekly,
} from "./metrics";
import type { Rating, Review, ThemeMeta } from "./types";

const THEMES: ThemeMeta[] = [
  { key: "t1", name: "Update / Chart", label: "Charts", color: "#7C3AED", terms: ["chart", "update"] },
  { key: "t2", name: "Support / Service", label: "Support", color: "#F97362", terms: ["support"] },
  { key: "other", name: "other", label: "Other", color: "#64748B", terms: [] },
];

let seq = 0;
function review(date: string, rating: Rating, theme = "t1", extra: Partial<Review> = {}): Review {
  seq += 1;
  return {
    id: `r${seq}`,
    date,
    rating,
    version: "18.1.0",
    theme,
    confidence: "high",
    quote_eligible: true,
    text: "The chart screen keeps freezing after the latest update, please fix it soon.",
    ...extra,
  };
}

describe("weeks", () => {
  it("computes ISO weeks, including year boundaries", () => {
    expect(isoWeek("2026-10-26")).toBe("2026-W44"); // Monday
    expect(isoWeek("2026-11-01")).toBe("2026-W44"); // Sunday
    expect(isoWeek("2026-11-02")).toBe("2026-W45");
    expect(isoWeek("2027-01-01")).toBe("2026-W53");
    expect(isoWeek("2025-12-29")).toBe("2026-W01");
  });

  it("maps a week key back to Monday and Sunday", () => {
    const { start, end } = weekDates("2026-W44");
    expect(start.toISOString().slice(0, 10)).toBe("2026-10-26");
    expect(end.toISOString().slice(0, 10)).toBe("2026-11-01");
    expect(weekDates("2026-W01").start.toISOString().slice(0, 10)).toBe("2025-12-29");
  });

  it("lists every week without gaps and slices lookbacks", () => {
    const weeks = allWeeks([review("2026-10-30", 1), review("2026-10-01", 5)]);
    expect(weeks).toEqual(["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]);
    expect(lookbackWeeks(weeks, "2026-W43", 2)).toEqual(["2026-W42", "2026-W43"]);
    expect(lookbackWeeks(weeks, "2026-W44", 12)).toEqual(weeks);
    expect(previousWeek(weeks, "2026-W40")).toBeNull();
  });
});

describe("summaries", () => {
  it("splits sentiment by rating: 1-2 negative, 3 neutral, 4-5 positive", () => {
    const s = summarize([review("2026-10-30", 1), review("2026-10-30", 2), review("2026-10-30", 3), review("2026-10-30", 5)]);
    expect(s).toMatchObject({ count: 4, avg: 2.75, negative: 0.5, neutral: 0.25, positive: 0.25 });
    expect(summarize([]).avg).toBeNull();
  });

  it("fills weeks with no reviews", () => {
    const points = weekly([review("2026-10-30", 4)], ["2026-W43", "2026-W44"]);
    expect(points.map((p) => p.count)).toEqual([0, 1]);
    expect(points[0].avg).toBeNull();
  });
});

describe("themes", () => {
  const rows = [
    review("2026-10-30", 1, "t1"),
    review("2026-10-30", 1, "t1"),
    review("2026-10-30", 5, "t1"),
    review("2026-10-30", 1, "t2"),
    review("2026-10-30", 5, "other"),
    review("2026-10-30", 5, "other"),
    review("2026-10-30", 5, "other"),
    review("2026-10-30", 5, "other"),
  ];

  it("orders by count with other last, and picks the pain point by negative volume", () => {
    const stats = themeStats(rows, THEMES);
    expect(stats.map((s) => s.theme.key)).toEqual(["t1", "t2", "other"]);
    expect(stats[0]).toMatchObject({ count: 3, share: 3 / 8, negativeCount: 2 });
    expect(topPain(stats)?.theme.key).toBe("t1");
  });

  it("reports week-over-week movers only above the minimum base", () => {
    const data = [
      ...Array.from({ length: 10 }, () => review("2026-10-21", 1, "t2")), // W43
      ...Array.from({ length: 3 }, () => review("2026-10-28", 1, "t2")), // W44
      review("2026-10-21", 1, "t1"),
      review("2026-10-28", 1, "t1"),
      review("2026-10-28", 1, "t1"),
    ];
    const m = movers(data, THEMES, "2026-W44", "2026-W43");
    expect(m).toHaveLength(1);
    expect(m[0]).toMatchObject({ previous: 10, current: 3, change: -0.7 });
    expect(headline(topPain(themeStats(data, THEMES)), m[0])).toBe(
      "Support is the #1 complaint area, 100% negative. Support mentions fell 70% this week.",
    );
  });
});

describe("filters and lists", () => {
  it("applies rating, theme and version filters together", () => {
    const rows = [review("2026-10-30", 1, "t1"), review("2026-10-30", 5, "t2", { version: "18.2.0" }), review("2026-10-30", 1, "t2")];
    expect(cohort(rows, { ratings: [1], themes: ["t2"], versions: [] })).toHaveLength(1);
    expect(cohort(rows, { ratings: [], themes: [], versions: ["18.2.0"] })).toHaveLength(1);
  });

  it("searches case-insensitively and sorts stably", () => {
    const a = review("2026-10-01", 5, "t1", { text: "Withdrawal took three days" });
    const b = review("2026-10-02", 1);
    expect(search([a, b], "WITHDRAWAL")).toEqual([a]);
    expect(sortReviews([a, b], "newest")).toEqual([b, a]);
    expect(sortReviews([b, a], "highest")).toEqual([a, b]);
  });

  it("sorts versions numerically, newest first", () => {
    const rows = [review("2026-10-30", 1, "t1", { version: "18.9.1" }), review("2026-10-30", 3, "t1", { version: "18.10.0" })];
    expect(versionStats(rows).map((v) => v.version)).toEqual(["18.10.0", "18.9.1"]);
  });

  it("picks representative quotes that mix ratings and skip ineligible reviews", () => {
    const rows = [
      review("2026-10-30", 1),
      review("2026-10-29", 1),
      review("2026-10-28", 5),
      review("2026-10-27", 3),
      review("2026-10-26", 2, "t1", { quote_eligible: false }),
      review("2026-10-26", 4, "t1", { confidence: "low" }),
    ];
    expect(representative(rows, 3).map((r) => r.rating)).toEqual([1, 5, 3]);
  });

  it("counts term matches as word prefixes", () => {
    const rows = [review("2026-10-30", 1, "t1", { text: "Charts broken" }), review("2026-10-30", 1, "t1", { text: "flowchart ok" })];
    expect(termCounts(rows, ["chart"])).toEqual([{ term: "chart", count: 1 }]);
  });
});
