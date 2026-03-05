"""Home / Bid Dashboard — project selector + bid management."""

import hashlib

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui.components import (
    page_header, metric_card, section_header, empty_state,
    confirm_dialog, status_badge, bid_status_color,
)
from app.ui import state
from app import query
from app.doc_processing import extract_document, chunk_text
from app.database import get_connection


STATUS_OPTIONS = ["active", "awarded", "lost", "no_bid", "archived"]
DOC_CATEGORIES = ["general", "rfp", "addendum", "specification", "scope", "bid_form", "schedule"]


def _get_kb_stats():
    try:
        conn = get_connection()
        try:
            rl = conn.execute("SELECT COUNT(*) as cnt FROM rate_library").fetchone()["cnt"]
            jobs = conn.execute(
                "SELECT COUNT(DISTINCT source_jobs) as cnt FROM rate_library WHERE source_jobs IS NOT NULL"
            ).fetchone()["cnt"]
            return rl, jobs
        finally:
            conn.close()
    except Exception:
        return 0, 0


def _get_bid_stats(bid_id):
    """Get quick stats for a bid card (non-dollar)."""
    try:
        sov = query.get_sov_summary(bid_id)
        items = sov.get("total_items", 0) if sov else 0
    except Exception:
        items = 0
    try:
        rollup = query.get_bid_activity_rollup(bid_id)
        activities = rollup.get("total_activities", 0) if rollup else 0
    except Exception:
        activities = 0
    return items, activities


@ui.page("/")
async def home_page():
    state.set("current_path", "/")
    page_layout("WEIS")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("WEIS", "Wollam Estimating Intelligence System")

        # KPI row
        rl_count, _ = _get_kb_stats()
        with ui.row().classes("w-full").style("gap: 1rem"):
            try:
                overview = query.get_database_overview()
                counts = overview.get("record_counts", {})
                with ui.column().classes("flex-1"):
                    metric_card("Projects", counts.get("projects", 0), icon="business")
                with ui.column().classes("flex-1"):
                    metric_card("Total Records", f"{sum(counts.values()):,}", icon="storage")
                with ui.column().classes("flex-1"):
                    metric_card("KB Rates", rl_count, icon="library_books")
                with ui.column().classes("flex-1"):
                    bids = query.get_active_bids()
                    metric_card("Active Bids", len(bids) if bids else 0, icon="gavel")
            except Exception:
                bids = []

        ui.separator()

        # ═══ Active Bids ═══
        section_header("Active Bids", "Select a bid to enter its workspace")

        # Create New Bid
        _render_create_bid()

        # Bid Cards
        try:
            bids = query.get_active_bids()
        except Exception:
            bids = []

        if not bids:
            empty_state("No active bids yet. Create one above to get started.", icon="gavel")
            return

        with ui.row().classes("w-full flex-wrap").style("gap: 1rem"):
            for bid in bids:
                _render_bid_card(bid)


def _render_create_bid():
    """Render the create bid expansion panel."""
    with ui.expansion("Create New Bid", icon="add_circle").classes("w-full"):
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full").style("gap: 1rem"):
                with ui.column().classes("flex-1").style("gap: 0.5rem"):
                    name_in = ui.input("Bid Name *", placeholder="e.g., Acme Industrial Expansion") \
                        .classes("w-full")
                    number_in = ui.input("Bid Number", placeholder="e.g., 8610") \
                        .classes("w-full")
                    owner_in = ui.input("Owner", placeholder="e.g., Acme Corp") \
                        .classes("w-full")
                    gc_in = ui.input("General Contractor", placeholder="e.g., Kiewit") \
                        .classes("w-full")
                with ui.column().classes("flex-1").style("gap: 0.5rem"):
                    date_in = ui.input("Bid Date", placeholder="YYYY-MM-DD") \
                        .classes("w-full")
                    type_in = ui.input("Project Type", placeholder="e.g., Industrial") \
                        .classes("w-full")
                    loc_in = ui.input("Location", placeholder="e.g., Salt Lake City, UT") \
                        .classes("w-full")
                    value_in = ui.number("Estimated Value ($)", value=0, min=0, step=100000) \
                        .classes("w-full")

            def create():
                if not name_in.value:
                    ui.notify("Bid name is required", type="warning")
                    return
                bid_id = query.create_active_bid(
                    bid_name=name_in.value,
                    bid_number=number_in.value or None,
                    owner=owner_in.value or None,
                    general_contractor=gc_in.value or None,
                    bid_date=date_in.value or None,
                    project_type=type_in.value or None,
                    location=loc_in.value or None,
                    estimated_value=value_in.value if value_in.value and value_in.value > 0 else None,
                )
                ui.notify(f"Created bid: {name_in.value} (ID: {bid_id})", type="positive")
                ui.navigate.to("/")

            ui.button("Create Bid", icon="add", on_click=create) \
                .props("color=primary").classes("q-mt-sm")


