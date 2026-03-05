"""Bid Review page — run agents, view reports."""

import json

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card, section_header, empty_state, status_badge
from app.ui import state
from app.ui.theme import SUCCESS, WARNING, DANGER, PRIMARY
from app import query
from app.agents import AGENT_REGISTRY
from app.agents.runner import run_agent, run_all_agents


STATUS_ICONS = {"pending": "hourglass_top", "running": "sync", "complete": "check_circle", "error": "error"}
RISK_COLORS = {"LOW": "green", "MEDIUM": "amber", "HIGH": "red", "DO_NOT_BID": "red"}


@ui.page("/bid-review")
async def bid_review_page():
    state.set("current_path", "/bid-review")
    page_layout("Bid Review")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Bid Review", "Run intelligence agents to analyze bid documents")

        focus_bid = query.get_focus_bid()
        if not focus_bid:
            empty_state(
                "No focus bid set. Go to Active Bids and set a focus bid first.",
                icon="gavel",
                action_label="Active Bids",
                action_url="/active-bids",
            )
            return

        bid_id = focus_bid["id"]

        # Header
        ui.label(focus_bid["bid_name"]).classes("text-h6 text-grey-9 text-weight-bold")
        with ui.row().classes("flex-wrap").style("gap: 1rem"):
            for label, val in [
                ("Owner", focus_bid.get("owner")),
                ("GC", focus_bid.get("general_contractor")),
                ("Bid Date", focus_bid.get("bid_date")),
            ]:
                if val:
                    with ui.column().classes("items-center"):
                        ui.label(str(val)).classes("text-weight-bold")
                        ui.label(label).classes("text-caption text-grey-7 uppercase")

            docs = query.get_bid_documents_list(bid_id)
            total_words = sum(d.get("word_count", 0) or 0 for d in docs)
            with ui.column().classes("items-center"):
                ui.label(str(len(docs))).classes("text-weight-bold")
                ui.label("Documents").classes("text-caption text-grey-7 uppercase")
            with ui.column().classes("items-center"):
                ui.label(f"{total_words:,}").classes("text-weight-bold")
                ui.label("Total Words").classes("text-caption text-grey-7 uppercase")

        if not docs:
            empty_state("No documents uploaded yet. Upload bid documents on Active Bids first.",
                        icon="upload_file", action_label="Active Bids", action_url="/active-bids")
            return

        ui.separator()

        # Staleness detection
        staleness = query.get_bid_staleness(bid_id)
        if staleness["is_stale"]:
            with ui.card().classes("w-full bg-amber-1 q-pa-md"):
                ui.label("Reports may be outdated — new documents uploaded since last agent run.") \
                    .classes("text-amber-9 text-weight-medium")

        # Cost summary
        existing_reports = query.get_agent_reports(bid_id)
        if existing_reports:
            total_tokens = sum(r.get("tokens_used", 0) or 0 for r in existing_reports)
            total_cost = total_tokens / 1_000_000 * 3
            total_duration = sum(r.get("duration_seconds", 0) or 0 for r in existing_reports)
            completed = sum(1 for r in existing_reports if r["status"] == "complete")

            with ui.row().classes("w-full").style("gap: 1rem"):
                for label, val, icon in [
                    ("Agents Run", f"{completed}/{len(AGENT_REGISTRY)}", "smart_toy"),
                    ("Total Tokens", f"{total_tokens:,}", "token"),
                    ("Est. Cost", f"${total_cost:.3f}", "attach_money"),
                    ("Duration", f"{total_duration:.0f}s", "timer"),
                ]:
                    with ui.column().classes("flex-1"):
                        metric_card(label, val, icon=icon)

            ui.separator()

        # Run All button
        async def run_all():
            n = ui.notification("Running all agents...", spinner=True, timeout=None)
            agent_names = list(AGENT_REGISTRY.keys())
            for name in agent_names:
                try:
                    await run.io_bound(run_agent, name, bid_id)
                except Exception as e:
                    ui.notify(f"{name}: {e}", type="negative")
            n.dismiss()
            ui.notify("All agents complete!", type="positive")
            ui.navigate.to("/bid-review")

        ui.button("Run All Agents", icon="play_arrow", on_click=run_all) \
            .props("color=primary")

        ui.separator()

        # Agent cards
        existing_map = {r["agent_name"]: r for r in query.get_agent_reports(bid_id)}

        for agent_name, agent_cls in AGENT_REGISTRY.items():
            agent = agent_cls()
            report_row = existing_map.get(agent_name)
            status = report_row["status"] if report_row else "pending"
            icon = STATUS_ICONS.get(status, "hourglass_top")
            agent_stale = staleness["agents"].get(agent_name, {}).get("is_stale", False)

            # Build label
            label = agent.AGENT_DISPLAY_NAME
            if agent_stale:
                label += " (outdated)"
            if report_row and report_row.get("flags_count"):
                label += f" — {report_row['flags_count']} flag(s)"
            if report_row and report_row.get("risk_rating"):
                label += f" — {report_row['risk_rating']}"

            with ui.expansion(label, icon=icon).classes("w-full"):
                if agent_stale:
                    ui.label("New documents uploaded since this report was generated") \
                        .classes("text-caption text-amber-9")

                with ui.row().classes("items-center").style("gap: 0.5rem"):
                    # Run / Re-run button
                    async def make_run(name=agent_name):
                        n = ui.notification(f"Running {AGENT_REGISTRY[name]().AGENT_DISPLAY_NAME}...",
                                            spinner=True, timeout=None)
                        try:
                            await run.io_bound(run_agent, name, bid_id)
                            n.dismiss()
                            ui.notify("Done!", type="positive")
                            ui.navigate.to("/bid-review")
                        except Exception as e:
                            n.dismiss()
                            ui.notify(str(e), type="negative")

                    btn_label = "Re-run" if status == "complete" else "Run"
                    btn_color = "primary" if status != "complete" or agent_stale else None
                    btn = ui.button(btn_label, icon="play_arrow", on_click=make_run)
                    if btn_color:
                        btn.props(f"color={btn_color} size=sm")
                    else:
                        btn.props("outline size=sm")

                    if report_row:
                        if report_row.get("duration_seconds"):
                            ui.label(f"{report_row['duration_seconds']:.1f}s") \
                                .classes("text-caption text-grey-6")
                        if report_row.get("tokens_used"):
                            cost = report_row["tokens_used"] / 1_000_000 * 3
                            ui.label(f"{report_row['tokens_used']:,} tokens (~${cost:.3f})") \
                                .classes("text-caption text-grey-6")
                        if report_row.get("updated_at"):
                            ui.label(f"Last run: {report_row['updated_at']}") \
                                .classes("text-caption text-grey-6")

                # Summary
                if report_row and report_row.get("summary_text"):
                    ui.markdown(report_row["summary_text"]).classes("q-mt-sm")

                if report_row and status == "error" and report_row.get("error_message"):
                    ui.label(report_row["error_message"]).classes("text-red-9 q-mt-sm")

                # Structured report
                if report_row and report_row.get("report_json"):
                    try:
                        report_data = json.loads(report_row["report_json"])
                    except json.JSONDecodeError:
                        report_data = None

                    if report_data:
                        ui.separator().classes("my-2")
                        _render_report(agent_name, report_data)


