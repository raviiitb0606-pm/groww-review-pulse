import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { allWeeks, cohort, inWeeks, lookbackWeeks, previousWeek } from "./metrics";
import type { Dashboard, Filters, Review, ThemeMeta } from "./types";

export const LOOKBACKS = [4, 8, 12] as const;

export function defaultFilters(data: Dashboard, weeks: string[]): Filters {
  return {
    week: weeks.includes(data.run_id) ? data.run_id : weeks[weeks.length - 1],
    lookback: 12,
    ratings: [],
    themes: [],
    versions: [],
    search: "",
    sort: "newest",
  };
}

/** How many filter groups narrow the cohort: the badge on the Filters button. */
export function activeFilterCount(f: Filters): number {
  return [f.lookback !== 12, f.ratings.length, f.themes.length, f.versions.length].filter(Boolean)
    .length;
}

interface Store {
  data: Dashboard;
  weeks: string[]; // every week in the data, oldest first
  filters: Filters;
  setFilters: (patch: Partial<Filters>) => void;
  resetFilters: () => void;
  theme: (key: string) => ThemeMeta;
  /** Cohort reviews (rating, theme, version filters) across the lookback window. */
  window: Review[];
  windowWeeks: string[];
  /** Cohort reviews of the selected week and the one before it. */
  week: Review[];
  prevWeek: string | null;
  prev: Review[];
  /** Cohort reviews of every week, for week-over-week comparisons. */
  all: Review[];
}

const Ctx = createContext<Store | null>(null);

export function StoreProvider({ data, children }: { data: Dashboard; children: ReactNode }) {
  const weeks = useMemo(() => allWeeks(data.reviews), [data]);
  const [filters, set] = useState<Filters>(() => defaultFilters(data, weeks));

  const store = useMemo<Store>(() => {
    const all = cohort(data.reviews, filters);
    const windowWeeks = lookbackWeeks(weeks, filters.week, filters.lookback);
    const prevWeek = previousWeek(weeks, filters.week);
    const byKey = new Map(data.themes.map((t) => [t.key, t]));
    return {
      data,
      weeks,
      filters,
      setFilters: (patch) => set((f) => ({ ...f, ...patch })),
      resetFilters: () => set((f) => ({ ...defaultFilters(data, weeks), week: f.week })),
      theme: (key) => byKey.get(key) ?? byKey.get("other")!,
      all,
      window: inWeeks(all, windowWeeks),
      windowWeeks,
      week: inWeeks(all, [filters.week]),
      prevWeek,
      prev: prevWeek ? inWeeks(all, [prevWeek]) : [],
    };
  }, [data, weeks, filters]);

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const store = useContext(Ctx);
  if (!store) throw new Error("useStore outside StoreProvider");
  return store;
}
