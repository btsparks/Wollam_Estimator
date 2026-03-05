"""Active Bids page — bid CRUD + doc upload."""

import hashlib

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui import state
from app.ui.components import (
    page_header, metric_card, section_header, empty_state,
    confirm_dialog, status_badge, bid_status_color,
)
from app import query
from app.doc_processing import extract_document, chunk_text
from app.database import init_db, get_connection


STATUS_OPTIONS = ["active", "awarded", "lost", "no_bid", "archived"]
DOC_CATEGORIES = ["general", "rfp", "addendum", "specification", "scope", "bid_form", "schedule"]


@ui.page("/active-bids")
async def active_bids_page():
    state.set("current_path", "/active-bids")
    page_layout("Active Bids")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Active Bids", "Manage active bids, upload bid documents, and set the focus bid")

        # ═══ Create New Bid ═══
        _render_create_bid()

        ui.separator()

        # ═══ Bid Cards ═══
        try:
            bids = query.get_active_bids()
        except Exception:
            bids = []

        if not bids:
            empty_state("No active bids yet. Create one above to get started.",
                        icon="gavel")
            return

        ui.label(f"{len(bids)} Active Bid{'s' if len(bids) != 1 else ''}") \
            .classes("text-h6 text-weight-bold")

        for bid in bids:
            _render_bid_card(bid)


def _render_create_bid():
    """Render the create bid form."""
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
                ui.navigate.to("/active-bids")

            ui.button("Create Bid", icon="add", on_click=create) \
                .props("color=primary").classes("q-mt-sm")


def _render_bid_card(bid):
    """Render a single bid card."""
    bid_id = bid["id"]
    is_focus = bid.get("is_focus", False)
    status = bid.get("status", "active")
    color = bid_status_color(status)

    focus_icon = "star" if is_focus else ""
    with ui.expansion(
        f"{bid['bid_name']}" + (" (FOCUS)" if is_focus else ""),
        icon=focus_icon or "gavel",
    ).classes("w-full").props(f"header-class='{'bg-amber-1' if is_focus else ''}'"):

        # Status badge
        status_badge(status.upper(), color)

        # Metadata
        with ui.row().classes("flex-wrap q-mt-sm").style("gap: 1.5rem"):
            for label, val in [
                ("Owner", bid.get("owner")),
                ("GC", bid.get("general_contractor")),
                ("Bid Date", bid.get("bid_date")),
                ("Est. Value", f"${bid['estimated_value']:,.0f}" if bid.get("estimated_value") else None),
                ("Docs", f"{bid.get('doc_count', 0)} ({bid.get('total_words', 0):,} words)"),
            ]:
                if val:
                    with ui.column().classes("gap-0"):
                        ui.label(label).classes("text-caption text-grey-6 uppercase")
                        ui.label(str(val)).classes("text-body2")

        if bid.get("bid_number"):
            ui.label(f"Bid #{bid['bid_number']}").classes("text-caption text-grey-6")
        if bid.get("notes"):
            ui.label(bid["notes"]).classes("text-caption text-grey-7")

        # Controls
        with ui.row().classes("q-mt-md").style("gap: 0.5rem"):
            if is_focus:
                def clear_focus():
                    query.clear_focus_bid()
                    ui.navigate.to("/active-bids")
                ui.button("Clear Focus", icon="star_border", on_click=clear_focus) \
                    .props("outline size=sm")
            else:
                def set_focus(bid_id=bid_id):
                    query.set_focus_bid(bid_id)
                    ui.navigate.to("/active-bids")
                ui.button("Set as Focus", icon="star", on_click=set_focus) \
                    .props("color=primary size=sm")

            # Status select
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
                    ui.navigate.to("/active-bids")
                return handler

            ui.select(STATUS_OPTIONS, value=status,
                      on_change=make_status_handler(bid_id)) \
                .classes("w-32")

            # Delete
            def make_delete(b):
                def do_delete():
                    query.delete_bid_cascade(b["id"])
                    ui.notify(f"Deleted {b['bid_name']}", type="positive")
                    ui.navigate.to("/active-bids")
                return do_delete

            dialog = confirm_dialog(
                f"Delete {bid['bid_name']} and all its documents?",
                make_delete(bid),
            )
            ui.button("Remove", icon="delete", on_click=dialog.open) \
                .props("color=negative outline size=sm")

        ui.separator().classes("my-3")

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
                    ui.label(f"{doc['filename']} [{cat}]" + (f" — {label}" if label else "")) \
                        .classes("text-body2 flex-1")
                    ui.label(f"{words:,} words").classes("text-caption text-grey-6")
                    if doc.get("extraction_warning"):
                        ui.icon("warning").classes("text-sm text-amber-9") \
                            .tooltip(doc["extraction_warning"][:100])

                    def make_doc_delete(doc_id):
                        def handler():
                            query.delete_bid_document(doc_id)
                            ui.navigate.to("/active-bids")
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
            ui.navigate.to("/active-bids")

        ui.button("Process Files", icon="cloud_upload", on_click=process_files) \
            .props("color=primary").classes("q-mt-sm")
