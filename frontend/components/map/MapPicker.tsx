"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";

// Default Leaflet marker images break under bundlers, so the pin is a divIcon (no image files needed).
const pinIcon = L.divIcon({
  className: "",
  html: '<div style="font-size:30px;line-height:36px;width:36px;height:36px;text-align:center">📍</div>',
  iconSize: [36, 36],
  iconAnchor: [18, 33], // the pin's tip sits at the clicked point
});

const DEFAULT_CENTER: [number, number] = [18.5204, 73.8567]; // Pune

export interface MapPickerProps {
  lat: number | null;
  lng: number | null;
  radiusKm: number;
  onPick: (lat: number, lng: number) => void;
}

function ClickToPin({ onPick }: { onPick: MapPickerProps["onPick"] }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

function Fit({ lat, lng, radiusKm }: { lat: number | null; lng: number | null; radiusKm: number }) {
  const map = useMap();
  useEffect(() => {
    if (lat === null || lng === null) return;
    map.fitBounds(L.latLng(lat, lng).toBounds(radiusKm * 2000 * 1.3), { animate: true });
  }, [map, lat, lng, radiusKm]);
  return null;
}

export default function MapPicker({ lat, lng, radiusKm, onPick }: MapPickerProps) {
  const has = lat !== null && lng !== null;
  return (
    <MapContainer
      center={has ? [lat, lng] : DEFAULT_CENTER}
      zoom={has ? 13 : 11}
      scrollWheelZoom
      className="h-[380px] w-full rounded-card border-[3px] border-ink"
      style={{ zIndex: 0 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickToPin onPick={onPick} />
      {has && (
        <>
          <Marker position={[lat, lng]} icon={pinIcon} />
          <Circle
            center={[lat, lng]}
            radius={radiusKm * 1000}
            pathOptions={{ color: "#17151F", weight: 3, fillColor: "#C3B1F5", fillOpacity: 0.35 }}
          />
          <Fit lat={lat} lng={lng} radiusKm={radiusKm} />
        </>
      )}
    </MapContainer>
  );
}
