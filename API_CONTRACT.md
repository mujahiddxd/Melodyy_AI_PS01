# API_CONTRACT.md — Hinglish Order Desk

Single source of truth for every HTTP endpoint. Frontend (`frontend/lib/types.ts`, `lib/api.ts`) and backend (`backend/app/schemas`, `routers`) must match this file exactly. If an endpoint changes, update this file in the same commit.

Base URL (dev): `http://localhost:8000` · Interactive docs: `/docs`.
Status column: **LIVE** = implemented in the repo now. **PLANNED (Stage N)** = specified here, built in that stage.

---

## 1. Conventions

### 1.1 Auth headers

| Caller | Header | Notes |
|---|---|---|
| Shopkeeper (`owner`) | `Authorization: Bearer <owner_jwt>` | JWT `{sub, role:"shopkeeper", shop_id?, exp}`, 24 h expiry |
| Verified customer | `Authorization: Bearer <customer_jwt>` | JWT `{sub, role:"customer", exp}`. Only issued after OTP verify |
| Guest (chat before verification) | `X-Guest-Session: <token>` | Issued in the response of `POST /shops/{slug}/conversations`. Valid only for that conversation |
| Public | none | |

"session" in the Auth column means: guest `X-Guest-Session` **or** customer Bearer token that owns the conversation. Confirming an order always needs the customer Bearer token.
Frontend token storage: `owner_token`, `customer_token` (memory + `localStorage`). No secrets ever live in the frontend; the only public variable is `NEXT_PUBLIC_API_URL`.

### 1.2 Content types
JSON requests: `Content-Type: application/json`. File uploads: `multipart/form-data`. All timestamps are ISO-8601 UTC strings (`2026-10-02T09:30:00Z`). Money is a **string with 2 decimals** (`"155.00"`), never a float. Quantities that can be fractional are strings with up to 3 decimals (`"0.500"`). Distances are numbers in km.

### 1.3 Error format
Every error returns JSON with a `detail` key. Never a stack trace.

Simple error:
```json
{ "detail": "Incorrect email or password." }
```
Coded error (frontend branches on `code`):
```json
{ "detail": { "code": "OUT_OF_RADIUS", "message": "Sharma Kirana delivers within 3 km. This address is 5.4 km away.", "distance_km": 5.4, "radius_km": 3.0 } }
```
Request-body validation failure (FastAPI default, status 422):
```json
{ "detail": [ { "loc": ["body", "price"], "msg": "Input should be greater than 0", "type": "greater_than" } ] }
```
Unexpected server failure (status 500): `{ "detail": "Something went wrong. Please try again." }`

### 1.4 Error codes

| HTTP | `code` | When |
|---|---|---|
| 400 | `OTP_INVALID` | Wrong OTP code |
| 400 | `OTP_EXPIRED` | OTP older than 5 minutes or already used |
| 400 | `FILE_TYPE_NOT_ALLOWED` | Upload MIME type not accepted |
| 400 | `NO_UPI_VPA` | `/orders/{id}/upi-qr` and shop has no VPA |
| 401 | `UNAUTHORIZED` | Missing, invalid or expired token (simple string detail is also acceptable) |
| 403 | `FORBIDDEN` | Valid token but not allowed (another shop's data, another customer's order) |
| 404 | `NOT_FOUND` | Resource missing, or demo inbox when `OTP_PROVIDER != mock` |
| 409 | `INVALID_TRANSITION` | Order state machine refuses the move |
| 409 | `STOCK_CHANGED` | Stock too low at confirm. Transaction rolled back |
| 409 | `PRICE_CHANGED` | Price differs from quote at confirm. Re-quoted, `requires_reapproval=true` |
| 409 | `OPEN_CLARIFICATIONS` | Confirm attempted while clarifications are open |
| 409 | `AMENDMENT_NOT_ALLOWED` | Amendment after `out_for_delivery` |
| 409 | `CONFLICT` | Duplicate phone/email on signup |
| 413 | `FILE_TOO_LARGE` | Upload over the size limit |
| 502 | `SMS_FAILED` | OTP SMS provider (MSG91) refused or is not configured |
| 502 | `UPLOAD_FAILED` | Storage provider (Cloudinary) failed while saving a photo |
| 422 | `OUT_OF_RADIUS` | Address outside the delivery radius (also from `/confirm`) |
| 422 | `SHOP_LOCATION_NOT_SET` | Shop has no lat/lng/radius configured |
| 422 | `VALIDATION_ERROR` | Business-rule validation (use FastAPI default list for schema errors) |
| 422 | `MESSAGE_TOO_LONG` | Message over 1,000 characters |
| 429 | `OTP_TOO_MANY_ATTEMPTS` | 6th wrong attempt on one OTP |
| 429 | `OTP_RATE_LIMITED` | More than 3 OTP requests per phone per 10 minutes, or a resend within 30 s |
| 502 | `LLM_FAILED` | LLM/STT/OCR provider failed after retry (chat shows a friendly message) |

