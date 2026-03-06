"""
Knowledge Base — Streamlit Page

Browsable view of everything WEIS has learned from approved rate cards:
    - Rate Library: filterable table of all aggregated rates
    - Benchmarks: high-level project metrics
    - Lessons Learned: searchable list from PM interviews
"""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Knowledge Base", page_icon="📚", layout="wide")

from app.database import get_connection

st.title("Knowledge Base")
st.caption("Everything WEIS has learned from your completed jobs — rates, benchmarks, and lessons.")


# ── Load all KB data ───────────────────────────────────────────

conn = get_connection()
try:
    rates = conn.execute(
        "SELECT discipline, activity, description, rate, unit, rate_type, "
        "confidence, jobs_count, source_jobs, rate_low, rate_high "
        "FROM rate_library ORDER BY discipline, activity"
    ).fetchall()

    benchmarks = conn.execute(
        "SELECT metric, description, value, unit, project_type, "
        "jobs_count, source_jobs, range_low, range_high "
        "FROM benchmark ORDER BY metric"
    ).fetchall()

    lessons = conn.execute(
        "SELECT l.lesson_id, l.discipline, l.category, l.description, l.impact, "
        "l.recommendation, l.pm_name, l.captured_date, j.job_number, j.name as job_name "
        "FROM lesson_learned l LEFT JOIN job j ON l.job_id = j.job_id "
        "ORDER BY l.captured_date DESC"
    ).fetchall()
finally:
    conn.close()


# ── Empty state ────────────────────────────────────────────────

if not rates and not benchmarks and not lessons:
    st.markdown("---")
    st.markdown(
        "### No knowledge base data yet\n\n"
        "Import jobs and approve rate cards on the **Job Intelligence** page to get started."
    )
    st.page_link("pages/6_Job_Intelligence.py", label="Go to Job Intelligence", icon="📊")
    st.stop()

# Top-level stats
k1, k2, k3 = st.columns(3)
k1.metric("Rate Library Entries", len(rates))
k2.metric("Benchmarks", len(benchmarks))
k3.metric("Lessons Learned", len(lessons))

st.divider()


# ═══════════════════════════════════════════════════════════════
# Rate Library
# ═══════════════════════════════════════════════════════════════

if rates:
    st.header("Rate Library")

    # Discipline filter
    all_disciplines = sorted(set(
        (r["discipline"] or "Other").replace("_", " ").title() for r in rates
    ))
    selected_disc = st.selectbox(
        "Filter by discipline",
        ["All Disciplines"] + all_disciplines,
        key="kb_disc_filter",
    )

    # Build dataframe
    rows = []
    for r in rates:
        disc_display = (r["discipline"] or "Other").replace("_", " ").title()
        if selected_disc != "All Disciplines" and disc_display != selected_disc:
            continue

        conf = (r["confidence"] or "moderate").capitalize()
        range_text = "—"
        if r["rate_low"] is not None and r["rate_high"] is not None:
            range_text = f"{r['rate_low']:.4f} — {r['rate_high']:.4f}"

        rows.append({
            "Discipline": disc_display,
            "Cost Code": r["activity"],
            "Description": r["description"] or "—",
            "Rate": r["rate"],
            "Unit": r["unit"] or "—",
            "Confidence": conf,
            "Jobs": r["jobs_count"] or 0,
            "Source Jobs": r["source_jobs"] or "—",
            "Range": range_text,
        })

    if rows:
        df = pd.DataFrame(rows)

        # Style confidence column
        def _style_confidence(val):
            colors = {
                "Strong": "background-color: #d4edda; color: #155724",
                "Moderate": "background-color: #fff3cd; color: #856404",
                "Limited": "background-color: #f8d7da; color: #721c24",
            }
            return colors.get(val, "")

        # Format rate column
        df["Rate"] = df["Rate"].apply(lambda x: f"{x:.4f}")

        styled = df.style.map(_style_confidence, subset=["Confidence"])
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            height=min(len(rows) * 40 + 40, 600),
        )

        st.caption(f"Showing {len(rows)} of {len(rates)} rates")
    else:
        st.info(f"No rates found for {selected_disc}.")

    st.divider()


# ═══════════════════════════════════════════════════════════════
# Benchmarks
# ═══════════════════════════════════════════════════════════════

if benchmarks:
    st.header("Benchmarks")

    cols = st.columns(min(len(benchmarks), 3))
    for i, bm in enumerate(benchmarks):
        col = cols[i % 3]
        label = (bm["description"] or bm["metric"]).replace("_", " ").title()
        unit = bm["unit"] or ""

        with col:
            with st.container(border=True):
                st.metric(label, f"{bm['value']:.4f} {unit}")

                details = []
                if bm["range_low"] is not None and bm["range_high"] is not None:
                    details.append(f"Range: {bm['range_low']:.2f} — {bm['range_high']:.2f}")
                if bm["project_type"]:
                    details.append(f"Type: {bm['project_type'].replace('_', ' ').title()}")
                details.append(f"{bm['jobs_count'] or 0} job(s)")
                if bm["source_jobs"]:
                    details.append(f"Jobs: {bm['source_jobs']}")
                st.caption(" | ".join(details))

    st.divider()


# ═══════════════════════════════════════════════════════════════
# Lessons Learned
# ═══════════════════════════════════════════════════════════════

if lessons:
    st.header("Lessons Learned")

    # Filters
    f1, f2 = st.columns(2)
    with f1:
        all_categories = sorted(set(
            (ls["category"] or "general").capitalize() for ls in lessons
        ))
        cat_filter = st.selectbox(
            "Filter by category",
            ["All Categories"] + all_categories,
            key="kb_cat_filter",
        )
    with f2:
        lesson_disciplines = sorted(set(
            (ls["discipline"] or "General").replace("_", " ").title()
            for ls in lessons
        ))
        disc_filter = st.selectbox(
            "Filter by discipline",
            ["All Disciplines"] + lesson_disciplines,
            key="kb_lesson_disc_filter",
        )

    IMPACT_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    shown = 0
    for ls in lessons:
        cat = (ls["category"] or "general").capitalize()
        disc = (ls["discipline"] or "General").replace("_", " ").title()

        if cat_filter != "All Categories" and cat != cat_filter:
            continue
        if disc_filter != "All Disciplines" and disc != disc_filter:
            continue

        shown += 1
        impact_icon = IMPACT_ICON.get(ls["impact"], "⚪")

        with st.container(border=True):
            st.markdown(f"{impact_icon} **[{cat}] [{disc}]** {ls['description']}")

            if ls["recommendation"]:
                st.markdown(f"**Recommendation:** {ls['recommendation']}")

            meta = []
            if ls["impact"]:
                meta.append(f"Impact: {ls['impact'].capitalize()}")
            if ls["job_number"]:
                meta.append(f"Job {ls['job_number']}")
            if ls["pm_name"]:
                meta.append(f"PM: {ls['pm_name']}")
            if meta:
                st.caption(" | ".join(meta))

    if shown == 0:
        st.info("No lessons match the current filters.")
    else:
        st.caption(f"Showing {shown} of {len(lessons)} lessons")
