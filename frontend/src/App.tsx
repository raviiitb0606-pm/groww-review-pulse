import { AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Shell } from "./components/Shell";
import type { Dashboard } from "./lib/types";
import { useRoute } from "./lib/router";
import { StoreProvider } from "./lib/store";
import { Overview } from "./pages/Overview";
import { Reviews } from "./pages/Reviews";
import { ThemeDetail } from "./pages/ThemeDetail";

function Pages() {
  const route = useRoute();
  if (route.page === "themes") return <ThemeDetail key={route.theme ?? ""} themeKey={route.theme} />;
  if (route.page === "reviews") return <Reviews />;
  return <Overview />;
}

function Loading() {
  return (
    <div className="mx-auto max-w-[1440px] animate-pulse px-4 pt-8 sm:pl-24 sm:pr-8" aria-busy="true" aria-label="Loading">
      <div className="h-52 rounded-3xl bg-gradient-to-br from-indigo-200 to-violet-200" />
      <div className="-mt-12 grid grid-cols-1 gap-5 px-6 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-32 rounded-2xl bg-white shadow-sm" />
        ))}
      </div>
      <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="h-64 rounded-2xl bg-white" />
        <div className="h-64 rounded-2xl bg-white" />
      </div>
    </div>
  );
}

function Failed({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="card max-w-lg p-8">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
          <AlertCircle size={22} />
        </span>
        <h1 className="mt-4 font-display text-title-md font-bold text-ink">Dashboard data not found</h1>
        <p className="mt-2 text-body-md text-slate-600">
          Export it from the pipeline, then reload this page:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-xl bg-ink p-4 font-mono text-body-sm text-violet-100">
          uv run pulse dashboard --week 2026-W44
        </pre>
        <p className="mt-3 text-label-md text-muted">{message}</p>
      </div>
    </div>
  );
}

export function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}dashboard.json`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`dashboard.json: HTTP ${r.status}`);
        return r.json() as Promise<Dashboard>;
      })
      .then((d) => {
        if (!Array.isArray(d.reviews) || !Array.isArray(d.themes)) throw new Error("dashboard.json has an unexpected shape");
        setData(d);
        document.title = `${d.app} Review Pulse`;
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <Failed message={error} />;
  if (!data) return <Loading />;
  return (
    <StoreProvider data={data}>
      <Shell>
        <Pages />
      </Shell>
    </StoreProvider>
  );
}
