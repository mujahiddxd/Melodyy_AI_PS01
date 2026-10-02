"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { ShopTile, ShopTileSkeleton } from "@/components/shops/ShopTile";
import { api, ApiError } from "@/lib/api";
import type { ShopCard, ShopListResponse } from "@/lib/types";

const PAGE_SIZE = 12;
const DEBOUNCE_MS = 300;

/** Customer shop discovery: search (name or address), a grid of shops, "Load more". Reads GET /shops. */
export function ShopDiscovery() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState(""); // the debounced text actually sent to the API
  const [shops, setShops] = useState<ShopCard[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);
  const latest = useRef(0); // ignore responses of requests that were replaced by a newer search

  const fetchPage = useCallback(async (q: string, pageNo: number, append: boolean) => {
    const id = ++latest.current;
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    setMoreError(null);
    try {
      const params = new URLSearchParams({ page: String(pageNo), page_size: String(PAGE_SIZE) });
      if (q) params.set("q", q);
      const res = await api<ShopListResponse>(`/shops?${params.toString()}`);
      if (id !== latest.current) return;
      setShops((prev) => (append ? [...prev, ...res.items.filter((s) => !prev.some((p) => p.id === s.id))] : res.items));
      setTotal(res.total);
      setPage(res.page);
      setHasMore(res.has_more);
    } catch (e) {
      if (id !== latest.current) return;
      const message = e instanceof ApiError ? e.message : "Could not load shops.";
      if (append) setMoreError(message);
      else setError(message);
    } finally {
      if (id === latest.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  // search box -> debounce -> new first page
  useEffect(() => {
    const t = setTimeout(() => setQuery(input.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [input]);

  useEffect(() => {
    fetchPage(query, 1, false);
  }, [query, fetchPage]);

  const searching = query !== "";

  return (
    <section id="shops" className="scroll-mt-6 py-12" aria-labelledby="shops-heading">
      <p className="eyebrow">Find a shop</p>
      <h2 id="shops-heading" className="mt-2 text-4xl md:text-5xl">
        Browse kirana stores
      </h2>
      <p className="mt-2 max-w-xl text-muted">Pick a shop to see its products and order in your own words.</p>

      <div className="relative mt-6 max-w-xl">
        <span className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-lg" aria-hidden>
          🔍
        </span>
        <label htmlFor="shop-search" className="sr-only">
          Search shops by name or location
        </label>
        <input
          id="shop-search"
          type="search"
          value={input}
          maxLength={100}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Search by shop name or area, e.g. Kothrud"
          className="w-full rounded-full border-[3px] border-ink bg-white py-3.5 pl-12 pr-12 shadow-brutal-sm outline-none placeholder:text-muted focus:ring-[3px] focus:ring-lavender-deep [&::-webkit-search-cancel-button]:appearance-none"
        />
        {input && (
          <button
            type="button"
            onClick={() => setInput("")}
            aria-label="Clear search"
            className="absolute right-3 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-cream text-sm font-bold hover:bg-butter"
          >
            ✕
          </button>
        )}
      </div>

      <div className="mt-8">
        {loading ? (
          <div role="status" aria-busy="true" aria-label="Loading shops">
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }, (_, n) => (
                <ShopTileSkeleton key={n} />
              ))}
            </div>
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={() => fetchPage(query, 1, false)} />
        ) : shops.length === 0 ? (
          searching ? (
            <EmptyState
              icon="🔍"
              title={`No shops match “${query}”`}
              hint="Try a different name or area, or clear the search to see every shop."
              action={
                <button type="button" className="btn-secondary" onClick={() => setInput("")}>
                  Clear search
                </button>
              }
            />
          ) : (
            <EmptyState
              icon="🏪"
              title="No shops yet"
              hint="No shop has finished setup yet. Shopkeepers can create theirs in a few minutes, and it appears here automatically."
              action={
                <Link href="/owner/signup" className="btn-primary">
                  Set up your shop →
                </Link>
              }
            />
          )
        ) : (
          <>
            <p className="mb-4 text-sm text-muted" aria-live="polite">
              {total} shop{total === 1 ? "" : "s"}
              {searching ? ` for “${query}”` : ""}
            </p>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {shops.map((s) => (
                <ShopTile key={s.id} shop={s} />
              ))}
            </div>
            {moreError && (
              <div className="mt-6">
                <ErrorState message={moreError} onRetry={() => fetchPage(query, page + 1, true)} />
              </div>
            )}
            {hasMore && !moreError && (
              <div className="mt-8 flex justify-center">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={loadingMore}
                  onClick={() => fetchPage(query, page + 1, true)}
                >
                  {loadingMore ? "Loading…" : "Load more shops"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
