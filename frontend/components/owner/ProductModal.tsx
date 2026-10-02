"use client";

import { useState, type FormEvent } from "react";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { api, ApiError } from "@/lib/api";
import type { PackUnit, ProductInput, ProductOwner, SellMode } from "@/lib/types";

const UNITS: PackUnit[] = ["g", "kg", "ml", "l", "pc", "dozen", "packet"];

interface F {
  name: string;
  brand: string;
  category: string;
  sell_mode: SellMode;
  pack_size: string;
  pack_unit: PackUnit;
  price: string;
  stock_qty: string;
  low_stock_threshold: string;
  max_normal_qty: string;
  aliases: string;
  shelf: string;
}

function initial(p: ProductOwner | null): F {
  if (!p) {
    return {
      name: "", brand: "", category: "", sell_mode: "pack", pack_size: "1", pack_unit: "kg",
      price: "", stock_qty: "0", low_stock_threshold: "5", max_normal_qty: "", aliases: "", shelf: "",
    };
  }
  const t = (v: string) => String(parseFloat(v));
  return {
    name: p.name, brand: p.brand ?? "", category: p.category, sell_mode: p.sell_mode, pack_size: t(p.pack_size),
    pack_unit: p.pack_unit, price: t(p.price), stock_qty: t(p.stock_qty), low_stock_threshold: t(p.low_stock_threshold),
    max_normal_qty: p.max_normal_qty ? t(p.max_normal_qty) : "", aliases: p.aliases.join(", "), shelf: p.shelf ?? "",
  };
}

const num = (s: string) => (s.trim() === "" ? NaN : Number(s));

export function ProductModal({
  product,
  categories,
  onClose,
  onSaved,
}: {
  product: ProductOwner | null; // null = add
  categories: string[];
  onClose: () => void;
  onSaved: (p: ProductOwner) => void;
}) {
  const [f, setF] = useState<F>(() => initial(product));
  const [errors, setErrors] = useState<Partial<Record<keyof F, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof F>(k: K, v: F[K]) => setF((x) => ({ ...x, [k]: v }));

  function validate(): boolean {
    const e: typeof errors = {};
    if (!f.name.trim()) e.name = "Name is required";
    if (!f.category.trim()) e.category = "Category is required";
    if (!(num(f.pack_size) > 0)) e.pack_size = "Must be more than 0";
    if (!(num(f.price) > 0)) e.price = "Price must be more than 0";
    if (!(num(f.stock_qty) >= 0)) e.stock_qty = "Stock can't be negative";
    if (!(num(f.low_stock_threshold) >= 0)) e.low_stock_threshold = "Can't be negative";
    if (f.max_normal_qty.trim() !== "" && !(num(f.max_normal_qty) > 0)) e.max_normal_qty = "Must be more than 0 (or blank)";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    setFormError(null);
    if (!validate()) return;
    const body: ProductInput = {
      name: f.name.trim(),
      brand: f.brand.trim() || null,
      category: f.category.trim(),
      sell_mode: f.sell_mode,
      pack_size: f.pack_size.trim(),
      pack_unit: f.pack_unit,
      price: Number(f.price).toFixed(2),
      stock_qty: f.stock_qty.trim(),
      low_stock_threshold: f.low_stock_threshold.trim(),
      max_normal_qty: f.max_normal_qty.trim() || null,
      aliases: f.aliases.split(",").map((a) => a.trim()).filter(Boolean),
      shelf: f.shelf.trim() || null,
    };
    setBusy(true);
    try {
      const saved = await api<ProductOwner>(product ? `/owner/products/${product.id}` : "/owner/products", {
        method: product ? "PATCH" : "POST",
        role: "owner",
        json: body,
      });
      onSaved(saved);
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Could not save the product.");
      setBusy(false);
    }
  }

  return (
    <Modal title={product ? "Edit product" : "Add product"} onClose={onClose}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="p-name" error={errors.name}>
            <input id="p-name" className="input" value={f.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Brand" htmlFor="p-brand">
            <input id="p-brand" className="input" value={f.brand} onChange={(e) => set("brand", e.target.value)} />
          </Field>
          <Field label="Category" htmlFor="p-cat" error={errors.category}>
            <input id="p-cat" list="p-cats" className="input" value={f.category} onChange={(e) => set("category", e.target.value)} />
            <datalist id="p-cats">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>
          <Field label="Sold as" htmlFor="p-mode" hint="Loose = priced per unit, e.g. ₹ per kg">
            <select id="p-mode" className="input" value={f.sell_mode} onChange={(e) => set("sell_mode", e.target.value as SellMode)}>
              <option value="pack">Pack</option>
              <option value="loose">Loose</option>
            </select>
          </Field>
          <Field label="Pack size" htmlFor="p-size" error={errors.pack_size}>
            <input id="p-size" inputMode="decimal" className="input" value={f.pack_size} onChange={(e) => set("pack_size", e.target.value)} />
          </Field>
          <Field label="Unit" htmlFor="p-unit">
            <select id="p-unit" className="input" value={f.pack_unit} onChange={(e) => set("pack_unit", e.target.value as PackUnit)}>
              {UNITS.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </Field>
          <Field label={f.sell_mode === "loose" ? `Price (₹ per ${f.pack_unit})` : "Price (₹ per pack)"} htmlFor="p-price" error={errors.price}>
            <input id="p-price" inputMode="decimal" className="input" value={f.price} onChange={(e) => set("price", e.target.value)} />
          </Field>
          <Field label={f.sell_mode === "loose" ? `Stock (${f.pack_unit})` : "Stock (packs)"} htmlFor="p-stock" error={errors.stock_qty}>
            <input id="p-stock" inputMode="decimal" className="input" value={f.stock_qty} onChange={(e) => set("stock_qty", e.target.value)} />
          </Field>
          <Field label="Low-stock alert at" htmlFor="p-low" error={errors.low_stock_threshold}>
            <input id="p-low" inputMode="decimal" className="input" value={f.low_stock_threshold} onChange={(e) => set("low_stock_threshold", e.target.value)} />
          </Field>
          <Field label="Max normal quantity" htmlFor="p-max" error={errors.max_normal_qty} hint="Optional. Larger orders get a double-check.">
            <input id="p-max" inputMode="decimal" className="input" value={f.max_normal_qty} onChange={(e) => set("max_normal_qty", e.target.value)} />
          </Field>
        </div>
        <Field label="Aliases" htmlFor="p-alias" hint="Other names customers use, comma separated: tel, oil, तेल">
          <input id="p-alias" className="input" value={f.aliases} onChange={(e) => set("aliases", e.target.value)} />
        </Field>
        <Field label="Shelf" htmlFor="p-shelf">
          <input id="p-shelf" className="input" value={f.shelf} onChange={(e) => set("shelf", e.target.value)} />
        </Field>
        {formError && (
          <p role="alert" className="rounded-input bg-danger-fill p-3 font-medium text-danger">
            {formError}
          </p>
        )}
        <div className="flex gap-3">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Saving…" : product ? "Save changes" : "Add product"}
          </button>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