### 1.5 Enums

| Name | Values |
|---|---|
| `OrderStatus` | `draft`, `needs_clarification`, `awaiting_confirmation`, `confirmed`, `packing`, `out_for_delivery`, `delivered`, `cancelled` |
| `OrderItemStatus` | `matched`, `ambiguous`, `out_of_stock`, `unmatched`, `vague_qty`, `removed`, `substituted`, `pending_amendment` |
| `ClarificationKind` | `ambiguous_product`, `pack_size`, `out_of_stock`, `unmatched`, `vague_qty`, `unusual_qty`, `price_change` |
| `PaymentMethod` | `cod`, `upi`, `razorpay` |
| `PaymentStatus` | `pending`, `paid`, `cod` |
| `MessageSender` | `customer`, `bot`, `shopkeeper`, `system` |
| `MessageType` | `text`, `audio`, `image`, `system`, `bill` |
| `ConversationStatus` | `open`, `closed` |
| `Language` | `hinglish`, `hindi`, `marathi`, `english` |
| `Script` | `latin`, `devanagari` |
| `Intent` | `new_order`, `add_items`, `remove_items`, `change_quantity`, `answer_clarification`, `confirm`, `cancel`, `repeat_last_order`, `status_query`, `gibberish`, `other` |
| `AgentName` | `intake`, `parser`, `matcher`, `inventory`, `clarifier`, `billing`, `messaging`, `stt`, `ocr`, `explainer` |
| `AgentStatus` | `running`, `success`, `error`, `skipped` |
| `SellMode` | `pack`, `loose` |
| `PackUnit` | `g`, `kg`, `ml`, `l`, `pc`, `dozen`, `packet` |
| `UploadKind` | `shop_photo`, `list_image`, `audio` |
| `PaymentRecordStatus` | `pending`, `paid`, `failed` |
| `ReturnStatus` | `requested`, `approved`, `rejected`, `refunded` |

### 1.6 Order state machine
```
draft -> needs_clarification -> awaiting_confirmation -> confirmed -> packing -> out_for_delivery -> delivered
any pre-delivery state -> cancelled
```
Customer actions: only `draft`, `needs_clarification`, `awaiting_confirmation` (plus amendments while `confirmed`/`packing`). Shopkeeper: `confirmed -> packing -> out_for_delivery -> delivered`, and cancel. Anything else returns `409 INVALID_TRANSITION`.

### 1.7 Shared object shapes

**Product (public)**
```json
{ "id": 14, "name": "Fortune Sunflower Oil 1L", "brand": "Fortune", "category": "Oil", "sell_mode": "pack", "pack_size": "1.000", "pack_unit": "l", "price": "155.00", "stock_qty": "24.000", "stock_status": "in_stock", "aliases": ["tel", "oil"], "shelf": "B1" }
```
`stock_status`: `in_stock` | `low_stock` (qty <= `low_stock_threshold`, shown as "Only N left") | `out_of_stock` (qty = 0).
**Product (owner)** adds: `low_stock_threshold`, `max_normal_qty`, `is_active`, `updated_at`.

**Shop (public)** — never includes owner details
```json
{ "id": 1, "name": "Sharma Kirana", "slug": "sharma-kirana", "description": "Your neighbourhood kirana store.", "address_text": "Shop 4, Karve Road, Kothrud, Pune", "lat": 18.5074, "lng": 73.8077, "delivery_radius_km": 3.0, "photo_url": "https://res.cloudinary.com/.../shop.jpg", "upi_vpa": "sharmakirana@upi", "min_order_value": "0.00", "delivery_fee": "0.00", "is_open": true }
```
`lat`, `lng`, `delivery_radius_km` are `null` until the owner sets the location (UI then shows "Delivery area not configured" and disables ordering).

