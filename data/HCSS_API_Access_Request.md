# HCSS API Access Request — Wollam Construction

**Prepared:** March 9, 2026
**Purpose:** Reference document for HCSS conversation about expanding API access
**Current Client Credentials Scopes:** `heavyjob:read timecards:read dis:read e360:read e360:timecards:read`
**Business Unit:** `MANAGER` / Wollam Construction (`319078ad-cbfe-49e7-a8b4-b62fe0be273d`)

---

## Background

We're building an internal estimating intelligence system (WEIS) that uses HCSS data to benchmark historical job performance for future bids. We've integrated the HeavyJob REST API and are pulling timecard data, cost codes, employees, pay items, and forecasts. However, several critical data points are either inaccessible or missing from the current API.

We probed every documented and discoverable endpoint across HeavyJob, HeavyBid, E360, and DIS/Setups APIs. Below is what we found and what we need.

---

## 1. HeavyBid API Access (Estimate Data) — TOP PRIORITY

**What we need:** Read access to the HeavyBid Estimate Insights API.

**Current state:** Every endpoint at `https://api.hcssapps.com/heavybid-estimate-insights` returns 404:
- `/api/v1/businessUnits` — 404
- `/api/v1/estimates` — 404
- `/api/v1/bidItems` — 404
- `/api/v1/activities` — 404
- `/api/v1/resources` — 404
- `/api/v1/materials` — 404
- `/api/v1/activityCodebook` — 404
- `/api/v1/materialCodebook` — 404

