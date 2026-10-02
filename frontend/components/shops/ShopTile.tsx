"use client";

import Link from "next/link";
import { useState } from "react";
import { rupees, trimQty } from "@/lib/format";
import type { ShopCard } from "@/lib/types";

/** One shop in the discovery grid. Only real shop data is shown. "View shop" opens the existing public shop page. */
export function ShopTile({ shop }: { shop: ShopCard }) {
  const [broken, setBroken] = useState(false);
  const photo = shop.photo_url && !broken ? shop.photo_url : "/placeholder-shop.svg";
  const minOrder = parseFloat(shop.min_order_value) > 0;
  const fee = parseFloat(shop.delivery_fee) > 0;

  return (
    <article
      className="card flex flex-col overflow-hidden !p-0 transition duration-150 ease-out hover:-translate-x-0.5 hover:-translate-y-0.5"
      data-testid="shop-card"
    >
      <div className="relative">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={photo}
          alt={`${shop.name} storefront`}
          loading="lazy"
          onError={() => setBroken(true)}
          className="h-40 w-full border-b-[3px] border-ink object-cover"
        />
        <span
          className={`badge absolute left-3 top-3 border-2 border-ink ${shop.is_open ? "bg-mint" : "bg-white text-muted"}`}
        >
          {shop.is_open ? "● Open now" : "Closed"}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <h3 className="text-2xl leading-tight">{shop.name}</h3>
          {shop.address_text ? (
            <p className="mt-1 line-clamp-2 text-sm text-muted">📍 {shop.address_text}</p>
          ) : (
            <p className="mt-1 text-sm text-muted">Address not added</p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {shop.delivery_radius_km !== null && (
            <span className="badge border-2 border-ink bg-sky">Delivers within {trimQty(shop.delivery_radius_km)} km</span>
          )}
          {minOrder && <span className="badge border-2 border-ink bg-white">Min order {rupees(shop.min_order_value)}</span>}
          {fee && <span className="badge border-2 border-ink bg-white">Delivery {rupees(shop.delivery_fee)}</span>}
          <span className={`badge border-2 border-ink ${shop.product_count > 0 ? "bg-white" : "bg-cream-yellow"}`}>
            {shop.product_count > 0 ? `${shop.product_count} item${shop.product_count === 1 ? "" : "s"}` : "No products yet"}
          </span>
        </div>

        <Link href={`/shop/${shop.slug}`} className="btn-primary mt-auto self-start" aria-label={`View shop ${shop.name}`}>
          View shop →
        </Link>
      </div>
    </article>
  );
}

export function ShopTileSkeleton() {
  return (
    <div className="card overflow-hidden !p-0" aria-hidden>
      <div className="h-40 animate-pulse border-b-[3px] border-ink bg-cream" />
      <div className="space-y-3 p-5">
        <div className="h-7 w-2/3 animate-pulse rounded-full bg-cream" />
        <div className="h-4 w-full animate-pulse rounded-full bg-cream" />
        <div className="flex gap-2">
          <div className="h-6 w-28 animate-pulse rounded-full bg-cream" />
          <div className="h-6 w-20 animate-pulse rounded-full bg-cream" />
        </div>
        <div className="h-11 w-36 animate-pulse rounded-full bg-cream" />
      </div>
    </div>
  );
}