def _render_report(agent_name: str, report: dict):
    if agent_name == "document_control":
        _render_document_control(report)
    elif agent_name == "legal":
        _render_legal(report)
    elif agent_name in ("quality", "safety"):
        _render_findings(report, agent_name)
    elif agent_name == "subcontract":
        _render_subcontract(report)
    elif agent_name == "chief_estimator":
        _render_chief_estimator(report)
    else:
        ui.label(json.dumps(report, indent=2)).classes("text-caption font-mono")


def _render_document_control(report: dict):
    change_log = report.get("change_log")
    if change_log:
        ui.label("Change Log (since last run)").classes("text-weight-bold text-body2")
        if change_log.get("change_summary"):
            ui.label(change_log["change_summary"]).classes("text-body2 text-blue-9")
        for doc in change_log.get("documents_added", []):
            ui.label(f"+ {doc}").classes("text-caption text-green-9")
        for doc in change_log.get("documents_removed", []):
            ui.label(f"- {doc}").classes("text-caption text-red-9")
        for doc in change_log.get("documents_changed", []):
            ui.label(f"~ {doc}").classes("text-caption text-amber-9")

    docs = report.get("document_register", [])
    if docs:
        ui.label("Document Register").classes("text-weight-bold text-body2 q-mt-sm")
        for doc in docs:
            ui.label(f"{doc.get('filename', '?')} [{doc.get('category', '?')}] — {doc.get('key_contents', '')}") \
                .classes("text-caption")

    comp = report.get("completeness_assessment", {})
    if comp:
        ui.label("Completeness").classes("text-weight-bold text-body2 q-mt-sm")
        with ui.row().classes("flex-wrap").style("gap: 0.5rem"):
            for key, val in comp.items():
                icon = "check_circle" if val else "cancel"
                color = "text-green-9" if val else "text-red-9"
                label = key.replace("has_", "").replace("_", " ").title()
                with ui.row().classes("items-center").style("gap: 0.25rem"):
                    ui.icon(icon).classes(f"text-sm {color}")
                    ui.label(label).classes("text-caption")

    _render_list(report, "missing_documents", "Missing Documents", "warning")
    _render_key_dates(report)
    _render_list(report, "recommended_actions", "Recommended Actions")


