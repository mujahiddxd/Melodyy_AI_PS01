"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CustomerBar } from "@/components/customer/CustomerBar";
import { DeliveryAddress, type ChosenAddress } from "@/components/customer/DeliveryAddress";
import { OtpModal } from "@/components/customer/OtpModal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { MockBadge } from "@/components/ui/MockBadge";
import { Spinner } from "@/components/ui/Spinner";
import { api, ApiError } from "@/lib/api";
import { useCustomer } from "@/lib/customer";
import type { PublicShopResponse, ShopPublic } from "@/lib/types";

export default function ChatPlaceholder() {
  const { slug } = useParams<{ slug: string }>();
  const { customer } = useCustomer();
  const [shop, setShop] = useState<ShopPublic | null>(null);
  const [error, setError] = useState<{ message: string; notFound: boolean } | null>(null);
  const [otpOpen, setOtpOpen] = useState(false);
  const [address, setAddress] = useState<ChosenAddress | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setShop((await api<PublicShopResponse>(`/shops/${encodeURIComponent(slug)}`)).shop);
    } catch (e) {
      setError({
        message: e instanceof ApiError ? e.message : "Could not load this shop.",
        notFound: e instanceof ApiError && e.status === 404,
      });
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  const ready = !!customer && !!address?.eligible;

  return (
    <main className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6">
      <Link href={`/shop/${slug}`} className="font-display text-lg">
        ← Back to shop
      </Link>

      <div className="mt-6">
        <EmptyState
          icon="💬"
          title="Chat ordering is coming"
          hint="You'll type or speak your order in Hinglish here. This arrives in Stage 3. No login is needed to chat."
          action={<MockBadge>PLACEHOLDER</MockBadge>}
        />
      </div>

      <section className="card mt-10 flex flex-col gap-6" aria-label="Verify and set address">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <span className="badge border-2 border-ink bg-coral">TEMPORARY · STAGE 2 TEST</span>
            <h2 className="mt-3 text-3xl">Verify &amp; set address</h2>
            <p className="mt-1 max-w-xl text-muted">
              You only need this before confirming an order. Browsing and chatting stay open to everyone.
            </p>
          </div>
          <CustomerBar onVerify={() => setOtpOpen(true)} />
        </div>

        {error ? (
          error.notFound ? (
            <EmptyState icon="🔍" title="Shop not found" hint="Check the link." />
          ) : (
            <ErrorState message={error.message} onRetry={load} />
          )
        ) : !shop ? (
          <Spinner label="Loading shop…" />
        ) : (
          <DeliveryAddress shop={shop} onRequestVerify={() => setOtpOpen(true)} onChange={setAddress} />
        )}

        <div className="flex flex-wrap items-center gap-3 border-t-[3px] border-ink/10 pt-5">
          <span className={`badge border-2 border-ink ${customer ? "bg-mint" : "bg-white"}`}>
            {customer ? "✓" : "○"} Phone verified
          </span>
          <span className={`badge border-2 border-ink ${address?.eligible ? "bg-mint" : "bg-white"}`}>
            {address?.eligible ? "✓" : "○"} Address in delivery area
          </span>
          <button type="button" className="btn-primary ml-auto" disabled={!ready} title="Ordering arrives in Stage 3-4">
            Continue to order →
          </button>
        </div>
      </section>

      {otpOpen && <OtpModal onClose={() => setOtpOpen(false)} />}
    </main>
  );
}