**Order item**
```json
{ "id": 71, "product_id": 3, "product_name": "Atta (Loose)", "raw_text": "2 kilo atta", "name_guess": "atta", "quantity_value": "2.000", "unit": "kg", "normalized_qty": "2.000", "product_qty": "2.000", "unit_price_snapshot": "45.00", "line_total": "90.00", "confidence": 0.93, "status": "matched", "candidates": [], "source_span": [7, 18], "parent_item_id": null }
```
**Clarification**
```json
{ "id": 9, "order_item_id": 72, "kind": "ambiguous_product", "question": "Kaunsa tel chahiye?", "options": [ { "product_id": 14, "label": "Fortune Sunflower 1L", "price": "155.00", "stock_status": "in_stock" } ], "answer": null, "resolved_at": null }
```
**Order**
```json
{ "id": 42, "order_no": 1042, "shop_id": 1, "conversation_id": 7, "status": "needs_clarification", "requires_reapproval": false, "items": [], "clarifications": [], "subtotal": "0.00", "discount": "0.00", "delivery_fee": "0.00", "total": "0.00", "delivery_address_text": null, "delivery_lat": null, "delivery_lng": null, "distance_km": null, "requested_delivery_text": "kal subah tak", "requested_delivery_at": "2026-10-03T02:30:00Z", "payment_method": null, "payment_status": null, "quoted_at": null, "confirmed_at": null, "created_at": "2026-10-02T09:30:00Z" }
```
`order_no = 1000 + id`.
**Message**
```json
{ "id": 301, "conversation_id": 7, "sender": "bot", "type": "text", "content": "Kaunsa tel chahiye?", "media_url": null, "meta": { "options_for_clarification_id": 9 }, "created_at": "2026-10-02T09:30:04Z" }
```
**AgentRun**
```json
{ "id": 55, "agent": "parser", "status": "success", "input": {}, "output": {}, "error": null, "started_at": "2026-10-02T09:30:01Z", "duration_ms": 812 }
```

---

## 2. Stage 0

### GET /health — LIVE
Auth: none.
Response `200`:
```json
{ "status": "ok", "db": "ok" }
```
Response `503` (database unreachable):
```json
{ "status": "degraded", "db": "error" }
```

---

## 3. Stage 1 — Shopkeeper, shop, catalog, public shop (LIVE)

### POST /auth/owner/signup
Auth: none. Request (`phone` **or** `email` required; phone = 10 digits, starts 6-9; password >= 6 chars):
```json
{ "name": "Ramesh Sharma", "email": "ramesh@example.com", "phone": null, "password": "secret123" }
```
Response `201`:
```json
{ "access_token": "eyJ...", "token_type": "bearer", "shop_id": null, "has_shop": false }
```
Errors: `409 CONFLICT` (phone/email taken), `422` validation.

### POST /auth/owner/login
Auth: none. Request (`identifier` = email or phone):
```json
{ "identifier": "demo@shop.in", "password": "demo1234" }
```
Response `200`: same shape as signup. `has_shop` is `false` until the shop has name + location, so the frontend redirects to `/owner/setup`, else `/owner/orders`.
Errors: `401` `{ "detail": "Incorrect email/phone or password." }` (same message for an unknown account or a wrong password).

### GET /owner/shop
Auth: owner. Response `200`: full **Shop (public)** object plus `{ "photo_public_id": "...", "is_configured": true }`. `is_configured` is true when name, lat, lng and radius are all set. `404 NOT_FOUND` ("Set up your shop first.") if the owner has no shop yet.
Auth errors on every `/owner/*` endpoint: `401 UNAUTHORIZED` (missing/invalid/expired token), `403 FORBIDDEN` (a valid token of another role).

### PUT /owner/shop
Auth: owner. Creates the shop if none exists, otherwise updates. Slug is generated from the name on create (unique, e.g. `sharma-kirana-2`) and never changes afterwards.
```json
{ "name": "Sharma Kirana", "description": "...", "address_text": "...", "lat": 18.5074, "lng": 73.8077, "delivery_radius_km": 3.0, "upi_vpa": "sharmakirana@upi", "min_order_value": "0.00", "delivery_fee": "0.00", "is_open": true }
```
Only the fields sent are changed (an explicit `null` clears `description`, `address_text`, `lat`/`lng`, `delivery_radius_km`, `upi_vpa`). `lat` and `lng` must be sent together. Validation: `name` required; `upi_vpa` matches `^[\w.\-]{2,}@[\w]{2,}$`; `delivery_radius_km` 0.5-10; lat -90..90; lng -180..180.
Response `200`: same as GET /owner/shop.

