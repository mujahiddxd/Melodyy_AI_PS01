// Shared API types. Keep in sync with /API_CONTRACT.md.

export interface Health {
  status: "ok" | "degraded";
  db: "ok" | "error";
}

// ---- Auth (Stage 1)
export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  shop_id: number | null;
  has_shop: boolean;
}

// ---- Shop
export interface ShopPublic {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  address_text: string | null;
  lat: number | null;
  lng: number | null;
  delivery_radius_km: number | null;
  photo_url: string | null;
  upi_vpa: string | null;
  min_order_value: string;
  delivery_fee: string;
  is_open: boolean;
}

export interface ShopOwner extends ShopPublic {
  photo_public_id: string | null;
  is_configured: boolean;
}

export interface ShopInput {
  name: string;
  description: string | null;
  address_text: string | null;
  lat: number | null;
  lng: number | null;
  delivery_radius_km: number | null;
  upi_vpa: string | null;
  min_order_value: string;
  delivery_fee: string;
  is_open: boolean;
}

export interface PhotoResponse {
  photo_url: string;
  photo_public_id: string;
}

export interface GeoResult {
  display_name: string;
  lat: number;
  lng: number;
}

// ---- Products
export type SellMode = "pack" | "loose";
export type PackUnit = "g" | "kg" | "ml" | "l" | "pc" | "dozen" | "packet";
export type StockStatus = "in_stock" | "low_stock" | "out_of_stock";

export interface ProductPublic {
  id: number;
  name: string;
  brand: string | null;
  category: string;
  sell_mode: SellMode;
  pack_size: string;
  pack_unit: PackUnit;
  price: string;
  stock_qty: string;
  stock_status: StockStatus;
  aliases: string[];
  shelf: string | null;
}

export interface ProductOwner extends ProductPublic {
  low_stock_threshold: string;
  max_normal_qty: string | null;
  is_active: boolean;
  updated_at: string;
}

export interface ProductInput {
  name: string;
  brand: string | null;
  category: string;
  sell_mode: SellMode;
  pack_size: string;
  pack_unit: PackUnit;
  price: string;
  stock_qty: string;
  low_stock_threshold: string;
  max_normal_qty: string | null;
  aliases: string[];
  shelf: string | null;
}

export interface ProductList {
  items: ProductOwner[];
  total: number;
}

export interface PublicShopResponse {
  shop: ShopPublic;
  categories: { name: string; products: ProductPublic[] }[];
}

// ---- Customer (Stage 2)
export interface OtpRequestResponse {
  status: "sent";
  expires_in_seconds: number;
  resend_after_seconds: number;
  provider: "mock" | "msg91" | "twilio";
}

export interface Customer {
  id: number;
  phone: string;
  name: string | null;
}

export interface CustomerAuthResponse {
  access_token: string;
  token_type: "bearer";
  customer: Customer;
}

export interface DemoInbox {
  messages: { phone: string; code: string; created_at: string; expires_at: string }[];
}

export type AddressLabel = "Home" | "Work" | "Other";

export interface Address {
  id: number;
  label: AddressLabel;
  address_text: string;
  lat: number;
  lng: number;
  created_at: string;
}

export interface DeliveryCheck {
  eligible: boolean;
  distance_km: number;
  radius_km: number;
}
