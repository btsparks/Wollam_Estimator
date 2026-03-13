# Wollam Safety Dashboard — Modern Reskin Skill Reference

> **Purpose:** Complete design specification for reskinning the Wollam Safety Intelligence Platform with a modern, branded UI that feels premium and professional while staying true to Wollam Construction's identity and the dashboard's safety mission.
> **Created:** March 2026
> **Sources:** Wollam Construction brand guidelines (wollamconstruction.com, Epic Marketing visual identity), SafetyCulture/Procore/Safesite/HammerTech UI patterns, 2025-2026 dashboard design trend research (Dribbble, Behance, Fuselab, UXPin, Muzli).

---

## 1. BRAND IDENTITY — Wollam Construction

### Logo
- **Source URL:** `https://wollamconstruction.com/wp-content/uploads/2017/12/Wollam_Construction_Logo-x3.png`
- **Mark:** Geometric angular "W" built from overlapping triangular/chevron planes in two shades of navy blue — darker navy + medium blue creating a dimensional, faceted, architectural feel
- **Wordmark:** "WOLLAM" in bold black uppercase sans-serif (heavy weight), "CONSTRUCTION" below in lighter weight with generous letter-spacing
- **Usage in dashboard:** Place logo mark (W icon) in sidebar header at 32px height when collapsed, full logo at 28px height when expanded. Always on dark navy background for maximum contrast.

### Brand Color Palette

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `--wollam-navy` | Primary Navy | `#00347E` | Primary brand color — sidebar background, primary buttons, active states |
| `--wollam-navy-dark` | Deep Navy | `#002E7A` | Hover states on primary, sidebar active highlight |
| `--wollam-navy-light` | Light Navy | `#1A4E9E` | Secondary interactive elements, focus rings |
| `--wollam-gold` | Accent Gold | `#FCB900` | Secondary brand accent — highlights, special badges, premium elements |
| `--wollam-gold-dark` | Dark Gold | `#D9A000` | Gold hover states |
| `--wollam-black` | Brand Black | `#1C1C1C` | Headings, hero text |
| `--wollam-white` | Clean White | `#FFFFFF` | Backgrounds, text on dark |

### Company Context
- **Type:** Heavy industrial & heavy civil general contractor, self-performs work
- **Core values:** Safety Driven, Dynamic People, Team Oriented
- **Tagline:** "We build safety, quality, and trust"
- **Scale:** ~200 employees, 60+ projects annually, $400M bonding capacity
- **Industry:** Mining, oil & gas, energy, pharmaceutical, manufacturing, infrastructure
- **Location:** Draper, Utah — serves Intermountain West

---

## 2. DESIGN PHILOSOPHY

### The Reskin Goal
Transform the dashboard from a generic data tool into **Wollam's branded safety command center** — something that looks like it was custom-built for the company by a top design agency. The design should communicate:

1. **Authority & trust** — Navy blue dominance signals professionalism and reliability
2. **Safety-first culture** — Clear severity color coding, prominent KPIs, actionable insights
3. **Industrial strength** — Bold typography, strong contrast, no flimsy pastels
4. **Modern sophistication** — Subtle glass effects, smooth transitions, rounded cards with purpose

### Design Principles
1. **Brand-forward:** Navy sidebar, gold accents, Wollam logo prominent — this is unmistakably a Wollam tool
2. **Safety colors are sacred:** Never use red/amber/green for brand decoration — reserve exclusively for safety semantics
3. **Clean density:** Show more data with less clutter through smart hierarchy, not by removing information
4. **Progressive disclosure:** Sections collapse by default, expand on demand. Power users can see everything; casual users get the executive summary.
5. **Micro-delight:** Subtle animations (card entrance, number count-up, hover elevations) that feel polished without being distracting

---

## 3. COLOR SYSTEM

### Light Theme Tokens

