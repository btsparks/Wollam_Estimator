# Dropbox-Linked Bidding — Architecture Spec

**Date:** April 6, 2026
**Status:** Approved for implementation
**Authors:** Travis Sparks & Claude (Brainstorm Session)

---

## The Change

Replace the manual drag-and-drop document upload system for active bids with a Dropbox folder link. Each bid is tied to its Dropbox estimating folder by bid number. The system scans that folder on demand (via a "Sync Now" button) and automatically discovers, categorizes, extracts, and tracks all documents — including detecting new files, modified files, and removed files between syncs.

## Why This Is Better

1. **Eliminates dual maintenance.** Estimators already put files in Dropbox because that's where the team collaborates. The old approach required them to separately upload those same files into WEIS. Now WEIS stays current automatically.

2. **Addendum tracking becomes automatic.** Folder structure and naming conventions tell the system which addendum a file belongs to, rather than requiring manual tagging on every upload.

3. **Agents get a live feed.** When Layer 2 agents are built, they can re-analyze whenever files change — triggered by a sync rather than waiting for someone to remember to re-upload.

4. **Leverages existing infrastructure.** The Phase 1 Dropbox scanner (`app/services/dropbox_scanner.py`) already knows how to walk folders, categorize files by path, track modification timestamps, and extract text. This adapts that proven logic for active bids.

---

## Dropbox Folder Convention

Every bid at Wollam gets an estimate number. That estimate number IS the Dropbox folder identifier. The estimating folders live under a known root within the Wollam Dropbox:

```
C:\Users\Travis Sparks\Dropbox (Wollam)\
  └── Estimating\              ← WEIS_ESTIMATING_ROOT (new config var)
      ├── 2847 - Rio Tinto Boron\
      │   ├── Specifications\
      │   ├── Drawings\
      │   ├── Addendum 1\
      │   ├── Addendum 2\
      │   ├── Contract\
      │   ├── RFIs\
      │   └── Bid Schedule.xlsx
      ├── 2848 - Chevron El Segundo\
      │   └── ...
      └── 2849 - Northrop Grumman\
          └── ...
```

The bid number (e.g., "2847") maps directly to the folder prefix. When a bid is created in WEIS with `bid_number = "2847"`, the system resolves the Dropbox folder path by scanning `WEIS_ESTIMATING_ROOT` for a folder starting with "2847".

---

## Data Model Changes

### `active_bids` table — add columns:

```sql
ALTER TABLE active_bids ADD COLUMN dropbox_folder_path TEXT;  -- resolved path to the Dropbox folder
ALTER TABLE active_bids ADD COLUMN last_synced_at DATETIME;   -- timestamp of most recent folder sync
ALTER TABLE active_bids ADD COLUMN sync_status TEXT DEFAULT 'never';  -- 'never', 'syncing', 'complete', 'error'
```

### `bid_documents` table — add column:

```sql
ALTER TABLE bid_documents ADD COLUMN dropbox_path TEXT;  -- original Dropbox file path (source of truth)
ALTER TABLE bid_documents ADD COLUMN sync_action TEXT;   -- 'new', 'updated', 'unchanged', 'removed' (from last sync)
```

### No new tables required

The existing `bid_documents` table already has everything needed: `file_hash`, `file_path`, `addendum_number`, `doc_category`, `extracted_text`, `extraction_status`, `version`, `supersedes_id`. The sync engine populates these fields automatically instead of the upload endpoint doing it manually.

---

## New Config Variable

In `app/config.py`:

```python
# Dropbox Estimating folder root (for bid folder linking)
ESTIMATING_ROOT = Path(os.getenv(
    "WEIS_ESTIMATING_ROOT",
    DROPBOX_ROOT / "Estimating"
))
```

The exact path may need adjustment based on Travis's actual Dropbox folder structure. The `.env.example` should document this.

---

## New Service: `app/services/bid_sync.py`

This is the core sync engine. It adapts logic from the existing `dropbox_scanner.py` for the bidding context.

### Key Functions:

**`resolve_bid_folder(bid_number: str) -> Path | None`**
- Scans `ESTIMATING_ROOT` for a folder whose name starts with the bid number
- Uses regex: `^{bid_number}\s*-\s*` to match "2847 - Rio Tinto Boron"
- Returns the full path, or None if not found
- Called when a bid is created or when manually linking a bid to a folder

**`sync_bid_documents(bid_id: int) -> SyncResult`**
- Reads `dropbox_folder_path` from the bid record
- Walks the folder recursively for all extractable files
- For each file found:
  - Calculates SHA256 hash
  - Checks if already in `bid_documents` by `dropbox_path`
  - **New file:** Insert into `bid_documents`, extract text, set `sync_action = 'new'`
  - **Modified file** (hash changed): Re-extract text, increment version, set `sync_action = 'updated'`, optionally create supersedes chain
  - **Unchanged file** (hash matches): Set `sync_action = 'unchanged'`, skip extraction
- After walking: any `bid_documents` records whose `dropbox_path` no longer exists on disk get marked `sync_action = 'removed'`
- Auto-categorizes using folder structure (adapts `_categorize_file()` from dropbox_scanner)
- Auto-detects addendum number from folder path (e.g., "Addendum 1" → `addendum_number = 1`)
- Updates `last_synced_at` and `sync_status` on the bid record
- Returns a `SyncResult` with counts: new, updated, unchanged, removed

