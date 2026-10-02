"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { MapContainer, Marker, Polyline, TileLayer, useMap } from "react-leaflet";

function emojiIcon(emoji: string) {
  return L.divIcon({
    className: "",
    html: `<div style="font-size:28px;line-height:34px;width:34px;height:34px;text-align:center">${emoji}</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 31],
  });
}
const pinIcon = emojiIcon("📍");
const shopIcon = emojiIcon("🏪");

export interface MiniMapPoint {
  lat: number;
  lng: number;
}

function FitBoth({ a, b }: { a: MiniMapPoint | null; b: MiniMapPoint }) {
  const map = useMap();
  useEffect(() => {
    const pts = [L.latLng(b.lat, b.lng)];
    if (a) pts.push(L.latLng(a.lat, a.lng));
    map.fitBounds(L.latLngBounds(pts).pad(0.4), { maxZoom: 16, animate: false });
  }, [map, a, b]);
  return null;
}

/** Read-only map: the delivery address pin (and the shop, when known). */
export default function MiniMap({ delivery, shop }: { delivery: MiniMapPoint; shop: MiniMapPoint | null }) {
  return (
    <MapContainer
      center={[delivery.lat, delivery.lng]}
      zoom={15}
      scrollWheelZoom={false}
      dragging={false}
      zoomControl={false}
      doubleClickZoom={false}
      touchZoom={false}
      className="h-48 w-full rounded-2xl border-[3px] border-ink"
      style={{ zIndex: 0 }}
      aria-label="Delivery address map"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {shop && (
        <>
          <Marker position={[shop.lat, shop.lng]} icon={shopIcon} />
          <Polyline positions={[[shop.lat, shop.lng], [delivery.lat, delivery.lng]]} pathOptions={{ color: "#6E56D9", weight: 3, dashArray: "6 8" }} />
        </>
      )}
      <Marker position={[delivery.lat, delivery.lng]} icon={pinIcon} />
      <FitBoth a={shop} b={delivery} />
    </MapContainer>
  );
}