### POST /owner/shop/photo
Auth: owner, and the shop must exist (`404` otherwise). `multipart/form-data`, field `file` (jpg/png/webp, <= 5 MB). The real file type is checked from the file's first bytes, not just the declared MIME type. Replacing deletes the old asset (best effort, after the new one is saved).
Response `200`:
```json
{ "photo_url": "https://res.cloudinary.com/.../shop.jpg", "photo_public_id": "hod/shops/abc123" }
```
Without `CLOUDINARY_URL` the file is saved locally; then `photo_url` is `<BACKEND_PUBLIC_URL>/media/shops/<uuid>.jpg` and `photo_public_id` is `local:shops/<uuid>.jpg`.
Errors: `400 FILE_TYPE_NOT_ALLOWED`, `413 FILE_TOO_LARGE`, `502 UPLOAD_FAILED`.

### GET /owner/products?q=&include_inactive=false
Auth: owner. `q` matches name, brand, category and aliases (case-insensitive). Ordered by category then name. Response `200`: `{ "items": [ <Product (owner)> ], "total": 43 }`. `404 NOT_FOUND` if the owner has no shop yet (same for POST/PATCH/DELETE).

### POST /owner/products
Auth: owner. Request:
```json
{ "name": "Amul Butter 100g", "brand": "Amul", "category": "Dairy", "sell_mode": "pack", "pack_size": "100", "pack_unit": "g", "price": "54.00", "stock_qty": "10", "low_stock_threshold": "5", "max_normal_qty": "6", "aliases": ["butter", "makkhan"], "shelf": "C1" }
```
Validation: price > 0, stock_qty >= 0, pack_size > 0, `low_stock_threshold` >= 0, `max_normal_qty` > 0 or null, `pack_unit` in the `PackUnit` enum. Violations return `422` (FastAPI list). Response `201`: **Product (owner)**.

### PATCH /owner/products/{id}
Auth: owner. Partial update, any field of the POST body. A changed `price` writes a `price_history` row (same-price edits do not). `is_active: true` reactivates a deactivated product. Explicit `null` is only accepted for `brand`, `max_normal_qty`, `shelf`. Response `200`: **Product (owner)**. `403 FORBIDDEN` for another shop's product, `404` if it doesn't exist.

### DELETE /owner/products/{id}
Auth: owner. Soft delete (`is_active=false`). Response `204`.

### GET /geo/search?q=Kothrud
Auth: none. Backend proxy to the Google Geocoding API (key in `GOOGLE_MAPS_API_KEY`, backend only). Results are cached for 1 hour and upstream calls are limited to 1 per second. At most 5 results, biased to India. `q` is 2-200 characters. Response `200`:
```json
[ { "display_name": "Kothrud, Pune, Maharashtra, India", "lat": 18.5074, "lng": 73.8077 } ]
```
Empty/too-short `q`, a Google error (e.g. `REQUEST_DENIED`) or a missing key: `200 []` (map click and GPS still work). The key is never returned or logged.

### GET /shops/{slug}
Auth: none. Response `200`:
```json
{ "shop": { "...Shop (public)": "..." }, "categories": [ { "name": "Oil", "products": [ { "...Product (public)": "..." } ] } ] }
```
Only active products. `404` if the slug is unknown.

---

## 4. Stage 2 — Customer OTP, addresses, delivery check (LIVE, except `claim`)

Browsing (`GET /shops/{slug}`), `delivery-check` and chat need no login. Only a successful OTP verify issues a customer token.

### POST /auth/customer/otp/request
Auth: none. Request: `{ "phone": "9876543210" }`. Phone = 10 digits starting 6-9; `+91 98765 43210` is also accepted and normalised. Response `202`:
```json
{ "status": "sent", "expires_in_seconds": 300, "resend_after_seconds": 30, "provider": "mock" }
```
- The code is 6 random digits (CSPRNG, never fixed). The DB stores only `sha256(code + phone + OTP_SECRET)`.
- A new request invalidates any older unused code for that phone, so only the latest code can verify.
- `provider` is `mock` | `msg91` (set by `OTP_PROVIDER`). The frontend shows the Demo SMS inbox only for `mock`.

