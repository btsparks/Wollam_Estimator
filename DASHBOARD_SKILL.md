# 📊 Dashboard UI Design & Development — Skill Reference
> **Purpose:** A complete reference for designing, building, and evaluating modern, functional, and robust data dashboards with Claude Code. Covers design principles, component specs, chart selection, accessibility, tech stack, and domain-specific guidance for construction safety data.
> **Last Updated:** February 2026
> **Sources:** Carbon Design System (IBM), Material Design 3 (Google), UXPin, Toptal, Brand.dev, LoopStudio, Mokkup.ai, primary research on dashboard UX best practices.

---

## ⚡ Quick Reference (Read This First)

These are the most critical rules. Internalize these before reading anything else.

1. **8px grid** — All spacing, sizing, and layout dimensions must be multiples of 8px (or 4px for fine-grained control)
2. **Font stack** — `'Inter', system-ui, sans-serif` for UI; `font-variant-numeric: tabular-nums` on all numbers
3. **KPI value size** — 32–48px Bold; label 12–14px Regular muted; trend 14px Medium semantic color
4. **Color tokens** — Never use raw hex in components; always reference semantic tokens (`--bg-surface`, `--text-primary`, etc.)
5. **Categorical chart colors** — Indigo → Cyan → Emerald → Amber → Pink → Violet → Red → Teal (in that order, max 5–7 series)
6. **Status colors** — Green = safe/positive, Amber = warning, Red = danger/negative, Blue = informational
7. **Layout zones** — Fixed header (48–64px) + collapsible sidebar (240px expanded / 60px collapsed) + 12-column content grid
8. **KPI cards** — Always show: value, label, trend delta (% vs prior period), and sparkline if space allows
9. **Chart titles** — Write as an answered question ("Which projects had the most negative observations?") not a label ("Observations by Project")
10. **No 3D charts, no pie charts with >5 slices, no dual Y-axes** — ever
11. **Every chart needs** — title, axis labels with units, tooltip on hover, last-updated timestamp
12. **Tables** — numbers right-aligned with thousands separator; text left-aligned; status center-aligned as badges
13. **Skeleton states** — always show shimmer placeholders before data loads; never a blank screen or spinner alone
14. **WCAG AA minimum** — 4.5:1 contrast for body text; 3:1 for large text and UI graphics
15. **Mobile first** — single column on mobile; KPI cards 2-up on tablet; full grid on desktop

---

## Domain Context: Construction Safety Dashboards

> **Read this section when building dashboards for Wollam Construction or similar construction safety data.**

### Data Model
Safety observation data typically includes these fields. Use them to drive smart defaults:

| Field | Type | Notes |
|---|---|---|
| Date | Date | Filter anchor; default to last 30 days |
| Project # | String | e.g. "8600", "8597" — primary grouping dimension |
| Project Name | String | e.g. "QTS DUCTBANKS (RESTART)" |
| Kind of Observation | Enum | `Positive` / `Negative` — primary KPI split |
| Cause | Enum | `Safe Act`, `Safe Condition`, `Unsafe Act`, `Unsafe Condition`, `Unsure` |
| Type | Enum | `Equipment Related`, `Physical Hazard`, `Utility`, `Administrative`, `Struck By/Struck Against` |
| Risk Rating | Integer 0–5 | 0 = Safe, 5 = Catastrophic — most important safety signal |
| Recorder | String | Person who filed the observation |
| Foreman | String | Site foreman |
| Description | Text | Free text narrative |

### Key KPIs to Surface (Priority Order)
1. **Total Observations** (period) with trend vs prior period
2. **Positive Rate** (% positive of total) — higher is better; target >80%
3. **High-Risk Count** (Risk Rating ≥ 3) — lower is better; flag prominently
4. **Observations by Project** — bar chart sorted descending
5. **Risk Rating Distribution** — bar chart colored by severity (0–5)
6. **Cause Breakdown** — donut chart (Safe vs Unsafe acts/conditions)
7. **Observations Over Time** — line chart by week or day
8. **Top Recorders** — table showing who is most engaged in safety reporting

### Color Semantics for Safety Data
- **Positive observations** → `#22C55E` (Green)
- **Negative observations** → `#EF4444` (Red)
- **Risk Rating 0** → `#22C55E` (Green)
- **Risk Rating 1–2** → `#F59E0B` (Amber)
- **Risk Rating 3–4** → `#EF4444` (Red)
- **Risk Rating 5** → `#7C3AED` (Dark Violet — catastrophic, rare)
- **Neutral / informational** → `#3B82F6` (Blue)

### Layout Recommendation for Safety Dashboards
Use the **Z-Pattern** layout:
- **Row 1:** 4 KPI cards — Total Observations, Positive Rate, High-Risk Count, Projects Active
- **Row 2:** Observations Over Time (line, 8 cols) + Positive vs Negative donut (4 cols)
- **Row 3:** Observations by Project (bar, 8 cols) + Risk Rating distribution (bar, 4 cols)
- **Row 4:** Full-width observations table with search, filter, and drill-down

---

