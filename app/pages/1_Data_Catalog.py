"""WEIS Data Catalog — View loaded projects, record counts, quality, and manage data."""

import sys
from pathlib import Path

# Ensure project root on sys.path for Streamlit page discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from app import query
from app.database import delete_project_cascade

st.set_page_config(
    page_title="WEIS — Data Catalog",
    page_icon="📊",
    layout="wide",
)

st.title("Data Catalog")
st.caption("All loaded projects and their data completeness")

# ---------------------------------------------------------------------------
# Top Metrics
# ---------------------------------------------------------------------------

projects = query.get_all_projects_with_detail()

col1, col2, col3 = st.columns(3)
col1.metric("Projects Loaded", len(projects))
total_records = sum(p.get("total_records", 0) for p in projects)
col2.metric("Total Records", f"{total_records:,}")
disciplines_count = sum(len(p.get("disciplines_detail", [])) for p in projects)
col3.metric("Disciplines", disciplines_count)

st.divider()

# ---------------------------------------------------------------------------
# Per-Project Cards
# ---------------------------------------------------------------------------

if not projects:
    st.info("No projects loaded yet. Use the **Upload JCD** page to add project data.")
else:
    for proj in projects:
        quality = proj.get("data_quality", "unknown")
        quality_colors = {
            "complete": "🟢",
            "partial": "🟡",
            "minimal": "🔴",
        }
        badge = quality_colors.get(quality, "⚪")

        with st.expander(
            f"**Job {proj['job_number']}** — {proj.get('job_name', 'Unknown')}  "
            f"{badge} {quality.upper()}",
            expanded=len(projects) == 1,
        ):
            # Project info row
            info_cols = st.columns(4)
            info_cols[0].markdown(f"**Owner:** {proj.get('owner') or '—'}")
            info_cols[1].markdown(f"**Type:** {proj.get('project_type') or '—'}")
            info_cols[2].markdown(f"**Cataloged:** {proj.get('cataloged_date') or '—'}")
            info_cols[3].markdown(f"**By:** {proj.get('cataloged_by') or '—'}")

            # Financial summary if available
            if proj.get("total_actual_cost"):
                fin_cols = st.columns(4)
                fin_cols[0].metric("Actual Cost", f"${proj['total_actual_cost']:,.0f}")
                if proj.get("total_actual_mh"):
                    fin_cols[1].metric("Actual MH", f"{proj['total_actual_mh']:,.0f}")
                if proj.get("total_budget_cost"):
                    fin_cols[3].metric("Budget Cost", f"${proj['total_budget_cost']:,.0f}")

            st.markdown("---")

            # Record counts table
            st.markdown("**Record Counts**")
            counts = proj.get("record_counts", {})
            table_labels = {
                "disciplines": "Disciplines",
                "cost_codes": "Cost Codes",
                "unit_costs": "Unit Costs",
                "production_rates": "Production Rates",
                "crew_configurations": "Crew Configs",
                "material_costs": "Material Costs",
                "subcontractors": "Subcontractors",
                "lessons_learned": "Lessons Learned",
                "general_conditions_breakdown": "GC Breakdown",
            }

            count_cols = st.columns(3)
            items = list(table_labels.items())
            for i, (key, label) in enumerate(items):
                c = counts.get(key, 0)
                dot = "🟢" if c > 0 else "⚫"
                count_cols[i % 3].markdown(f"{dot} **{label}**: {c}")

            # Discipline breakdown
            discs = proj.get("disciplines_detail", [])
            if discs:
                st.markdown("---")
                st.markdown("**Disciplines**")
                for d in discs:
                    budget = d.get("budget_cost") or 0
                    actual = d.get("actual_cost") or 0
                    variance = d.get("variance_cost") or (actual - budget)
                    color = "red" if variance > 0 else "green"
                    st.markdown(
                        f"- **{d['discipline_name']}** (`{d['discipline_code']}`) — "
                        f"Budget: ${budget:,.0f} · Actual: ${actual:,.0f} · "
                        f"Variance: :{color}[${variance:+,.0f}]"
                    )

            # Data browser — expandable tables of actual records
            st.markdown("---")
            st.markdown("**Data Browser** — _this is exactly what WEIS sees when answering questions_")

            records = query.get_project_records(proj["id"])

            data_tables = {
                "cost_codes": "Cost Codes",
                "unit_costs": "Unit Costs",
                "production_rates": "Production Rates",
                "crew_configurations": "Crew Configurations",
                "material_costs": "Material Costs",
                "subcontractors": "Subcontractors",
                "lessons_learned": "Lessons Learned",
                "general_conditions_breakdown": "GC Breakdown",
            }

            for table_key, table_label in data_tables.items():
                rows = records.get(table_key, [])
                count = len(rows)
                if count > 0:
                    with st.expander(f"{table_label} ({count} records)"):
                        df = pd.DataFrame(rows)
                        # Clean up column names for display
                        df.columns = [
                            c.replace("_", " ").title() for c in df.columns
                        ]
                        st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.markdown(f"⚫ _{table_label}_ — no records")

            # Remove button
            st.markdown("---")
            remove_key = f"remove_{proj['id']}"
            confirm_key = f"confirm_remove_{proj['id']}"

            if st.session_state.get(confirm_key):
                st.warning(
                    f"Are you sure you want to remove **Job {proj['job_number']}** "
                    f"and all {proj.get('total_records', 0)} records?"
                )
                btn_cols = st.columns([1, 1, 4])
                if btn_cols[0].button("Yes, Remove", key=f"yes_{proj['id']}", type="primary"):
                    deleted = delete_project_cascade(proj["id"])
                    total_deleted = sum(deleted.values())
                    st.session_state[confirm_key] = False
                    # Clear cached engine so system prompt refreshes
                    st.cache_resource.clear()
                    st.success(f"Removed Job {proj['job_number']} — {total_deleted} records deleted.")
                    st.rerun()
                if btn_cols[1].button("Cancel", key=f"cancel_{proj['id']}"):
                    st.session_state[confirm_key] = False
                    st.rerun()
            else:
                if st.button(
                    f"Remove Project {proj['job_number']}",
                    key=remove_key,
                    type="secondary",
                ):
                    st.session_state[confirm_key] = True
                    st.rerun()