Errors:
- `429 OTP_RATE_LIMITED` `{ "code", "message", "retry_after_seconds": 27 }`: a second request within 30 s of the last one, or a 4th request within 10 minutes.
- `502 SMS_FAILED`: the SMS provider refused. This attempt does not count toward the limit.
- `422`: invalid phone.

### POST /auth/customer/otp/verify
Auth: none. Request: `{ "phone": "9876543210", "code": "482913" }` (`code` = exactly 6 digits). Checks the latest code for that phone. Response `200`:
```json
{ "access_token": "eyJ...", "token_type": "bearer", "customer": { "id": 5, "phone": "9876543210", "name": null } }
```
Creates the customer on first verify and sets `verified_at`. The code is marked consumed.
Errors:
- `400 OTP_INVALID` `{ "code", "message", "attempts_left": 3 }`: wrong code. Every attempt counts.
- `400 OTP_EXPIRED`: no code, code older than 5 minutes, already used, or replaced by a newer one.
- `429 OTP_TOO_MANY_ATTEMPTS` `{ "code", "message", "attempts_left": 0 }`: the 6th attempt on one code (max 5), even with the right code. The customer must request a new code.

### GET /auth/customer/otp/demo-inbox?phone=9876543210
Auth: none. **Only when `OTP_PROVIDER=mock`, else `404`.** The UI shows a `MOCK SMS` badge. Response `200`:
```json
{ "messages": [ { "phone": "9876543210", "code": "482913", "created_at": "2026-10-02T09:31:00Z", "expires_at": "2026-10-02T09:36:00Z" } ] }
```
Returns only the latest unexpired, unconsumed code for that phone, otherwise `{ "messages": [] }`. The plain code lives only in the backend process memory (mock mode), never in the DB.

### GET /customer/me
Auth: customer. Response `200`: `{ "id": 5, "phone": "9876543210", "name": null }`. Used by the frontend to check that a stored `customer_token` is still valid.
Auth errors on every `/customer/*` endpoint: `401 UNAUTHORIZED` (missing/invalid/expired token), `403 FORBIDDEN` (a valid token of another role, e.g. an owner token).

### GET /customer/addresses
Auth: customer. Newest first. Response `200`: `{ "items": [ { "id": 3, "label": "Home", "address_text": "Flat 12, Karve Nagar", "lat": 18.50, "lng": 73.81, "created_at": "..." } ] }`

### POST /customer/addresses
Auth: customer. Request: `{ "label": "Home", "address_text": "Flat 12, Karve Nagar", "lat": 18.50, "lng": 73.81 }`. Validation: `label` = `Home` | `Work` | `Other`; `address_text` 1-500 chars; lat -90..90; lng -180..180. Response `201`: the address object.

### POST /shops/{slug}/delivery-check
Auth: none (guests can check). Request: `{ "lat": 18.51, "lng": 73.81 }`. Response `200`:
```json
{ "eligible": true, "distance_km": 1.8, "radius_km": 3.0 }
```
Boundary is inclusive (`distance <= radius`), decided on the unrounded distance. `distance_km` is rounded to 2 decimals. Distance is straight-line haversine (R = 6371 km). The same `check_delivery()` runs again at order confirm (Stage 4).
Errors: `404` unknown slug, `422 SHOP_LOCATION_NOT_SET` (`"<shop> hasn't set its delivery area yet."`), `422` invalid lat/lng.

### POST /conversations/{id}/claim — PLANNED (Stage 3, needs conversations)
Auth: customer Bearer **and** `X-Guest-Session` of that conversation. Attaches the guest conversation (and its open order) to the customer. Response `200`: `{ "conversation_id": 7, "customer_id": 5 }`.

---

## 5. Stage 3 — Conversations and AI text ordering (PLANNED)

### POST /shops/{slug}/conversations
Auth: none, or customer Bearer. Response `201`:
```json
{ "conversation": { "id": 7, "shop_id": 1, "language": null, "script": null, "status": "open", "created_at": "..." }, "guest_session": "gs_9f2c...", "messages": [], "order": null }
```
`guest_session` is `null` when called with a customer token.

### GET /conversations/{id}
Auth: session. Response `200`:
```json
{ "conversation": { "...": "..." }, "messages": [ "<Message>" ], "order": "<Order> | null", "agent_runs": [ "<AgentRun> (latest message only)" ] }
```