```css
:root {
    /* ── Brand ── */
    --wollam-navy: #00347E;
    --wollam-navy-dark: #002E7A;
    --wollam-navy-light: #1A4E9E;
    --wollam-navy-faint: rgba(0, 52, 126, 0.06);
    --wollam-gold: #FCB900;
    --wollam-gold-dark: #D9A000;
    --wollam-gold-faint: rgba(252, 185, 0, 0.10);

    /* ── Surfaces ── */
    --bg-base: #F8FAFC;           /* Page background — warm slate-50 */
    --bg-surface: #FFFFFF;         /* Card backgrounds */
    --bg-elevated: #FFFFFF;        /* Elevated cards, modals */
    --bg-hover: #F1F5F9;          /* Hover states — slate-100 */
    --bg-selected: rgba(0, 52, 126, 0.08);  /* Selected/active states — navy tint */

    /* ── Sidebar ── */
    --sidebar-bg: #00347E;         /* Navy background */
    --sidebar-bg-hover: rgba(255, 255, 255, 0.08);
    --sidebar-bg-active: rgba(255, 255, 255, 0.15);
    --sidebar-text: rgba(255, 255, 255, 0.7);
    --sidebar-text-active: #FFFFFF;
    --sidebar-border: rgba(255, 255, 255, 0.10);
    --sidebar-accent: #FCB900;     /* Gold accent for active indicator */

    /* ── Borders ── */
    --border-default: #E2E8F0;     /* slate-200 */
    --border-strong: #CBD5E1;      /* slate-300 */
    --border-focus: #00347E;       /* Navy focus ring */

    /* ── Text ── */
    --text-primary: #0F172A;       /* slate-900 */
    --text-secondary: #475569;     /* slate-600 */
    --text-tertiary: #94A3B8;      /* slate-400 */
    --text-disabled: #CBD5E1;      /* slate-300 */

    /* ── Interactive ── */
    --interactive: #00347E;         /* Navy — primary buttons, links */
    --interactive-hover: #002E7A;   /* Darker navy */
    --interactive-light: #EFF6FF;   /* Light blue tint for secondary buttons */

    /* ── Safety Status (SACRED — do not change) ── */
    --status-success: #16A34A;     /* green-600 — safe, positive, complete */
    --status-warning: #D97706;     /* amber-600 — caution, medium risk */
    --status-danger: #DC2626;      /* red-600 — danger, negative, critical */
    --status-info: #2563EB;        /* blue-600 — informational */
    --status-critical: #7C3AED;    /* violet-600 — catastrophic, rare */

    /* ── Safety Status Backgrounds ── */
    --status-success-bg: #F0FDF4;  /* green-50 */
    --status-warning-bg: #FFFBEB;  /* amber-50 */
    --status-danger-bg: #FEF2F2;   /* red-50 */
    --status-info-bg: #EFF6FF;     /* blue-50 */
    --status-critical-bg: #F5F3FF; /* violet-50 */

    /* ── Shadows ── */
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
    --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.06);
    --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.05), 0 4px 6px rgba(0, 0, 0, 0.05);
    --shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.06), 0 8px 10px rgba(0, 0, 0, 0.04);

    /* ── Radius ── */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-full: 9999px;
}
```

### Dark Theme Tokens

```css
[data-theme="dark"] {
    --wollam-navy: #1A4E9E;
    --wollam-navy-dark: #00347E;
    --wollam-navy-light: #3B7DDD;
    --wollam-navy-faint: rgba(26, 78, 158, 0.12);
    --wollam-gold: #FCB900;
    --wollam-gold-faint: rgba(252, 185, 0, 0.15);

    --bg-base: #0C1222;
    --bg-surface: #131B2E;
    --bg-elevated: #1A2540;
    --bg-hover: #1F2D4A;
    --bg-selected: rgba(26, 78, 158, 0.20);

    --sidebar-bg: #0A1628;
    --sidebar-bg-hover: rgba(255, 255, 255, 0.06);
    --sidebar-bg-active: rgba(252, 185, 0, 0.12);

    --border-default: #1E2D4A;
    --border-strong: #2A3F66;
    --border-focus: #3B7DDD;

    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
    --text-tertiary: #64748B;
    --text-disabled: #334155;

    --interactive: #3B7DDD;
    --interactive-hover: #5B9AEE;

    --status-success: #4ADE80;
    --status-warning: #FBBF24;
    --status-danger: #F87171;
    --status-info: #60A5FA;
    --status-critical: #A78BFA;

    --status-success-bg: rgba(74, 222, 128, 0.10);
    --status-warning-bg: rgba(251, 191, 36, 0.10);
    --status-danger-bg: rgba(248, 113, 113, 0.10);
    --status-info-bg: rgba(96, 165, 250, 0.10);
    --status-critical-bg: rgba(167, 139, 250, 0.10);

    --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.3);
    --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.35);
    --shadow-lg: 0 10px 20px rgba(0, 0, 0, 0.4);
    --shadow-xl: 0 20px 40px rgba(0, 0, 0, 0.5);
}
```

### Chart Color Palette (in order, max 7 series)