**What we're looking for:**
- Estimate records (bid date, total cost, total price, status)
- Bid items / pay items (owner line items with quantities and prices)
- Activities (cost buildup: labor, equipment, material, sub by activity)
- Resources (labor and equipment rate book — assumed rates per trade/equipment)
- Production rates (estimator's assumed crew productivity)

**Why it matters:** HeavyBid is the planned side. HeavyJob is the actual side. Comparing what the estimator assumed (HeavyBid) to what actually happened in the field (HeavyJob timecards) is the core of building better estimates. Without HeavyBid data, we can only look at actuals in isolation.

**Ask:** Enable the `heavybid-estimate-insights` scope (or equivalent) for our client credentials. Confirm which endpoints are available once enabled.

---

## 2. Actual Cost Dollars per Cost Code — CRITICAL GAP

**What we need:** Actual labor cost ($), equipment cost ($), material cost ($), and subcontract cost ($) per cost code.

**Current state:** The `/api/v1/costCodes` endpoint returns **budget** dollars only:
- `laborDollars` — budget labor cost
- `equipmentDollars` — budget equipment cost
- `materialDollars` — budget material cost
- `subcontractDollars` — budget subcontract cost

The timecard detail endpoint (`/api/v1/timeCards/{id}`) returns **hours** per employee per cost code, but no dollar amounts. We can calculate MH/unit (manhours per unit of production), but we cannot calculate actual $/unit without cost data.

**Endpoints we tried (all 404):**
- `/api/v1/costCodeProgress`
- `/api/v1/quantities`
- `/api/v1/installedQuantities`

**Questions:**
1. Is there an endpoint that returns actual cost by cost code (to-date labor $, equipment $, material $, sub $)?
2. Does the forecasts endpoint have a cost-code-level breakdown? Currently it only returns one job-level record.
3. If actual cost isn't available via REST API, is it available through HCSS Direct Access (SQL)?

**Why it matters:** Hours-based rates (MH/unit) are stable across time but don't capture cost. Dollar-based rates ($/unit) are critical for recent jobs (last 3-5 years) where material and labor rates are still relevant. Without actual cost data, we're estimating with only half the picture.

---

## 3. Pay Classes Endpoint — 403 Forbidden

**What we need:** Read access to `/api/v1/payClasses`.

**Current state:** Returns 403 Forbidden (both `/api/v1/payClasses` and `/api/v1/payclasses`).

**What this endpoint contains:** The pay class lookup table — trade codes (FORE, OPER, LAB, WELD, IRON, PIPE, CARP, etc.) mapped to descriptions and hourly wage rates.

**Why it matters:** We're already pulling trade codes from timecards (`payClassCode` field). If we had the pay class table with **hourly rates per trade**, we could calculate actual labor cost from hours even without a dedicated cost actuals endpoint. This is a potential workaround for item #2 above.

**Ask:** Add whatever scope controls `/api/v1/payClasses` read access to our client credentials.

---

## 4. HCSS Direct Access (SQL)

**What we need:** Read-only SQL access to the HeavyJob database.

**Why:** If the REST API doesn't expose actual cost data, Direct Access likely does. The underlying HeavyJob database contains everything — actual costs, change orders, daily logs, material receipts, subcontract records — that the REST API may not surface.

**What we'd query:**
- Actual cost by cost code (labor, equipment, material, subcontract dollars)
- Change order records (scope changes, design development, amounts, status)
- Material receipts (vendor, quantity, unit cost)
- Subcontract records (scope, contract amount, actual amount)
- Daily diary / daily log entries (weather, conditions, notes)
- Equipment roster with internal rates
- Pay class wage rate table

**Questions:**
1. Does our HCSS subscription include Direct Access, or is it a separate add-on?
2. If available, what's the connection method (ODBC, SQL Server, etc.)?
3. Can Direct Access be scoped to read-only?

---

## 5. Other Missing Endpoints (Lower Priority)

These all returned 404. We'd like access if available:

| Endpoint Attempted | Data | Estimating Value |
|---|---|---|
| `/api/v1/changeOrders` | Change orders by job | Track scope changes vs design development; CO risk analysis |
| `/api/v1/materials`, `/api/v1/materialEntries` | Material receipts | Material cost benchmarking by vendor, unit cost history |
| `/api/v1/subcontracts`, `/api/v1/subcontractors` | Subcontract records | Sub scope identification, cost tracking, performance |
| `/api/v1/dailyDiaries`, `/api/v1/dailies` | Daily logs | Weather impacts, site conditions, production notes |
| `/api/v1/equipment`, `/api/v1/equipments` | Equipment roster | Equipment list with internal ownership/rental rates |
| `/api/v1/safety`, `/api/v1/incidents` | Safety records | Safety performance by job type |
| `/api/v1/tags`, `/api/v1/notes`, `/api/v1/jobNotes` | Job metadata | Additional job context and categorization |

**Questions:**
1. Are any of these available under a different scope or endpoint path?
2. Are any of these planned for future API releases?

---

## 6. Rate Limit Increase

**Current behavior:** We hit 429 (Too Many Requests) after sustained use at ~1 request/second. The `Retry-After` header ranges from 1-60 seconds, and retrying during a penalty window extends the penalty.

**Our use case:** Syncing 197 jobs worth of timecard data. Large jobs have 1,500+ timecards, each requiring an individual detail fetch (`/api/v1/timeCards/{id}`). A full sync currently takes many hours across multiple runs due to rate limiting.

**Ask:** Increase our rate limit to 5-10 requests/second, or provide guidance on the optimal sustained request rate for bulk data pulls.

**Contact:** api-team@hcss.com

---

## Current Working Endpoints (For Reference)

These are the endpoints that currently work with our credentials:

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/v1/businessUnits` | GET | 200 | Returns 1 BU (Wollam Construction) |
| `/api/v1/jobs?businessUnitId={id}` | GET | 200 | 265 jobs, skip/take pagination |
| `/api/v1/employees?businessUnitId={id}` | GET | 200 | 500K+ records (all-time), filter to active |
| `/api/v1/payItems?businessUnitId={id}` | GET | 200 | 250K+ records, all jobs all-time |
| `/api/v1/costCodes?jobId={id}` | GET | 200 | Budget values only (no actuals) |
| `/api/v1/costCodes/search` | POST | 200 | Batch cost codes by jobIds |
| `/api/v1/timeCardInfo?jobId={id}` | GET | 200 | Timecard summaries, cursor pagination |
| `/api/v1/timeCards/{id}` | GET | 200 | Full detail (employees, equipment, cost codes) |
| `/api/v1/forecasts?businessUnitId={id}` | GET | 200 | Job-level forecasts (only 1 returned) |
| `/api/v1/payClasses` | GET | **403** | Forbidden — need additional scope |

### E360 (Equipment Mechanic Timecards)
| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/v2/timecards?businessUnitId={id}` | GET | 200 | Different BU ID than HeavyJob, minimal data |

---

## Summary — Priority Order

1. **HeavyBid API** — Unlocks planned-vs-actual comparison (the whole point of estimating intelligence)
2. **Actual cost per cost code** — The single biggest data gap in HeavyJob
3. **Pay classes (403 fix)** — Quick win, gives wage rates as a cost workaround
4. **Direct Access** — Fallback if REST API can't deliver cost data
5. **Rate limit increase** — Cuts sync time from hours to minutes
6. **Missing endpoints** — Change orders, materials, subs, daily logs
