"""
Job Intelligence — Streamlit Page

The demo centerpiece. Shows synced job data as actionable intelligence:
    A. Data Import (collapsed after first sync)
    B. Job Overview — card-style blocks per job with KPIs
    C. Rate Card Detail — human-readable table with variance highlighting
    D. PM Review — cleaner interview flow
    E. Knowledge Base summary
"""

import asyncio
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Job Intelligence", page_icon="📊", layout="wide")

from pathlib import Path
from app.hcss.auth import HCSSAuth
from app.hcss.sync import HCSSSyncOrchestrator, MockHeavyJobSource, MockHeavyBidSource
from app.hcss.file_source import FileHeavyJobSource, EmptyHeavyBidSource
from app.hcss import storage
from app.catalog.review import RateCardReview
from app.catalog.interview import PMInterviewWorkflow
from app.transform.rate_card import RateCardGenerator
from app.database import get_connection

# ── Setup ──────────────────────────────────────────────────────
auth = HCSSAuth()
is_live = auth.is_configured
PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "HJ Cost Reports"
has_file_reports = REPORTS_DIR.exists() and any(REPORTS_DIR.glob("* - CstAlys.xlsx"))


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _run_sync(source_type: str):
    if source_type == "file":
        orchestrator = HCSSSyncOrchestrator(
            heavyjob_source=FileHeavyJobSource(REPORTS_DIR),
            heavybid_source=EmptyHeavyBidSource(),
        )
    elif source_type == "mock":
        orchestrator = HCSSSyncOrchestrator(
            heavyjob_source=MockHeavyJobSource(),
            heavybid_source=MockHeavyBidSource(),
        )
    else:
        st.error("Live API sync not yet configured")
        return

    result = _run_async(orchestrator.sync_all_closed_jobs())

    if result["jobs_failed"] == 0:
        st.success(f"Sync complete: {result['jobs_processed']} jobs processed")
    else:
        st.warning(
            f"Sync finished with errors: {result['jobs_processed']} processed, "
            f"{result['jobs_failed']} failed"
        )
        for err in result["errors"]:
            st.error(err)
    st.rerun()


def _get_kb_counts():
    """Get knowledge base counts for display."""
    conn = get_connection()
    try:
        rl = conn.execute("SELECT COUNT(*) as cnt FROM rate_library").fetchone()["cnt"]
        bm = conn.execute("SELECT COUNT(*) as cnt FROM benchmark").fetchone()["cnt"]
        ll = conn.execute("SELECT COUNT(*) as cnt FROM lesson_learned").fetchone()["cnt"]
        return rl, bm, ll
    except Exception:
        return 0, 0, 0
    finally:
        conn.close()


# ── Page Header ────────────────────────────────────────────────

st.title("Job Intelligence")
st.caption("Turn completed job data into estimating intelligence — rates, benchmarks, and lessons backed by real field performance.")

# Top KPI row
cards = storage.get_all_rate_cards()
rl_count, bm_count, ll_count = _get_kb_counts()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Jobs Analyzed", len(cards))
kpi2.metric("Rate Cards", len(cards))
kpi3.metric("Knowledge Base Rates", rl_count)
kpi4.metric("Flagged Items", sum(c.get("flagged_count", 0) for c in cards))

st.divider()

# ═══════════════════════════════════════════════════════════════
# Section A: Data Import (collapsed by default when data exists)
# ═══════════════════════════════════════════════════════════════

with st.expander("Import Job Data", expanded=len(cards) == 0):
    # Source detection
    if is_live:
        st.success("Live API credentials detected — connected to HCSS")
    elif has_file_reports:
        report_files = list(REPORTS_DIR.glob("* - CstAlys.xlsx"))
        job_nums = [f.name.split(" - ")[0] for f in report_files]
        st.info(f"HeavyJob Cost Reports found: {', '.join(sorted(job_nums))}")
    else:
        st.info("No API credentials — using mock data from Phase B test files")

    col_sync1, col_sync2, col_spacer = st.columns([1, 1, 2])

    with col_sync1:
        if has_file_reports:
            if st.button("Sync from Files", type="primary", use_container_width=True):
                with st.spinner("Syncing from HJ Cost Reports..."):
                    _run_sync("file")
        else:
            if st.button("Sync Mock Data", type="primary", use_container_width=True):
                with st.spinner("Syncing mock data..."):
                    _run_sync("mock")

    with col_sync2:
        if has_file_reports:
            if st.button("Sync Mock Data", use_container_width=True):
                with st.spinner("Syncing mock data..."):
                    _run_sync("mock")

    # Compact sync history
    history = storage.get_sync_history(limit=5)
    if history:
        st.markdown("**Recent imports:**")
        for h in history:
            icon = {"completed": "✅", "failed": "❌", "running": "⏳"}.get(h["status"], "❓")
            st.caption(
                f"{icon} {h['started_at'][:19]} — {h['sync_type']} — "
                f"{h['jobs_processed']} jobs — {h['status']}"
            )

