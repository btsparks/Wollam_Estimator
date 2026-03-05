"""Upload JCD page — 3-stage file upload workflow."""

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card
from app.ui import state
from app.ingest import extract_jcd, validate_extraction, ingest_extracted_data


@ui.page("/upload-jcd")
async def upload_jcd_page():
    state.set("current_path", "/upload-jcd")
    page_layout("Upload JCD")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Upload JCD", "Upload Job Cost Data markdown files for AI-powered extraction and cataloging")

        stage = state.get("upload_stage", "input")

        if stage == "input":
            _render_input_stage()
        elif stage == "preview":
            _render_preview_stage()
        elif stage == "done":
            _render_done_stage()


def _render_input_stage():
    """Stage 1: File input."""
    ui.label("Step 1: Upload Files").classes("text-h6 text-weight-bold")

    job_input = ui.input("Job Number", placeholder="e.g., 8576") \
        .classes("w-48")

    uploaded_data = {"files": []}

    def handle_upload(e):
        for file in e.files if hasattr(e, 'files') else [e]:
            content = file.content.read()
            uploaded_data["files"].append({
                "name": file.name,
                "content": content.decode("utf-8"),
            })
        ui.notify(f"{len(uploaded_data['files'])} file(s) ready", type="info")

    upload = ui.upload(
        label="JCD Markdown Files (.md)",
        multiple=True,
        auto_upload=True,
        on_upload=handle_upload,
    ).props("accept=.md").classes("w-full")

    async def extract():
        if not uploaded_data["files"]:
            ui.notify("Upload files first", type="warning")
            return
        if not job_input.value:
            ui.notify("Enter a job number", type="warning")
            return

        job_number = job_input.value
        extractions = []
        n = ui.notification("Extracting...", spinner=True, timeout=None)

        for f in uploaded_data["files"]:
            try:
                data = await run.io_bound(extract_jcd, f["content"], f["name"], job_number)
                warnings = validate_extraction(data)
                extractions.append({
                    "filename": f["name"],
                    "data": data,
                    "warnings": warnings,
                })
            except Exception as e:
                extractions.append({
                    "filename": f["name"],
                    "data": {"error": str(e)},
                    "warnings": [],
                })

        n.dismiss()
        state.set("extractions", extractions)
        state.set("upload_stage", "preview")
        ui.navigate.to("/upload-jcd")

    ui.button("Extract Data", icon="science", on_click=extract) \
        .props("color=primary").classes("q-mt-sm")


def _render_preview_stage():
    """Stage 2: Preview extraction results."""
    ui.label("Step 2: Review Extraction").classes("text-h6 text-weight-bold")

    extractions = state.get("extractions", [])

    for ext in extractions:
        data = ext["data"]
        warnings = ext["warnings"]
        is_error = "error" in data

        status_icon = "error" if is_error else ("warning" if warnings else "check_circle")
        status_color = "text-red-9" if is_error else ("text-amber-9" if warnings else "text-green-9")
        disc = data.get("discipline", {}).get("discipline_name", "Unknown") if not is_error else "Error"
        meta = data.get("_extraction_meta", {}) if not is_error else {}
        quality = meta.get("data_quality", "unknown") if not is_error else "error"

        with ui.expansion(f"{ext['filename']} — {disc} ({quality})", icon=status_icon) \
                .classes(f"w-full {status_color}"):
            if is_error:
                ui.label(data["error"]).classes("text-red-9")
                continue

            # Summary metrics
            record_counts = meta.get("record_counts", {})
            total = sum(record_counts.values()) if record_counts else 0
            with ui.row().style("gap: 1rem"):
                for lbl, val in [
                    ("Discipline", disc),
                    ("Quality", quality.upper()),
                    ("Records Found", total),
                    ("Warnings", len(warnings)),
                ]:
                    with ui.column().classes("items-center"):
                        ui.label(str(val)).classes("text-weight-bold")
                        ui.label(lbl).classes("text-caption text-grey-7 uppercase")

            if warnings:
                for w in warnings:
                    ui.label(f"Warning: {w}").classes("text-amber-9 text-body2 q-mt-xs")

            if record_counts:
                ui.label("Records by type:").classes("text-weight-bold text-body2 q-mt-sm")
                with ui.row().classes("flex-wrap").style("gap: 1rem"):
                    for table, count in record_counts.items():
                        label = table.replace("_", " ").title()
                        ui.label(f"{label}: {count}").classes("text-caption")

    # Action buttons
    valid = [e for e in extractions if "error" not in e["data"]]

    with ui.row().classes("q-mt-md").style("gap: 0.5rem"):
        async def confirm_save():
            results = []
            n = ui.notification("Saving to database...", spinner=True, timeout=None)
            for ext in valid:
                try:
                    result = await run.io_bound(ingest_extracted_data, ext["data"])
                    result["filename"] = ext["filename"]
                    result["status"] = "success"
                except Exception as e:
                    result = {"filename": ext["filename"], "status": "error", "error": str(e)}
                results.append(result)

            n.dismiss()
            state.set("ingest_results", results)
            state.set("upload_stage", "done")
            ui.navigate.to("/upload-jcd")

        if valid:
            ui.button(f"Confirm & Save ({len(valid)} files)", icon="save",
                      on_click=confirm_save).props("color=primary")

        def cancel():
            state.set("upload_stage", "input")
            state.pop("extractions", None)
            ui.navigate.to("/upload-jcd")

        ui.button("Cancel", on_click=cancel).props("outline color=grey-8")


def _render_done_stage():
    """Stage 3: Results."""
    ui.label("Upload Complete").classes("text-h6 text-weight-bold")

    results = state.get("ingest_results", [])
    successes = [r for r in results if r.get("status") == "success"]
    failures = [r for r in results if r.get("status") == "error"]

    if successes:
        total_inserted = sum(r.get("total_records", 0) for r in successes)
        with ui.card().classes("w-full bg-green-1 q-pa-md"):
            ui.label(f"Successfully inserted {total_inserted} records from {len(successes)} file(s).") \
                .classes("text-weight-bold text-green-9")
            for r in successes:
                ui.label(
                    f"{r['filename']} -> Job {r.get('job_number', '?')}, "
                    f"{r.get('discipline_code', 'N/A')} — "
                    f"{r.get('total_records', 0)} records ({r.get('data_quality', '?')})"
                ).classes("text-body2 text-green-9")

    if failures:
        with ui.card().classes("w-full bg-red-1 q-pa-md"):
            ui.label(f"{len(failures)} file(s) failed:").classes("text-weight-bold text-red-9")
            for r in failures:
                ui.label(f"{r['filename']}: {r.get('error', 'Unknown')}") \
                    .classes("text-body2 text-red-9")

    with ui.row().classes("q-mt-md").style("gap: 0.5rem"):
        def upload_another():
            state.set("upload_stage", "input")
            state.pop("extractions", None)
            state.pop("ingest_results", None)
            ui.navigate.to("/upload-jcd")

        ui.button("Upload Another", icon="upload", on_click=upload_another) \
            .props("color=primary")
        ui.button("View in Catalog", icon="folder_open",
                  on_click=lambda: ui.navigate.to("/data-catalog"))