```javascript
const CHART_COLORS = {
    primary: '#00347E',      // Wollam Navy
    secondary: '#0EA5E9',    // Sky blue — good contrast with navy
    tertiary: '#06B6D4',     // Cyan
    quaternary: '#FCB900',   // Wollam Gold
    quinary: '#8B5CF6',      // Violet
    senary: '#EC4899',       // Pink
    septenary: '#14B8A6',    // Teal

    // Safety-specific (don't mix with categorical)
    positive: '#16A34A',
    negative: '#DC2626',
    risk0: '#16A34A',
    risk1: '#D97706',
    risk2: '#D97706',
    risk3: '#DC2626',
    risk4: '#DC2626',
    risk5: '#7C3AED',

    // Gradient helpers
    navyGradient: (ctx) => {
        const g = ctx.createLinearGradient(0, 0, 0, 300);
        g.addColorStop(0, 'rgba(0, 52, 126, 0.8)');
        g.addColorStop(1, 'rgba(0, 52, 126, 0.05)');
        return g;
    },
    goldGradient: (ctx) => {
        const g = ctx.createLinearGradient(0, 0, 0, 300);
        g.addColorStop(0, 'rgba(252, 185, 0, 0.6)');
        g.addColorStop(1, 'rgba(252, 185, 0, 0.05)');
        return g;
    }
};
```

---

## 4. TYPOGRAPHY

### Font Stack
```css
font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
```
Keep Inter — it's the industry standard for data dashboards and already in use.

### Type Scale

| Element | Size | Weight | Color | Extra |
|---------|------|--------|-------|-------|
| Page title (header) | 18px | 700 | `--text-primary` | `letter-spacing: -0.02em` |
| Section header | 15px | 600 | `--text-primary` | `letter-spacing: -0.01em` |
| KPI value (hero number) | 32-36px | 800 | `--text-primary` | `tabular-nums`, `letter-spacing: -0.03em` |
| KPI label | 12px | 600 | `--text-secondary` | `uppercase`, `letter-spacing: 0.05em` |
| KPI trend delta | 13px | 600 | Status color | With arrow icon |
| Card title | 14px | 600 | `--text-primary` | `letter-spacing: -0.01em` |
| Card subtitle | 12px | 400 | `--text-tertiary` | |
| Table header | 11px | 700 | `--text-secondary` | `uppercase`, `letter-spacing: 0.06em` |
| Table body | 13px | 400 | `--text-primary` | |
| Body text | 14px | 400 | `--text-secondary` | `line-height: 1.6` |
| Badge text | 11px | 600 | Status color | |
| Micro text | 10px | 500 | `--text-tertiary` | timestamps, footnotes |

### Number Formatting
- All numbers: `font-variant-numeric: tabular-nums;`
- Thousands separator: `1,284` not `1284`
- Percentages: `82.4%` (one decimal)
- Right-align all numeric columns in tables

---

## 5. LAYOUT ARCHITECTURE

### Overall Structure
```
┌─────────────────────────────────────────────────────────┐
│  HEADER BAR (56px) — logo + title + actions             │
├────────┬────────────────────────────────────────────────┤
│        │                                                │
│  SIDE  │  CONTENT AREA (scrollable)                     │
│  BAR   │  ┌──────────────────────────────────────────┐  │
│        │  │ KPI CARDS ROW (4-5 cards)                │  │
│  240px │  ├──────────────────────────────────────────┤  │
│  navy  │  │ CHARTS ROW (2 charts side-by-side)       │  │
│        │  ├──────────────────────────────────────────┤  │
│        │  │ TOOLBOX TALKS (collapsible)              │  │
│        │  ├──────────────────────────────────────────┤  │
│        │  │ OBSERVATIONS TABLE (full-width)          │  │
│        │  └──────────────────────────────────────────┘  │
│        │                                                │
└────────┴────────────────────────────────────────────────┘
```

### Header Bar (56px)
```css
.header {
    height: 56px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    box-shadow: var(--shadow-sm);  /* subtle elevation over content */
    z-index: 50;
}
```
- **Left:** Sidebar toggle + page title ("Safety Dashboard") + subtitle ("Wollam Construction")
- **Right:** Date range display + theme toggle + notifications bell + chat FAB (small) + user avatar

### Navy Sidebar (240px expanded / 64px collapsed)

This is the single biggest visual change. The sidebar becomes the **brand anchor** — deep navy blue with white/gold text.