if not cards:
    st.info("No job data yet. Import jobs above to get started.")
    st.stop()


# ═══════════════════════════════════════════════════════════════
# Section B: Job Overview
# ═══════════════════════════════════════════════════════════════

st.header("Job Overview")

# Initialize selected card in session state
if "ji_selected_card_id" not in st.session_state:
    st.session_state.ji_selected_card_id = None

STATUS_BADGE = {
    "draft": ("Draft", "🔘", "#6c757d"),
    "pending_review": ("In Review", "🟡", "#f0ad4e"),
    "approved": ("Approved", "🟢", "#28a745"),
}

for card in cards:
    badge_label, badge_icon, _color = STATUS_BADGE.get(card["status"], ("Unknown", "⚪", "#999"))
    items = storage.get_rate_items_for_card(card["card_id"])
    flagged_count = card.get("flagged_count", 0)
    with st.container(border=True):
        # Header row
        h_col1, h_col2 = st.columns([4, 1])
        with h_col1:
            st.subheader(f"Job {card['job_number']} — {card['job_name']}")
        with h_col2:
            st.markdown(f"{badge_icon} **{badge_label}**")

        # Stats row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cost Codes", len(items))
        m2.metric("Flagged", flagged_count)
        m3.metric("Budget", f"${card.get('total_budget', 0):,.0f}" if card.get("total_budget") else "N/A")
        m4.metric("Actual", f"${card.get('total_actual', 0):,.0f}" if card.get("total_actual") else "N/A")

        if st.button("View Details", key=f"view_{card['card_id']}", use_container_width=False):
            st.session_state.ji_selected_card_id = card["card_id"]

st.divider()


# ═══════════════════════════════════════════════════════════════
# Section C: Rate Card Detail
# ═══════════════════════════════════════════════════════════════

# Find selected card
selected_card = None
if st.session_state.ji_selected_card_id:
    for c in cards:
        if c["card_id"] == st.session_state.ji_selected_card_id:
            selected_card = c
            break

# Fallback to selectbox if no button was clicked
if selected_card is None:
    st.header("Rate Card Detail")
    card_options = {
        f"Job {c['job_number']} — {c['job_name']} ({STATUS_BADGE.get(c['status'], ('?',))[0]})": c
        for c in cards
    }
    selected_label = st.selectbox("Select a job", list(card_options.keys()))
    selected_card = card_options[selected_label]
else:
    badge_label = STATUS_BADGE.get(selected_card["status"], ("?",))[0]
    st.header(f"Rate Card — Job {selected_card['job_number']} ({badge_label})")

card_id = selected_card["card_id"]
items = storage.get_rate_items_for_card(card_id)

