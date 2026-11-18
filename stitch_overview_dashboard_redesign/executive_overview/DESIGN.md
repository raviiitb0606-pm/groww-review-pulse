---
name: Executive Overview
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#4a4455'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#7b7486'
  outline-variant: '#ccc3d7'
  surface-tint: '#7331df'
  primary: '#5300b7'
  on-primary: '#ffffff'
  primary-container: '#6d28d9'
  on-primary-container: '#dac5ff'
  inverse-primary: '#d3bbff'
  secondary: '#5b598c'
  on-secondary: '#ffffff'
  secondary-container: '#c7c3fe'
  on-secondary-container: '#514f81'
  tertiary: '#004b31'
  on-tertiary: '#ffffff'
  tertiary-container: '#006544'
  on-tertiary-container: '#58e7ab'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ebddff'
  primary-fixed-dim: '#d3bbff'
  on-primary-fixed: '#250059'
  on-primary-fixed-variant: '#5b00c5'
  secondary-fixed: '#e3dfff'
  secondary-fixed-dim: '#c4c1fb'
  on-secondary-fixed: '#181445'
  on-secondary-fixed-variant: '#444173'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.025em
  display-lg-mobile:
    fontFamily: Manrope
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-xl:
    fontFamily: Manrope
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Manrope
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  title-md:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  metric-xl:
    fontFamily: Manrope
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.03em
  metric-md:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  margin: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system establishes an executive intelligence surface: calm, authoritative, and profoundly discerning. It is engineered for leadership teams, founders, and product directors who must distill high-velocity customer feedback, sentiment trends, and granular category friction into confident operational decisions.

The design philosophy combines **Modern Executive Minimalism** with subtle **Tonal Tactility**:
- **Clarity over Clutter:** High data density balanced by generous white space and deliberate typographic cadence.
- **Calm Authority:** Eliminates visual noise, harsh container borders, and neon saturation in favor of a warm, paper-like foundation with hyper-refined semantic indicators.
- **Editorial Data Architecture:** Metrics, customer quotes, and qualitative breakdowns are presented with editorial elegance, turning unstructured sentiment into strategic clarity.

## Colors

The palette rests upon an organic canvas that reduces eye strain while elevating content depth:
- **Canvas Base (`#FAFAF7`):** Warm off-white, imparting an executive editorial substrate that separates the surface from clinical enterprise software.
- **Card & Surface (`#FFFFFF`):** Crisp pure white applied to elevated modules to achieve separation purely through ambient luminance.
- **Primary Brand Arc:**
  - Rich Violet (`#6D28D9`): Primary interactive anchors, key filtering triggers, and aggregated insight highlights.
  - Deep Indigo (`#1E1B4B`): Structural headlines, executive summaries, and prominent numeric data.
- **Sentiment & System Feedback:**
  - Positive / Delight: Mint Emerald (`#10B981`) for upward sentiment velocity, positive ratings, and resolved friction.
  - Negative / Friction: Rose (`#E11D48`) for critical issues, dropping satisfaction scores, and urgent churn indicators.
  - Alert / Neutral: Amber (`#F59E0B`) for plateauing sentiment, anomalies, and watchlist categories.
- **Domain Thematic Palette:** Used strictly for categorical tag pills, multi-line trend charts, and topic clustering:
  - App Updates & Product Velocity: `#7C3AED` (Violet)
  - Customer Support & Operations: `#F97362` (Coral)
  - Ease of Use & Portfolio/Funds: `#14B8A6` (Teal)
  - Trading Execution & Markets: `#0EA5E9` (Sky Blue)
  - Charges, Fees & Brokerage: `#F59E0B` (Amber)
  - General / Cross-functional: `#64748B` (Slate Grey)

## Typography

The typographical framework pairs **Manrope** for primary titles, section landmarks, and big-number telemetry with **Inter** for dense analytical tables, review copy, and administrative labels:
- **Numerical Hierarchy:** Data metrics (`metric-xl`, `metric-md`) use tabular numeric lining figures via Manrope to ensure proportional vertical scanning across comparative review buckets.
- **Review Excerpts:** Body text for long-form user feedback employs `body-md` with `lineHeight: 20px`, optimized for scan speed and legibility under continuous review sessions.
- **Meta & Chips:** Domain tags and status indicators use uppercase/small-caps formatting via `label-sm` with widened tracking (`0.04em`) to maintain legibility when paired with categorical pastel backgrounds.

## Layout & Spacing

The architecture operates on an adaptive 12-column layout governed by strict mathematical rhythm:
- **Canvas Margins:** 
  - Desktop (>1200px): `2rem` (32px) margins with a 12-column grid and `1.5rem` (24px) gutters. Maximum content canvas bounded at 1440px to retain executive focal length.
  - Tablet (768px - 1199px): `1.5rem` (24px) margins with an 8-column layout. Metric modules transition to 2x2 cards.
  - Mobile (<768px): `1rem` (16px) margins with a 4-column layout. High-level metric bars convert to horizontally scrolling carousels.