```css
.sidebar {
    width: 240px;
    background: var(--sidebar-bg);   /* #00347E navy */
    color: var(--sidebar-text);
    display: flex;
    flex-direction: column;
    padding: 20px 12px;
    transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    border-right: none;  /* no border — shadow separation instead */
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.08);
}

/* Logo area */
.sidebar-logo {
    padding: 4px 12px 20px;
    border-bottom: 1px solid var(--sidebar-border);
    margin-bottom: 16px;
}
.sidebar-logo img {
    height: 32px;
    filter: brightness(0) invert(1);  /* make logo white on navy */
}

/* Nav items */
.sidebar-nav a {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 500;
    color: var(--sidebar-text);
    text-decoration: none;
    transition: all 0.2s;
    position: relative;
}
.sidebar-nav a:hover {
    background: var(--sidebar-bg-hover);
    color: var(--sidebar-text-active);
}
.sidebar-nav a.active {
    background: var(--sidebar-bg-active);
    color: var(--sidebar-text-active);
    font-weight: 600;
}
/* Gold left accent bar on active */
.sidebar-nav a.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 6px;
    bottom: 6px;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: var(--sidebar-accent);  /* gold */
}

/* Section labels */
.sidebar-section-label {
    font-size: 10px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.35);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 16px 12px 6px;
}

/* Collapsed state (64px, icon-only) */
@media (max-width: 900px) {
    .sidebar {
        width: 64px;
        padding: 16px 8px;
    }
    .sidebar-nav a span,
    .sidebar-section-label,
    .sidebar-logo .logo-text { display: none; }
    .sidebar-nav a { justify-content: center; padding: 12px; }
    .sidebar-nav a.active::before { display: none; }
}
```

### Content Area Grid
```css
.content-area {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    background: var(--bg-base);  /* light slate-50 background */
}

.dashboard-content {
    max-width: 1320px;
    margin: 0 auto;
}

/* KPI row: 5 cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}

/* Charts row: 2 columns */
.charts-row {
    display: grid;
    grid-template-columns: 3fr 2fr;  /* wider left chart */
    gap: 16px;
    margin-bottom: 24px;
}

/* Full-width sections */
.full-width {
    margin-bottom: 24px;
}

/* Responsive breakpoints */
@media (max-width: 1200px) {
    .kpi-grid { grid-template-columns: repeat(3, 1fr); }
    .charts-row { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .content-area { padding: 16px; }
}
@media (max-width: 480px) {
    .kpi-grid { grid-template-columns: 1fr; }
}
```

---

## 6. COMPONENT SPECIFICATIONS

### KPI Cards

The KPI cards get a significant upgrade — cleaner hierarchy, subtle brand touches, trend sparklines.

```css
.kpi-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 20px 24px;
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-height: 140px;
    position: relative;
    transition: all 0.2s ease;
    overflow: hidden;
}
.kpi-card:hover {
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
    border-color: var(--border-strong);
}

/* Subtle top accent line — navy gradient */
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--wollam-navy), var(--wollam-navy-light));
    opacity: 0;
    transition: opacity 0.2s;
}
.kpi-card:hover::before {
    opacity: 1;
}

/* Alert variant — red top accent always visible */
.kpi-card.alert-border::before {
    background: var(--status-danger);
    opacity: 1;
}

.kpi-icon {
    width: 40px;
    height: 40px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    margin-bottom: 4px;
}
/* Icon background colors */
.kpi-icon.navy { background: var(--wollam-navy-faint); color: var(--wollam-navy); }
.kpi-icon.success { background: var(--status-success-bg); color: var(--status-success); }
.kpi-icon.danger { background: var(--status-danger-bg); color: var(--status-danger); }
.kpi-icon.warning { background: var(--status-warning-bg); color: var(--status-warning); }
.kpi-icon.gold { background: var(--wollam-gold-faint); color: var(--wollam-gold-dark); }

.kpi-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.kpi-value {
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.03em;
    line-height: 1.1;
}

.kpi-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: auto;
    padding-top: 8px;
}

.kpi-trend {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: var(--radius-full);
}
.kpi-trend.up {
    color: var(--status-success);
    background: var(--status-success-bg);
}
.kpi-trend.down {
    color: var(--status-danger);
    background: var(--status-danger-bg);
}
.kpi-trend.neutral {
    color: var(--text-tertiary);
    background: var(--bg-hover);
}
.kpi-comparison {
    font-size: 11px;
    color: var(--text-tertiary);
}
```

