# DESIGN.md — Neo-Brutalism x Claymorphism (Trizpyy-style)

> Agents: follow this file for ALL UI. Substance > polish: reuse the same few components everywhere. No new colors, shadows or fonts outside this file.

## 1. Visual theme
Playful, chunky, friendly. **Neo-brutalism** gives structure (thick dark outlines, hard offset shadows, bold type). **Claymorphism** gives softness (pastel fills, huge radii, soft inner highlights, puffy inputs/chips). Cream paper background with a faint dot grid. Sticker-like badges, slightly rotated. Lots of whitespace, big headlines, one idea per card.

## 2. Colors (approximate, sampled from screenshots)
| Token | Hex | Use |
|---|---|---|
| `cream` | `#F5F1E8` | page background (+ dot grid) |
| `ink` | `#17151F` | text, borders, primary buttons, hard shadows |
| `paper` | `#FFFFFF` | cards, inputs, chips |
| `lavender` | `#C3B1F5` | hero/featured cards, AI insight box |
| `lavender-deep` | `#6E56D9` | purple offset shadow on dark buttons, links |
| `butter` | `#F9D56E` | active tab, match badge, FAB, highlights |
| `mint` | `#B9E4A1` | selected chip, positive/success, "sale" |
| `sky` | `#A8CCF4` | info cards, weather/neutral stats |
| `coral` | `#F2A58B` | NEW badge, warning tiles, "udhaar" |
| `cream-yellow` | `#FDF1D0` | promo/notice banner |
| `danger` | `#D64545` | at-risk text/border (+ `#FDECEC` fill) |
| `muted` | `#5A5870` | secondary text |

Rule: **one pastel per card**, ink for everything structural. Never gradients except soft radial "sun/glow" blobs behind cards (optional).

## 3. Typography
- **Display (headings, numbers):** heavy geometric grotesk, weight 800, tight letter-spacing (-0.02em). Google Font: `Bricolage Grotesque` or `Syne` (800).
- **Body/UI:** `Outfit` (or `Poppins`), weights 400/500/600.
- **Mono (codes, ids):** `JetBrains Mono` in a small white chip.
- Scale: hero 56-72px / h1 40px / h2 28px / h3 20px / body 16px / small 13px.
- Eyebrow labels: 12px, uppercase, tracking-widest, `muted` (e.g. "RECOMMENDED").
- Hero emphasis: yellow marker swipe behind a key phrase (`bg-butter` strip at ~40% height under the text).

## 4. Shape, borders, shadows
- Border: **3px solid `ink`** on cards/buttons/featured items. Chips and inputs use **no border** (clay soft shadow) unless selected.
- Radius: cards `28px`, buttons/chips/tabs `9999px`, inputs `20px`.
- **Hard shadow (brutal):** `6px 6px 0 0 #17151F` for cards; `0 4px 0 0 #17151F` (or purple `#6E56D9`) for buttons. Pressed state: translate(2px,2px) + shadow shrinks.
- **Clay soft shadow:** `0 6px 14px rgba(23,21,31,0.10), inset 0 2px 0 rgba(255,255,255,0.8)` for chips/inputs/nav.
- Background dot grid: `radial-gradient(#17151F14 1px, transparent 1px)` size 22px.

## 5. Components
**Primary button:** `ink` bg, white text, pill, 600 weight, icon (arrow) left, purple hard shadow `0 4px 0 #6E56D9`.
**Secondary button:** white bg, 3px ink border, ink text, ink hard shadow `0 4px 0 ink`.
**Nav:** floating white pill (clay shadow), items with icon + label; active item = `ink` pill with white text. Right side: icon button (white circle), outline "Log out", avatar circle (`sky`).
**Segmented tabs / role switch:** white pill container with ink border; active = `butter` pill with ink border + hard shadow.
**Chips (filters / suggestions):** white pill, clay shadow, 14px text, optional sparkle icon for AI suggestions. Selected = `mint` bg + 3px ink border + hard shadow + check icon.
**Search / text input:** big white pill/rounded-xl, clay shadow (search bar gets 3px ink border + hard shadow), icon left, muted placeholder with example text.
**Card (default):** white, 3px ink border, 28px radius, 6px hard shadow, 24px padding.
**Feature card:** same but pastel fill (`lavender`/`mint`/`sky`/`coral`), small white pill label on top (e.g. "60 seconds"), bold title, one-line subtitle, text link with arrow.
**Badges:** pill, 12-13px, 700. `NEW` = coral fill white text. Match/score = `butter` fill + 2px ink border. Status "At risk" = `danger` text on `#FDECEC`. Rows at risk: 3px `danger` border + strikethrough title.
**Stickers:** starburst shape (`butter` or `sky`), bold uppercase text ("ZAP!", "RAIN!"), rotate -8 to 8deg, ink outline, placed overlapping card corners. Use max 1-2 per screen.
**Notice banner:** `cream-yellow` bg, 28px radius, no border, tag icon, bold text, mono code chip, muted right-aligned note.
**List row:** white rounded-2xl, 56px icon tile (pastel, rounded-xl) + time/eyebrow + title; no border unless state.
**Floating action button:** bottom-right, 64px circle, `butter` fill, 3px ink border, hard shadow, icon centered, tiny green status dot top-right.
**Illustrations:** flat cartoon style with outlines and soft shapes (suitcase with face, car, plane). Optional; use emoji/SVG icons if no time.

