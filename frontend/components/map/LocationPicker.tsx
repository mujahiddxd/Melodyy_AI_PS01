"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import type { GeoResult } from "@/lib/types";
import type { CircleSpec, LatLng } from "./MapPicker";

// Leaflet touches `window`, so it must never render on the server.
const MapPicker = dynamic(() => import("./MapPicker"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[380px] items-center justify-center rounded-card border-[3px] border-ink bg-white">
      <Spinner label="Loading map…" />
    </div>
  ),
});

/**
 * Map + place search + "Use my location". Used by the shop setup (pin + radius slider)
 * and by customers choosing a delivery point (pin + the shop's fixed delivery circle).
 */
export function LocationPicker({
  pin,
  circle,
  shopMarker,
  radius,
  pinHint = "Click the map to drop the pin.",
  onPick,
}: {
  pin: LatLng | null;
  circle: CircleSpec | null;
  shopMarker?: LatLng | null;
  /** Shows the 0.5-10 km radius slider (shop setup only). */
  radius?: { valueKm: number; onChange: (km: number) => void };
  pinHint?: string;
  onPick: (lat: number, lng: number, label?: string) => void;
}) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<GeoResult[] | null>(null);
  const [locating, setLocating] = useState(false);

  async function search() {
    if (q.trim().length < 2) return;
    setSearching(true);
    try {
      setResults(await api<GeoResult[]>(`/geo/search?q=${encodeURIComponent(q.trim())}`));
    } catch (err) {
      setResults([]);
      toast.show(err instanceof ApiError ? err.message : "Search failed. Click the map instead.", "error");
    } finally {
      setSearching(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      toast.show("Your browser can't share its location. Click the map instead.", "error");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        onPick(pos.coords.latitude, pos.coords.longitude);
      },
      () => {
        setLocating(false);
        toast.show("Couldn't get your location. Allow access, or click the map instead.", "error");
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row">
        {/* not a <form>: this component sits inside the setup form, and nested forms would also trigger its save */}
        <div className="flex flex-1 gap-2">
          <input
            className="input"
            aria-label="Search for a place"
            placeholder="Search a place, e.g. Kothrud, Pune"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void search();
              }
            }}
          />
          <button type="button" className="btn-secondary" onClick={() => void search()} disabled={searching}>
            {searching ? "…" : "Search"}
          </button>
        </div>
        <button type="button" className="btn-secondary" onClick={useMyLocation} disabled={locating}>
          {locating ? "Locating…" : "◎ Use my location"}
        </button>
      </div>

      {results !== null && (
        <ul className="flex flex-col gap-2" aria-label="Search results">
          {results.length === 0 ? (
            <li className="text-muted">No places found. Try another search, or click the map to drop the pin.</li>
          ) : (
            results.map((r, i) => (
              <li key={i}>
                <button
                  type="button"
                  className="chip w-full text-left"
                  onClick={() => {
                    onPick(r.lat, r.lng, r.display_name);
                    setResults(null);
                  }}
                >
                  📍 {r.display_name}
                </button>
              </li>
            ))
          )}
        </ul>
      )}

      <MapPicker pin={pin} circle={circle} shopMarker={shopMarker} onPick={(a, b) => onPick(a, b)} />
      <p className="text-sm text-muted">
        {pin === null ? pinHint : `Pin at ${pin.lat.toFixed(5)}, ${pin.lng.toFixed(5)}. Click the map to move it.`}
      </p>

      {radius && (
        <div>
          <label htmlFor="radius" className="eyebrow">
            Delivery radius: <span className="text-ink">{radius.valueKm} km</span>
          </label>
          <input
            id="radius"
            type="range"
            min={0.5}
            max={10}
            step={0.5}
            value={radius.valueKm}
            onChange={(e) => radius.onChange(parseFloat(e.target.value))}
            className="mt-2 w-full accent-ink"
          />
          <div className="flex justify-between text-xs text-muted">
            <span>0.5 km</span>
            <span>10 km</span>
          </div>
        </div>
      )}
    </div>
  );
}