def _render_bid_card(bid):
    """Render a single bid card with stats and workspace entry."""
    bid_id = bid["id"]
    status = bid.get("status", "active")
    color = bid_status_color(status)
    items, activities = _get_bid_stats(bid_id)
    doc_count = bid.get("doc_count", 0)

    with ui.card().classes("q-pa-md").style("min-width: 320px; max-width: 480px; flex: 1 1 380px"):
        # Header row: name + status badge
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(bid["bid_name"]).classes("text-subtitle1 text-weight-bold")
            status_badge(status.upper(), color)

        # Metadata line
        meta_parts = []
        if bid.get("owner"):
            meta_parts.append(bid["owner"])
        if bid.get("general_contractor"):
            meta_parts.append(bid["general_contractor"])
        if bid.get("bid_date"):
            meta_parts.append(bid["bid_date"])
        if meta_parts:
            ui.label(" \u00b7 ".join(meta_parts)).classes("text-caption text-grey-7")

        # Stats row
        with ui.row().classes("q-mt-sm").style("gap: 1.5rem"):
            with ui.column().classes("gap-0 items-center"):
                ui.label(str(items)).classes("text-body1 text-weight-bold")
                ui.label("Bid Items").classes("text-caption text-grey-6")
            with ui.column().classes("gap-0 items-center"):
                ui.label(str(activities)).classes("text-body1 text-weight-bold")
                ui.label("Activities").classes("text-caption text-grey-6")
            with ui.column().classes("gap-0 items-center"):
                ui.label(str(doc_count)).classes("text-body1 text-weight-bold")
                ui.label("Documents").classes("text-caption text-grey-6")

        # Action buttons
        with ui.row().classes("q-mt-md w-full").style("gap: 0.5rem"):
            def enter_workspace(bid_id=bid_id):
                query.set_focus_bid(bid_id)
                ui.navigate.to("/bid-sov")

            ui.button("Enter Workspace", icon="arrow_forward", on_click=enter_workspace) \
                .props("color=primary")

            # Manage expansion
            with ui.expansion("Manage", icon="settings").classes("flex-1"):
                _render_bid_manage(bid)