- **Rhythm & Enclosure:** Internal card padding standardizes on `space-lg` (24px) for parent analytics cards and `space-md` (16px) for nested feedback item modules. Element grouping inside cards maintains a compact `space-xs` (4px) to `space-sm` (8px) distance.

## Elevation & Depth

Visual hierarchy is maintained without structural outlines or rigid box lines. Cards merge seamlessly with the canvas through pure-white illumination and ultra-diffused atmospheric shadows:

- **Surface Tiers:**
  - **Base Canvas:** Flat `#FAFAF7`.
  - **Standard Card Deck:** `#FFFFFF` resting at Elevation 1. Shadow properties: `0 4px 20px -2px rgba(30, 27, 75, 0.04), 0 2px 6px -1px rgba(30, 27, 75, 0.02)`. The faint indigo tint prevents the shadow from looking dirty or muddy.
  - **Interactive Hover / Focused Review:** Elevated to Elevation 2: `0 12px 32px -4px rgba(30, 27, 75, 0.07), 0 4px 12px -2px rgba(30, 27, 75, 0.03)`. Micro-lift translation of `-1px` on hover.
  - **Dropdown Flyouts & Overlays:** Elevation 3: `0 20px 48px -8px rgba(30, 27, 75, 0.12), 0 8px 16px -4px rgba(30, 27, 75, 0.04)`.
- **Zero-Border Directive:** Outer borders on review cards are explicitly absent (`border: none`). Boundaries are perceived through contrast between `#FAFAF7` and `#FFFFFF`. Hairline dividers (`1px solid rgba(100, 116, 139, 0.08)`) are reserved strictly for horizontal splits within data tables.

## Shapes

The design system implements balanced rounded corners:
- **Card Enclosures:** Standard cards and overview dashboards use `1rem` (16px) corner radiuses (`rounded-lg`), providing soft, architectural containment without feeling playful.
- **Pills and Indicators:** Categorical feedback badges, sentiment indicators, and status chips leverage a complete pill shape (`9999px`) to visually disassociate metadata from card bodies.
- **Interactive Controls:** Buttons, inputs, and dropdown selectors use `0.5rem` (8px) radiuses (`roundedness: 2`), reflecting precision and enterprise discipline.

## Components

### Buttons
- **Primary:** Background `#6D28D9`, foreground `#FFFFFF`, height 40px, padding `0 1.25rem`. Subtly rounded (8px). On hover: `#5B21B6`. Active: `#4C1D95`.
- **Secondary / Ghost:** Transparent background with `#1E1B4B` text. Hover brings in `rgba(109, 40, 217, 0.05)`.
- **Filter Action:** Compact button (32px height) with light neutral fill `rgba(100, 116, 139, 0.08)` and `#1E1B4B` typography.

### Sentiment & Categorical Chips
- **Structure:** Height 24px, inline-flex, centered text, `label-sm` font, horizontal padding 8px.
- **Sentiment Variations:**
  - Positive: Soft emerald background `rgba(16, 185, 129, 0.12)` with solid emerald `#047857` text and an optional `6px` circular status indicator.
  - Negative: Soft rose background `rgba(225, 29, 72, 0.12)` with `#BE123C` text.
  - Neutral: Soft amber background `rgba(245, 158, 11, 0.12)` with `#B45309` text.
- **Theme Chips:** Colored according to the designated category palettes (e.g., Trading & Markets: `rgba(14, 165, 233, 0.12)` background, `#0369A1` text).

### Review & Feedback Cards
- **Architecture:** Pure white `#FFFFFF` surface, completely borderless, ambient shadow.
- **Internal Layout:** 
  - **Header:** Reviewer credential / platform source, star-rating / CSAT glyph, and relative timestamp.
  - **Body:** Manrope headline for review title (`title-md`) followed by Inter `body-md` review text with soft slate coloration `#334155`.
  - **Footer:** Theme chip, sentiment tag, and immediate action triggers (e.g., "Create Jira Issue", "Mark Investigated").

### Data Metric Cards (KPI Displays)
- Pure white container, padded at 24px (`space-lg`).
- Label positioned at top in `label-md` (`#64748B`), large numeric indicator in `metric-xl` (`#1E1B4B`), followed by a 14-day micro-sparkline or percentage change indicator (in mint emerald or rose).

### Form Controls & Search Filter
- **Global Search:** Full-width input resting on `#FFFFFF` with minimal ambient shadow, no border, 44px height, placeholder color `#94A3B8`. Left-aligned search icon in `#64748B`.
- **Checkboxes & Radios:** Primary accent `#6D28D9` when checked. Unchecked: `1.5px solid #CBD5E1` border on pure white fill.

### List & Feed Items
- Alternating review stream separated by `0.75rem` vertical spacing, avoiding continuous borders. Each review row floats as an independent micro-card or clean indented unit with subtle hover states.