def _render_legal(report: dict):
    findings = report.get("findings", [])
    if findings:
        ui.label("Findings").classes("text-weight-bold text-body2")
        for f in findings:
            severity = f.get("severity", "?")
            icon = {"HIGH": "error", "MEDIUM": "warning", "LOW": "check_circle"}.get(severity, "help")
            color = {"HIGH": "text-red-9", "MEDIUM": "text-amber-9", "LOW": "text-green-9"} \
                .get(severity, "")
            found = f.get("found", False)
            cat = f.get("category", "?").replace("_", " ").title()

            if not found:
                ui.label(f"{cat} — NOT FOUND").classes("text-caption text-grey-6")
                continue

            with ui.row().classes("items-start").style("gap: 0.25rem"):
                ui.icon(icon).classes(f"text-sm {color} mt-1")
                with ui.column().classes("gap-0"):
                    ui.label(f"{cat} [{severity}]").classes("text-body2 text-weight-medium")
                    ui.label(f.get("summary", "")).classes("text-caption")
                    if f.get("recommendation"):
                        ui.label(f"Recommendation: {f['recommendation']}").classes("text-caption text-grey-6")

    _render_list(report, "missing_provisions", "Missing Provisions", "warning")
    _render_list(report, "recommended_clarifications", "Recommended Clarifications")


def _render_findings(report: dict, agent_name: str):
    findings = report.get("findings", [])
    if findings:
        ui.label("Findings").classes("text-weight-bold text-body2")
        for f in findings:
            impact = f.get("cost_impact", "NONE")
            icon = {"HIGH": "error", "MEDIUM": "warning", "LOW": "check_circle", "NONE": "radio_button_unchecked"} \
                .get(impact, "help")
            color = {"HIGH": "text-red-9", "MEDIUM": "text-amber-9", "LOW": "text-green-9"} \
                .get(impact, "text-grey-6")
            found = f.get("found", False)
            cat = f.get("category", "?").replace("_", " ").title()

            if not found:
                ui.label(f"{cat} — NOT FOUND").classes("text-caption text-grey-6")
                continue

            above_key = "above_wollam_standard" if agent_name == "quality" else "above_wollam_baseline"
            above = f.get(above_key, False)

            with ui.row().classes("items-start").style("gap: 0.25rem"):
                ui.icon(icon).classes(f"text-sm {color} mt-1")
                with ui.column().classes("gap-0"):
                    ui.label(f"{cat} [Cost: {impact}]" + (" ⬆" if above else "")) \
                        .classes("text-body2 text-weight-medium")
                    ui.label(f.get("description", "")).classes("text-caption")
                    if f.get("source"):
                        ui.label(f"Source: {f['source']}").classes("text-caption text-grey-6")

    cost_items = report.get("cost_impacting_items", [])
    if cost_items:
        ui.label("Cost-Impacting Items").classes("text-weight-bold text-body2 q-mt-sm")
        for item in cost_items:
            ui.label(f"{item.get('item', '?')} — {item.get('estimated_impact', '?')}") \
                .classes("text-caption text-weight-medium")
            if item.get("basis"):
                ui.label(f"Basis: {item['basis']}").classes("text-caption text-grey-6")

    if report.get("cost_impact_summary"):
        ui.label(f"Cost Impact Summary: {report['cost_impact_summary']}").classes("text-body2 q-mt-sm")

    _render_list(report, "workforce_availability_flags", "Workforce Flags", "warning")
    _render_list(report, "submittal_schedule", "Required Submittals")


def _render_subcontract(report: dict):
    packages = report.get("identified_packages", [])
    if packages:
        ui.label("Identified Sub Packages").classes("text-weight-bold text-body2")
        for pkg in packages:
            with ui.card().classes("w-full q-pa-sm"):
                ui.label(f"{pkg.get('package_name', '?')} ({pkg.get('discipline', '?')})") \
                    .classes("text-weight-medium text-body2")
                ui.label(pkg.get("scope_description", "")).classes("text-caption")
                specs = pkg.get("spec_sections", [])
                if specs:
                    ui.label(f"Specs: {', '.join(specs)}").classes("text-caption text-grey-6")
                subs = pkg.get("historical_subs", [])
                for sub in subs:
                    parts = [sub.get("sub_name", "?")]
                    if sub.get("past_project"):
                        parts.append(f"({sub['past_project']})")
                    if sub.get("performance"):
                        parts.append(f"[{sub['performance']}]")
                    ui.label(f"Historical: {' '.join(parts)}").classes("text-caption text-grey-6")

    _render_list(report, "self_perform_recommendations", "Self-Perform Recommendations")
    _render_list(report, "procurement_flags", "Procurement Flags", "warning")


