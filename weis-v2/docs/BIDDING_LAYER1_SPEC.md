# WEIS v2 — Bidding Platform: Layer 1 Implementation Spec

**Feature:** Bid Board + Bid Schedule of Values + Document Management
**Date:** April 6, 2026
**Purpose:** Build the data model, API, and frontend for active bid project management — the container that all future agent intelligence (Layer 2) will attach to.

---

## Overview

This is an entirely new section of WEIS, separate from the existing historicals platform. The historicals section (Jobs, Estimates, Chat) provides reference intelligence from completed projects. The **Bidding** section is where active bid work happens — managing RFP packages, organizing documents, and structuring the bid schedule of values that becomes the backbone of the estimate.

Layer 1 focuses on three capabilities:
1. **Bid Board** — Create and manage active bid projects with deadlines
2. **Bid Schedule of Values** — Upload and parse owner bid schedules into structured line items, with AI-assisted parsing for messy formats and a pricing group (holding account) concept
3. **Document Management** — Upload, categorize, and organize RFP documents by addendum with text extraction

No AI agents or analysis in this layer — just solid data management and organization.

---

## What Already Exists in the Database

The following tables already exist in `database.py` (schema v2.7) and should be **reused and enhanced**, not recreated:

### `active_bids` — Needs minor column additions
```
Existing: id, bid_name, bid_number, owner, general_contractor, bid_date, project_type,
          location, estimated_value, status, notes, is_focus, created_at, updated_at
```
**Add columns:**
- `bid_due_time TEXT` — time of day bid is due (some owners specify exact time)
- `description TEXT` — brief project description
- `contact_name TEXT` — owner contact for questions
- `contact_email TEXT` — owner contact email

### `bid_documents` — Needs addendum tracking columns
```
Existing: id, bid_id, filename, file_type, file_size_bytes, doc_category, doc_label,
          extraction_status, extraction_warning, page_count, word_count, file_hash,
          version, supersedes_id, created_at
```
**Add columns:**
- `addendum_number INTEGER DEFAULT 0` — 0 = original package, 1+ = addendums
- `date_received DATE` — when this document was received from the owner
- `file_path TEXT` — stored file path on disk
- `extracted_text TEXT` — full extracted text (in addition to chunks)
- `notes TEXT` — user notes about this document

### `bid_document_chunks` — Exists, no changes needed
```
Existing: id, document_id, bid_id, chunk_index, chunk_text, section_heading, created_at
```

### `bid_sov_item` — Needs pricing group column
```
Existing: id, bid_id, item_number, description, quantity, unit, owner_amount,
          cost_code, discipline, mapped_by, unit_price, total_price, rate_source,
          rate_confidence, notes, sort_order, pm_quantity, pm_unit, quantity_status,
          quantity_notes, quantity_verified_at, created_at, updated_at
```
**Add column:**
- `pricing_group_id INTEGER REFERENCES pricing_group(id)` — for holding account grouping

### `bid_activity` — Exists, no changes needed for Layer 1

### New Table: `pricing_group`
```sql
CREATE TABLE IF NOT EXISTS pricing_group (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_id      INTEGER NOT NULL REFERENCES active_bids(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pricing_group_bid ON pricing_group(bid_id);
```

---

## API Endpoints — New Router: `app/api/bidding.py`

Create a new API router at `/api/bidding` (do NOT modify the existing `estimates.py` which serves HeavyBid historicals).

### Bid CRUD
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/bidding/bids` | List all bids (with optional status filter) |
| `POST` | `/api/bidding/bids` | Create a new bid project |
| `GET` | `/api/bidding/bids/{bid_id}` | Get bid detail (with doc count, SOV item count) |
| `PUT` | `/api/bidding/bids/{bid_id}` | Update bid fields |
| `DELETE` | `/api/bidding/bids/{bid_id}` | Delete bid and all children (CASCADE) |

### Document Management
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/bidding/bids/{bid_id}/documents` | Upload document(s) with metadata (addendum_number, doc_category, date_received) |
| `GET` | `/api/bidding/bids/{bid_id}/documents` | List documents (filterable by addendum_number, doc_category) |
| `GET` | `/api/bidding/documents/{doc_id}` | Get single document detail including extracted text |
| `PUT` | `/api/bidding/documents/{doc_id}` | Update document metadata (category, label, addendum, notes) |
| `DELETE` | `/api/bidding/documents/{doc_id}` | Delete document and its chunks |

