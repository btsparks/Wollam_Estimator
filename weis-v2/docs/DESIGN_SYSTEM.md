# Wollam Design System — Estimating Intelligence

> Adapted from the Wollam Safety Dashboard reskin spec. This document defines the visual design system for all Wollam Construction internal tools, applied here to the estimating platform.

## Brand Identity

### Logo
- **Source:** `https://wollamconstruction.com/wp-content/uploads/2017/12/Wollam_Construction_Logo-x3.png`
- **Mark:** Geometric angular "W" — two shades of navy creating a dimensional, faceted look
- **Dashboard usage:** W icon in sidebar header (32px collapsed, 28px expanded), white on navy

### Brand Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `--wollam-navy` | Primary Navy | `#00347E` | Sidebar, primary buttons, active states |
| `--wollam-navy-dark` | Deep Navy | `#002E7A` | Hover states on navy elements |
| `--wollam-navy-light` | Light Navy | `#1A4E9E` | Secondary interactive, focus rings |
| `--wollam-gold` | Accent Gold | `#FCB900` | Highlights, active nav indicator, special badges |
| `--wollam-gold-dark` | Dark Gold | `#D9A000` | Gold hover states |
| `--wollam-black` | Brand Black | `#1C1C1C` | Headings, hero text |

### Design Philosophy
This is Wollam's tool. It should feel like a $50K custom build, not a template.

1. **Brand-forward**: Navy sidebar, gold accents, Wollam logo prominent
2. **Data-dense but clean**: Show information through smart hierarchy, not by removing it
3. **Industrial strength**: Bold typography, strong contrast, no flimsy pastels
4. **Modern sophistication**: Subtle glass effects, smooth transitions, purposeful rounded corners

---

## Color System — Light Theme

```css
:root {
    /* Brand */
    --wollam-navy: #00347E;
    --wollam-navy-dark: #002E7A;
    --wollam-navy-light: #1A4E9E;
    --wollam-navy-faint: rgba(0, 52, 126, 0.06);
    --wollam-gold: #FCB900;
    --wollam-gold-dark: #D9A000;
    --wollam-gold-faint: rgba(252, 185, 0, 0.10);

    /* Surfaces */
    --bg-base: #F8FAFC;
    --bg-surface: #FFFFFF;
    --bg-elevated: #FFFFFF;
    --bg-hover: #F1F5F9;
    --bg-selected: rgba(0, 52, 126, 0.08);

    /* Sidebar */
    --sidebar-bg: #00347E;
    --sidebar-bg-hover: rgba(255, 255, 255, 0.08);
    --sidebar-bg-active: rgba(255, 255, 255, 0.15);
    --sidebar-text: rgba(255, 255, 255, 0.7);
    --sidebar-text-active: #FFFFFF;
    --sidebar-border: rgba(255, 255, 255, 0.10);
    --sidebar-accent: #FCB900;

    /* Borders */
    --border-default: #E2E8F0;
    --border-strong: #CBD5E1;
    --border-focus: #00347E;

    /* Text */
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-tertiary: #94A3B8;
    --text-disabled: #CBD5E1;

    /* Interactive */
    --interactive: #00347E;
    --interactive-hover: #002E7A;
    --interactive-light: #EFF6FF;

    /* Confidence Colors (estimating-specific) */
    --confidence-high: #16A34A;
    --confidence-high-bg: #F0FDF4;
    --confidence-moderate: #D97706;
    --confidence-moderate-bg: #FFFBEB;
    --confidence-low: #DC2626;
    --confidence-low-bg: #FEF2F2;
    --confidence-none: #94A3B8;
    --confidence-none-bg: #F1F5F9;

    /* Status (info, success, warning, danger) */
    --status-success: #16A34A;
    --status-warning: #D97706;
    --status-danger: #DC2626;
    --status-info: #2563EB;
    --status-success-bg: #F0FDF4;
    --status-warning-bg: #FFFBEB;
    --status-danger-bg: #FEF2F2;
    --status-info-bg: #EFF6FF;

    /* Shadows */
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
    --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06);
    --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.05), 0 4px 6px rgba(0, 0, 0, 0.05);

    /* Radius */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-full: 9999px;
}
```

---

## Typography

### Font Stack
```css
font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```

### Type Scale

| Element | Size | Weight | Color | Extra |
|---------|------|--------|-------|-------|
| Page title | 18px | 700 | `--text-primary` | `letter-spacing: -0.02em` |
| Section header | 15px | 600 | `--text-primary` | `letter-spacing: -0.01em` |
| KPI value (hero) | 32-36px | 800 | `--text-primary` | `tabular-nums`, `letter-spacing: -0.03em` |
| KPI label | 12px | 600 | `--text-secondary` | `uppercase`, `letter-spacing: 0.05em` |
| Card title | 14px | 600 | `--text-primary` | |
| Table header | 11px | 700 | `--text-secondary` | `uppercase`, `letter-spacing: 0.06em` |
| Table body | 13px | 400 | `--text-primary` | |
| Body text | 14px | 400 | `--text-secondary` | `line-height: 1.6` |
| Badge text | 11px | 600 | Confidence color | |

### Number Formatting
- All numbers: `font-variant-numeric: tabular-nums;`
- Thousands separator: `1,284` not `1284`
- MH/unit: 2-4 decimal places as appropriate (0.28, 0.0415)
- Dollar amounts: `$1,234` (no cents for estimates)
- Percentages: `82.4%` (one decimal)
- Right-align all numeric columns

---

