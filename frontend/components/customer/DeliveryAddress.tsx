"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LocationPicker } from "@/components/map/LocationPicker";
import type { LatLng } from "@/components/map/MapPicker";
import { ErrorState } from "@/components/ui/ErrorState";
import { Field } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { useCustomer } from "@/lib/customer";
import { km } from "@/lib/format";
import type { Address, AddressLabel, DeliveryCheck, ShopPublic } from "@/lib/types";

const LABELS: AddressLabel[] = ["Home", "Work", "Other"];

type Check =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done"; result: DeliveryCheck }
  | { kind: "error"; message: string; notConfigured: boolean };

export interface ChosenAddress {
  /** Set once the address is saved (or picked from the saved ones): orders are confirmed against a saved address. */
  id?: number;
  lat: number;
  lng: number;
  address_text: string;
  label: AddressLabel;
  eligible: boolean;
  distance_km: number;
}

/** Shows a distance precisely enough that it never looks equal to the radius when it's just outside. */
function distanceText(d: number, radius: number) {
  return Math.abs(d - radius) < 0.1 ? `${d.toFixed(2)} km` : km(d);
}

export function DeliveryAddress({
  shop,
  onRequestVerify,
  onChange,
}: {
  shop: ShopPublic;
  onRequestVerify: () => void;
  onChange?: (a: ChosenAddress | null) => void;
}) {
  const toast = useToast();
  const { customer } = useCustomer();
  const [pin, setPin] = useState<LatLng | null>(null);
  const [label, setLabel] = useState<AddressLabel>("Home");
  const [text, setText] = useState("");
  const [textError, setTextError] = useState<string | null>(null);
  const [check, setCheck] = useState<Check>({ kind: "idle" });
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [saved, setSaved] = useState<{ loading: boolean; error: string | null; items: Address[] }>({
    loading: false,
    error: null,
    items: [],
  });
  const seq = useRef(0);

  const configured = shop.lat !== null && shop.lng !== null && shop.delivery_radius_km !== null;

  // Backend decides eligibility (haversine, inclusive boundary). Stale answers are dropped.
  const runCheck = useCallback(
    async (p: LatLng) => {
      const id = ++seq.current;
      setCheck({ kind: "loading" });
      try {
        const result = await api<DeliveryCheck>(`/shops/${shop.slug}/delivery-check`, { method: "POST", json: p });
        if (id === seq.current) setCheck({ kind: "done", result });
      } catch (e) {
        if (id !== seq.current) return;
        setCheck({
          kind: "error",
          message: e instanceof ApiError ? e.message : "Could not check delivery for this address.",
          notConfigured: e instanceof ApiError && e.code === "SHOP_LOCATION_NOT_SET",
        });
      }
    },
    [shop.slug],
  );

  useEffect(() => {
    if (pin) void runCheck(pin);
    else {
      seq.current++;
      setCheck({ kind: "idle" });
    }
  }, [pin, runCheck]);

  useEffect(() => {
    if (!onChange) return;
    if (pin && check.kind === "done") {
      onChange({
        ...pin,
        id: savedId ?? undefined,
        address_text: text.trim(),
        label,
        eligible: check.result.eligible,
        distance_km: check.result.distance_km,
      });
    } else onChange(null);
  }, [pin, check, text, label, savedId, onChange]);

  const loadSaved = useCallback(async () => {
    if (!customer) return setSaved({ loading: false, error: null, items: [] });
    setSaved((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await api<{ items: Address[] }>("/customer/addresses", { role: "customer" });
      setSaved({ loading: false, error: null, items: res.items });
    } catch (e) {
      setSaved({ loading: false, error: e instanceof ApiError ? e.message : "Could not load saved addresses.", items: [] });
    }
  }, [customer]);

  useEffect(() => {
    void loadSaved();
  }, [loadSaved]);

  function pickSaved(a: Address) {
    setPin({ lat: a.lat, lng: a.lng });
    setText(a.address_text);
    setLabel(a.label);
    setSavedId(a.id);
    setTextError(null);
  }

  async function save() {
    if (!pin) return;
    if (!text.trim()) {
      setTextError("Add flat / house number and a landmark so the delivery person can find you.");
      return;
    }
    setTextError(null);
    if (!customer) return onRequestVerify();
    setSaving(true);
    try {
      const a = await api<Address>("/customer/addresses", {
        method: "POST",
        role: "customer",
        json: { label, address_text: text.trim(), lat: pin.lat, lng: pin.lng },
      });
      setSaved((s) => ({ ...s, items: [a, ...s.items] }));
      setSavedId(a.id);
      toast.show("Address saved.", "success");
    } catch (e) {
      toast.show(e instanceof ApiError ? e.message : "Could not save the address.", "error");
    } finally {
      setSaving(false);
    }
  }

  if (!configured) {
    return (
      <div className="rounded-input bg-cream-yellow p-4 font-medium">
        {shop.name} hasn&apos;t set its delivery area yet, so delivery can&apos;t be checked. Ordering is unavailable.
      </div>
    );
  }

  const eligible = check.kind === "done" && check.result.eligible;

  return (
    <div className="flex flex-col gap-6">
      {customer && (
        <section aria-label="Saved addresses">
          <h3 className="mb-3 text-xl">Saved addresses</h3>
          {saved.loading ? (
            <Spinner label="Loading saved addresses…" />
          ) : saved.error ? (
            <ErrorState message={saved.error} onRetry={loadSaved} />
          ) : saved.items.length === 0 ? (
            <p className="rounded-input bg-white p-4 text-muted shadow-clay">No saved addresses yet. Drop a pin below and save one.</p>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {saved.items.map((a) => {
                const active = pin?.lat === a.lat && pin?.lng === a.lng;
                return (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => pickSaved(a)}
                      className={`flex w-full items-start gap-3 rounded-2xl p-4 text-left ${active ? "chip-active" : "bg-white shadow-clay"}`}
                    >
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-sky text-xl" aria-hidden>
                        {a.label === "Home" ? "🏠" : a.label === "Work" ? "💼" : "📍"}
                      </span>
                      <span>
                        <span className="eyebrow block">{a.label}</span>
                        <span className="font-medium">{a.address_text}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      <LocationPicker
        pin={pin}
        circle={{ lat: shop.lat!, lng: shop.lng!, radiusKm: shop.delivery_radius_km! }}
        shopMarker={{ lat: shop.lat!, lng: shop.lng! }}
        pinHint={`Click the map where you want delivery. The shaded circle is the area ${shop.name} delivers to.`}
        onPick={(lat, lng, placeLabel) => {
          setPin({ lat, lng });
          setSavedId(null); // a new pin is a new, unsaved address
          if (placeLabel && !text.trim()) setText(placeLabel);
        }}
      />

      {check.kind === "loading" && <Spinner label="Checking delivery…" />}
      {check.kind === "error" &&
        (check.notConfigured ? (
          <div className="rounded-input bg-cream-yellow p-4 font-medium">{check.message}</div>
        ) : (
          <ErrorState message={check.message} onRetry={() => pin && runCheck(pin)} />
        ))}
      {check.kind === "done" &&
        (check.result.eligible ? (
          <div role="status" className="rounded-card border-[3px] border-ink bg-mint p-4 font-semibold">
            ✓ Delivers to this address ({distanceText(check.result.distance_km, check.result.radius_km)})
          </div>
        ) : (
          <div role="alert" className="flex flex-col gap-3 rounded-card border-[3px] border-danger bg-danger-fill p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="font-semibold text-danger">
              Sorry, {shop.name} delivers within {km(check.result.radius_km)}. This address is{" "}
              {distanceText(check.result.distance_km, check.result.radius_km)} away.
            </p>
            <button
              type="button"
              className="btn-secondary shrink-0 !py-2"
              onClick={() => {
                setPin(null);
                setSavedId(null);
                setText("");
              }}
            >
              Choose another address
            </button>
          </div>
        ))}

      {pin && eligible && (
        <div className="card flex flex-col gap-4">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Address label">
            {LABELS.map((l) => (
              <button
                key={l}
                type="button"
                role="radio"
                aria-checked={label === l}
                onClick={() => setLabel(l)}
                className={`chip ${label === l ? "chip-active" : ""}`}
              >
                {label === l ? "✓ " : ""}
                {l}
              </button>
            ))}
          </div>
          <Field label="Flat / house, landmark" htmlFor="addr-text" error={textError}>
            <input
              id="addr-text"
              className="input"
              placeholder="Flat 12, Shanti Apts, near Karve Nagar bus stop"
              value={text}
              maxLength={500}
              onChange={(e) => {
                setText(e.target.value);
                setSavedId(null);
              }}
            />
          </Field>
          <button type="button" className="btn-primary self-start" onClick={save} disabled={saving}>
            {saving ? "Saving…" : customer ? "Save address" : "Verify phone to save address"}
          </button>
        </div>
      )}
    </div>
  );
}