def _render_chief_estimator(report: dict):
    go = report.get("go_no_go", "")
    if go:
        go_colors = {"GO": "text-green-9 bg-green-1", "CONDITIONAL_GO": "text-amber-9 bg-amber-1",
                     "NO_GO": "text-red-9 bg-red-1"}
        go_labels = {"GO": "GO", "CONDITIONAL_GO": "CONDITIONAL GO", "NO_GO": "NO GO"}
        css = go_colors.get(go, "")
        ui.label(f"Recommendation: {go_labels.get(go, go)}") \
            .classes(f"text-h6 text-weight-bold q-pa-sm rounded-borders {css}")
        if report.get("go_no_go_rationale"):
            ui.markdown(report["go_no_go_rationale"]).classes("text-body2")

    risks = report.get("top_risks", [])
    if risks:
        ui.label("Top Risks").classes("text-weight-bold text-body2 q-mt-md")
        for r in risks:
            sev = r.get("severity", "?")
            icon = {"HIGH": "error", "MEDIUM": "warning", "LOW": "check_circle"}.get(sev, "help")
            with ui.row().classes("items-start").style("gap: 0.25rem"):
                ui.icon(icon).classes("text-sm mt-1")
                with ui.column().classes("gap-0"):
                    ui.label(f"{r.get('risk', '?')} [{sev}]").classes("text-body2 text-weight-medium")
                    parts = []
                    if r.get("source_agent"):
                        parts.append(f"Source: {r['source_agent'].replace('_', ' ').title()}")
                    if r.get("mitigation"):
                        parts.append(f"Mitigation: {r['mitigation']}")
                    if parts:
                        ui.label(" · ".join(parts)).classes("text-caption text-grey-6")

    adders = report.get("cost_adders", [])
    if adders:
        ui.label("Cost Adders").classes("text-weight-bold text-body2 q-mt-md")
        for a in adders:
            include = "check_circle" if a.get("include_in_estimate") else "warning"
            ui.label(f"{a.get('item', '?')} — {a.get('estimated_impact', '?')}") \
                .classes("text-caption text-weight-medium")

    packages = report.get("sub_packages", [])
    if packages:
        ui.label("Subcontract Packages").classes("text-weight-bold text-body2 q-mt-md")
        for pkg in packages:
            subs = pkg.get("historical_subs", [])
            subs_str = f" — Subs: {', '.join(subs)}" if subs else ""
            ui.label(f"{pkg.get('package', '?')}: {pkg.get('estimated_scope', '')}{subs_str}") \
                .classes("text-caption")

    completeness = report.get("document_completeness")
    if completeness:
        comp_icon = {"COMPLETE": "check_circle", "PARTIAL": "info", "INSUFFICIENT": "error"} \
            .get(completeness, "help")
        with ui.row().classes("items-center q-mt-md").style("gap: 0.25rem"):
            ui.icon(comp_icon).classes("text-sm")
            ui.label(f"Document Completeness: {completeness}").classes("text-weight-bold text-body2")

    _render_list(report, "missing_information", "Missing Information", "warning")
    _render_key_dates(report)

    coverage = report.get("agent_coverage", [])
    if coverage:
        ui.label("Agent Coverage").classes("text-weight-bold text-body2 q-mt-md")
        for ac in coverage:
            status_icon = {"complete": "check_circle", "error": "error", "pending": "hourglass_top"} \
                .get(ac.get("status", ""), "help")
            name = ac.get("agent", "?").replace("_", " ").title()
            ui.label(f"{name}: {ac.get('key_finding', '')}").classes("text-caption")

    _render_list(report, "recommended_actions", "Recommended Actions", numbered=True)


def _render_list(report: dict, key: str, title: str, icon: str = None, numbered: bool = False):
    items = report.get(key, [])
    if not items:
        return
    ui.label(title).classes("text-weight-bold text-body2 q-mt-sm")
    for i, item in enumerate(items, 1):
        prefix = f"{i}. " if numbered else "• "
        with ui.row().classes("items-start").style("gap: 0.25rem"):
            if icon:
                ui.icon(icon).classes("text-sm text-amber-9 mt-1")
            ui.label(f"{prefix}{item}").classes("text-caption")


def _render_key_dates(report: dict):
    dates = report.get("key_dates", {})
    if not dates:
        return
    ui.label("Key Dates").classes("text-weight-bold text-body2 q-mt-sm")
    for key, val in dates.items():
        if key != "other" and val and val != "NOT FOUND":
            ui.label(f"{key.replace('_', ' ').title()}: {val}").classes("text-caption")
    for item in dates.get("other", []):
        ui.label(str(item)).classes("text-caption")
