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

// ---- Conversations and AI ordering (Stage 3)
export type OrderStatus =
  | "draft"
  | "needs_clarification"
  | "awaiting_confirmation"
  | "confirmed"
  | "packing"
  | "out_for_delivery"
  | "delivered"
  | "cancelled";

export type OrderItemStatus =
  | "matched"
  | "ambiguous"
  | "out_of_stock"
  | "unmatched"
  | "vague_qty"
  | "removed"
  | "substituted"
  | "pending_amendment";

export type ClarificationKind =
  | "ambiguous_product"
  | "pack_size"
  | "out_of_stock"
  | "unmatched"
  | "vague_qty"
  | "unusual_qty"
  | "price_change";

export type AgentName =
  | "intake"
  | "parser"
  | "matcher"
  | "inventory"
  | "clarifier"
  | "billing"
  | "messaging"
  | "stt"
  | "ocr"
  | "explainer";

export interface ConversationInfo {
  id: number;
  shop_id: number;
  language: string | null;
  script: string | null;
  status: "open" | "closed";
  created_at: string;
}

export interface ChatMessage {
  id: number;
  conversation_id: number;
  sender: "customer" | "bot" | "shopkeeper" | "system";
  type: "text" | "audio" | "image" | "system" | "bill";
  content: string;
  media_url: string | null;
  meta: {
    clarification_ids?: number[];
    order_id?: number;
    /** "bill" | "order_confirmed" | "order_status" (Stage 4 messages) */
    kind?: string;
    status?: OrderStatus;
    order_no?: number;
    bill?: Bill;
    [k: string]: unknown;
  } | null;
  created_at: string;
}

export interface AgentRun {
  id: number;
  agent: AgentName;
  status: "running" | "success" | "error" | "skipped";
  input: unknown;
  output: unknown;
  error: string | null;
  started_at: string;
  duration_ms: number | null;
}

export interface ProductSummary {
  id: number;
  name: string;
  brand: string | null;
  sell_mode: SellMode;
  pack_size: string;
  pack_unit: PackUnit;
  price: string;
  stock_status: StockStatus;
}

export interface OrderItem {
  id: number;
  product_id: number | null;
  product_name: string | null;
  raw_text: string;
  name_guess: string;
  quantity_value: string | null;
  unit: string | null;
  normalized_qty: string | null;
  product_qty: string | null;
  unit_price_snapshot: string | null;
  line_total: string | null;
  confidence: number;
  status: OrderItemStatus;
  candidates: unknown[];
  source_span: [number, number] | null;
  parent_item_id: number | null;
  product: ProductSummary | null;
}

export interface ClarificationOption {
  product_id: number;
  label: string;
  pack: string;
  price: string;
  stock_status: StockStatus;
}

export interface Clarification {
  id: number;
  order_item_id: number;
  kind: ClarificationKind;
  question: string;
  options: ClarificationOption[];
  answer: Record<string, unknown> | null;
  resolved_at: string | null;
}

export interface Order {
  id: number;
  order_no: number;
  shop_id: number;
  conversation_id: number;
  status: OrderStatus;
  requires_reapproval: boolean;
  items: OrderItem[];
  clarifications: Clarification[];
  subtotal: string;
  discount: string;
  delivery_fee: string;
  total: string;
  delivery_address_text: string | null;
  delivery_lat: number | null;
  delivery_lng: number | null;
  distance_km: number | null;
  requested_delivery_text: string | null;
  requested_delivery_at: string | null;
  payment_method: PaymentMethod | null;
  payment_status: "pending" | "paid" | "cod" | null;
  quoted_at: string | null;
  confirmed_at: string | null;
  created_at: string;
}

export type PaymentMethod = "cod" | "upi" | "razorpay";

export interface CreateConversationResponse {
  conversation: ConversationInfo;
  guest_session: string | null;
  messages: ChatMessage[];
  order: Order | null;
  llm_mock: boolean;
}

export interface ConversationState {
  conversation: ConversationInfo;
  messages: ChatMessage[];
  order: Order | null;
  agent_runs: AgentRun[];
  llm_mock: boolean;
}

export interface ChatResponse {
  messages: ChatMessage[];
  order: Order | null;
  agent_runs: AgentRun[];
}

// ---- Shop discovery
export interface ShopCard {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  address_text: string | null;
  photo_url: string | null;
  is_open: boolean;
  delivery_radius_km: number | null;
  min_order_value: string;
  delivery_fee: string;
  product_count: number;
}

export interface ShopListResponse {
  items: ShopCard[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// ---- Bill, confirm, owner board (Stage 4)
export interface BillLine {
  item_id: number;
  product_id: number;
  name: string;
  qty: string;
  /** product unit for loose items ("kg", "l"), "pack" for packed ones */
  unit: string;
  /** what the customer gets: "2 kg" or "×4" */
  qty_label: string;
  unit_price: string;
  line_total: string;
}

export interface Bill {
  order_id: number;
  order_no: number;
  lines: BillLine[];
  subtotal: string;
  discount: string;
  delivery_fee: string;
  total: string;
  payment_method: PaymentMethod | null;
  requires_reapproval: boolean;
  quoted_at: string | null;
}

export interface StatusEvent {
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  actor: "customer" | "shopkeeper" | "system";
  note: string | null;
  created_at: string;
}

export interface CustomerOrderResponse {
  order: Order;
  timeline: StatusEvent[];
}

export interface ConfirmResponse {
  order: Order;
  message: string;
  newly_confirmed: boolean;
}

export interface OwnerOrderCard {
  id: number;
  order_no: number;
  status: OrderStatus;
  customer_phone_masked: string | null;
  item_count: number;
  total: string;
  payment_method: PaymentMethod | null;
  payment_status: "pending" | "paid" | "cod" | null;
  requested_delivery_text: string | null;
  requested_delivery_at: string | null;
  has_problem: boolean;
  created_at: string;
  updated_at: string;
}

export interface OwnerOrderDetail {
  order: Order;
  customer: { phone_masked: string | null };
  shop: { name: string; lat: number | null; lng: number | null };
  messages: ChatMessage[];
  bill: Bill | null;
  problems: string[];
  allowed_next: OrderStatus[];
  timeline: StatusEvent[];
  agent_runs: AgentRun[];
}

export interface DeliveryNote {
  order_no: number;
  shop_name: string;
  customer_phone: string | null;
  delivery_address_text: string | null;
  delivery_lat: number | null;
  delivery_lng: number | null;
  requested_delivery_text: string | null;
  requested_delivery_at: string | null;
  items: { name: string; qty: string; unit: string; qty_label: string; unit_price: string; line_total: string }[];
  subtotal: string;
  delivery_fee: string;
  total: string;
  payment_method: PaymentMethod | null;
  payment_status: "pending" | "paid" | "cod" | null;
  created_at: string;
}

export interface CustomerOrderRow {
  id: number;
  order_no: number;
  shop_slug: string;
  shop_name: string;
  status: OrderStatus;
  is_cart: boolean;
  item_count: number;
  total: string;
  created_at: string;
  confirmed_at: string | null;
  items: { name: string; quantity: string | null; line_total: string | null }[];
}

export interface CustomerOrderList {
  cart: CustomerOrderRow[];
  past: CustomerOrderRow[];
}