def _render_bid_manage(bid):
    """Render bid management controls: docs, status, delete."""
    bid_id = bid["id"]
    status = bid.get("status", "active")

    # ═══ Document List ═══
    docs = query.get_bid_documents(bid_id)
    if docs:
        ui.label("Documents").classes("text-weight-bold text-body2")
        for doc in docs:
            ext_status = doc.get("extraction_status", "pending")
            icon = {"success": "check_circle", "partial": "info", "failed": "error", "pending": "hourglass_top"} \
                .get(ext_status, "hourglass_top")
            icon_color = {"success": "text-green-9", "partial": "text-amber-9",
                          "failed": "text-red-9"}.get(ext_status, "text-grey-6")
            cat = doc.get("doc_category", "general")
            label = doc.get("doc_label", "")
            words = doc.get("word_count") or 0

            with ui.row().classes("w-full items-center").style("gap: 0.5rem"):
                ui.icon(icon).classes(f"text-sm {icon_color}")
                ui.label(f"{doc['filename']} [{cat}]" + (f" \u2014 {label}" if label else "")) \
                    .classes("text-body2 flex-1")
                ui.label(f"{words:,} words").classes("text-caption text-grey-6")
                if doc.get("extraction_warning"):
                    ui.icon("warning").classes("text-sm text-amber-9") \
                        .tooltip(doc["extraction_warning"][:100])

                def make_doc_delete(doc_id):
                    def handler():
                        query.delete_bid_document(doc_id)
                        ui.navigate.to("/")
                    return handler

                ui.button(icon="delete", on_click=make_doc_delete(doc["id"])) \
                    .props("flat round size=xs color=negative")

    # ═══ Upload Documents ═══
    ui.label("Upload Documents").classes("text-weight-bold text-body2 q-mt-md")

    uploaded_files_data = {"files": []}
    cat_select = ui.select(DOC_CATEGORIES, value="general", label="Category") \
        .classes("w-40")
    label_input = ui.input("Label (optional)", placeholder="e.g., Division 03 Concrete") \
        .classes("w-64")

    def on_upload(e):
        content = e.content.read()
        uploaded_files_data["files"].append({
            "name": e.name,
            "bytes": content,
        })
        ui.notify(f"Added {e.name}", type="info")

    ui.upload(
        label="Upload (PDF, DOCX, XLSX, MD, TXT)",
        multiple=True,
        auto_upload=True,
        on_upload=on_upload,
    ).props("accept=.pdf,.docx,.xlsx,.md,.txt").classes("w-full")

    async def process_files():
        files = uploaded_files_data["files"]
        if not files:
            ui.notify("No files to process", type="warning")
            return

        n = ui.notification("Processing documents...", spinner=True, timeout=None)
        replaced = 0
        new = 0

        for f in files:
            file_bytes = f["bytes"]
            ext = f["name"].rsplit(".", 1)[-1].lower() if "." in f["name"] else "txt"
            file_hash = hashlib.sha256(file_bytes).hexdigest()

            existing = query.find_document_by_filename(bid_id, f["name"])
            result = await run.io_bound(extract_document, file_bytes, f["name"])

            if existing and existing.get("file_hash") == file_hash:
                continue

            if existing:
                old_version = existing.get("version", 1) or 1
                doc_id = query.replace_bid_document(
                    old_doc_id=existing["id"], bid_id=bid_id,
                    filename=f["name"], file_type=ext,
                    file_size_bytes=len(file_bytes), file_hash=file_hash,
                    doc_category=cat_select.value,
                    doc_label=label_input.value or None,
                    extraction_status=result["status"],
                    extraction_warning=result.get("warning"),
                    page_count=result.get("page_count"),
                    word_count=result["word_count"],
                    old_version=old_version,
                )
                replaced += 1
            else:
                doc_id = query.insert_bid_document(
                    bid_id=bid_id, filename=f["name"], file_type=ext,
                    file_size_bytes=len(file_bytes),
                    doc_category=cat_select.value,
                    doc_label=label_input.value or None,
                    extraction_status=result["status"],
                    extraction_warning=result.get("warning"),
                    page_count=result.get("page_count"),
                    word_count=result["word_count"],
                )
                conn = get_connection()
                try:
                    conn.execute("UPDATE bid_documents SET file_hash = ? WHERE id = ?",
                                 (file_hash, doc_id))
                    conn.commit()
                finally:
                    conn.close()
                new += 1

            if result["status"] in ("success", "partial") and result["text"].strip():
                chunks = chunk_text(result["text"])
                if chunks:
                    query.insert_bid_chunks(doc_id, bid_id, chunks)

        n.dismiss()
        parts = []
        if new:
            parts.append(f"{new} new")
        if replaced:
            parts.append(f"{replaced} updated")
        ui.notify(
            f"Processed {len(files)} file(s) ({', '.join(parts) if parts else 'all skipped'})",
            type="positive",
        )
        uploaded_files_data["files"] = []
        ui.navigate.to("/")

    ui.button("Process Files", icon="cloud_upload", on_click=process_files) \
        .props("color=primary").classes("q-mt-sm")

    ui.separator().classes("my-3")

    # ═══ Status + Delete ═══
    with ui.row().classes("items-center").style("gap: 0.5rem"):
        def make_status_handler(bid_id):
            def handler(e):
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE active_bids SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (e.value, bid_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                ui.navigate.to("/")
            return handler

        ui.select(STATUS_OPTIONS, value=status, label="Status",
                  on_change=make_status_handler(bid_id)) \
            .classes("w-32")

        def make_delete(b):
            def do_delete():
                query.delete_bid_cascade(b["id"])
                ui.notify(f"Deleted {b['bid_name']}", type="positive")
                ui.navigate.to("/")
            return do_delete

        dialog = confirm_dialog(
            f"Delete {bid['bid_name']} and all its documents?",
            make_delete(bid),
        )
        ui.button("Delete", icon="delete", on_click=dialog.open) \
            .props("color=negative outline size=sm")
