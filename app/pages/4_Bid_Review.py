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
    elif agent_name == "chief_estimator":
        _render_chief_estimator(report)
    else:
        st.json(report)


def _render_document_control(report: dict):
    """Render Document Control report."""
    # Change log (if this was a re-run)
    change_log = report.get("change_log")
    if change_log:
        st.markdown("**Change Log (since last run):**")
        if change_log.get("change_summary"):
            st.info(change_log["change_summary"])
        if change_log.get("documents_added"):
            for doc in change_log["documents_added"]:
                st.markdown(f"- 🆕 {doc}")
        if change_log.get("documents_removed"):
            for doc in change_log["documents_removed"]:
                st.markdown(f"- ❌ {doc}")
        if change_log.get("documents_changed"):
            for doc in change_log["documents_changed"]:
                st.markdown(f"- ♻️ {doc}")
        if change_log.get("affected_agents"):
            agents_str = ", ".join(
                a.replace("_", " ").title() for a in change_log["affected_agents"]
            )
            st.caption(f"Agents that should re-run: {agents_str}")
        st.divider()

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


def _render_chief_estimator(report: dict):
    """Render Chief Estimator Brief."""
    # Go/No-Go recommendation
    go = report.get("go_no_go", "")
    go_colors = {"GO": "green", "CONDITIONAL_GO": "orange", "NO_GO": "red"}
    go_labels = {"GO": "GO", "CONDITIONAL_GO": "CONDITIONAL GO", "NO_GO": "NO GO"}
    if go:
        go_color = go_colors.get(go, "gray")
        go_label = go_labels.get(go, go)
        st.markdown(f"### Recommendation: :{go_color}[{go_label}]")
        if report.get("go_no_go_rationale"):
            st.markdown(report["go_no_go_rationale"])

    # Top Risks
    risks = report.get("top_risks", [])
    if risks:
        st.markdown("**Top Risks:**")
        for r in risks:
            sev = r.get("severity", "?")
            sev_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")
            st.markdown(f"{sev_icon} **{r.get('risk', '?')}** [{sev}]")
            parts = []
            if r.get("source_agent"):
                parts.append(f"Source: {r['source_agent'].replace('_', ' ').title()}")
            if r.get("mitigation"):
                parts.append(f"Mitigation: {r['mitigation']}")
            if parts:
                st.caption(" · ".join(parts))

    # Cost Adders
    adders = report.get("cost_adders", [])
    if adders:
        st.markdown("**Cost Adders:**")
        for a in adders:
            include = "✅" if a.get("include_in_estimate") else "⚠️"
            st.markdown(f"- {include} **{a.get('item', '?')}** — {a.get('estimated_impact', '?')}")
            if a.get("source_agent"):
                st.caption(f"  Source: {a['source_agent'].replace('_', ' ').title()}")

    # Sub Packages
    packages = report.get("sub_packages", [])
    if packages:
        st.markdown("**Subcontract Packages:**")
        for pkg in packages:
            subs = pkg.get("historical_subs", [])
            subs_str = f" — Subs: {', '.join(subs)}" if subs else ""
            st.markdown(f"- **{pkg.get('package', '?')}**: {pkg.get('estimated_scope', '')}{subs_str}")

    # Document Completeness
    completeness = report.get("document_completeness")
    if completeness:
        comp_icons = {"COMPLETE": "✅", "PARTIAL": "🟡", "INSUFFICIENT": "🔴"}
        st.markdown(f"**Document Completeness:** {comp_icons.get(completeness, '⚪')} {completeness}")

    # Missing Information
    missing = report.get("missing_information", [])
    if missing:
        st.markdown("**Missing Information:**")
        for item in missing:
            st.markdown(f"- ⚠️ {item}")

    # Key Dates
    dates = report.get("key_dates", {})
    if dates:
        st.markdown("**Key Dates:**")
        for key, val in dates.items():
            if val and val != "NOT FOUND":
                st.markdown(f"- **{key.replace('_', ' ').title()}:** {val}")

    # Agent Coverage
    coverage = report.get("agent_coverage", [])
    if coverage:
        st.markdown("**Agent Coverage:**")
        for ac in coverage:
            status_icon = {"complete": "✅", "error": "❌", "pending": "⏳"}.get(ac.get("status", ""), "⚪")
            name = ac.get("agent", "?").replace("_", " ").title()
            finding = ac.get("key_finding", "")
            st.markdown(f"- {status_icon} **{name}**: {finding}")

    # Recommended Actions
    actions = report.get("recommended_actions", [])
    if actions:
        st.markdown("**Recommended Actions:**")
        for i, item in enumerate(actions, 1):
            st.markdown(f"{i}. {item}")


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
# Staleness Detection (Priority 2)
# ---------------------------------------------------------------------------

staleness = query.get_bid_staleness(bid_id)
if staleness["is_stale"]:
    st.warning(
        "**Reports may be outdated** — new documents have been uploaded since the last agent run. "
        "Consider re-running agents to incorporate the latest documents."
    )

# ---------------------------------------------------------------------------
# Cost Summary (Priority 5)
# ---------------------------------------------------------------------------

existing_reports_list = query.get_agent_reports(bid_id)
if existing_reports_list:
    total_tokens = sum(r.get("tokens_used", 0) or 0 for r in existing_reports_list)
    total_cost = total_tokens / 1_000_000 * 3
    total_duration = sum(r.get("duration_seconds", 0) or 0 for r in existing_reports_list)
    completed_count = sum(1 for r in existing_reports_list if r["status"] == "complete")

    cost_cols = st.columns(4)
    cost_cols[0].metric("Agents Run", f"{completed_count}/{len(AGENT_REGISTRY)}")
    cost_cols[1].metric("Total Tokens", f"{total_tokens:,}")
    cost_cols[2].metric("Est. Cost", f"${total_cost:.3f}")
    cost_cols[3].metric("Total Duration", f"{total_duration:.0f}s")

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

    # Check staleness for this agent
    agent_stale = staleness["agents"].get(agent_name, {}).get("is_stale", False)
    stale_badge = " ⚠️" if agent_stale else ""

    label = f"{icon} **{agent.AGENT_DISPLAY_NAME}**{stale_badge}"
    if report_row and report_row.get("flags_count"):
        label += f" — {report_row['flags_count']} flag(s)"
    if report_row and report_row.get("risk_rating"):
        rating = report_row["risk_rating"]
        color = RISK_COLORS.get(rating, "gray")
        label += f" — :{color}[{rating}]"

    with st.expander(label, expanded=(status == "complete")):
        # Staleness warning per agent
        if agent_stale:
            st.caption("⚠️ New documents uploaded since this report was generated")

        ctrl_cols = st.columns([2, 2, 2, 4])

        with ctrl_cols[0]:
            btn_label = "Re-run" if status == "complete" else "Run"
            btn_type = "primary"
            if status == "complete" and not agent_stale:
                btn_type = "secondary"
            if st.button(btn_label, key=f"run_{agent_name}", use_container_width=True,
                         type=btn_type):
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
            with ctrl_cols[3]:
                if report_row.get("updated_at"):
                    st.caption(f"Last run: {report_row['updated_at']}")

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