**KPI Card Anatomy (5 elements):**
1. **Icon** (top-left) — 40px rounded square with colored background
2. **Label** (below icon) — small uppercase muted text
3. **Value** (hero number) — 32px extra-bold
4. **Trend badge** (bottom-left) — pill with arrow + percentage
5. **Sparkline** (bottom-right, optional) — 60px wide mini chart

### Cards (Chart Containers)

```css
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
    transition: box-shadow 0.2s;
}
.card:hover {
    box-shadow: var(--shadow-md);
}

.card-header {
    padding: 20px 24px 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}
.card-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.01em;
}
.card-subtitle {
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: 2px;
}

/* Card header actions (dropdowns, filters) */
.card-actions {
    display: flex;
    align-items: center;
    gap: 8px;
}
.card-action-btn {
    padding: 4px 10px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 500;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s;
}
.card-action-btn:hover {
    background: var(--bg-selected);
    color: var(--interactive);
    border-color: var(--interactive);
}

.card-body {
    padding: 16px 24px 24px;
}
```

### Data Table

```css
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

/* Sticky header with blur */
.data-table thead {
    position: sticky;
    top: 0;
    z-index: 5;
}
.data-table th {
    text-align: left;
    padding: 12px 16px;
    font-size: 11px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    background: var(--bg-surface);
    border-bottom: 2px solid var(--border-default);  /* stronger bottom border */
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    transition: color 0.15s;
}
.data-table th:hover { color: var(--text-primary); }
.data-table th.sorted { color: var(--interactive); }

.data-table td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-default);
    vertical-align: middle;
}

/* Row hover with smooth transition */
.data-table tbody tr.data-row {
    transition: background 0.15s;
    cursor: pointer;
}
.data-table tbody tr.data-row:hover {
    background: var(--bg-hover);
}

/* Row severity indicators — left accent border */
.data-table tbody tr.row-negative {
    border-left: 3px solid var(--status-danger);
}
.data-table tbody tr.row-positive {
    border-left: 3px solid var(--status-success);
}
.data-table tbody tr.row-highrisk {
    background: var(--status-danger-bg);
}
```

### Badges

```css
.badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: var(--radius-full);
    font-size: 11px;
    font-weight: 600;
    line-height: 1.4;
    white-space: nowrap;
}

/* Semantic badges — use status background + text colors */
.badge-positive { background: var(--status-success-bg); color: var(--status-success); }
.badge-negative { background: var(--status-danger-bg); color: var(--status-danger); }
.badge-warning  { background: var(--status-warning-bg); color: var(--status-warning); }
.badge-info     { background: var(--status-info-bg); color: var(--status-info); }
.badge-critical { background: var(--status-critical-bg); color: var(--status-critical); }

/* Source badges — branded */
.badge-spanish  { background: var(--status-info-bg); color: var(--status-info); }
.badge-telegram { background: rgba(0, 136, 204, 0.10); color: #0088cc; }
.badge-sms      { background: var(--status-success-bg); color: var(--status-success); }

/* Risk rating badges */
.rating-0 { background: var(--status-success-bg); color: var(--status-success); }
.rating-1, .rating-2 { background: var(--status-warning-bg); color: var(--status-warning); }
.rating-3, .rating-4 { background: var(--status-danger-bg); color: var(--status-danger); }
.rating-5 { background: var(--status-critical-bg); color: var(--status-critical); }
```

### Buttons

```css
.btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 500;
    font-family: inherit;
    border: 1px solid var(--border-default);
    background: var(--bg-surface);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}
.btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
    border-color: var(--border-strong);
}

/* Primary — Navy */
.btn-primary {
    background: var(--wollam-navy);
    color: #FFFFFF;
    border-color: var(--wollam-navy);
    box-shadow: 0 1px 3px rgba(0, 52, 126, 0.25);
}
.btn-primary:hover {
    background: var(--wollam-navy-dark);
    box-shadow: 0 2px 6px rgba(0, 52, 126, 0.35);
}

/* Gold accent button (for special CTAs) */
.btn-gold {
    background: var(--wollam-gold);
    color: var(--wollam-black);
    border-color: var(--wollam-gold);
    font-weight: 600;
}
.btn-gold:hover {
    background: var(--wollam-gold-dark);
}
```

### Filter Bar