**Document categories:** `spec`, `drawing`, `contract`, `bid_schedule`, `rfi_clarification`, `addendum_package`, `bond_form`, `insurance`, `general`

**Supported file types:** `.pdf`, `.xlsx`, `.xls`, `.csv`, `.txt`, `.docx`, `.doc` (extend the existing ALLOWED_EXTENSIONS)

**File storage:** Store uploaded files in `data/bid_documents/{bid_id}/` (new directory, separate from the existing `data/documents/` used by historicals)

**Text extraction:** Reuse `app/services/document_extract.py` (already handles PDF, Excel, CSV, TXT). Add `.docx` support if not present.

### Bid Schedule of Values
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/bidding/bids/{bid_id}/sov/upload` | Upload bid schedule file → AI parse → return structured preview |
| `POST` | `/api/bidding/bids/{bid_id}/sov/confirm` | Confirm parsed items → save to bid_sov_item |
| `GET` | `/api/bidding/bids/{bid_id}/sov` | Get all SOV items for a bid |
| `POST` | `/api/bidding/bids/{bid_id}/sov` | Manually add a SOV item |
| `PUT` | `/api/bidding/sov/{item_id}` | Update a SOV item |
| `DELETE` | `/api/bidding/sov/{item_id}` | Delete a SOV item |
| `PUT` | `/api/bidding/sov/reorder` | Reorder SOV items (batch sort_order update) |

### Pricing Groups (Holding Accounts)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/bidding/bids/{bid_id}/groups` | Create a pricing group |
| `GET` | `/api/bidding/bids/{bid_id}/groups` | List pricing groups for a bid |
| `PUT` | `/api/bidding/groups/{group_id}` | Update group name/description |
| `DELETE` | `/api/bidding/groups/{group_id}` | Delete group (nullify items' pricing_group_id) |
| `POST` | `/api/bidding/groups/{group_id}/assign` | Assign SOV items to a group (body: list of item_ids) |
| `POST` | `/api/bidding/groups/{group_id}/unassign` | Remove SOV items from a group |

---

## Service: AI Bid Schedule Parser — `app/services/sov_parser.py`

This service handles the messy-format-to-structured-data conversion for bid schedules.

### Flow
1. Accept uploaded file (Excel, PDF, Word, CSV, TXT)
2. Extract raw text/table content using existing `document_extract.py`
3. Send to Claude API with a specialized prompt that:
   - Identifies bid schedule line items from any format
   - Extracts: item_number, description, unit, quantity for each line item
   - Handles multi-format chaos (merged cells, nested headers, multi-page tables)
   - Returns a clean JSON array of parsed items
4. Return the parsed items as a preview for user review
5. On confirmation, save to `bid_sov_item` table

### Claude Prompt Strategy
The prompt should explain that this is a construction bid schedule of values from an owner's RFP. The expected output is a JSON array where each object has `item_number`, `description`, `unit`, `quantity`. The AI should:
- Ignore header rows, totals rows, and formatting artifacts
- Preserve the owner's item numbering exactly as written
- Extract units as-is (LS, LF, CY, EA, SF, TON, etc.)
- Extract quantities as numbers (strip commas, handle blank = null)
- Skip any pricing columns (we don't need owner's budget amounts)

Use Claude Haiku for cost efficiency since this is a structured extraction task.

---

## Frontend — New Bidding Section

### Sidebar Navigation
Add a new nav item: **"Bidding"** (between Estimates and Chat, or wherever it fits the flow). Uses a gavel icon or briefcase icon.

### Page: Bid Board (`page === 'bidding'`)
A card-based or table view showing all active bids.

**Each bid card shows:**
- Bid name (prominent)
- Owner name
- Bid due date (with countdown: "Due in 12 days" or "OVERDUE" in red)
- Status badge (Active, Submitted, No-Bid, Awarded)
- Document count and SOV item count as small stats
- Click → navigates to bid detail

**Actions:**
- "New Bid" button → modal or inline form to create a bid
- Filter by status
- Sort by due date (default: soonest first)

### Page: Bid Detail (`page === 'bidding' && bidId`)
Tabbed interface inside a bid project:

**Tab 1: Overview**
- Editable bid info (name, owner, due date, location, description, status)
- Summary stats: X documents, Y schedule items, Z pricing groups

**Tab 2: Schedule of Values**
- Table showing all SOV items: item_number, description, unit, quantity, pricing group
- "Upload Schedule" button → file picker → shows AI-parsed preview → confirm/edit → save
- "Add Item" button for manual entry
- Inline editing of items
- Drag-to-reorder or sort controls
- Pricing group column: click to assign/create groups
- Color-code rows by pricing group
- Items within the same group get a visual indicator (colored dot, matching background tint)

**Tab 3: Documents**
- Document library with upload area (drag-and-drop zone at the top)
- Upload form captures: file(s), addendum number, doc category, date received
- Document list grouped by addendum (Addendum 0 = Original Package, Addendum 1, 2, 3...)
- Each document shows: filename, category badge, date received, page/word count, extraction status
- Click document → expands to show extracted text preview
- Edit metadata (category, notes)
- Delete with confirmation

### Design Notes
- Follow the Wollam design system defined in `docs/DESIGN_SYSTEM.md` and `docs/RESKIN_SKILL_REFERENCE.md`
- Match the existing UI patterns in `static/app.js` and `static/styles.css`
- Use the same `api()` helper, `navigate()` pattern, and `state` object
- Cards should use the existing card styling (`.card` class with `--glass-bg`, `--shadow-sm`, etc.)
- Status badges should use the existing badge patterns
- Document upload area: dashed border, icon, "Drag files here or click to upload"
- Keep it consistent with the rest of the app — this should feel like a natural extension, not a bolt-on

---

## Database Migration

Add migration `_migrate_2_7_to_2_8` in `database.py`:

1. Add new columns to `active_bids`: `bid_due_time`, `description`, `contact_name`, `contact_email`
2. Add new columns to `bid_documents`: `addendum_number`, `date_received`, `file_path`, `extracted_text`, `notes`
3. Create `pricing_group` table
4. Add `pricing_group_id` column to `bid_sov_item`
5. Update `SCHEMA_VERSION` to `"2.8"`
6. Add the migration to the `init_db()` chain

---

## Config Updates

In `app/config.py`, add:
```python
BID_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "bid_documents"
```

---

## File Storage

Create `data/bid_documents/` directory structure:
```
data/bid_documents/
└── {bid_id}/
    ├── original_package/    # (optional subfolder organization)
    └── uploaded files...
```

For simplicity in Layer 1, just store flat in `data/bid_documents/{bid_id}/filename`.

---

## Router Registration

In `app/main.py`, add:
```python
from app.api.bidding import router as bidding_router
app.include_router(bidding_router)
```

---

## Testing

Create `tests/test_bidding.py` with tests for:
1. Bid CRUD (create, list, get, update, delete)
2. Document upload and metadata
3. SOV item CRUD and reorder
4. Pricing group CRUD and assignment
5. SOV upload/parse endpoint (mock the Claude API call)

---

## What This Does NOT Include (Layer 2+)
- No AI agent analysis of documents
- No addendum diffing
- No Chief Estimator chat
- No sub package generation
- No connection to historical data from Phase 1
- No intelligent document categorization

These all come in Layer 2 and build on the container we're creating here.