**`categorize_bid_file(rel_path: str, file_name: str) -> tuple[str, int]`**
- Returns `(doc_category, addendum_number)`
- Adapts the existing `_categorize_file()` logic from dropbox_scanner.py
- Additionally parses addendum folder names: "Addendum 1", "ADD-1", "Addendum #2", etc.
- Maps folder names to `DOC_CATEGORIES`: spec, drawing, contract, bid_schedule, rfi_clarification, addendum_package, bond_form, insurance, general

---

## API Changes: `app/api/bidding.py`

### New Endpoints:

**`POST /api/bidding/bids/{bid_id}/sync`** — Trigger a Dropbox folder sync
- Calls `sync_bid_documents(bid_id)`
- Returns the `SyncResult` (counts of new/updated/unchanged/removed)
- Sets `sync_status = 'syncing'` at start, `'complete'` or `'error'` at end

**`POST /api/bidding/bids/{bid_id}/link-folder`** — Manually link/resolve a Dropbox folder
- Body: `{ "bid_number": "2847" }` (or uses the bid's existing `bid_number`)
- Calls `resolve_bid_folder()` to find the path
- Updates `dropbox_folder_path` on the bid record
- Returns the resolved path or 404 if not found

**`GET /api/bidding/bids/{bid_id}/sync-status`** — Check sync state
- Returns `{ sync_status, last_synced_at, document_counts: { new, updated, unchanged, removed, total } }`

### Modified Behavior:

**`POST /api/bidding/bids` (Create Bid)** — Auto-resolve folder
- When a bid is created with a `bid_number`, automatically attempt to resolve the Dropbox folder
- If found, set `dropbox_folder_path` on creation
- If not found, leave it null (can be linked manually later)
- Do NOT auto-sync on creation — the user triggers that explicitly

**Document upload endpoint stays but becomes secondary.**
- Keep `POST /api/bidding/bids/{bid_id}/documents` for manual uploads (files not in Dropbox)
- Synced documents have `dropbox_path` populated; manually uploaded ones don't
- The UI should make it clear which documents came from Dropbox sync vs. manual upload

---

## Frontend Changes: `static/app.js`

### Documents Tab Updates:

1. **Sync button** at the top of the Documents tab: "Sync from Dropbox" with a refresh icon
   - Shows spinner while syncing
   - On completion, shows summary: "Found 3 new files, 1 updated, 12 unchanged"
   - Refreshes the document list

2. **Last synced timestamp** displayed next to the sync button
   - Format: "Last synced: April 6, 2026 at 2:34 PM" or "Never synced"

3. **Sync action badges** on each document row
   - New files: green "NEW" badge (for the most recent sync)
   - Updated files: amber "UPDATED" badge
   - Removed files: red "REMOVED" badge (shown but greyed out)

4. **Folder link indicator** on the bid overview tab
   - Shows the linked Dropbox folder path (truncated, with tooltip for full path)
   - If no folder linked: shows "No Dropbox folder linked" with a "Link Folder" button
   - "Link Folder" button calls the resolve endpoint using the bid number

5. **Keep drag-and-drop** as a fallback for files outside Dropbox
   - Manual uploads appear in the list without a `dropbox_path`
   - Visually distinguished (e.g., "Manually uploaded" tag)

### Bid Creation Dialog:

- When `bid_number` is entered, show a note: "Will auto-link to Dropbox estimating folder {bid_number}"
- After creation, if folder was found, show confirmation: "Linked to: Estimating/2847 - Rio Tinto Boron"
- If not found, show info: "No matching Dropbox folder found. You can link one manually later."

---

## What This Replaces

The primary document management flow shifts from:
1. ~~Estimator downloads files from Dropbox~~
2. ~~Estimator drags files into WEIS~~
3. ~~Estimator manually tags addendum numbers~~
4. ~~Estimator manually categorizes each file~~

To:
1. Estimator creates bid with bid number in WEIS
2. Folder auto-links (or they click "Link Folder")
3. Estimator clicks "Sync from Dropbox"
4. WEIS scans the folder, categorizes everything, extracts text, detects addendums
5. When new documents arrive (owner sends addendum), estimator clicks Sync again

---

## What This Does NOT Change

- **`bid_documents` table schema** — stays as-is, just gets two new columns (`dropbox_path`, `sync_action`)
- **Text extraction pipeline** — same `extract_text()` function, same chunking
- **SOV parsing** — unchanged (still upload an Excel and parse it)
- **Pricing groups** — unchanged
- **Agent reports** — unchanged (agents will eventually trigger on sync events)
- **Document detail endpoint** — unchanged (still serves extracted text)
- **Manual upload** — preserved as fallback

---

## Future Enhancements (Not in This Implementation)

- **Auto-sync on timer** — poll every N minutes while a bid is active (requires background task infrastructure)
- **Dropbox webhooks** — real-time notification when files change (requires Dropbox API credentials and a server)
- **Document diffing** — when a file is updated, automatically diff the old and new extracted text and summarize changes (this is Layer 2 Document Control agent territory)
- **Agent trigger on sync** — when sync detects new/updated files, automatically queue relevant agent re-analysis