### POST /conversations/{id}/messages
Auth: session. Runs the orchestrator **synchronously** (typically 3-8 s). Request (max 1,000 chars):
```json
{ "type": "text", "content": "bhaiya 2 kilo atta, ek Amul butter aur sugar half kilo, tel bhi chahiye" }
```
Response `200`:
```json
{
  "messages": [ { "id": 300, "sender": "customer", "type": "text", "content": "bhaiya 2 kilo atta, ...", "created_at": "..." },
                { "id": 301, "sender": "bot", "type": "text", "content": "Kaunsa tel chahiye - sunflower, groundnut ya mustard? Aur 1L ya 5L?", "meta": { "clarification_ids": [9] }, "created_at": "..." } ],
  "order": "<Order>",
  "agent_runs": [ "<AgentRun>" ]
}
```
Gibberish input: `messages` has the bot's "please repeat" reply, `order` is `null`/unchanged, no order rows created.
Errors: `422 MESSAGE_TOO_LONG`, `502 LLM_FAILED` (the bot also stores a friendly "Thoda problem hua, dobara bhejiye" message; nothing is written to the order).

### POST /conversations/{id}/clarifications/{cid}/answer
Auth: session. Request (one of):
```json
{ "option_product_id": 14 }
```
```json
{ "text": "sunflower wala 1 litre" }
```
`option_product_id` must be one of the clarification's `options` (otherwise `422`). Re-runs Matcher + Inventory + Clarifier for that item only. Response `200`: same shape as `POST /conversations/{id}/messages`. When nothing is left open the order moves to `awaiting_confirmation`.

---

## 6. Stage 4 — Bill, confirm, owner board (PLANNED)

### POST /orders/{id}/quote
Auth: session. Recomputes totals from **current DB prices**, snapshots `unit_price_snapshot`, sets `quoted_at`, posts a `bill` message. Response `200`:
```json
{ "order": "<Order>", "bill": { "lines": [ { "item_id": 71, "name": "Atta (Loose)", "qty": "2.000", "unit": "kg", "unit_price": "45.00", "line_total": "90.00" } ], "subtotal": "272.00", "discount": "0.00", "delivery_fee": "0.00", "total": "272.00" } }
```
Errors: `409 OPEN_CLARIFICATIONS`.

