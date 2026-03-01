"""WEIS Upload JCD — Upload markdown files, preview extraction, confirm insert."""

import sys
from pathlib import Path

# Ensure project root on sys.path for Streamlit page discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from app.ingest import extract_jcd, validate_extraction, ingest_extracted_data

st.set_page_config(
    page_title="WEIS — Upload JCD",
    page_icon="📤",
    layout="wide",
)

st.title("Upload JCD")
st.caption("Upload Job Cost Data markdown files for AI-powered extraction and cataloging")

# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

if "upload_stage" not in st.session_state:
    st.session_state.upload_stage = "input"  # input → preview → done
if "extractions" not in st.session_state:
    st.session_state.extractions = []  # list of {filename, data, warnings}
if "ingest_results" not in st.session_state:
    st.session_state.ingest_results = []


def reset_upload():
    st.session_state.upload_stage = "input"
    st.session_state.extractions = []
    st.session_state.ingest_results = []


# ---------------------------------------------------------------------------
# Stage 1: Input
# ---------------------------------------------------------------------------

if st.session_state.upload_stage == "input":
    st.markdown("### Step 1: Upload Files")

    job_number = st.text_input(
        "Job Number",
        placeholder="e.g., 8576",
        help="The job number this data belongs to. All uploaded files will be associated with this job.",
    )

    uploaded_files = st.file_uploader(
        "JCD Markdown Files",
        type=["md"],
        accept_multiple_files=True,
        help="Upload one or more .md files containing job cost data sections.",
    )

    if uploaded_files and job_number:
        st.markdown(f"**{len(uploaded_files)}** file(s) ready for Job **{job_number}**")

        if st.button("Extract Data", type="primary", use_container_width=True):
            extractions = []
            progress = st.progress(0, text="Extracting data...")

            for i, f in enumerate(uploaded_files):
                progress.progress(
                    (i) / len(uploaded_files),
                    text=f"Extracting {f.name}...",
                )
                content = f.read().decode("utf-8")
                data = extract_jcd(content, f.name, job_number)
                warnings = validate_extraction(data)

                extractions.append({
                    "filename": f.name,
                    "data": data,
                    "warnings": warnings,
                })

            progress.progress(1.0, text="Extraction complete!")
            st.session_state.extractions = extractions
            st.session_state.upload_stage = "preview"
            st.rerun()

    elif uploaded_files and not job_number:
        st.warning("Please enter a job number before extracting.")

# ---------------------------------------------------------------------------
# Stage 2: Preview
# ---------------------------------------------------------------------------

elif st.session_state.upload_stage == "preview":
    st.markdown("### Step 2: Review Extraction")

    extractions = st.session_state.extractions
    has_errors = any("error" in e["data"] for e in extractions)

    for ext in extractions:
        data = ext["data"]
        warnings = ext["warnings"]
        is_error = "error" in data

        # Header
        status_icon = "❌" if is_error else ("⚠️" if warnings else "✅")
        disc = data.get("discipline", {}).get("discipline_name", "Unknown")
        meta = data.get("_extraction_meta", {})
        quality = meta.get("data_quality", "unknown") if not is_error else "error"

        with st.expander(
            f"{status_icon} **{ext['filename']}** — {disc} ({quality})",
            expanded=True,
        ):
            if is_error:
                st.error(data["error"])
                continue

            # Summary metrics
            record_counts = meta.get("record_counts", {})
            cols = st.columns(4)
            cols[0].metric("Discipline", disc)
            cols[1].metric("Quality", quality.upper())
            total = sum(record_counts.values()) if record_counts else 0
            cols[2].metric("Records Found", total)
            cols[3].metric("Warnings", len(warnings))

            # Warnings
            if warnings:
                for w in warnings:
                    st.warning(w)

            # Record count breakdown
            if record_counts:
                st.markdown("**Records by type:**")
                count_cols = st.columns(4)
                for i, (table, count) in enumerate(record_counts.items()):
                    label = table.replace("_", " ").title()
                    count_cols[i % 4].markdown(f"- {label}: **{count}**")

            # Preview data tables
            st.markdown("---")
            preview_tables = {
                "cost_codes": "Cost Codes",
                "unit_costs": "Unit Costs",
                "production_rates": "Production Rates",
                "crew_configurations": "Crew Configurations",
                "material_costs": "Material Costs",
                "subcontractors": "Subcontractors",
                "lessons_learned": "Lessons Learned",
            }

            for key, label in preview_tables.items():
                records = data.get(key, [])
                if records:
                    with st.expander(f"{label} ({len(records)} records)"):
                        df = pd.DataFrame(records)
                        st.dataframe(df, use_container_width=True, hide_index=True)

    # Action buttons
    st.divider()
    btn_cols = st.columns([2, 2, 4])

    valid_extractions = [e for e in extractions if "error" not in e["data"]]

    with btn_cols[0]:
        if valid_extractions and st.button(
            f"Confirm & Save ({len(valid_extractions)} files)",
            type="primary",
            use_container_width=True,
        ):
            results = []
            progress = st.progress(0, text="Saving to database...")

            for i, ext in enumerate(valid_extractions):
                progress.progress(
                    i / len(valid_extractions),
                    text=f"Inserting {ext['filename']}...",
                )
                try:
                    result = ingest_extracted_data(ext["data"])
                    result["filename"] = ext["filename"]
                    result["status"] = "success"
                except Exception as e:
                    result = {
                        "filename": ext["filename"],
                        "status": "error",
                        "error": str(e),
                    }
                results.append(result)

            progress.progress(1.0, text="Done!")
            st.session_state.ingest_results = results
            st.session_state.upload_stage = "done"
            # Clear cached engine so system prompt refreshes
            st.cache_resource.clear()
            st.rerun()

    with btn_cols[1]:
        if st.button("Cancel", use_container_width=True):
            reset_upload()
            st.rerun()

# ---------------------------------------------------------------------------
# Stage 3: Done
# ---------------------------------------------------------------------------

elif st.session_state.upload_stage == "done":
    st.markdown("### Upload Complete")

    results = st.session_state.ingest_results
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] == "error"]

    if successes:
        total_inserted = sum(r.get("total_records", 0) for r in successes)
        st.success(
            f"Successfully inserted **{total_inserted}** records "
            f"from **{len(successes)}** file(s)."
        )

        for r in successes:
            st.markdown(
                f"- **{r['filename']}** → Job {r.get('job_number', '?')}, "
                f"{r.get('discipline_code', 'N/A')} — "
                f"{r.get('total_records', 0)} records ({r.get('data_quality', '?')})"
            )

    if failures:
        st.error(f"**{len(failures)}** file(s) failed to save:")
        for r in failures:
            st.markdown(f"- **{r['filename']}**: {r.get('error', 'Unknown error')}")

    st.divider()
    btn_cols = st.columns([2, 2, 4])
    with btn_cols[0]:
        if st.button("Upload Another", type="primary", use_container_width=True):
            reset_upload()
            st.rerun()
    with btn_cols[1]:
        if st.button("View in Catalog", use_container_width=True):
            st.switch_page("pages/1_Data_Catalog.py")
