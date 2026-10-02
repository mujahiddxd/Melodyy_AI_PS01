"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ProductModal } from "@/components/owner/ProductModal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { StockBadge } from "@/components/ui/StockBadge";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { packLabel, trimQty } from "@/lib/format";
import type { ProductList, ProductOwner } from "@/lib/types";

/** A number cell that saves on blur/Enter. Reverts and reports if the save fails. */
function InlineNumber({
  value,
  label,
  prefix,
  onSave,
}: {
  value: string;
  label: string;
  prefix?: string;
  onSave: (v: string) => Promise<void>;
}) {
  const shown = trimQty(value);
  const [draft, setDraft] = useState(shown);
  const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(shown), [shown]);

  async function commit() {
    const v = draft.trim();
    if (v === shown) return;
    setBusy(true);
    try {
      await onSave(v);
    } catch {
      setDraft(shown);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-1">
      {prefix}
      <input
        aria-label={label}
        inputMode="decimal"
        className="w-20 rounded-xl bg-cream px-2 py-1 text-right shadow-clay outline-none focus:ring-[3px] focus:ring-ink disabled:opacity-50"
        value={draft}
        disabled={busy}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") setDraft(shown);
        }}
      />
    </span>
  );
}

export default function ProductsPage() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [data, setData] = useState<ProductList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; noShop: boolean } | null>(null);
  const [editing, setEditing] = useState<ProductOwner | "new" | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q: query, include_inactive: String(showInactive) });
      setData(await api<ProductList>(`/owner/products?${params}`, { role: "owner" }));
    } catch (e) {
      const noShop = e instanceof ApiError && e.status === 404;
      setError({ message: e instanceof ApiError ? e.message : "Could not load products.", noShop });
    } finally {
      setLoading(false);
    }
  }, [query, showInactive]);

  useEffect(() => {
    load();
  }, [load]);

  const categories = useMemo(() => Array.from(new Set((data?.items ?? []).map((p) => p.category))).sort(), [data]);

  function replace(p: ProductOwner) {
    setData((d) => (d ? { ...d, items: d.items.map((x) => (x.id === p.id ? p : x)) } : d));
  }

  async function patch(p: ProductOwner, body: Record<string, unknown>, okMsg?: string) {
    try {
      const saved = await api<ProductOwner>(`/owner/products/${p.id}`, { method: "PATCH", role: "owner", json: body });
      replace(saved);
      if (okMsg) toast.show(okMsg, "success");
    } catch (e) {
      toast.show(e instanceof ApiError ? e.message : "Could not save.", "error");
      throw e;
    }
  }

  async function deactivate(p: ProductOwner) {
    try {
      await api(`/owner/products/${p.id}`, { method: "DELETE", role: "owner" });
      toast.show(`${p.name} deactivated.`, "success");
      load();
    } catch (e) {
      toast.show(e instanceof ApiError ? e.message : "Could not deactivate.", "error");
    }
  }

  const items = data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Catalog</p>
          <h1 className="text-4xl">Products</h1>
        </div>
        <button type="button" className="btn-primary" onClick={() => setEditing("new")} disabled={error?.noShop}>
          + Add product
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <input
          aria-label="Search products"
          className="input max-w-md !border-[3px] !border-ink shadow-brutal-sm"
          placeholder="Search by name, brand or alias, e.g. makkhan"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="flex items-center gap-2 font-medium">
          <input type="checkbox" className="h-5 w-5 accent-ink" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
          Show inactive
        </label>
        {data && <span className="text-muted">{data.total} items</span>}
      </div>

      {loading && !data ? (
        <Spinner label="Loading products…" />
      ) : error?.noShop ? (
        <EmptyState
          icon="🏪"
          title="Set up your shop first"
          hint="Add your shop details and delivery area, then come back to add products."
          action={<Link href="/owner/setup" className="btn-primary">→ Go to setup</Link>}
        />
      ) : error ? (
        <ErrorState message={error.message} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          icon="📦"
          title={query ? "No products match your search" : "No products yet"}
          hint={query ? "Try a different word." : "Add your first product. CSV import is coming later."}
          action={
            !query && (
              <button type="button" className="btn-primary" onClick={() => setEditing("new")}>
                + Add product
              </button>
            )
          }
        />
      ) : (
        <div className={`card !p-0 overflow-x-auto ${loading ? "opacity-60" : ""}`}>
          <table className="w-full min-w-[860px] text-left">
            <thead>
              <tr className="border-b-[3px] border-ink">
                {["Product", "Pack", "Price", "Stock", "Aliases", "Status", ""].map((h) => (
                  <th key={h} className="eyebrow px-4 py-3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className={`border-b border-ink/10 ${p.is_active ? "" : "opacity-60"}`}>
                  <td className="px-4 py-3">
                    <div className="font-semibold">{p.name}</div>
                    <div className="text-sm text-muted">
                      {[p.brand, p.category].filter(Boolean).join(" · ")}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm">{packLabel(p)}</td>
                  <td className="px-4 py-3">
                    <InlineNumber
                      prefix="₹"
                      label={`Price of ${p.name}`}
                      value={p.price}
                      onSave={(v) => patch(p, { price: Number(v).toFixed(2) }, "Price updated.")}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col items-start gap-1">
                      <InlineNumber
                        label={`Stock of ${p.name}`}
                        value={p.stock_qty}
                        onSave={(v) => patch(p, { stock_qty: v }, "Stock updated.")}
                      />
                      <StockBadge p={p} />
                    </div>
                  </td>
                  <td className="max-w-[200px] px-4 py-3 text-sm text-muted">{p.aliases.join(", ") || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`badge border-2 border-ink ${p.is_active ? "bg-mint" : "bg-white"}`}>
                      {p.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <button type="button" className="chip mr-2" onClick={() => setEditing(p)}>
                      Edit
                    </button>
                    {p.is_active ? (
                      <button type="button" className="chip text-danger" onClick={() => deactivate(p)}>
                        Deactivate
                      </button>
                    ) : (
                      <button type="button" className="chip" onClick={() => patch(p, { is_active: true }, "Reactivated.").then(load)}>
                        Reactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <ProductModal
          product={editing === "new" ? null : editing}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={() => {
            toast.show(editing === "new" ? "Product added." : "Product saved.", "success");
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}