### POST /orders/{id}/confirm
Auth: customer Bearer (order must belong to that customer's conversation). Request:
```json
{ "address_id": 3, "payment_method": "cod" }
```
Steps: state check -> `check_delivery()` again -> one transaction with `SELECT ... FOR UPDATE` on products, stock and price re-check -> deduct stock -> `confirmed`. Idempotent: confirming an already-confirmed order returns it unchanged (no second deduction). Response `200`:
```json
{ "order": "<Order, status=confirmed, payment_status=cod>", "message": "Order #1042 confirmed" }
```
Errors:
- `401` no/invalid customer token; `403`/`404` not this customer's order
- `409 OPEN_CLARIFICATIONS`
- `422 OUT_OF_RADIUS` with `distance_km`, `radius_km`
- `409 STOCK_CHANGED`: `{ "detail": { "code": "STOCK_CHANGED", "message": "Stock changed for Amul Butter 100g, please review.", "items": [ { "item_id": 72, "product_name": "Amul Butter 100g", "available_qty": "0.000" } ] } }`
- `409 PRICE_CHANGED`: `{ "detail": { "code": "PRICE_CHANGED", "message": "Price changed for Fortune Sunflower Oil 1L.", "changes": [ { "item_id": 73, "product_name": "Fortune Sunflower Oil 1L", "old_price": "155.00", "new_price": "160.00" } ], "old_total": "412.00", "new_total": "417.00" } }`

### POST /orders/{id}/cancel
Auth: customer Bearer (before confirmation only) **or** owner Bearer (any time before delivery). Request: `{ "reason": "Changed my mind" }` (optional). Cancelling a confirmed order restores stock in a transaction. Response `200`: `{ "order": "<Order, status=cancelled>" }`. `409 INVALID_TRANSITION` after delivery.

### GET /orders/{id}
Auth: customer Bearer (own orders only; `403`/`404` otherwise). Response `200`:
```json
{ "order": "<Order>", "timeline": [ { "from_status": "awaiting_confirmation", "to_status": "confirmed", "actor": "customer", "note": null, "created_at": "..." } ] }
```

### GET /owner/orders?status=&q=
Auth: owner. `status` optional filter (any `OrderStatus`); `q` matches order number or masked phone. Response `200`:
```json
{ "items": [ { "id": 42, "order_no": 1042, "status": "confirmed", "customer_phone_masked": "98****3210", "item_count": 4, "total": "272.00", "payment_method": "cod", "payment_status": "cod", "requested_delivery_text": "kal subah tak", "requested_delivery_at": "2026-10-03T02:30:00Z", "has_problem": false, "created_at": "...", "updated_at": "..." } ] }
```
Frontend polls every 3 seconds.

### GET /owner/orders/{id}
Auth: owner (other shop's order -> `403`/`404`). Response `200`:
```json
{ "order": "<Order>", "customer": { "phone_masked": "98****3210" }, "messages": [ "<Message> (customer messages for this order)" ], "timeline": [ "<status event>" ], "agent_runs": [ "<AgentRun>" ] }
```

### POST /owner/orders/{id}/status
Auth: owner. Request: `{ "to": "packing", "note": null }`. Allowed: `confirmed->packing`, `packing->out_for_delivery`, `out_for_delivery->delivered`, any pre-delivery -> `cancelled` (with `note` as reason). Writes an `order_status_events` row and a system message in the customer chat. Response `200`: `{ "order": "<Order>" }`. `409 INVALID_TRANSITION` otherwise.

### GET /owner/orders/{id}/delivery-note
Auth: owner. Response `200`:
```json
{ "order_no": 1042, "shop_name": "Sharma Kirana", "customer_phone": "9876543210", "delivery_address_text": "Flat 12, Karve Nagar", "delivery_lat": 18.5, "delivery_lng": 73.81, "requested_delivery_text": "kal subah tak", "items": [ { "name": "Atta (Loose)", "qty": "2.000", "unit": "kg", "line_total": "90.00" } ], "total": "272.00", "payment_method": "cod", "created_at": "..." }
```

---

## 7. Stage 5 — Smart conversation (PLANNED)

### POST /orders/{id}/approve-price-change
Auth: customer Bearer. Re-quotes at current prices and clears `requires_reapproval`. Response `200`: `{ "order": "<Order>", "bill": "<bill>" }`. `409 INVALID_TRANSITION` if nothing is pending.

### POST /orders/{id}/substitutions/{item_id}/accept
Auth: session. `item_id` = the out-of-stock item. Request: `{ "substitute_product_id": 20 }` (must be one of the suggested substitutes, max 3). Creates a `substituted` item linked by `parent_item_id`. Response `200`: `{ "order": "<Order>" }`.

### POST /orders/{id}/amendments/confirm
Auth: customer Bearer. Confirms `pending_amendment` items on a `confirmed`/`packing` order; deducts stock only for those items, in a transaction. Response `200`: `{ "order": "<Order>", "delta": { "added_total": "48.00", "new_total": "320.00" } }`. Errors: `409 AMENDMENT_NOT_ALLOWED` (`out_for_delivery` or later), `409 STOCK_CHANGED`.

### GET /customer/history
Auth: customer. Response `200`:
```json
{ "orders": [ { "id": 40, "order_no": 1040, "status": "delivered", "total": "412.00", "created_at": "...", "items": [ { "product_id": 14, "name": "Fortune Sunflower Oil 1L", "qty": "1.000" } ] } ], "frequent_products": [ { "product_id": 14, "name": "Fortune Sunflower Oil 1L", "times_bought": 3 } ] }
```
Orders limited to the last 5; frequent products to the top 10.

---

## 8. Stage 6 — Voice, handwritten list, bill explanation (PLANNED)

### POST /conversations/{id}/messages/audio
Auth: session. `multipart/form-data`, field `file` (audio/*, <= 5 MB, <= 60 s). Runs STT agent then the normal orchestrator. Response `200`: same shape as `POST /conversations/{id}/messages`; the customer message has `type:"audio"`, `meta: { "transcript": "...", "stt_provider": "sarvam", "detected_lang": "mr" }`. Errors: `400 FILE_TYPE_NOT_ALLOWED`, `413 FILE_TOO_LARGE`, `422` empty audio (`"Kuch sunai nahi diya"`), `502 LLM_FAILED`.

### POST /conversations/{id}/messages/image
Auth: session. `multipart/form-data`, field `file` (jpg/png/webp, <= 8 MB). Stores in `hod/lists`, runs the OCR agent, then the orchestrator. Response `200`: same shape as messages; customer message has `type:"image"`, `media_url`, `meta: { "ocr_lines": ["atta 2 kg", "..."] }`. Illegible: bot message asks for a clearer photo, no order change.

### POST /orders/{id}/explain-bill
Auth: session. Response `200`: `{ "explanation": "2 kilo atta ka 90 rupaye...", "language": "hinglish", "cached": false }`. Every rupee amount in the text is verified against the bill JSON; fallback is a template.

---

## 9. Stage 7 — Payments, fulfilment, analytics (PLANNED)

### GET /orders/{id}/upi-qr
Auth: customer Bearer (own order). Response `200`: `image/png` (QR of `upi://pay?pa={vpa}&pn={shop}&am={total}&cu=INR&tn=Order%20{no}`). Header `X-UPI-Link` carries the deep link. `400 NO_UPI_VPA`. UI label: "Payment confirmation is manual in demo".

### POST /owner/orders/{id}/mark-paid
Auth: owner. Response `200`: `{ "order": "<Order, payment_status=paid>", "payment": { "id": 5, "method": "upi", "amount": "272.00", "status": "paid", "created_at": "..." } }`. Posts "Payment received" to the chat.

### PATCH /owner/orders/{id}/items/{item_id}/packed
Auth: owner. Request: `{ "packed": true }`. Response `200`: `{ "item_id": 71, "packed": true, "packed_count": 2, "total_count": 4 }`.

### POST /orders/{id}/razorpay-link  (optional)
Auth: customer Bearer. Response `200`: `{ "payment_link_url": "https://rzp.io/i/...", "status": "pending" }`.

### POST /webhooks/razorpay  (optional)
Auth: `X-Razorpay-Signature` header verified with `RAZORPAY_WEBHOOK_SECRET`. Response `200`: `{ "status": "ok" }`. Bad signature: `401`.

### GET /owner/analytics/summary?range=7d
Auth: owner. `range` = `today` | `7d`. Counts **confirmed and later** orders only. Response `200`:
```json
{ "revenue_today": "1240.00", "orders_today": 6, "avg_order_value": "206.67", "pending_orders": 2, "revenue_by_day": [ { "date": "2026-09-26", "revenue": "980.00", "orders": 5 } ], "top_items": [ { "product_id": 3, "name": "Atta (Loose)", "qty": "14.000", "revenue": "630.00" } ] }
```

### GET /owner/analytics/low-stock
Auth: owner. Response `200`: `{ "items": [ { "product_id": 30, "name": "Maggi Noodles 70g", "stock_qty": "3.000", "low_stock_threshold": "5.000" } ] }`

### GET /owner/analytics/demand-gaps
Auth: owner. Response `200`: `{ "items": [ { "name_guess": "oats", "count": 3, "last_asked_at": "..." } ] }`

### POST /owner/analytics/restock-suggestion  (optional)
Auth: owner. Response `200`: `{ "suggestions": [ "Restock Maggi Noodles 70g: 3 left, threshold 5" ] }`. Numbers come from the data, not the LLM.

### GET /conversations/{id}/agent-runs?message_id=
Auth: session. Response `200`: `{ "runs": [ "<AgentRun>" ] }`.

### GET /owner/orders/{id}/agent-runs
Auth: owner. Response `200`: `{ "runs": [ "<AgentRun>" ] }`.

---

## 10. Stage 8 — Optional (PLANNED)

### POST /owner/orders/{id}/returns
Auth: owner. Request: `{ "order_item_id": 71, "qty": "1.000", "reason": "Packet torn" }`. Rule: `qty <= delivered qty - already returned`. Refund = `qty x unit_price_snapshot`; stock restored in a transaction; payout is **DEMO / MOCK** (recorded only). Response `201`:
```json
{ "return": { "id": 1, "order_item_id": 71, "qty": "1.000", "reason": "Packet torn", "refund_amount": "45.00", "status": "refunded", "refund_note": "Cash refund (recorded, mock)" } }
```

---

## 11. Out of scope
Khata / udhaar / credit: **no endpoints, tables or UI.** Real WhatsApp Business API: deferred.

## 12. Change log
- 2026-10-02: Initial contract (Stage 0). `/health` LIVE; all other Appendix D endpoints specified as PLANNED.