## Layout

### Overall Structure
```
┌─────────────────────────────────────────────────────────┐
│  HEADER BAR (56px) — logo + page title + actions         │
├────────┬────────────────────────────────────────────────┤
│        │                                                │
│  SIDE  │  CONTENT AREA (scrollable)                     │
│  BAR   │                                                │
│        │  Page-specific content                         │
│  240px │  (Interview or Chat)                           │
│  navy  │                                                │
│        │                                                │
└────────┴────────────────────────────────────────────────┘
```

### Navy Sidebar (240px / 64px collapsed)
- Background: `--sidebar-bg` (#00347E)
- Logo at top, white on navy
- Nav items: icon + label, semi-transparent white text
- Active item: white text, gold left accent bar (3px), `--sidebar-bg-active` background
- Section labels: 10px, uppercase, dim white (35% opacity)
- Collapsed at <900px: 64px wide, icon-only

### Header (56px)
- Background: `--bg-surface`
- Border bottom: `--border-default`
- Subtle shadow for elevation
- Left: sidebar toggle + page title
- Right: user info / settings

---

## Components

### Cards
```css
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);   /* 12px */
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s;
}
.card:hover {
    box-shadow: var(--shadow-md);
}
```

### Confidence Badges
These are critical for the estimating UI. Every rate display must show confidence.

```css
.badge-high     { background: var(--confidence-high-bg);     color: var(--confidence-high); }
.badge-moderate { background: var(--confidence-moderate-bg);  color: var(--confidence-moderate); }
.badge-low      { background: var(--confidence-low-bg);       color: var(--confidence-low); }
.badge-none     { background: var(--confidence-none-bg);      color: var(--confidence-none); }
```

Display format: `HIGH · 47 timecards` or `LOW · 2 timecards`

### Buttons
- **Primary**: Navy background, white text, navy shadow
- **Secondary**: White background, navy border, navy text
- **Gold accent**: Gold background, black text (for special CTAs)
- Press effect: `transform: scale(0.98)` on `:active`

### Data Tables
- Sticky header with 2px bottom border
- 11px uppercase header text
- 13px body text
- Hover: `--bg-hover` background
- Numeric columns: right-aligned, `tabular-nums`
- Sortable columns: cursor pointer, navy color when sorted

### Form Inputs (for Interview)
- Background: `--bg-base`
- Border: `--border-default`
- Focus: navy border + faint navy shadow ring
- Textarea: min-height 80px, auto-grow
- Labels: 12px, 600 weight, `--text-secondary`

### Chat Messages
- **User message**: Right-aligned, navy background, white text, rounded (16px top, 4px bottom-right)
- **AI message**: Left-aligned, white card with border, full width
- **Source citation bar**: Bottom of AI message, collapsible, shows job/code/confidence badges
- **Loading**: Shimmer skeleton animation in message shape

---

## Micro-Interactions

### Card Entrance (staggered)
```css
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}
.card-animate { animation: fadeInUp 0.4s ease-out forwards; opacity: 0; }
.card-animate:nth-child(1) { animation-delay: 0s; }
.card-animate:nth-child(2) { animation-delay: 0.05s; }
/* etc. */
```

### Skeleton Loading
```css
.skeleton {
    background: linear-gradient(90deg, var(--bg-hover) 25%, var(--bg-surface) 50%, var(--bg-hover) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite ease-in-out;
    border-radius: var(--radius-sm);
}
```

### Auto-save Indicator (for Interview)
When PM context auto-saves:
- Small "Saved" text appears next to the field, fades out after 2 seconds
- Green checkmark appears next to cost code in the sidebar list
- No modal, no toast — subtle and non-disruptive

---

## Responsive Strategy

| Breakpoint | Sidebar | Content |
|-----------|---------|---------|
| Desktop (>1200px) | 240px expanded | Full layout |
| Tablet (901-1200px) | 240px expanded | Narrower content |
| Small tablet (769-900px) | 64px collapsed | Full-width content |
| Mobile (<768px) | Hidden + hamburger | Single column |

---

## Estimating-Specific Design Patterns

### Rate Display Card
For showing a historical rate with all its context:
```
┌────────────────────────────────────────────┐
│ 📊 Wall Forming (C_F/S Walls)              │
│ Cost Code: 2215 · Job 8553                 │
├────────────────────────────────────────────┤
│                                            │
│  0.28 MH/SF                               │
│  ████████████████████░░░░  HIGH            │
│                                            │
│  Crew: 8.2 avg/day                         │
│  Production: 643 SF/day avg                │
│  Data: 47 timecards · 23 days             │
│                                            │
│  PM Notes: One-sided pours against         │
│  excavation, EFCO forms, 20-30' walls     │
└────────────────────────────────────────────┘
```

### Job Card (for Interview list)
```
┌────────────────────────────────────────────┐
│ Job 8553                  ● Complete       │
│ RTK SPD Pump Station                       │
│                                            │
│ 87 cost codes · 62 with data              │
│ ████████████████████░░░░  85% richness    │
│                                            │
│ Context: 15 of 62 codes (24%)             │
│ ████░░░░░░░░░░░░░░░░░░░░                  │
└────────────────────────────────────────────┘
```

### Chat Source Citation
```
┌─ Sources ──────────────────────────────────┐
│ [8553 · 2215 · HIGH] [8553 · 2220 · MOD]  │
│ [8576 · 2215 · LOW]                        │
└────────────────────────────────────────────┘
```
Each badge is clickable — expands to show the full rate data.
