import { useSyncExternalStore } from "react";

// Hash routes, so the built app is plain static files: #/, #/themes/t1, #/reviews.
export type Route =
  | { page: "overview" }
  | { page: "themes"; theme: string | null }
  | { page: "reviews" };

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "themes") return { page: "themes", theme: parts[1] ?? null };
  if (parts[0] === "reviews") return { page: "reviews" };
  return { page: "overview" };
}

export function href(route: Route): string {
  if (route.page === "themes") return route.theme ? `#/themes/${route.theme}` : "#/themes";
  if (route.page === "reviews") return "#/reviews";
  return "#/";
}

export function go(route: Route): void {
  window.location.hash = href(route);
  window.scrollTo({ top: 0 });
}

function subscribe(cb: () => void) {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parse(hash);
}
