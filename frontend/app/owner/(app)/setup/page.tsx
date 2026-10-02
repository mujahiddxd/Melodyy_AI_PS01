"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { LocationPicker } from "@/components/map/LocationPicker";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError, uploadFile } from "@/lib/api";
import { VPA_RE } from "@/lib/format";
import type { PhotoResponse, ShopOwner } from "@/lib/types";

const MAX_PHOTO = 5 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface Form {
  name: string;
  description: string;
  address_text: string;
  upi_vpa: string;
  min_order_value: string;
  delivery_fee: string;
  is_open: boolean;
}
const EMPTY: Form = { name: "", description: "", address_text: "", upi_vpa: "", min_order_value: "0", delivery_fee: "0", is_open: true };

export default function SetupPage() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [shop, setShop] = useState<ShopOwner | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(null);
  const [radius, setRadius] = useState(3);
  const [errors, setErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [saving, setSaving] = useState(false);

  // photo
  const [photoUrl, setPhotoUrl] = useState<string | null>(null); // saved photo
  const [preview, setPreview] = useState<string | null>(null); // local preview of a picked file
  const [pending, setPending] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const apply = useCallback((s: ShopOwner) => {
    setShop(s);
    setForm({
      name: s.name,
      description: s.description ?? "",
      address_text: s.address_text ?? "",
      upi_vpa: s.upi_vpa ?? "",
      min_order_value: String(parseFloat(s.min_order_value)),
      delivery_fee: String(parseFloat(s.delivery_fee)),
      is_open: s.is_open,
    });
    setPos(s.lat !== null && s.lng !== null ? { lat: s.lat, lng: s.lng } : null);
    setRadius(s.delivery_radius_km ?? 3);
    setPhotoUrl(s.photo_url);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      apply(await api<ShopOwner>("/owner/shop", { role: "owner" }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setShop(null); // new owner: blank form
      else setLoadError(e instanceof ApiError ? e.message : "Could not load your shop.");
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function sendPhoto(file: File) {
    setPhotoError(null);
    setProgress(0);
    try {
      const res = await uploadFile<PhotoResponse>("/owner/shop/photo", file, "owner", setProgress);
      setPhotoUrl(res.photo_url);
      setPreview(null);
      setPending(null);
      toast.show("Photo uploaded.", "success");
    } catch (e) {
      setPhotoError(e instanceof ApiError ? e.message : "Photo upload failed.");
    } finally {
      setProgress(null);
    }
  }

  function onPickFile(file: File | undefined) {
    if (!file) return;
    setPhotoError(null);
    if (!PHOTO_TYPES.includes(file.type)) return setPhotoError("Use a JPG, PNG or WebP image.");
    if (file.size > MAX_PHOTO) return setPhotoError("Photo must be 5 MB or smaller.");
    setPreview(URL.createObjectURL(file));
    setPending(file);
    if (shop) void sendPhoto(file); // a brand-new shop uploads right after its first save
  }

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function validate(): boolean {
    const e: typeof errors = {};
    if (!form.name.trim()) e.name = "Shop name is required";
    if (form.upi_vpa.trim() && !VPA_RE.test(form.upi_vpa.trim())) e.upi_vpa = "UPI ID must look like name@bank";
    for (const k of ["min_order_value", "delivery_fee"] as const) {
      const n = Number(form[k]);
      if (form[k].trim() === "" || Number.isNaN(n) || n < 0) e[k] = "Enter 0 or more";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function onSave(ev: FormEvent) {
    ev.preventDefault();
    if (!validate()) return toast.show("Please fix the highlighted fields.", "error");
    setSaving(true);
    try {
      const saved = await api<ShopOwner>("/owner/shop", {
        method: "PUT",
        role: "owner",
        json: {
          name: form.name.trim(),
          description: form.description.trim() || null,
          address_text: form.address_text.trim() || null,
          lat: pos?.lat ?? null,
          lng: pos?.lng ?? null,
          delivery_radius_km: pos ? radius : null,
          upi_vpa: form.upi_vpa.trim() || null,
          min_order_value: Number(form.min_order_value).toFixed(2),
          delivery_fee: Number(form.delivery_fee).toFixed(2),
          is_open: form.is_open,
        },
      });
      const hadShop = shop !== null;
      apply(saved);
      toast.show("Shop saved.", "success");
      if (!hadShop && pending) await sendPhoto(pending);
    } catch (e) {
      toast.show(e instanceof ApiError ? e.message : "Could not save. Please try again.", "error");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spinner label="Loading your shop…" />;
  if (loadError) return <ErrorState message={loadError} onRetry={load} />;

  const shownPhoto = preview ?? photoUrl;

  return (
    <form onSubmit={onSave} noValidate className="flex flex-col gap-8">
      <div>
        <p className="eyebrow">Setup</p>
        <h1 className="text-4xl">{shop ? "Your shop" : "Set up your shop"}</h1>
        {shop && (
          <p className="mt-2 text-muted">
            Public page:{" "}
            <Link href={`/shop/${shop.slug}`} className="font-mono text-lavender-deep underline" target="_blank">
              /shop/{shop.slug}
            </Link>
          </p>
        )}
        {shop && !shop.is_configured && (
          <p className="mt-3 rounded-input bg-cream-yellow p-3 font-medium">
            Drop a map pin and save to finish setup. Customers can&apos;t order until the delivery area is set.
          </p>
        )}
      </div>

      <section className="card flex flex-col gap-5">
        <h2 className="text-2xl">Details</h2>
        <Field label="Shop name" htmlFor="name" error={errors.name}>
          <input id="name" className="input" value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Address" htmlFor="address">
          <input
            id="address"
            className="input"
            placeholder="Shop 4, Karve Road, Kothrud, Pune"
            value={form.address_text}
            onChange={(e) => set("address_text", e.target.value)}
          />
        </Field>
        <Field label="Description" htmlFor="description">
          <textarea
            id="description"
            rows={3}
            className="input"
            placeholder="Your neighbourhood kirana store."
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </Field>
        <div className="grid gap-5 sm:grid-cols-3">
          <Field label="UPI ID" htmlFor="upi" error={errors.upi_vpa} hint="e.g. sharmakirana@upi">
            <input id="upi" className="input" value={form.upi_vpa} onChange={(e) => set("upi_vpa", e.target.value)} />
          </Field>
          <Field label="Minimum order (₹)" htmlFor="minorder" error={errors.min_order_value}>
            <input
              id="minorder"
              inputMode="decimal"
              className="input"
              value={form.min_order_value}
              onChange={(e) => set("min_order_value", e.target.value)}
            />
          </Field>
          <Field label="Delivery fee (₹)" htmlFor="fee" error={errors.delivery_fee}>
            <input
              id="fee"
              inputMode="decimal"
              className="input"
              value={form.delivery_fee}
              onChange={(e) => set("delivery_fee", e.target.value)}
            />
          </Field>
        </div>
        <label className="flex items-center gap-3 font-medium">
          <input type="checkbox" checked={form.is_open} onChange={(e) => set("is_open", e.target.checked)} className="h-5 w-5 accent-ink" />
          Shop is open for orders
        </label>
      </section>

      <section className="card flex flex-col gap-4">
        <h2 className="text-2xl">Shop photo</h2>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={shownPhoto ?? "/placeholder-shop.svg"}
            alt="Shop photo preview"
            className="h-40 w-full rounded-input border-[3px] border-ink object-cover sm:w-72"
          />
          <div className="flex flex-col gap-3">
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                onPickFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <button type="button" className="btn-secondary" onClick={() => fileRef.current?.click()} disabled={progress !== null}>
              {photoUrl || preview ? "Replace photo" : "Choose photo"}
            </button>
            <p className="text-sm text-muted">JPG, PNG or WebP, up to 5 MB.</p>
            {!shop && pending && <p className="text-sm font-medium">Photo will upload when you save the shop.</p>}
            {progress !== null && (
              <div role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
                <div className="h-4 w-56 overflow-hidden rounded-full border-2 border-ink bg-white">
                  <div className="h-full bg-mint transition-all" style={{ width: `${progress}%` }} />
                </div>
                <p className="mt-1 text-sm">Uploading… {progress}%</p>
              </div>
            )}
            {photoError && (
              <p role="alert" className="text-sm font-medium text-danger">
                {photoError}
              </p>
            )}
          </div>
        </div>
      </section>

      <section className="card flex flex-col gap-4">
        <h2 className="text-2xl">Location and delivery radius</h2>
        <LocationPicker
          lat={pos?.lat ?? null}
          lng={pos?.lng ?? null}
          radiusKm={radius}
          onRadius={setRadius}
          onPick={(lat, lng, label) => {
            setPos({ lat, lng });
            if (label && !form.address_text.trim()) set("address_text", label);
          }}
        />
      </section>

      <div className="flex flex-wrap items-center gap-4">
        <button type="submit" className="btn-primary" disabled={saving || progress !== null}>
          {saving ? "Saving…" : "→ Save shop"}
        </button>
        {shop?.is_configured && (
          <Link href="/owner/products" className="btn-secondary">
            Manage products
          </Link>
        )}
      </div>
    </form>
  );
}
