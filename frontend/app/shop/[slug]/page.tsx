"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { StockBadge } from "@/components/ui/StockBadge";
import { api, ApiError } from "@/lib/api";
import { packLabel, rupees, trimQty } from "@/lib/format";
import type { PublicShopResponse } from "@/lib/types";

export default function PublicShopPage() {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<PublicShopResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; notFound: boolean } | null>(null);
  const [photoBroken, setPhotoBroken] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api<PublicShopResponse>(`/shops/${encodeURIComponent(slug)}`));
    } catch (e) {
      setError({
        message: e instanceof ApiError ? e.message : "Could not load this shop.",
        notFound: e instanceof ApiError && e.status === 404,
      });
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <main className="mx-auto max-w-[1200px] px-6 py-16">
        <Spinner label="Loading shop…" />
      </main>
    );
  }
  if (error) {
    return (
      <main className="mx-auto max-w-[1200px] px-6 py-16">
        {error.notFound ? (
          <EmptyState
            icon="🔍"
            title="Shop not found"
            hint="Check the link, or open the demo shop."
            action={<Link href="/shop/sharma-kirana" className="btn-primary">→ Open demo shop</Link>}
          />
        ) : (
          <ErrorState message={error.message} onRetry={load} />
        )}
      </main>
    );
  }
  if (!data) return null;

  const { shop, categories } = data;
  const configured = shop.lat !== null && shop.lng !== null && shop.delivery_radius_km !== null;
  const photo = shop.photo_url && !photoBroken ? shop.photo_url : "/placeholder-shop.svg";

  return (
    <main className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6">
      <Link href="/" className="font-display text-lg">
        ← Hinglish Order Desk
      </Link>

      <section className="mt-6 grid items-center gap-8 md:grid-cols-2">
        <div>
          <p className="eyebrow">{shop.is_open ? "Open now" : "Currently closed"}</p>
          <h1 className="mt-2 text-4xl leading-tight md:text-6xl">{shop.name}</h1>
          {shop.address_text && <p className="mt-3 text-lg text-muted">📍 {shop.address_text}</p>}
          {shop.description && <p className="mt-2 max-w-lg">{shop.description}</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            {configured ? (
              <span className="badge border-2 border-ink bg-sky">
                Delivers within {trimQty(shop.delivery_radius_km!)} km
              </span>
            ) : (
              <span className="badge border-2 border-ink bg-cream-yellow">Delivery area not configured</span>
            )}
            {parseFloat(shop.min_order_value) > 0 && (
              <span className="badge border-2 border-ink bg-white">Min order {rupees(shop.min_order_value)}</span>
            )}
          </div>
          <div className="mt-8">
            {configured ? (
              <Link href={`/shop/${shop.slug}/chat`} className="btn-primary">
                Order on chat →
              </Link>
            ) : (
              <button type="button" className="btn-primary" disabled>
                Ordering unavailable
              </button>
            )}
          </div>
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={photo}
          alt={`${shop.name} storefront`}
          onError={() => setPhotoBroken(true)}
          className="h-72 w-full rounded-card border-[3px] border-ink object-cover shadow-brutal"
        />
      </section>

      <section className="mt-16">
        <p className="eyebrow">Catalog</p>
        <h2 className="mb-6 text-3xl">What&apos;s on the shelf</h2>
        {categories.length === 0 ? (
          <EmptyState icon="🛒" title="No products listed yet" hint="This shop hasn't added any products. Check back soon." />
        ) : (
          <div className="flex flex-col gap-12">
            {categories.map((c) => (
              <div key={c.name}>
                <h3 className="mb-4 text-2xl">{c.name}</h3>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {c.products.map((p) => (
                    <article key={p.id} className="card flex flex-col gap-2 !p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h4 className="font-sans text-lg font-semibold leading-snug">{p.name}</h4>
                          <p className="text-sm text-muted">{[p.brand, packLabel(p)].filter(Boolean).join(" · ")}</p>
                        </div>
                        <span className="font-display text-xl">{rupees(p.price)}</span>
                      </div>
                      <div className="mt-auto pt-2">
                        <StockBadge p={p} />
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