## 6. Layout
- Max width 1200px, centered; 24px page padding; 8px spacing grid.
- Sections: eyebrow -> big heading -> content. Generous vertical rhythm (48-64px).
- Hero: 2 columns (text left, one hero card right). Auth: 50/50 split, left `lavender` panel with headline + illustration, right cream form.
- Grids: 3-column cards on desktop, 1 on mobile. Cards equal height.

## 7. Motion (keep minimal)
Buttons/cards: hover = translate(-2px,-2px) and shadow grows 2px; active = translate(2px,2px), shadow shrinks. 150ms ease-out. No other animations required.

## 8. Do / Don't
**Do:** thick ink borders, hard offset shadows, pastel fills, huge radii, bold headings, 1 accent per card, plenty of whitespace.
**Don't:** gradients, thin 1px borders on cards, glassmorphism/blur, dark mode, more than 5 pastels on one screen, tiny light-gray text, mixed shadow styles on the same component.

## 9. Dashboard mapping (for the hackathon app)
- **KPI tiles:** 4 feature cards, one pastel each: Sales today = `mint`, Udhaar baaki = `coral`, Low stock = `butter`, Transactions = `sky`. Big number (display font) + small label.
- **Charts (Recharts):** inside white cards with ink border; bars/lines use pastel fills with 2px ink stroke; no gridlines except faint dashed; labels in Outfit.
- **AI insight box:** `lavender` feature card with sparkle icon and 2-3 line text.
- **Mic button (voice capture):** large `butter` circle FAB-style, ink border + hard shadow; pulsing ring while recording.
- **Confirm card:** white card, editable table rows, primary "Approve" + secondary "Discard" buttons.
- **Udhaar ledger:** list rows; overdue/high-risk = "At risk" badge + `danger` border.
- **Suggested sentences:** sparkle chips under the mic.

## 10. Tailwind tokens (paste into tailwind.config)
```ts
theme: {
  extend: {
    colors: {
      cream: "#F5F1E8", ink: "#17151F", lavender: "#C3B1F5", "lavender-deep": "#6E56D9",
      butter: "#F9D56E", mint: "#B9E4A1", sky: "#A8CCF4", coral: "#F2A58B",
      "cream-yellow": "#FDF1D0", danger: "#D64545", muted: "#5A5870",
    },
    borderRadius: { card: "28px", input: "20px" },
    boxShadow: {
      brutal: "6px 6px 0 0 #17151F",
      "brutal-sm": "0 4px 0 0 #17151F",
      "brutal-purple": "0 4px 0 0 #6E56D9",
      clay: "0 6px 14px rgba(23,21,31,0.10), inset 0 2px 0 rgba(255,255,255,0.8)",
    },
    fontFamily: { display: ["Bricolage Grotesque", "sans-serif"], sans: ["Outfit", "sans-serif"], mono: ["JetBrains Mono", "monospace"] },
  },
}
```
Reusable classes (put in `globals.css`):
```css
body { background-color:#F5F1E8; background-image:radial-gradient(#17151F14 1px,transparent 1px); background-size:22px 22px; font-family:Outfit,sans-serif; color:#17151F; }
.card { @apply bg-white border-[3px] border-ink rounded-card shadow-brutal p-6; }
.btn-primary { @apply bg-ink text-white rounded-full px-6 py-3 font-semibold shadow-brutal-purple transition active:translate-y-[2px]; }
.btn-secondary { @apply bg-white text-ink border-[3px] border-ink rounded-full px-6 py-3 font-semibold shadow-brutal-sm transition active:translate-y-[2px]; }
.chip { @apply bg-white rounded-full px-4 py-2 text-sm shadow-clay; }
.chip-active { @apply bg-mint border-[3px] border-ink shadow-brutal-sm; }
.badge { @apply rounded-full px-3 py-1 text-xs font-bold; }
```