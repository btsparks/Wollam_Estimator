"""WEIS Bid Review — Run intelligence agents and view reports."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from app import query
from app.database import init_db, get_connection
from app.agents import AGENT_REGISTRY
from app.agents.runner import run_agent, run_all_agents

st.set_page_config(
    page_title="WEIS — Bid Review",
    page_icon="🔍",
    layout="wide",
)


def _ensure_tables():
    """Ensure agent_reports table exists."""
    conn = get_connection()
    try:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "agent_reports" not in tables:
            init_db()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report Rendering Functions
# ---------------------------------------------------------------------------


def _render_report(agent_name: str, report: dict):
    """Render a structured agent report based on agent type."""
    if agent_name == "document_control":
        _render_document_control(report)
    elif agent_name == "legal":
        _render_legal(report)
    elif agent_name in ("quality", "safety"):
        _render_findings_report(report, agent_name)
    elif agent_name == "subcontract":
        _render_subcontract(report)
    else:
        st.json(report)


def _render_document_control(report: dict):
    """Render Document Control report."""
    docs = report.get("document_register", [])
    if docs:
        st.markdown("**Document Register:**")
        for doc in docs:
            st.markdown(
                f"- **{doc.get('filename', '?')}** `[{doc.get('category', '?')}]` "
                f"— {doc.get('key_contents', '')}"
            )

    comp = report.get("completeness_assessment", {})
    if comp:
        st.markdown("**Completeness Assessment:**")
        cols = st.columns(3)
        items = list(comp.items())
        for i, (key, val) in enumerate(items):
            icon = "✅" if val else "❌"
            label = key.replace("has_", "").replace("_", " ").title()
            cols[i % 3].markdown(f"{icon} {label}")

    missing = report.get("missing_documents", [])
    if missing:
        st.markdown("**Missing Documents:**")
        for item in missing:
            st.markdown(f"- ⚠️ {item}")

    dates = report.get("key_dates", {})
    if dates:
        st.markdown("**Key Dates:**")
        for key, val in dates.items():
            if key != "other" and val and val != "NOT FOUND":
                st.markdown(f"- **{key.replace('_', ' ').title()}:** {val}")
        for item in dates.get("other", []):
            st.markdown(f"- {item}")

    actions = report.get("recommended_actions", [])
    if actions:
        st.markdown("**Recommended Actions:**")
        for item in actions:
            st.markdown(f"- {item}")


def _render_legal(report: dict):
    """Render Legal report with findings."""
    findings = report.get("findings", [])
    if findings:
        st.markdown("**Findings:**")
        for f in findings:
            severity = f.get("severity", "?")
            sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")
            found = f.get("found", False)

            if not found:
                st.markdown(f"⚪ **{f.get('category', '?').replace('_', ' ').title()}** — NOT FOUND")
                continue

            st.markdown(f"{sev_icon} **{f.get('category', '?').replace('_', ' ').title()}** [{severity}]")
            st.markdown(f"  {f.get('summary', '')}")
            if f.get("detail"):
                with st.popover("Detail"):
                    st.markdown(f.get("detail", ""))
                    if f.get("source"):
                        st.caption(f"Source: {f['source']}")
            if f.get("recommendation"):
                st.caption(f"Recommendation: {f['recommendation']}")

    missing = report.get("missing_provisions", [])
    if missing:
        st.markdown("**Missing Provisions:**")
        for item in missing:
            st.markdown(f"- ⚠️ {item}")

    clarifications = report.get("recommended_clarifications", [])
    if clarifications:
        st.markdown("**Recommended Clarifications:**")
        for item in clarifications:
            st.markdown(f"- {item}")


def _render_findings_report(report: dict, agent_name: str):
    """Render Quality or Safety findings report."""
    findings = report.get("findings", [])
    if findings:
        st.markdown("**Findings:**")
        for f in findings:
            impact = f.get("cost_impact", "NONE")
            impact_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "NONE": "⚪"}.get(impact, "⚪")
            found = f.get("found", False)

            if not found:
                st.markdown(f"⚪ **{f.get('category', '?').replace('_', ' ').title()}** — NOT FOUND")
                continue

            above_key = "above_wollam_standard" if agent_name == "quality" else "above_wollam_baseline"
            above = f.get(above_key, False)
            above_badge = " ⬆️" if above else ""

            st.markdown(
                f"{impact_icon} **{f.get('category', '?').replace('_', ' ').title()}** "
                f"[Cost: {impact}]{above_badge}"
            )
            st.markdown(f"  {f.get('description', '')}")
            if f.get("source"):
                st.caption(f"Source: {f['source']}")

    cost_items = report.get("cost_impacting_items", [])
    if cost_items:
        st.markdown("**Cost-Impacting Items:**")
        for item in cost_items:
            st.markdown(f"- **{item.get('item', '?')}** — {item.get('estimated_impact', '?')}")
            if item.get("basis"):
                st.caption(f"  Basis: {item['basis']}")

    if report.get("cost_impact_summary"):
        st.markdown(f"**Cost Impact Summary:** {report['cost_impact_summary']}")

    workforce = report.get("workforce_availability_flags", [])
    if workforce:
        st.markdown("**Workforce Availability Flags:**")
        for item in workforce:
            st.markdown(f"- ⚠️ {item}")

    submittals = report.get("submittal_schedule", [])
    if submittals:
        st.markdown("**Required Submittals:**")
        for item in submittals:
            st.markdown(f"- {item}")


def _render_subcontract(report: dict):
    """Render Subcontract report."""
    packages = report.get("identified_packages", [])
    if packages:
        st.markdown("**Identified Sub Packages:**")
        for pkg in packages:
            st.markdown(f"**{pkg.get('package_name', '?')}** ({pkg.get('discipline', '?')})")
            st.markdown(f"  {pkg.get('scope_description', '')}")

            specs = pkg.get("spec_sections", [])
            if specs:
                st.caption(f"Spec sections: {', '.join(specs)}")

            subs = pkg.get("historical_subs", [])
            if subs:
                for sub in subs:
                    parts = [sub.get("sub_name", "?")]
                    if sub.get("past_project"):
                        parts.append(f"({sub['past_project']})")
                    if sub.get("performance"):
                        parts.append(f"[{sub['performance']}]")
                    if sub.get("cost"):
                        parts.append(
                            f"${sub['cost']:,}" if isinstance(sub["cost"], (int, float))
                            else str(sub["cost"])
                        )
                    st.caption(f"  Historical: {' '.join(parts)}")

    self_perform = report.get("self_perform_recommendations", [])
    if self_perform:
        st.markdown("**Self-Perform Recommendations:**")
        for item in self_perform:
            st.markdown(f"- {item}")

    flags = report.get("procurement_flags", [])
    if flags:
        st.markdown("**Procurement Flags:**")
        for item in flags:
            st.markdown(f"- ⚠️ {item}")


# ---------------------------------------------------------------------------
# Page Layout
# ---------------------------------------------------------------------------

_ensure_tables()

st.title("Bid Review")
st.caption("Run intelligence agents to analyze bid documents — legal, quality, safety, subcontract")

# Focus Bid Check
focus_bid = query.get_focus_bid()

if not focus_bid:
    st.warning("No focus bid set. Go to **Active Bids** and set a focus bid first.")
    st.stop()

bid_id = focus_bid["id"]

# Header
st.markdown(f"### {focus_bid['bid_name']}")
header_cols = st.columns(5)
if focus_bid.get("owner"):
    header_cols[0].metric("Owner", focus_bid["owner"])
if focus_bid.get("general_contractor"):
    header_cols[1].metric("GC", focus_bid["general_contractor"])
if focus_bid.get("bid_date"):
    header_cols[2].metric("Bid Date", focus_bid["bid_date"])

docs = query.get_bid_documents_list(bid_id)
header_cols[3].metric("Documents", len(docs))
total_words = sum(d.get("word_count", 0) or 0 for d in docs)
header_cols[4].metric("Total Words", f"{total_words:,}")

if not docs:
    st.info("No documents uploaded yet. Upload bid documents on the **Active Bids** page first.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Run All Agents
# ---------------------------------------------------------------------------

run_all_col, status_col = st.columns([2, 6])

with run_all_col:
    run_all_clicked = st.button("Run All Agents", type="primary", use_container_width=True)

if run_all_clicked:
    progress_bar = st.progress(0, text="Starting agents...")
    status_text = st.empty()

    agent_names = list(AGENT_REGISTRY.keys())
    total = len(agent_names)

    def progress_cb(msg):
        status_text.text(msg)

    for i, name in enumerate(agent_names):
        progress_bar.progress(i / total, text=f"Running {AGENT_REGISTRY[name].AGENT_DISPLAY_NAME}...")
        try:
            run_agent(name, bid_id, progress_callback=progress_cb)
        except Exception as e:
            st.error(f"{AGENT_REGISTRY[name].AGENT_DISPLAY_NAME}: {e}")

    progress_bar.progress(1.0, text="All agents complete!")
    status_text.empty()
    st.rerun()

# ---------------------------------------------------------------------------
# Agent Cards
# ---------------------------------------------------------------------------

STATUS_ICONS = {
    "pending": "⏳",
    "running": "🔄",
    "complete": "✅",
    "error": "❌",
}

RISK_COLORS = {
    "LOW": "green",
    "MEDIUM": "orange",
    "HIGH": "red",
    "DO_NOT_BID": "red",
}

existing_reports = {r["agent_name"]: r for r in query.get_agent_reports(bid_id)}

for agent_name, agent_cls in AGENT_REGISTRY.items():
    agent = agent_cls()
    report_row = existing_reports.get(agent_name)

    status = report_row["status"] if report_row else "pending"
    icon = STATUS_ICONS.get(status, "⏳")

    label = f"{icon} **{agent.AGENT_DISPLAY_NAME}**"
    if report_row and report_row.get("flags_count"):
        label += f" — {report_row['flags_count']} flag(s)"
    if report_row and report_row.get("risk_rating"):
        rating = report_row["risk_rating"]
        color = RISK_COLORS.get(rating, "gray")
        label += f" — :{color}[{rating}]"

    with st.expander(label, expanded=(status == "complete")):
        ctrl_cols = st.columns([2, 2, 2, 4])

        with ctrl_cols[0]:
            btn_label = "Re-run" if status == "complete" else "Run"
            if st.button(btn_label, key=f"run_{agent_name}", use_container_width=True,
                         type="primary" if status != "complete" else "secondary"):
                with st.spinner(f"Running {agent.AGENT_DISPLAY_NAME}..."):
                    try:
                        run_agent(agent_name, bid_id)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        if report_row:
            with ctrl_cols[1]:
                if report_row.get("duration_seconds"):
                    st.caption(f"Duration: {report_row['duration_seconds']:.1f}s")
            with ctrl_cols[2]:
                if report_row.get("tokens_used"):
                    cost_est = report_row["tokens_used"] / 1_000_000 * 3
                    st.caption(f"Tokens: {report_row['tokens_used']:,} (~${cost_est:.3f})")

        if report_row and report_row.get("summary_text"):
            st.markdown(report_row["summary_text"])

        if report_row and status == "error" and report_row.get("error_message"):
            st.error(report_row["error_message"])

        if report_row and report_row.get("report_json"):
            try:
                report_data = json.loads(report_row["report_json"])
            except json.JSONDecodeError:
                report_data = None

            if report_data:
                _render_report(agent_name, report_data)
