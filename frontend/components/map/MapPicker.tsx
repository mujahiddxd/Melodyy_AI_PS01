"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";

// Default Leaflet marker images break under bundlers, so pins are divIcons (no image files needed).
function emojiIcon(emoji: string) {
  return L.divIcon({
    className: "",
    html: `<div style="font-size:30px;line-height:36px;width:36px;height:36px;text-align:center">${emoji}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 33], // the pin's tip sits at the clicked point
  });
}
const pinIcon = emojiIcon("📍");
const shopIcon = emojiIcon("🏪");

const DEFAULT_CENTER: [number, number] = [18.5204, 73.8567]; // Pune

export interface LatLng {
  lat: number;
  lng: number;
}
export interface CircleSpec extends LatLng {
  radiusKm: number;
}

export interface MapPickerProps {
  /** The point being chosen (shop pin in setup, delivery pin for customers). */
  pin: LatLng | null;
  /** Delivery area to draw. */
  circle: CircleSpec | null;
  /** Optional fixed marker, e.g. the shop when a customer picks an address. */
  shopMarker?: LatLng | null;
  onPick: (lat: number, lng: number) => void;
}

function ClickToPin({ onPick }: { onPick: MapPickerProps["onPick"] }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

function Fit({ pin, circle }: { pin: LatLng | null; circle: CircleSpec | null }) {
  const map = useMap();
  const cLat = circle?.lat, cLng = circle?.lng, cR = circle?.radiusKm;

  // whenever the area changes: show all of it
  useEffect(() => {
    if (cLat === undefined || cLng === undefined || cR === undefined) return;
    map.fitBounds(L.latLng(cLat, cLng).toBounds(cR * 2000 * 1.3), { animate: true });
  }, [map, cLat, cLng, cR]);

  // a pin off-screen (search / GPS result): bring it into view together with the area
  useEffect(() => {
    if (!pin) return;
    const p = L.latLng(pin.lat, pin.lng);
    if (map.getBounds().contains(p)) return;
    const b = cLat !== undefined && cLng !== undefined && cR !== undefined
      ? L.latLng(cLat, cLng).toBounds(cR * 2000 * 1.3).extend(p)
      : p.toBounds(2000);
    map.fitBounds(b.pad(0.1), { animate: true });
  }, [map, pin, cLat, cLng, cR]);
  return null;
}

export default function MapPicker({ pin, circle, shopMarker, onPick }: MapPickerProps) {
  const start = pin ?? circle;
  return (
    <MapContainer
      center={start ? [start.lat, start.lng] : DEFAULT_CENTER}
      zoom={start ? 13 : 11}
      scrollWheelZoom
      className="h-[380px] w-full rounded-card border-[3px] border-ink"
      style={{ zIndex: 0 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickToPin onPick={onPick} />
      {circle && (
        <Circle
          center={[circle.lat, circle.lng]}
          radius={circle.radiusKm * 1000}
          pathOptions={{ color: "#17151F", weight: 3, fillColor: "#C3B1F5", fillOpacity: 0.35 }}
        />
      )}
      {shopMarker && <Marker position={[shopMarker.lat, shopMarker.lng]} icon={shopIcon} title="Shop" />}
      {pin && <Marker position={[pin.lat, pin.lng]} icon={pinIcon} />}
      <Fit pin={pin} circle={circle} />
    </MapContainer>
  );
}