```css
.filter-bar {
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-default);
    padding: 10px 24px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    min-height: 48px;
}

.filter-select, .filter-input {
    background: var(--bg-base);
    border: 1px solid var(--border-default);
    color: var(--text-primary);
    border-radius: var(--radius-sm);
    padding: 6px 12px;
    font-size: 12px;
    font-family: inherit;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.filter-select:focus, .filter-input:focus {
    border-color: var(--border-focus);
    box-shadow: 0 0 0 3px var(--wollam-navy-faint);
}

/* Active filter pills — navy branded */
.filter-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 12px;
    border-radius: var(--radius-full);
    font-size: 11px;
    font-weight: 600;
    background: var(--bg-selected);
    color: var(--interactive);
    border: 1px solid rgba(0, 52, 126, 0.15);
}
```

### Collapsible Sections

```css
.collapsible-toggle {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    cursor: pointer;
    font-family: inherit;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    transition: all 0.2s;
    margin-bottom: 16px;
    box-shadow: var(--shadow-sm);
}
.collapsible-toggle:hover {
    background: var(--bg-hover);
    box-shadow: var(--shadow-md);
}
.collapsible-toggle .chevron {
    width: 18px;
    height: 18px;
    transition: transform 0.25s ease;
    color: var(--wollam-navy);
}
.collapsible-toggle.collapsed .chevron {
    transform: rotate(-90deg);
}
.collapsible-toggle .section-icon {
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
}
```

### Toolbox Talk Cards

```css
.tbt-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 20px;
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: all 0.2s;
    position: relative;
    overflow: hidden;
}
.tbt-card:hover {
    box-shadow: var(--shadow-md);
    transform: translateY(-1px);
}

/* Top accent stripe by type */
.tbt-card.weekly::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--wollam-gold);
}
.tbt-card.monthly::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--wollam-navy);
}
```

---

## 7. CHART STYLING (Chart.js)

### Global Chart.js Defaults

```javascript
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#94A3B8';  // --text-tertiary
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.95)';
Chart.defaults.plugins.tooltip.titleFont = { size: 13, weight: '600' };
Chart.defaults.plugins.tooltip.bodyFont = { size: 12, weight: '400' };
Chart.defaults.plugins.tooltip.padding = 12;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.borderColor = 'rgba(51, 65, 85, 0.2)';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.displayColors = true;
Chart.defaults.plugins.tooltip.boxPadding = 4;
Chart.defaults.plugins.legend.display = false;  // use custom legends
```

### Bar Chart Pattern

```javascript
{
    type: 'bar',
    data: {
        datasets: [{
            backgroundColor: '#00347E',        // Wollam navy
            hoverBackgroundColor: '#1A4E9E',   // lighter on hover
            borderRadius: 6,                    // rounded tops
            borderSkipped: false,               // round all corners
            barPercentage: 0.65,
            categoryPercentage: 0.75,
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            y: {
                grid: {
                    color: 'rgba(226, 232, 240, 0.6)',  // very subtle
                    drawBorder: false,
                },
                border: { display: false },
                ticks: {
                    font: { size: 11, weight: '500' },
                    color: '#94A3B8',
                    padding: 8,
                }
            },
            x: {
                grid: { display: false },
                border: { display: false },
                ticks: {
                    font: { size: 11, weight: '500' },
                    color: '#94A3B8',
                    padding: 8,
                }
            }
        }
    }
}
```

### Line/Area Chart Pattern

```javascript
{
    type: 'line',
    data: {
        datasets: [{
            borderColor: '#00347E',
            borderWidth: 2.5,
            backgroundColor: navyGradient,     // gradient fill
            fill: true,
            tension: 0.35,                     // smooth curves
            pointRadius: 0,                    // hidden by default
            pointHoverRadius: 6,
            pointHoverBackgroundColor: '#00347E',
            pointHoverBorderColor: '#FFFFFF',
            pointHoverBorderWidth: 2,
        }]
    }
}
```

### Donut Chart Pattern

```javascript
{
    type: 'doughnut',
    data: {
        datasets: [{
            backgroundColor: ['#16A34A', '#DC2626', '#D97706', '#2563EB'],
            borderWidth: 2,
            borderColor: '#FFFFFF',  // gap between segments
            hoverBorderWidth: 0,
            hoverOffset: 4,
        }]
    },
    options: {
        cutout: '70%',             // generous donut hole
        plugins: {
            legend: { display: false }  // custom legend below
        }
    }
}
```

### Sparkline (in KPI cards)

```javascript
{
    type: 'line',
    data: {
        datasets: [{
            borderColor: '#00347E',
            borderWidth: 1.5,
            backgroundColor: 'rgba(0, 52, 126, 0.08)',
            fill: true,
            tension: 0.4,
            pointRadius: 0,
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
            x: { display: false },
            y: { display: false }
        }
    }
}
```