if items:
    # Summary metrics
    total_items = len(items)
    flagged = storage.get_flagged_items_for_card(card_id)
    flagged_count = len(flagged)
    disciplines = set(i.get("discipline", "Unknown") for i in items)

    s1, s2, s3 = st.columns(3)
    s1.metric("Rate Items", total_items)
    s2.metric("Disciplines", len(disciplines))
    s3.metric("Flagged Variances", flagged_count)

    # Build display dataframe with human-readable column names
    df = pd.DataFrame(items)

    col_rename = {
        "discipline": "Discipline",
        "activity": "Cost Code",
        "description": "Description",
        "unit": "Unit",
        "bgt_mh_per_unit": "Budget Rate",
        "act_mh_per_unit": "Actual Rate",
        "rec_rate": "Recommended",
        "confidence": "Confidence",
        "variance_pct": "Variance %",
        "variance_flag": "Flagged",
    }

    display_cols = [c for c in col_rename.keys() if c in df.columns]
    display_df = df[display_cols].copy()

    # Format numeric columns
    for col in ["bgt_mh_per_unit", "act_mh_per_unit", "rec_rate"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"{x:.4f}" if x is not None else "—"
            )

    if "variance_pct" in display_df.columns:
        display_df["variance_pct"] = display_df["variance_pct"].apply(
            lambda x: f"{x:+.1f}%" if x is not None else "—"
        )

    if "variance_flag" in display_df.columns:
        display_df["variance_flag"] = display_df["variance_flag"].apply(
            lambda x: "Yes" if x else ""
        )

    if "confidence" in display_df.columns:
        display_df["confidence"] = display_df["confidence"].apply(
            lambda x: (x or "moderate").capitalize()
        )

    # Rename columns to human-readable
    rename_map = {k: v for k, v in col_rename.items() if k in display_df.columns}
    display_df = display_df.rename(columns=rename_map)

    # Highlight flagged rows
    def _highlight_flagged(row):
        if "Flagged" in row.index and row.get("Flagged") == "Yes":
            return ["background-color: #fff3cd"] * len(row)
        return [""] * len(row)

    styled = display_df.style.apply(_highlight_flagged, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Flagged items as alert list
    if flagged:
        st.subheader(f"Flagged Variances ({flagged_count})")
        for f_item in flagged:
            pct = f_item["variance_pct"]
            if pct > 0:
                st.error(
                    f"**{f_item['activity']}** — {f_item['description'] or 'N/A'} — "
                    f"{abs(pct):.0f}% over budget"
                )
            else:
                st.success(
                    f"**{f_item['activity']}** — {f_item['description'] or 'N/A'} — "
                    f"{abs(pct):.0f}% under budget"
                )
            if f_item.get("variance_explanation"):
                st.caption(f"Explanation: {f_item['variance_explanation']}")
else:
    st.info("No rate items for this card.")

st.divider()


# ═══════════════════════════════════════════════════════════════
# Section D: PM Review
# ═══════════════════════════════════════════════════════════════

review = RateCardReview()
current_status = selected_card["status"]

if current_status == "draft":
    st.header("Review")
    if st.button("Submit for PM Review", type="primary"):
        review.submit_for_review(card_id)
        st.success("Card submitted for PM review")
        st.rerun()

elif current_status == "pending_review":
    st.header("PM Review")
    st.caption(f"Review rate card for Job {selected_card['job_number']} — answer variance questions, then approve or reject.")

    job = storage.get_job_by_number(selected_card["job_number"])
    if job:
        codes = storage.get_cost_codes_for_job(job["job_id"])
        if codes:
            generator = RateCardGenerator()
            card_result = generator.generate_rate_card(
                job_number=selected_card["job_number"],
                job_name=selected_card.get("job_name", ""),
                cost_codes=codes,
            )

            workflow = PMInterviewWorkflow(rate_card=card_result)
            questions = workflow.generate_questions()

            if questions:
                if "interview_responses" not in st.session_state:
                    st.session_state.interview_responses = {}

                # Group questions by type
                q_by_type = {}
                for q in questions:
                    q_type = q["type"]
                    q_by_type.setdefault(q_type, []).append(q)

                TYPE_LABELS = {
                    "VARIANCE": "Variance Questions",
                    "LESSONS": "Lessons Learned",
                    "CONTEXT": "Project Context",
                    "RATE_CONFIRM": "Rate Confirmation",
                }

                # Show variance questions first (most important)
                type_order = ["VARIANCE", "LESSONS", "CONTEXT", "RATE_CONFIRM"]
                for q_type in type_order:
                    type_qs = q_by_type.get(q_type, [])
                    if not type_qs:
                        continue

                    label = TYPE_LABELS.get(q_type, q_type)
                    required_tag = " *(required)*" if q_type == "VARIANCE" else ""
                    st.subheader(f"{label}{required_tag}")

                    for q in type_qs:
                        key = f"q_{q['id']}"
                        response = st.text_area(
                            q["question_text"],
                            key=key,
                            value=st.session_state.interview_responses.get(q["id"], ""),
                            height=80,
                        )
                        if response:
                            st.session_state.interview_responses[q["id"]] = response
                            workflow.submit_response(q["id"], response)

                st.divider()

                # PM name pre-filled and approval
                pm_name = st.text_input("PM Name", value="Travis Sparks")
                pm_notes = st.text_area("Review Notes (optional)", height=60)

                col_approve, col_reject = st.columns(2)
                with col_approve:
                    if st.button("Approve Rate Card", type="primary", use_container_width=True):
                        for q_id, resp in st.session_state.interview_responses.items():
                            try:
                                workflow.submit_response(q_id, resp)
                            except ValueError:
                                pass

                        if workflow.is_complete():
                            workflow.finalize(pm_name=pm_name)
                            review.approve(card_id, pm_name=pm_name, notes=pm_notes)
                            st.success("Rate card approved and knowledge base updated!")
                            st.session_state.interview_responses = {}
                            st.rerun()
                        else:
                            st.error("Please answer all required variance questions before approving.")

                with col_reject:
                    reject_reason = st.text_input("Rejection reason")
                    if st.button("Reject — Back to Draft", use_container_width=True):
                        if reject_reason:
                            review.reject(card_id, reject_reason)
                            st.info("Card rejected and returned to draft.")
                            st.session_state.interview_responses = {}
                            st.rerun()
                        else:
                            st.error("Please provide a rejection reason.")

elif current_status == "approved":
    st.header("Review")
    st.success(
        f"Approved by {selected_card.get('pm_name', 'N/A')} "
        f"on {selected_card.get('review_date', 'N/A')}"
    )
    if selected_card.get("pm_notes"):
        st.caption(f"Notes: {selected_card['pm_notes']}")

st.divider()


# ═══════════════════════════════════════════════════════════════
# Section E: Knowledge Base Summary
# ═══════════════════════════════════════════════════════════════

st.header("Your Rate Library")

rl_count, bm_count, ll_count = _get_kb_counts()

if rl_count == 0 and bm_count == 0 and ll_count == 0:
    st.info("Approve rate cards to build your knowledge base.")
else:
    conn = get_connection()
    try:
        # Rate library grouped by discipline
        rates = conn.execute(
            "SELECT discipline, activity, description, rate, unit, confidence, "
            "jobs_count, source_jobs, rate_low, rate_high "
            "FROM rate_library ORDER BY discipline, activity"
        ).fetchall()

        if rates:
            st.subheader(f"Rates ({len(rates)})")

            # Group by discipline
            by_disc = {}
            for r in rates:
                disc = (r["discipline"] or "Other").replace("_", " ").title()
                by_disc.setdefault(disc, []).append(r)

            for disc, disc_rates in by_disc.items():
                with st.expander(f"{disc} ({len(disc_rates)} rates)", expanded=False):
                    for r in disc_rates:
                        conf_icon = {"strong": "🟢", "moderate": "🟡", "limited": "🔴"}.get(
                            r["confidence"], "⚪"
                        )
                        range_text = ""
                        if r["rate_low"] is not None and r["rate_high"] is not None:
                            range_text = f" (range: {r['rate_low']:.4f} — {r['rate_high']:.4f})"

                        jobs_text = f" from {r['jobs_count']} job(s)" if r["jobs_count"] else ""
                        if r["source_jobs"]:
                            jobs_text += f": {r['source_jobs']}"

                        st.markdown(
                            f"{conf_icon} **{r['activity']}** — {r['description'] or 'N/A'}\n\n"
                            f"Rate: **{r['rate']:.4f} {r['unit']}**{range_text}{jobs_text}"
                        )

        # Benchmarks
        benchmarks = conn.execute(
            "SELECT metric, description, value, unit, jobs_count, source_jobs, "
            "range_low, range_high FROM benchmark ORDER BY metric"
        ).fetchall()

        if benchmarks:
            st.subheader(f"Benchmarks ({len(benchmarks)})")
            for bm in benchmarks:
                label = (bm["description"] or bm["metric"]).replace("_", " ").title()
                range_text = ""
                if bm["range_low"] is not None and bm["range_high"] is not None:
                    range_text = f" (range: {bm['range_low']:.2f} — {bm['range_high']:.2f})"
                st.markdown(
                    f"**{label}**: {bm['value']:.4f} {bm['unit'] or ''}{range_text} "
                    f"— {bm['jobs_count'] or 0} job(s)"
                )

        # Lessons learned
        lessons = conn.execute(
            "SELECT l.discipline, l.category, l.description, l.impact, "
            "l.recommendation, l.pm_name, j.job_number "
            "FROM lesson_learned l LEFT JOIN job j ON l.job_id = j.job_id "
            "ORDER BY l.captured_date DESC"
        ).fetchall()

        if lessons:
            st.subheader(f"Lessons Learned ({len(lessons)})")
            for ls in lessons:
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    ls["impact"], "⚪"
                )
                cat = (ls["category"] or "general").capitalize()
                disc = (ls["discipline"] or "General").replace("_", " ").title()
                st.markdown(
                    f"{impact_icon} **[{cat}]** {ls['description']}"
                )
                details = []
                if ls["recommendation"]:
                    details.append(f"Recommendation: {ls['recommendation']}")
                if ls["job_number"]:
                    details.append(f"Job {ls['job_number']}")
                if ls["pm_name"]:
                    details.append(f"PM: {ls['pm_name']}")
                if details:
                    st.caption(" | ".join(details))

    finally:
        conn.close()