## Table of Contents
1. [Dashboard Fundamentals](#1-dashboard-fundamentals)
2. [Dashboard Types](#2-dashboard-types)
3. [Design Principles](#3-design-principles)
4. [Layout & Grid System](#4-layout--grid-system)
5. [Typography](#5-typography)
6. [Color System](#6-color-system)
7. [Spacing System](#7-spacing-system)
8. [Component Specifications](#8-component-specifications)
9. [Data Visualization & Chart Selection](#9-data-visualization--chart-selection)
10. [Navigation Patterns](#10-navigation-patterns)
11. [Interactivity & UX Patterns](#11-interactivity--ux-patterns)
12. [Responsive Design](#12-responsive-design)
13. [Accessibility Standards](#13-accessibility-standards)
14. [Performance Optimization](#14-performance-optimization)
15. [Dark Mode Design](#15-dark-mode-design)
16. [Alerting & Conditional Formatting](#16-alerting--conditional-formatting)
17. [Common Mistakes to Avoid](#17-common-mistakes-to-avoid)
18. [Modern Trends (2025–2026)](#18-modern-trends-20252026)
19. [Tech Stack & Implementation](#19-tech-stack--implementation)
20. [Evaluation Checklist](#20-evaluation-checklist)

---

## 1. Dashboard Fundamentals

### Definition
A dashboard is a visual display of the most important information needed to achieve one or more objectives, consolidated and arranged on a single screen so information can be monitored at a glance *(Stephen Few)*.

### Core Characteristics of a Great Dashboard
- **Clarity** — Users can interpret data quickly without confusion
- **Actionability** — Data drives decisions, not just awareness
- **Hierarchy** — Most critical information is immediately visible
- **Efficiency** — Everything one click away; drill-down for details
- **Customizability** — Filters and views tailored to user context
- **Consistency** — Uniform visual language throughout
- **Performance** — Loads fast and updates reliably

### The Three Layers of a Dashboard
1. **Data Layer** — Data collection, normalization, aggregation
2. **Visualization Layer** — Charts, graphs, tables, KPI cards
3. **Interaction Layer** — Filters, drill-downs, date pickers, user controls

### Goal-Setting Framework (SMART)
Before designing, define goals that are:
- **S**pecific — What exact problem does this solve?
- **M**easurable — What KPIs confirm success?
- **A**ctionable — Can users act on what they see?
- **R**ealistic — Does the data actually support this view?
- **T**ime-based — What time ranges are relevant?

### Key Questions to Ask Before Building
- Who are the users and what decisions will this dashboard inform?
- What is the single most important thing a user should see first?
- How frequently will this data change, and how fresh must it be?
- What devices will users access this on?
- What are the downstream actions a user takes after reading this dashboard?

---

## 2. Dashboard Types

### Operational Dashboards
- **Purpose:** Real-time monitoring of day-to-day operations
- **Users:** Managers, support teams, DevOps
- **Update frequency:** Real-time or near-real-time (seconds to minutes)
- **Examples:** Customer support queue, server uptime monitor, live sales feed
- **Key widgets:** Real-time counters, status indicators, activity feeds, gauges
- **Design:** High-density information, traffic-light colors, timestamps prominent

### Analytical Dashboards
- **Purpose:** Identify trends, patterns, and insights over time
- **Users:** Data analysts, business intelligence teams
- **Update frequency:** Daily, weekly, or on-demand
- **Examples:** Sales trend analysis, cohort analysis, funnel analysis
- **Key widgets:** Line charts, scatter plots, histograms, heat maps, data tables
- **Design:** Exploration-first, drill-down capability, filter-heavy

### Strategic Dashboards
- **Purpose:** High-level overview of organizational KPIs and long-term goals
- **Users:** C-suite executives, board members
- **Update frequency:** Weekly to monthly
- **Examples:** Revenue vs. target, market share, OKR tracker
- **Key widgets:** KPI cards with trend indicators, simple bar/line charts, scorecards
- **Design:** Maximum simplicity, minimal charts per screen, generous whitespace

### Tactical Dashboards *(best fit for construction safety)*
- **Purpose:** Mid-level performance tracking for specific initiatives or job sites
- **Users:** Department managers, project leads, safety supervisors
- **Update frequency:** Daily to weekly
- **Examples:** Marketing campaign tracker, sprint burndown, safety observation summary
- **Key widgets:** Progress bars, comparative bar charts, goal indicators, summary tables
- **Design:** Bridges operational detail with strategic context

---

## 3. Design Principles

### Principle 1: Establish Visual Hierarchy
- Place the most critical metrics **top-left** (F-pattern reading for Western users)
- Use **size, weight, color, and position** to communicate importance
- Primary KPIs: largest, most prominent
- Supporting metrics: smaller, subordinate position
- Reserve bright/accent colors for alerts and CTAs only — avoid "rainbow effect"
- Use **whitespace** (negative space) to separate sections — no lines needed

### Principle 2: Reduce Cognitive Load
- Follow the **"Less is More"** rule — every element must earn its place
- Ask: *"Does this component help the user make a better decision?"* If no, remove it
- Use **progressive disclosure** — reveal advanced info on demand (hover, expand, drill-down)
- Implement **modular design** — users add/remove/rearrange widgets
- Limit simultaneous choices, controls, and filters visible at once
- Group related metrics with proximity, not borders

### Principle 3: Maintain Consistency
- One color palette, one type scale, one icon set — across all views
- Uniform interaction patterns (filters behave the same everywhere)
- Consistent chart styles — same axis formatting, same grid lines
- Reusable component library prevents visual drift

### Principle 4: Affordance & Clarity
- Use chart titles as answers to the question the chart addresses (*"Which regions exceeded quota?"* not *"Regional Sales"*)
- Avoid acronyms — write out full terms
- Add tooltip explanations (ℹ️ icon) to every metric definition
- Show *what the data means*, not just what it is

### Principle 5: Context in Every Data Point
- Always show "Last updated at [timestamp]"
- Document data sources inline or via tooltips
- Explain any filters or data transformations applied
- Show targets/benchmarks alongside actuals
- Provide percentage change vs. previous period

### Principle 6: Progressive Disclosure
- **Level 1:** High-level KPI summary visible at a glance (no scroll)
- **Level 2:** Charts and trends accessible by scrolling or clicking
- **Level 3:** Detailed tables, raw data, export — via drill-down or modal
- Never show everything at once; create depth with navigation

---

## 4. Layout & Grid System

### The 8px Grid (Base Unit)
The foundational unit for all spacing, sizing, and layout decisions is **8px**. All dimensions should be multiples of 8 (or 4px for fine-grained control).

```
Mini unit = 8px
Component heights: 32px, 40px, 48px, 64px, 80px
Padding: 8px, 16px, 24px, 32px, 48px, 64px
Border radius: 8px (standard), 12px (cards), 16px (prominent), 9999px (pills/badges)
```

### Standard Breakpoints
| Breakpoint | Width (px) | Columns | Use Case |
|---|---|---|---|
| Small | 320–671 | 4 | Mobile portrait |
| Medium | 672–1055 | 8 | Tablet portrait |
| Large | 1056–1311 | 12 | Desktop / tablet landscape |
| X-Large | 1312–1583 | 16 | Wide desktop |
| Max | 1584+ | 16 | Ultra-wide |

Standard gutter: 16px between columns. Standard margin: 16px (small/medium) → 24px (max breakpoint).

### Dashboard Layout Zones
```
┌─────────────────────────────────────────────────────────┐
│  HEADER (fixed, 48–64px)                                │
│  Logo | Page title | Date filter | User avatar          │
├──────────┬──────────────────────────────────────────────┤
│          │  FILTER BAR (sticky, 48px)                   │
│ SIDEBAR  │  [Date ▾] [Project ▾] [Type ▾] [Reset]       │
│ 240px /  ├──────────────────────────────────────────────┤
│ 60px     │  KPI ROW                                     │
│ collapsed│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│          │  │ KPI  │ │ KPI  │ │ KPI  │ │ KPI  │        │
│          │  └──────┘ └──────┘ └──────┘ └──────┘        │
│          │                                              │
│          │  ┌──────────────────┐ ┌──────────────┐       │
│          │  │  Primary Chart   │ │  Secondary   │       │
│          │  │  (8 cols)        │ │  (4 cols)    │       │
│          │  └──────────────────┘ └──────────────┘       │
│          │                                              │
│          │  ┌──────────────────────────────────────┐    │
│          │  │  Data Table (full width)             │    │
│          │  └──────────────────────────────────────┘    │
└──────────┴──────────────────────────────────────────────┘
```

### Content Grid (12-Column Typical)
| Widget Type | Column Span | Notes |
|---|---|---|
| KPI Card | 3 cols (25%) | 4-up row |
| KPI Card | 4 cols (33%) | 3-up row |
| KPI Card | 6 cols (50%) | Full-width on mobile |
| Chart (primary) | 8 cols (67%) | Main trend/bar |
| Chart (secondary) | 4 cols (33%) | Supporting donut |
| Full-width chart | 12 cols | Tables, heatmaps |
| Sidebar panel | 3–4 cols | Filters, quick stats |

### Common Layout Patterns
**Z-Pattern** (executive / safety dashboards): Top row 4 KPI cards → large chart left (8 cols) + narrow chart right (4 cols) → data table full-width

**F-Pattern** (analytical dashboards): Filters/controls top bar → primary chart 60–70% left → secondary metrics right column → drill-down table below

**Grid Pattern** (operational dashboards): Equal-sized tiles, real-time status indicators, high information density

### Aspect Ratios for Charts & Cards
| Use Case | Ratio |
|---|---|
| KPI Card | 2:1 (landscape) or 1:1 |
| Bar / Line Chart | 16:9 or 2:1 |
| Donut / Pie Chart | 1:1 |
| Heatmap | 4:3 |
| Table | Fluid height |
| Hero metric | 3:1 (wide banner) |

---

## 5. Typography

### Type Scale (8pt-based)
| Token | Size (px) | Size (rem) | Use |
|---|---|---|---|
| `xs` | 11px | 0.6875rem | Legal, fine print, axis labels |
| `sm` | 12px | 0.75rem | Labels, captions, legend, timestamps |
| `body-sm` | 14px | 0.875rem | Secondary body, table data, trends |
| `body` | 16px | 1rem | Primary body, chart titles |
| `lg` | 18px | 1.125rem | Card subtitles, section headers |
| `xl` | 20px | 1.25rem | Page subheaders |
| `2xl` | 24px | 1.5rem | Page title |
| `3xl` | 32px | 2rem | KPI primary value |
| `4xl` | 40px | 2.5rem | Hero KPI |
| `5xl` | 48–64px | 3–4rem | Feature KPI (big number display) |

### Font Weight Usage
| Weight | Value | Use |
|---|---|---|
| Light | 300 | Supporting text, fine print |
| Regular | 400 | Body text, table data, labels |
| Medium | 500 | Subheadings, active nav items, trends |
| Semibold | 600 | Section headers, KPI labels, table headers |
| Bold | 700 | KPI values, page titles, alert text |

### Line Heights
| Text Type | Line Height |
|---|---|
| Display / KPI | 1.0–1.1 (tight) |
| Headings | 1.2–1.3 |
| Body | 1.5–1.6 |
| Labels / Captions | 1.3–1.4 |

### Font Stack
```css
/* Primary UI font */
font-family: 'Inter', 'IBM Plex Sans', 'Geist', system-ui, -apple-system, sans-serif;

/* Monospace — for codes, IDs, raw data */
font-family: 'JetBrains Mono', 'IBM Plex Mono', 'Fira Code', monospace;

/* Always use tabular numbers for any changing/numeric display */
font-variant-numeric: tabular-nums;
letter-spacing: -0.01em; /* Inter reads better slightly tighter at large sizes */
```

> **Always use `tabular-nums`** on KPI values and table data to prevent layout shift when numbers update.

### Typography Hierarchy in Practice
```
Page Title              → 24px / Semibold / --text-primary
Section Header          → 18–20px / Semibold / --text-primary
Chart Title             → 16px / Medium   / --text-primary
KPI Value               → 32–48px / Bold  / --text-primary
KPI Label               → 12–14px / Regular / --text-secondary
KPI Trend (+12.3%)      → 14px / Medium   / semantic color (green/red)
Body / Description      → 14–16px / Regular / --text-secondary
Axis Labels             → 11–12px / Regular / --text-tertiary
Legend Labels           → 12px / Regular  / --text-secondary
Tooltip Text            → 12–14px / Regular / inverted
Table Header            → 12–13px / Semibold / --text-secondary
Table Data              → 14px / Regular (tabular) / --text-primary
Badge / Pill Text       → 11–12px / Semibold / semantic
Timestamp / Meta        → 12px / Regular  / --text-tertiary
```

---

## 6. Color System

### Architecture (Always Use This Pattern)
```
Raw hex values (design palette)
    ↓
Semantic design tokens (role-based)
    ↓
Theme (light / dark / high-contrast)
    ↓
Component usage
```
**Never hardcode hex values in components.** Always reference CSS custom properties or design tokens.

### Semantic Color Tokens
| Token | Light Mode | Dark Mode | Use |
|---|---|---|---|
| `--bg-base` | #FFFFFF | #0F1117 | Page background |
| `--bg-surface` | #F4F4F5 | #1A1D27 | Card/panel backgrounds |
| `--bg-elevated` | #FFFFFF | #22263A | Elevated cards, modals |
| `--bg-hover` | #F0F0F1 | #2A2F42 | Hover states |
| `--bg-selected` | #EEF2FF | #1E2A4A | Selected rows/items |
| `--border-default` | #E4E4E7 | #2D3147 | Default borders |
| `--border-strong` | #D1D5DB | #3D4460 | Emphasized borders |
| `--text-primary` | #111827 | #F9FAFB | Body text, values |
| `--text-secondary` | #6B7280 | #9CA3AF | Labels, captions |
| `--text-tertiary` | #9CA3AF | #6B7280 | Placeholder, muted |
| `--text-disabled` | #D1D5DB | #374151 | Disabled state text |
| `--interactive` | #3B82F6 | #60A5FA | Links, primary actions |
| `--interactive-hover` | #2563EB | #93C5FD | Hover on interactive |
| `--focus` | #3B82F6 | #FFFFFF | Focus ring |

### Status / Alert Colors
| Role | Light | Dark | Use |
|---|---|---|---|
| Success | #22C55E | #4ADE80 | Positive, safe, on-target |
| Warning | #F59E0B | #FCD34D | Caution, approaching threshold |
| Danger | #EF4444 | #F87171 | Errors, critical, unsafe |
| Info | #3B82F6 | #60A5FA | Informational, neutral |
| Neutral | #6B7280 | #9CA3AF | No change, unknown |

### Data Visualization Palette (Apply in Order)
```
1. #6366F1  Indigo    — primary series
2. #06B6D4  Cyan      — secondary series
3. #10B981  Emerald   — tertiary series
4. #F59E0B  Amber     — quaternary series
5. #EC4899  Pink      — quinary series
6. #8B5CF6  Violet    — senary series
7. #EF4444  Red       — septenary (avoid alongside green unless semantic)
8. #14B8A6  Teal      — octonary series
```

**Sequential palette:** Light to dark in a single hue — for heatmaps, density plots (e.g., Blue 100 → Blue 900)

**Diverging palette:** Neutral center diverging to two hues — for +/- performance (e.g., Red ← Neutral → Green)

### Color Rules
- Apply colors sequentially — never skip or shuffle order
- Max 5–7 categories visible at once; group remainder as "Other"
- Never use color as the **only** differentiator — pair with labels, patterns, or icons
- Maintain 3:1 contrast ratio between adjacent data series (WCAG for graphics)
- Avoid red/green as the only distinction (color blindness)
- WCAG AA: 4.5:1 contrast for text < 24px; 3:1 for text ≥ 24px and UI graphics

### CSS Custom Properties Implementation
```css
:root {
  --bg-base: #FFFFFF;
  --bg-surface: #F4F4F5;
  --bg-elevated: #FFFFFF;
  --bg-hover: #F0F0F1;
  --bg-selected: #EEF2FF;
  --border-default: #E4E4E7;
  --border-strong: #D1D5DB;
  --text-primary: #111827;
  --text-secondary: #6B7280;
  --text-tertiary: #9CA3AF;
  --text-disabled: #D1D5DB;
  --interactive: #3B82F6;
  --interactive-hover: #2563EB;
  --focus: #3B82F6;
  --status-success: #22C55E;
  --status-warning: #F59E0B;
  --status-danger: #EF4444;
  --status-info: #3B82F6;
  --status-neutral: #6B7280;
}

[data-theme="dark"] {
  --bg-base: #0F1117;
  --bg-surface: #1A1D27;
  --bg-elevated: #22263A;
  --bg-hover: #2A2F42;
  --bg-selected: #1E2A4A;
  --border-default: #2D3147;
  --border-strong: #3D4460;
  --text-primary: #F9FAFB;
  --text-secondary: #9CA3AF;
  --text-tertiary: #6B7280;
  --text-disabled: #374151;
  --interactive: #60A5FA;
  --interactive-hover: #93C5FD;
  --focus: #FFFFFF;
  --status-success: #4ADE80;
  --status-warning: #FCD34D;
  --status-danger: #F87171;
  --status-info: #60A5FA;
  --status-neutral: #9CA3AF;
}
```

---

## 7. Spacing System

### The Spacing Scale (8px multiples)
| Token | px | rem | Common Use |
|---|---|---|---|
| `space-1` | 4px | 0.25rem | Icon gaps, tight internal spacing |
| `space-2` | 8px | 0.5rem | Icon-to-label gaps, chip padding |
| `space-3` | 12px | 0.75rem | Small component internal padding |
| `space-4` | 16px | 1rem | Card padding (compact), grid gutter |
| `space-5` | 20px | 1.25rem | Form field padding |
| `space-6` | 24px | 1.5rem | Card padding (standard), section gaps |
| `space-8` | 32px | 2rem | Between card rows, section headers |
| `space-10` | 40px | 2.5rem | Large section separation |
| `space-12` | 48px | 3rem | Page section breaks |
| `space-16` | 64px | 4rem | Major layout separations |
| `space-20` | 80px | 5rem | Hero sections |

### Component Spacing Rules

**Cards:**
```
Padding compact:   16px
Padding standard:  24px
Padding spacious:  32px
Gap between cards: 16–24px
Border radius:     12px (standard), 16px (prominent)
```

**KPI Cards:**
```
Height:            120–160px (compact) / 160–200px (standard)
Internal padding:  20–24px
Label → Value gap: 4–8px
Value → Trend gap: 4px
```

**Charts / Visualizations:**
```
Container padding:   16–24px
Title margin-bottom: 16px
Axis label padding:  8px from axis line
Legend margin-top:   12–16px
Tooltip padding:     8–12px vertical / 12–16px horizontal
```

**Tables:**
```
Cell padding (compact):  8px 12px
Cell padding (standard): 12px 16px
Cell padding (spacious): 16px 24px
Row height (standard):   48px
Header height:           40px
```

---

## 8. Component Specifications

### KPI / Metric Card
```
┌─────────────────────────────────────┐
│  ● Icon (opt)   LABEL          [ℹ️] │  ← 12–14px Semibold, --text-secondary
│                                     │
│  $1,284,000                         │  ← 32–48px Bold, --text-primary
│                                     │
│  ▲ +12.3%  vs. last month           │  ← 14px Medium, --status-success
│                                     │
│  ▁▂▄▆▅▇▆▄  (sparkline)              │  ← 40–48px tall, no axes
└─────────────────────────────────────┘
```
**Design rules:**
- Always show change context (%, delta, or vs-target)
- Use semantic color for trend indicator only (not the entire card background)
- Tooltip on ℹ️ hover: full metric definition + calculation method
- Border: 1px `--border-default`; shadow: `0 1px 3px rgba(0,0,0,0.06)`

**Variants:**
- **Minimal:** Value + Label + Trend
- **Standard:** Above + sparkline
- **Detailed:** Standard + progress bar toward target
- **Alert:** Standard + colored left border (4px) when threshold breached

### Chart Container Card
```
┌────────────────────────────────────────────────────┐
│  Chart Title (16px Medium)          [↗] [⋯]       │  ← 48–56px header
│  Subtitle / date range (12px muted)                │
├────────────────────────────────────────────────────┤
│                                                    │
│             CHART AREA (flexible height)           │
│                                                    │
├────────────────────────────────────────────────────┤
│  ● Series A   ● Series B   ● Series C              │  ← Legend
└────────────────────────────────────────────────────┘
```
**Overflow menu (⋯) options:** Download PNG, Download CSV, View as table, Expand fullscreen, Set alert threshold

### Data Tables

**Column alignment by data type:**
| Type | Align | Format Example |
|---|---|---|
| Text / Name | Left | As-is |
| Integer | Right | 1,234 |
| Currency | Right | $1,234.56 |
| Percentage | Right | 12.3% |
| Date | Left | Jan 23, 2026 |
| Status | Center | Badge pill |
| Risk Rating | Center | Colored badge (0–5) |
| Actions | Right | Icon buttons |

**Required table features:**
- Sortable columns (click header, show sort direction arrow)
- Column resizing (drag handle on header)
- Row hover highlight (`--bg-hover`)
- Sticky column headers on scroll
- Pagination OR virtual scroll for >100 rows
- Search/filter input above table
- Export button (CSV / Excel)
- Column visibility toggle
- Fixed first column (name/ID) when horizontal scroll is needed
- Row count label ("Showing 1–25 of 143")

### Status Badge / Pill
```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}
.badge-positive  { background: #DCFCE7; color: #15803D; }
.badge-negative  { background: #FEE2E2; color: #B91C1C; }
.badge-warning   { background: #FEF3C7; color: #92400E; }
.badge-neutral   { background: #F3F4F6; color: #374151; }
```

### Risk Rating Badge (Construction Safety Specific)
```
Rating 0 → Green  badge "0 — Safe"
Rating 1 → Green  badge "1"
Rating 2 → Amber  badge "2"
Rating 3 → Red    badge "3"
Rating 4 → Red    badge "4 — High"
Rating 5 → Violet badge "5 — Critical"
```

### Filters & Controls Bar
```
[Date Range ▾]  [Project ▾]  [Observation Type ▾]  [Risk Level ▾]  │  [🔍 Search]  [Reset]
```
- Show active filter count as a pill: "3 filters active ×"
- "Reset all" button always visible when any filter is active
- Filters persist in URL params for shareability
- Mobile: collapse into a "Filters" drawer/sheet

### Sidebar Navigation
```
Width expanded:  240–260px
Width collapsed: 60–72px (icon only)
Mobile:          full-screen drawer or 280px

Item height:     44px
Icon size:       20px (compact) / 24px (standard)
Icon-label gap:  12px
Padding:         16px horizontal
Active state:    --bg-selected + 3–4px left border in --interactive
Hover state:     --bg-hover, no border
Font:            14–15px Medium
```

### Tooltips
- Trigger: hover with 150–200ms delay, or click on ℹ️
- Position: above by default; auto-flip if near viewport edge
- Max width: 240–320px
- Background: `#1F2937` (dark, inverted) — works on both light and dark themes
- Content for chart tooltips: date/label, value with units, series name, % of total if applicable, comparison to prior period

---

## 9. Data Visualization & Chart Selection

### Chart Selection Decision Tree
```
What do you want to show?
│
├── COMPARISON (between categories)
│   ├── ≤ 7 categories             → Vertical Bar Chart
│   ├── > 7 categories             → Horizontal Bar Chart
│   ├── Parts of a whole           → Stacked Bar Chart
│   └── Ranking                    → Sorted Bar (descending)
│
├── TREND (change over time)
│   ├── One metric                 → Line Chart
│   ├── Multiple metrics (≤ 3)    → Multi-line Chart
│   ├── Volume + trend             → Area Chart
│   └── Distribution over time     → Stream Chart / Stacked Area
│
├── PART-TO-WHOLE
│   ├── ≤ 5 categories             → Donut Chart (preferred over Pie)
│   ├── Many categories            → Treemap
│   ├── Hierarchical               → Sunburst Chart
│   └── Over time                  → 100% Stacked Bar
│
├── DISTRIBUTION
│   ├── Single variable            → Histogram
│   ├── Statistical summary        → Box Plot
│   └── Large datasets             → Violin Plot
│
├── CORRELATION
│   ├── Two numeric variables      → Scatter Plot
│   ├── Three variables            → Bubble Chart
│   └── Many variables             → Heat Map / Parallel Coordinates
│
├── SINGLE VALUE (KPI / status)
│   ├── Current value              → Metric Card (Big Number)
│   ├── Progress toward goal       → Gauge / Bullet Chart / Progress Bar
│   └── Pass/fail threshold        → Status Badge
│
└── GEOGRAPHIC
    ├── Countries / regions        → Choropleth Map
    └── Points of interest         → Symbol Map
```

### Chart Anatomy Checklist
Every chart must include:
- [ ] Descriptive question-based title
- [ ] Axis labels with units (e.g. "Observations (Count)", "Risk Rating (0–5)")
- [ ] Legend (if multiple series)
- [ ] Interactive tooltip on hover
- [ ] Last-updated timestamp
- [ ] Empty state for no-data scenario

Every chart must avoid:
- [ ] 3D effects (distorts perception)
- [ ] Pie/donut with >5 slices
- [ ] Dual Y-axes (split into two separate charts)
- [ ] Y-axis that doesn't start at 0 (unless explicitly communicating delta)
- [ ] More than 5–7 colors in a single chart
- [ ] Decorative backgrounds or heavy gridlines

### Data-to-Ink Ratio (Edward Tufte)
Remove every visual element that doesn't represent data:
- Gridlines: light gray, horizontal only (`stroke: #E5E7EB; stroke-dasharray: 4`)
- No chart borders or heavy frames
- No fill on axes
- Clean, lightweight tick marks
- Direct labels over legends when space permits

### Specific Chart Guidance

**Line Charts:**
```
Minimum 2 data points to draw a line
Show point dots at nodes when < 12 data points
Smooth curves (monotone) for aesthetics; straight for precision data
Y-axis: always starts at 0 unless explicitly showing delta
Line width: 2–3px
Area fill below line: 8–15% opacity of line color
```

**Bar Charts:**
```
Bar width: 50–70% of available slot
Gap between bars: 30–50% of bar width
Horizontal bars preferred when labels > 8 chars
Sort descending by value unless temporal order matters
Single color per chart; use accent highlight for selected bar
```

**Donut / Pie Charts:**
```
Max 5–6 slices; group rest as "Other"
Donut hole: 50–60% of outer radius (leaves space for center KPI)
Always include percentage or data labels
No 3D, no explosion effects
Show total count in center hole
```

**KPI Sparklines:**
```
Width: full card width
Height: 40–56px
No axes, no labels — trend shape only
Line color: green if trending positive, red if negative, gray if neutral
Fill area: 10–20% opacity of line color
```

---

## 10. Navigation Patterns

### Sidebar Navigation (Recommended for Complex Dashboards)
- **Best for:** Multi-section dashboards with > 5 main views
- **Behavior:** Fixed or sticky; collapsible to icon-rail (60–72px)
- **Position:** Left side primary; right side only for contextual panels

### Top Navigation Bar
- **Best for:** Simple dashboards with ≤ 5 main sections
- **Height:** 56–64px

### Tabbed Navigation (within a page)
- **Best for:** Switching between related views on same dataset
- **Variants:** Underline tabs (cleanest), Card tabs, Pill tabs
- **Active indicator:** 2–3px underline in accent color, or filled background

### Breadcrumbs (Drill-Down Navigation)
```
Dashboard > Project 8600 > QTS Ductbanks > January 2026
```
- Always show on drill-down views; clicking any crumb navigates back

### Pagination Patterns
| Pattern | Use Case |
|---|---|
| Numbered pagination | Tables with predictable row counts |
| "Load more" button | Activity logs, feeds |
| Infinite scroll | High-frequency operational views |
| Virtual scroll | Tables with 10,000+ rows |

---

## 11. Interactivity & UX Patterns

### Filter Interactions
- **Date range picker:** Preset options (Today, 7D, 30D, 90D, YTD, Custom)
- **Dropdown filters:** Searchable for > 10 options
- **Multi-select:** Checkboxes inside dropdown, with "Select all / None"
- **Applied filters:** Removable pills/chips ("Project: 8600 ×")
- **Cross-filtering:** Clicking a chart element filters the entire dashboard
- **URL state:** All filter state reflected in URL for sharing/bookmarking

### Drill-Down Patterns
- Click a bar/segment → filter dashboard to that dimension
- Click a metric card → navigate to detailed view
- Hover over data point → rich tooltip with extended context
- Right-click or ⋯ menu → contextual options (drill down, export, set alert)

### Loading & Skeleton States
```
Order of loading:
1. Show skeleton placeholders immediately (same shape as content)
2. Load critical above-fold KPI cards first
3. Load charts progressively as data arrives
4. Lazy-load below-fold content via IntersectionObserver

Skeleton spec:
- Animated shimmer effect (left-to-right gradient)
- Gray placeholder blocks at correct dimensions
- Never show only a spinner — always skeleton at correct shape
```

### Empty States
Design intentional empty states for every scenario:
- **No data after filtering** → "No observations match these filters" + [Clear Filters]
- **No data yet** → "No observations recorded for this period" + guidance
- **Error loading** → Error message + [Retry]
- **Permission denied** → Explanation + [Request Access]

```
[Icon — e.g. clipboard with magnifier]
  "No observations found"              (16–18px Semibold)
  "Try adjusting your filters."        (14px muted)
  [Clear Filters]                      (primary button)
```

### Real-Time Updates
| Scenario | Pattern |
|---|---|
| High-frequency (< 5s) | WebSocket push, subtle value animation |
| Medium-frequency (5–60s) | Auto-poll with "Live" indicator badge |
| Low-frequency (1–15min) | Auto-refresh with countdown timer |
| On-demand | Manual "Refresh" button + last-updated timestamp |

**Visual feedback when data updates:**
- Briefly flash/highlight cells or values that changed
- Show subtle "Updated" toast notification (bottom-right, 3s timeout)
- Animate number transitions (count-up/count-down effect)
- Never full-page refresh — update components in place

### Responsive Table on Mobile
1. **Card view:** Each row becomes a label:value card
2. **Priority columns:** Hide low-priority columns; show on expand
3. **Horizontal scroll:** With sticky first column (name/ID)
4. **Swipe pagination:** Left/right through pages

---

## 12. Responsive Design

### Mobile-First Approach
Design for the smallest screen first, enhance for larger screens. This forces prioritization of what truly matters.

### Breakpoint Layout Adaptations

**Mobile (< 672px):**
- Single column layout; KPI cards 2-up (2 × 50%)
- Charts: Full width, simplified (remove secondary series if cluttered)
- Sidebar → Bottom tab bar or hamburger drawer
- Tables → Card view or horizontal scroll with sticky first column
- Filters → Full-screen filter drawer

**Tablet (672–1055px):**
- 2-column content grid; KPI cards 2–3 per row
- Sidebar: Collapsed by default (icon-only)

**Desktop (1056px+):**
- Full sidebar + 12-column content; KPI cards 4 per row

### Touch Target Sizes
```
Minimum tap target: 44 × 44px (Apple HIG & Material Design 3)
Preferred:          48 × 48px
Min gap between targets: 8px
```

### CSS Grid Implementation
```css
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
  padding: 16px;
}

.kpi-card     { grid-column: span 3; }   /* 4-up desktop */
.chart-main   { grid-column: span 8; }
.chart-side   { grid-column: span 4; }
.chart-full   { grid-column: span 12; }

@media (max-width: 1055px) {
  .kpi-card   { grid-column: span 6; }   /* 2-up tablet */
  .chart-main { grid-column: span 12; }
  .chart-side { grid-column: span 12; }
}

@media (max-width: 671px) {
  .dashboard-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
  .kpi-card   { grid-column: span 1; }
  .chart-main { grid-column: span 2; }
  .chart-full { grid-column: span 2; }
}

.sidebar { width: 240px; transition: width 200ms ease; }
.sidebar.collapsed { width: 60px; }
@media (max-width: 1055px) { .sidebar { display: none; } }
```

---

## 13. Accessibility Standards

### WCAG 2.1 Level AA Requirements (Minimum)

**Color Contrast:**
| Text Type | Min Ratio |
|---|---|
| Normal text (< 18px or < 14px bold) | 4.5:1 |
| Large text (≥ 18px or ≥ 14px bold) | 3:1 |
| UI components & graphical objects | 3:1 |
| Placeholder text | 4.5:1 |

**Keyboard Navigation:**
- All interactive elements reachable via Tab key
- Clear, always-visible focus indicator (2px outline, 3:1 contrast)
- Logical tab order (left-to-right, top-to-bottom)
- Keyboard shortcuts for common actions (documented in help modal)
- Skip navigation link: "Skip to main content" (first in DOM)

**Screen Reader Support:**
```html
<!-- Landmarks -->
<header role="banner">
<nav role="navigation" aria-label="Main navigation">
<main role="main">
<aside role="complementary">

<!-- Charts: always provide a text summary -->
<figure role="img" aria-label="Bar chart: Observations by project, January 2026">
  <figcaption>Project 8600 had the most observations (12), 3 were negative.</figcaption>
</figure>

<!-- KPI Cards -->
<article aria-label="Total Observations KPI">
  <h2>Total Observations</h2>
  <p aria-live="polite">143</p>
  <p>Up 18% from last month</p>
</article>

<!-- Loading states -->
<div aria-busy="true" aria-label="Loading dashboard data"><!-- skeleton --></div>

<!-- Live regions for real-time data -->
<div aria-live="polite" aria-atomic="true">Last updated: 2:34 PM</div>

<!-- Data tables -->
<table>
  <caption>Safety observations for January 2026</caption>
  <thead>
    <tr>
      <th scope="col" aria-sort="descending">Date</th>
      <th scope="col">Project</th>
      <th scope="col">Risk Rating</th>
    </tr>
  </thead>
</table>
```

**Don't Rely on Color Alone:**
- Use patterns, textures, icons, and labels to differentiate data
- Provide alt text for all non-decorative images
- Every chart must have a text description of its key insight
- Use `aria-describedby` to link chart to its `figcaption`

**Accessible Chart Data:**
- Provide a **"View as table"** toggle for every chart
- Include data download (CSV) for raw data access

**Focus Management:**
```css
:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
  border-radius: 2px;
}
```

**Testing Tools:**
- axe DevTools browser extension (target: 0 critical issues)
- WAVE Web Accessibility Evaluator
- Chrome Lighthouse Accessibility audit
- Color contrast checker: webaim.org/resources/contrastchecker
- Color blindness simulator: colororacle.org

---

## 14. Performance Optimization

### Loading Performance Targets
```
Initial page load (LCP):     < 2.5 seconds
Time to Interactive (TTI):   < 3.5 seconds
First Contentful Paint:      < 1.8 seconds
API data fetch timeout:      < 3 seconds (show skeleton)
Chart render time:           < 500ms per chart
Filter response time:        < 200ms (perceived instant)
```

### Loading Priority Order
```
Priority 1 (immediate):   Header, sidebar nav, filter bar skeletons
Priority 2 (< 500ms):     KPI cards with real data
Priority 3 (< 1s):        Above-fold charts
Priority 4 (lazy):        Below-fold charts and table (IntersectionObserver)
```

### Data Fetching Strategies
- **Lazy loading:** Only fetch data for visible widgets via `IntersectionObserver`
- **Pagination:** Never load more than 100–200 rows at once in tables
- **Virtual scrolling:** For tables > 200 rows (only render visible rows in DOM)
- **Query caching:** Cache common filter combinations (React Query / SWR / Redis)
- **Aggregation at source:** Pre-aggregate in data warehouse; don't compute in browser
- **Asynchronous loading:** Load charts independently; don't block all on one slow query
- **Debounce filters:** 300ms debounce before triggering refetch on filter change

### Caching Strategy by Data Type
```
Real-time data:       No cache (WebSocket)
Near-real-time:       5–30 second cache
Operational data:     5–15 minute cache
Analytical data:      1–24 hour cache
Historical reports:   24 hour – 7 day cache
```

### Frontend Performance
- Use SVG for charts with < 1,000 data points (accessible, scalable)
- Use Canvas or WebGL for > 1,000 data points (ECharts, D3 + canvas)
- Code-split dashboard sections — don't bundle all chart types upfront
- Use `will-change: transform` sparingly for animated chart elements
- Compress images (WebP/AVIF), use SVG icons

### Bundle Size Targets
```
Initial JS bundle:   < 200KB gzipped
Chart library:       < 50KB gzipped (tree-shake unused chart types)
Total page weight:   < 500KB initial, < 2MB total
```

---

## 15. Dark Mode Design

### When to Use Dark Mode
- B2B SaaS products used for extended hours (monitoring, operations, safety)
- Data-heavy applications where chart colors "pop" on dark backgrounds
- Always offer a manual toggle regardless of context

### Dark Mode Design Rules
- **Never** invert light mode colors naively — design a proper dark palette
- Use layered grays (not pure black): `#0F1117 → #1A1D27 → #22263A`
- Text: near-white (#F9FAFB) primary; mid-gray (#9CA3AF) secondary
- Reduce saturation of accent colors slightly in dark mode
- Use subtle borders instead of drop shadows on dark surfaces

### Dark Mode Color Layering Model
```
Page background (darkest):   #0F1117
Card / surface:              #1A1D27  (+1 step lighter)
Elevated card / modal:       #22263A  (+2 steps lighter)
Hover state:                 #2A2F42  (+3 steps lighter)
Active / selected:           #2D3580  (accent tinted)
```

### Theme Toggle Implementation
```javascript
// Respect system preference as default
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const saved = localStorage.getItem('theme');
const theme = saved ?? (prefersDark ? 'dark' : 'light');
document.documentElement.setAttribute('data-theme', theme);

// Manual toggle
function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'dark'
    ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
}
```

**Critical:** Set the theme attribute *before* first render (in `<head>` or a blocking script) to prevent flash of wrong theme on page load.

---

## 16. Alerting & Conditional Formatting

### Alert Severity Levels
| Level | Color | Icon | Use |
|---|---|---|---|
| Critical | Red (#EF4444) | 🔴 | Immediate action required |
| Warning | Amber (#F59E0B) | 🟡 | Approaching threshold |
| Info | Blue (#3B82F6) | 🔵 | Informational update |
| Success | Green (#22C55E) | 🟢 | Goal met, positive event |

### Alert Design Principles
- **Avoid alert fatigue:** Alert only on critical, high-impact metrics — max 5 alert types per dashboard
- **Make alerts actionable:** Include context + suggested next step
- **Allow customization:** Users should be able to set their own thresholds
- **Use severity levels:** Categorize clearly (info / warning / critical)
- **Persistent vs toast:** Toast for transient info (4s, dismissible); persistent banner for ongoing conditions

### Alert UI Patterns
```
┌──────────────────────────────────────────────────────────────────┐
│ ⚠️  2 high-risk observations require attention this week         │
│    Project 8600 · Project 8597                [View Details →]   │
└──────────────────────────────────────────────────────────────────┘
```
- Alerts appear in notification panel AND inline on the relevant widget
- Persistent alerts: stay visible until acknowledged
- Alert history/log: accessible from notification bell icon

### Conditional Formatting Rules
- Apply semantic colors to values that cross defined thresholds
- Show trend arrows (▲▼) with color for quick scanning
- Highlight table rows with subtle row tinting (never fill entire row with solid color)
- Always pair color with a secondary cue (icon or text label)

### In-Chart Threshold Lines
- Reference lines: dashed, 1px, `--text-tertiary` color
- Threshold annotation: small label at end of line
- Filled zone above/below threshold: 8% opacity of status color

### Construction Safety Specific Thresholds
| Condition | Treatment |
|---|---|
| Positive rate < 70% | Card gets 4px red left border + amber background tint |
| Any Risk Rating 4–5 | Danger badge, red accent, alert banner |
| High-risk count up vs prior period | Red trend arrow, red delta value |
| No observations in > 3 days | Info badge "No recent activity" |
| Risk Rating 3–5 table rows | Row background: `rgba(239,68,68,0.08)` subtle red tint |

---

## 17. Common Mistakes to Avoid

### Information Overload
- ❌ Putting every possible metric on one screen
- ✅ Limit to 5–7 primary KPIs; use drill-down for the rest
- ❌ Multiple charts at equal visual weight with no hierarchy
- ✅ Create clear hierarchy; one "hero" insight per section

### Wrong Chart Types
- ❌ Pie chart with 10+ slices
- ✅ Treemap or horizontal bar chart instead
- ❌ 3D bar/pie charts
- ✅ Flat, clean 2D charts always
- ❌ Line chart for categorical comparisons
- ✅ Bar chart for categories; line chart for time series only
- ❌ Dual Y-axes on the same chart
- ✅ Two separate charts with a shared X-axis

### Visual Design Mistakes
- ❌ Too many colors (rainbow charts)
- ✅ Max 5–7 colors; single color with varying shades when possible
- ❌ Truncated Y-axes starting at non-zero without disclosure
- ✅ Always start at 0, or clearly label the truncation
- ❌ Inconsistent color meaning (same color = different things on different charts)
- ✅ Assign colors to meanings globally via tokens and never deviate
- ❌ Hardcoded hex values in components
- ✅ Always use CSS custom property tokens

### UX / Layout Mistakes
- ❌ No empty states — blank space with no explanation
- ✅ Design intentional empty states for every possible scenario
- ❌ Filters that don't persist or aren't reflected in URL
- ✅ URL-serialized filter state for shareability
- ❌ No loading feedback (sudden appearance of data)
- ✅ Skeleton screens at correct dimensions immediately on load
- ❌ No "Reset filters" button — users get stuck in filtered views
- ✅ Always show clear filter reset when any filter is active
- ❌ Designing only for desktop
- ✅ Mobile-responsive or mobile-first design

### Data & Context Mistakes
- ❌ Metrics with no definition or calculation explanation
- ✅ Info tooltip (ℹ️) on every metric (definition + source)
- ❌ No timestamp showing data freshness
- ✅ "Last updated: X" always visible
- ❌ No target/benchmark alongside actuals
- ✅ Always show context: goal, previous period, or industry average
- ❌ Grouping unrelated metrics together
- ✅ Use logical grouping with clear section headers

### Accessibility Mistakes
- ❌ Color as the only differentiator in charts
- ✅ Labels, patterns, and icons alongside color
- ❌ Low contrast text (gray on white)
- ✅ Maintain WCAG AA 4.5:1 minimum everywhere
- ❌ Charts with no text alternative
- ✅ figcaption with key insight + "View as table" toggle for every chart

---

## 18. Modern Trends (2025–2026)

### AI-Powered Dashboards
- **Automated insights:** AI surfaces key anomalies and trends automatically above the charts
- **Natural language queries:** Users type "Show me top 5 projects by negative observations last quarter"
- **Predictive analytics:** Forecast lines shown alongside actuals with confidence interval shading
- **Anomaly detection:** Outliers automatically flagged with contextual explanation
- **Design implication:** Add AI insight panel, NLP search bar, forecast chart overlays

### Augmented Analytics
- **NLP search bar** above the dashboard for conversational data queries
- **Smart suggestions:** "You might also want to see..."
- **Design implication:** Prominent search bar, contextual recommendation cards below charts

### Personalization & Customization
- Users can rearrange, resize, add/remove widgets
- Role-based default views (executive vs. analyst vs. operator)
- Saved custom layouts per user
- Theme personalization (brand colors, logo)

### Glassmorphism & Layered Depth (Visual Trend)
- Frosted glass card effects: `backdrop-filter: blur(8px)` with semi-transparent background
- Subtle gradients and layered backgrounds
- Soft shadows replacing hard borders
- Use carefully — overdone glassmorphism kills readability

### Micro-Interactions & Motion
- Number count-up animations on KPI load (< 800ms)
- Chart bars/lines animate in on first render (< 500ms, easing)
- Smooth hover transitions (200ms ease)
- Skeleton shimmer for loading states
- Subtle card lift on hover: `transform: translateY(-1px)`

### Data Privacy & Security in UI
- **Role-Based Access Control (RBAC):** Hide or blur data the current user shouldn't see
- **Data masking:** Mask PII in shared or exported views
- **Audit trail:** "This data was last accessed by..." visible where relevant
- **Consent-aware displays:** GDPR/CCPA compliance indicators where required

### Embedded & White-Label Dashboards
- Dashboards embedded in other products (iframes, Web Components, SDK)
- Auto-theming to match host brand (logo, colors from parent app)
- Responsive embedding with `postMessage` communication
- Design for isolation: no external font/icon dependencies that could be blocked

### Trends to Avoid
- Excessive animation that delays data visibility or distracts from content
- Heavy gradients on chart bars (flat fills are more accurate visually)
- Cluttered "widget pickers" with 50+ chart types
- Auto-subscribing users to email alerts without explicit opt-in

---

## 19. Tech Stack & Implementation

### Recommended Frontend Frameworks
| Framework | Best For |
|---|---|
| React + TypeScript | Most SaaS dashboards; large ecosystem — **recommended** |
| Next.js | SSR/SSG dashboards, SEO-required |
| Vue 3 + Vite | Lighter weight, fast builds |
| SvelteKit | Performance-critical, minimal bundle size |

### UI Component Libraries
| Library | Style | Notes |
|---|---|---|
| shadcn/ui | Tailwind, headless | Highly customizable, copy-paste — **recommended** |
| Radix UI | Headless | Accessibility-first primitives |
| Ant Design (antd) | Material-ish | Enterprise dashboards, rich components |
| Chakra UI | Flexible | Good defaults, accessible |
| Mantine | Feature-rich | Charts + UI in one library |
| Material UI (MUI) | Material Design | Google-style, large ecosystem |

### Data Visualization Libraries
| Library | Best For | Notes |
|---|---|---|
| Recharts | React, standard charts | Simple, declarative — **recommended starting point** |
| Nivo | React, rich/animated | Beautiful defaults, D3-based |
| Tremor | React admin dashboards | Pre-built dashboard components |
| Chart.js | Any framework | Lightweight, CDN-friendly, wide chart types |
| ECharts (Apache) | Large datasets, maps | High performance — use for 1,000+ data points |
| D3.js | Custom visualizations | Maximum flexibility, steep learning curve |
| Observable Plot | Modern, composable | Excellent defaults, grammar of graphics |
| Vega-Lite | Statistical charts | Grammar of graphics approach |
| Plotly | Scientific / data science | Dash integration, complex charts |

**Recommendation:** Start with **Recharts** for standard bar/line/donut. Use **ECharts** for large datasets or advanced chart types.

### State Management & Data Fetching
| Tool | Use Case |
|---|---|
| TanStack Query (React Query) | Server state, caching, real-time — **recommended** |
| SWR | Lightweight stale-while-revalidate data fetching |
| Zustand | Client-side global state (filters, layout prefs) |
| Jotai | Atomic state for widget-level state |
| Redux Toolkit | Complex state with DevTools need |

### Real-Time Data Technologies
| Technology | Use Case |
|---|---|
| WebSockets | < 5s update frequency, bidirectional |
| Server-Sent Events (SSE) | Server-to-client streaming |
| HTTP Polling | Simple; appropriate for > 30s intervals |
| GraphQL Subscriptions | Real-time with a GraphQL API |

### CSS & Styling
| Tool | Notes |
|---|---|
| Tailwind CSS | Utility-first; excellent for dashboards |
| CSS Modules | Scoped styles without runtime |
| CSS Custom Properties | Essential for theming/dark mode (see Section 6) |
| PostCSS + autoprefixer | Browser compatibility |

### Testing
| Type | Tools |
|---|---|
| Unit | Vitest, Jest |
| Component | React Testing Library |
| End-to-End | Playwright, Cypress |
| Accessibility | axe-core, jest-axe |
| Visual Regression | Chromatic, Percy |
| Performance | Lighthouse CI, Web Vitals |

### Project File Structure
```
src/
├── components/
│   ├── dashboard/
│   │   ├── KPICard.tsx
│   │   ├── FilterBar.tsx
│   │   └── AlertBanner.tsx
│   ├── charts/
│   │   ├── ObservationsTrend.tsx
│   │   ├── ObservationsByProject.tsx
│   │   ├── RiskDistribution.tsx
│   │   └── PositiveNegativeDonut.tsx
│   ├── tables/
│   │   └── ObservationsTable.tsx
│   └── ui/
│       ├── Badge.tsx
│       ├── Card.tsx
│       ├── Skeleton.tsx
│       ├── Tooltip.tsx
│       └── EmptyState.tsx
├── hooks/
│   ├── useObservations.ts
│   ├── useFilters.ts
│   └── useDateRange.ts
├── styles/
│   ├── tokens.css          ← CSS custom properties (Section 6)
│   ├── typography.css
│   └── globals.css
├── types/
│   └── observations.ts
└── utils/
    ├── formatters.ts
    └── chartHelpers.ts
```

### TypeScript Data Model (Construction Safety)
```typescript
export type ObservationKind = 'Positive' | 'Negative';

export type ObservationCause =
  | 'Safe Act' | 'Safe Condition'
  | 'Unsafe Act' | 'Unsafe Condition' | 'Unsure';

export type ObservationType =
  | 'Equipment Related' | 'Physical Hazard' | 'Utility'
  | 'Administrative' | 'Struck By/Struck Against' | '';

export interface Observation {
  id: string;
  date: string;               // ISO 8601
  projectNumber: string;      // e.g. "8600"
  projectName: string;        // e.g. "QTS DUCTBANKS (RESTART)"
  kind: ObservationKind;
  cause: ObservationCause;
  type: ObservationType;
  riskRating: 0 | 1 | 2 | 3 | 4 | 5;
  description: string;
  recorder: string;
  foreman: string;
  time: string;
  attachments: string[];
}

export interface DashboardFilters {
  dateRange: { start: string; end: string };
  projects: string[];
  kinds: ObservationKind[];
  riskRatings: number[];
  types: ObservationType[];
  search: string;
}
```

### Utility Formatters
```typescript
export const formatCount = (n: number) =>
  new Intl.NumberFormat('en-US').format(n);

export const formatPercent = (n: number, decimals = 1) =>
  `${n.toFixed(decimals)}%`;

export const formatDelta = (n: number) =>
  `${n >= 0 ? '▲' : '▼'} ${Math.abs(n).toFixed(1)}%`;

export const getRiskColor = (rating: number): string => {
  if (rating <= 1) return 'var(--status-success)';
  if (rating <= 2) return 'var(--status-warning)';
  if (rating <= 4) return 'var(--status-danger)';
  return '#7C3AED';
};

export const getRiskLabel = (rating: number): string =>
  ['Safe', 'Low', 'Moderate', 'High', 'Very High', 'Critical'][rating] ?? 'Unknown';
```

---

## 20. Evaluation Checklist

Use this before shipping any dashboard. Every item should pass.

### Strategy & Content
- [ ] Dashboard has a clearly defined purpose and target user
- [ ] All displayed metrics are directly actionable
- [ ] KPIs limited to the most critical (≤ 7 primary)
- [ ] Every metric has a definition available (tooltip or docs)
- [ ] Data sources documented and disclosed
- [ ] Timestamp showing data freshness is visible
- [ ] Targets/benchmarks shown alongside actuals
- [ ] Context (period comparison, trend) provided for all values

### Visual Design
- [ ] Clear visual hierarchy (most important = most prominent)
- [ ] Color tokens used throughout (no hardcoded hex in components)
- [ ] All charts use the defined categorical palette in order
- [ ] Status colors (green/amber/red) used consistently
- [ ] Typography follows the defined scale
- [ ] 8px grid respected for all spacing and sizing
- [ ] No 3D charts, no misleading truncated axes
- [ ] Chart types match the data story being told
- [ ] Max 5–7 colors per chart; extras grouped as "Other"
- [ ] Whitespace used intentionally to create groupings

### KPI Cards
- [ ] Every KPI shows: value, label, trend vs prior period
- [ ] Trend indicator uses semantic color (green/red)
- [ ] ℹ️ tooltip provides metric definition
- [ ] Sparkline present where space allows

### Charts
- [ ] All charts have descriptive question-based titles
- [ ] All axes labeled with units
- [ ] Legend present for multi-series charts
- [ ] Tooltip present and informative on hover
- [ ] Y-axis starts at 0 (unless intentionally showing delta)
- [ ] Last-updated timestamp visible
- [ ] Empty state designed for no-data scenario
- [ ] "View as table" toggle available

### Tables
- [ ] Numbers right-aligned with thousands separator
- [ ] Text left-aligned
- [ ] Status fields use badge/pill components
- [ ] Columns sortable (arrow shows direction)
- [ ] Column resizing available
- [ ] Row hover highlight present
- [ ] Pagination or virtual scroll for large datasets
- [ ] Export (CSV) button present
- [ ] Column visibility toggle available

### Filters & Controls
- [ ] Date range picker has preset options (7D, 30D, 90D, YTD, Custom)
- [ ] Active filters shown as removable pills
- [ ] "Reset all" button visible when filters are active
- [ ] Filter state reflected in URL

### Accessibility
- [ ] All interactive elements keyboard-navigable
- [ ] Focus indicator visible (2px outline)
- [ ] Color contrast meets WCAG AA (4.5:1 body, 3:1 large text/graphics)
- [ ] Charts have aria-label and figcaption descriptions
- [ ] Tables have proper scope and caption attributes
- [ ] Status never conveyed by color alone (paired with icon/label)
- [ ] "View as table" toggle available for every chart
- [ ] aria-live regions for real-time updates
- [ ] Tested with axe DevTools (0 critical issues)

### Performance
- [ ] Initial page load < 2.5s (LCP)
- [ ] Skeleton screens shown within 200ms of navigation
- [ ] KPI cards load before charts
- [ ] Charts memoized; not re-rendering unnecessarily on unrelated filter changes
- [ ] Large tables use pagination or virtual scroll
- [ ] No layout shift when numbers update (tabular-nums applied)
- [ ] Bundle size within targets (< 200KB initial JS gzipped)

### Responsive Design
- [ ] Mobile (375px) — single column, 2-up KPI cards, all features functional
- [ ] Tablet (768px) — 2-column layout, collapsed sidebar
- [ ] Desktop (1280px) — full layout with sidebar
- [ ] Wide (1920px) — no unexpected layout breaks
- [ ] Touch targets ≥ 44px on mobile

### Dark Mode
- [ ] All colors reference CSS tokens (auto-switch works)
- [ ] Charts legible in dark mode
- [ ] No hardcoded white or light backgrounds in components
- [ ] Manual toggle present and preference persisted in localStorage
- [ ] No flash of wrong theme on page load

### Domain-Specific (Construction Safety)
- [ ] Risk ratings 3–5 are visually prominent and alarming
- [ ] Positive vs negative observations clearly distinguished throughout
- [ ] High-risk count KPI positioned prominently (first or second card)
- [ ] Alert banner appears when high-risk observations are present
- [ ] Project numbers and names both shown (not just one)
- [ ] Date of observation always visible in table view

---

## The 10 Golden Rules

1. **One key insight per section** — don't make users hunt for the story
2. **Top-left first** — most important information goes there
3. **Color = meaning** — assign colors to semantics globally and never deviate
4. **Every metric needs context** — delta, target, timestamp, definition
5. **Progressive disclosure** — summary first, detail on demand
6. **8px grid everywhere** — spacing, sizing, layout all multiples of 8
7. **Mobile-first** — if it works on mobile, it works everywhere
8. **Accessibility is not optional** — WCAG AA minimum, always
9. **Skeleton > spinner** — perceived performance matters as much as actual
10. **Test with real users** — 5 users will reveal 80% of usability issues

---

*Compiled from Carbon Design System (IBM), Material Design 3 (Google), UXPin, Toptal Design Blog, Brand.dev, LoopStudio, Mokkup.ai, and primary research on dashboard UX best practices. Last updated February 2026.*