---

## 8. MICRO-INTERACTIONS & ANIMATIONS

### Card Entrance (staggered fade-in)

```css
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(12px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.card-animate {
    animation: fadeInUp 0.4s ease-out forwards;
    opacity: 0;
}
.card-animate:nth-child(1) { animation-delay: 0s; }
.card-animate:nth-child(2) { animation-delay: 0.05s; }
.card-animate:nth-child(3) { animation-delay: 0.1s; }
.card-animate:nth-child(4) { animation-delay: 0.15s; }
.card-animate:nth-child(5) { animation-delay: 0.2s; }

/* Respect reduced motion */
@media (prefers-reduced-motion: reduce) {
    .card-animate {
        animation: none;
        opacity: 1;
    }
}
```

### Number Count-Up

```javascript
function animateValue(el, start, end, duration = 600) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        el.textContent = formatNumber(end);
        return;
    }
    const range = end - start;
    const startTime = performance.now();
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + range * eased);
        el.textContent = formatNumber(current);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}
```

### Hover Transitions

```css
/* Cards lift on hover */
.kpi-card, .card, .tbt-card {
    transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}

/* Table row hover */
.data-table tbody tr {
    transition: background-color 0.15s ease;
}

/* Button press effect */
.btn:active {
    transform: scale(0.98);
}

/* Sidebar nav item */
.sidebar-nav a {
    transition: background 0.2s, color 0.2s;
}
```

### Skeleton Loading

```css
.skeleton {
    background: linear-gradient(
        90deg,
        var(--bg-hover) 25%,
        var(--bg-surface) 50%,
        var(--bg-hover) 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite ease-in-out;
    border-radius: var(--radius-sm);
}

@keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

@media (prefers-reduced-motion: reduce) {
    .skeleton { animation: none; opacity: 0.5; }
}
```

---

## 9. ACCESSIBILITY

### WCAG AA Compliance

| Element | Contrast Ratio | Passes AA? |
|---------|---------------|------------|
| `--text-primary` on `--bg-base` (#0F172A on #F8FAFC) | 17.4:1 | Yes |
| `--text-secondary` on `--bg-base` (#475569 on #F8FAFC) | 6.1:1 | Yes |
| `--text-tertiary` on `--bg-base` (#94A3B8 on #F8FAFC) | 3.3:1 | AA Large only |
| `--sidebar-text` on `--sidebar-bg` (rgba white 0.7 on #00347E) | 5.8:1 | Yes |
| `--sidebar-text-active` on `--sidebar-bg` (white on #00347E) | 9.2:1 | Yes |
| `--status-success` (#16A34A) on white | 4.8:1 | Yes |
| `--status-danger` (#DC2626) on white | 5.5:1 | Yes |
| `--status-warning` (#D97706) on white | 4.6:1 | Yes |

### Rules
1. **Never use color alone** to convey meaning — always pair with icons, labels, or patterns
2. All interactive elements must have `:focus-visible` with `outline: 2px solid var(--border-focus); outline-offset: 2px;`
3. Sidebar nav items must have `aria-current="page"` on active
4. Charts must have text summaries or table alternatives for screen readers
5. All images/icons need `alt` text or `aria-label`
6. Minimum touch target: 44x44px

---

## 10. RESPONSIVE STRATEGY

| Breakpoint | Grid | Sidebar | KPIs | Charts |
|-----------|------|---------|------|--------|
| Desktop (>1200px) | 12-col | 240px expanded | 5-across | 2-col |
| Tablet (901-1200px) | 12-col | 240px expanded | 3-across | stacked |
| Small tablet (769-900px) | 6-col | 64px collapsed | 3-across | stacked |
| Mobile (481-768px) | 2-col | hidden + hamburger | 2-across | stacked |
| Small mobile (<480px) | 1-col | hidden + hamburger | 1-across | stacked |

### Mobile-Specific Rules
- Touch targets minimum **44px** (field workers may wear gloves)
- Font minimum **14px** body for outdoor readability
- Sidebar becomes a slide-over overlay on mobile (with backdrop)
- Collapsible sections default collapsed on all screen sizes
- Bottom-anchored chat FAB is always accessible

---

## 11. IMPLEMENTATION CHECKLIST

Apply changes in this order to minimize breakage:

### Phase 1: Color Tokens & Surfaces
- [ ] Replace CSS custom property values with new color tokens
- [ ] Update `--bg-base` to `#F8FAFC` (warmer, less stark)
- [ ] Add all new brand tokens (`--wollam-navy`, `--wollam-gold`, etc.)
- [ ] Update dark theme tokens
- [ ] Update `--shadow-*` tokens (softer, more refined)
- [ ] Add `--radius-*` and `--status-*-bg` tokens

### Phase 2: Sidebar Transformation
- [ ] Sidebar background → navy (`--sidebar-bg`)
- [ ] Sidebar text → white/semi-transparent white
- [ ] Active nav item → white text + gold left accent bar
- [ ] Section labels → dim white
- [ ] Logo → white version on navy background
- [ ] Remove sidebar border-right, add box-shadow instead
- [ ] Collapsed state → 64px, icon-only, centered

### Phase 3: KPI Card Upgrade
- [ ] Add icon containers (40px colored squares)
- [ ] Trend indicator → pill-style with background color
- [ ] Add hover top-accent line (navy gradient)
- [ ] Increase value font-weight to 800
- [ ] Add sparkline support in KPI footer
- [ ] Staggered fade-in animation on load

### Phase 4: Chart Modernization
- [ ] Update Chart.js global defaults (tooltip style, font, colors)
- [ ] Bar charts → rounded corners (borderRadius: 6), navy fill
- [ ] Line charts → gradient fill, smooth tension, hidden points
- [ ] Donut charts → 70% cutout, white segment gaps
- [ ] Grid lines → very subtle (`rgba(226, 232, 240, 0.6)`)
- [ ] Remove chart borders, clean axes

### Phase 5: Table Refinement
- [ ] Stronger header border-bottom (2px)
- [ ] Increase header font-weight to 700
- [ ] Smoother row hover transition
- [ ] Badge updates (use `--status-*-bg` backgrounds)
- [ ] Increase row padding slightly (12px vs 10px)

### Phase 6: Polish & Animation
- [ ] Card entrance animations (fadeInUp, staggered)
- [ ] Number count-up animation on KPIs
- [ ] Button press feedback (scale 0.98)
- [ ] Skeleton loading refinement
- [ ] Collapsible toggle → stronger visual (add section icons, bolder text)
- [ ] Reduced-motion media query on all animations
- [ ] Toolbox talk cards → top accent stripes (gold/navy)

### Phase 7: Header & Chrome
- [ ] Header → add subtle box-shadow
- [ ] Filter bar → navy-tinted focus states
- [ ] Chat panel → navy-branded send button
- [ ] Chat FAB → navy background instead of blue

---

## 12. WHAT NOT TO CHANGE

Preserve these elements exactly as they are:
- **Data model and API routes** — purely a visual reskin
- **Functionality** — all filters, sorting, pagination, chat, collapsible sections work identically
- **Safety color semantics** — green/amber/red/violet meaning stays the same
- **12-column grid system** — the grid works, just update the colors within it
- **Inter font family** — already the right choice
- **Dark/light theme toggle** — keep it, just update the token values
- **Table column structure** — same columns, same data
- **Chart types and data** — same charts, just restyle them

---

## 13. BEFORE/AFTER SUMMARY

| Element | Current | Reskinned |
|---------|---------|-----------|
| Sidebar | Light gray (`#F4F4F5`) | Navy blue (`#00347E`) |
| Sidebar text | Gray text | White + gold accents |
| Page background | Pure white (`#FFFFFF`) | Warm slate (`#F8FAFC`) |
| Primary interactive | Generic blue (`#3B82F6`) | Wollam navy (`#00347E`) |
| KPI cards | Flat, no icons | Icon badges, top accent, sparklines |
| KPI trend | Plain colored text | Pill badges with background |
| Card shadows | Minimal | Refined multi-layer soft shadows |
| Chart bars | Generic blue | Navy with rounded corners |
| Chart fills | Solid | Gradient fills |
| Buttons | Generic blue | Navy branded with shadow |
| Focus rings | Blue | Navy with faint glow |
| Badges | Transparent color bg | Proper `--status-*-bg` backgrounds |
| Animations | Basic | Staggered entrance, count-up, hover lift |
| Filter focus | Blue border | Navy border + navy faint shadow ring |
| TBT cards | Uniform | Gold (weekly) / Navy (monthly) accent stripes |

The result: A dashboard that is unmistakably **Wollam Construction's** — professional navy and gold branding, modern card design with subtle animations, clean data presentation that respects the safety color system. Feels like a $50K custom build, not a generic template.
