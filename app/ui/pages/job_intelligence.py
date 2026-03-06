"""Job Intelligence page — tabbed layout with job grid, rate card detail, PM review."""

from datetime import datetime
from pathlib import Path

from fastapi import Request
from nicegui import ui
from app.ui.layout import page_layout
from app.ui import state
from app.ui.components import (
    page_header, metric_card, status_badge,
    empty_state,
)
from app.ui.theme import PRIMARY, PRIMARY_LIGHT, SUCCESS, WARNING, DANGER, SURFACE
from app.hcss.auth import HCSSAuth
from app.hcss.sync import HCSSSyncOrchestrator, MockHeavyJobSource, MockHeavyBidSource
from app.hcss.file_source import FileHeavyJobSource, EmptyHeavyBidSource
from app.hcss import storage
from app.catalog.review import RateCardReview
from app.catalog.interview import PMInterviewWorkflow
from app.transform.rate_card import RateCardGenerator

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "HJ Cost Reports"

auth = HCSSAuth()
is_live = auth.is_configured
has_file_reports = REPORTS_DIR.exists() and any(REPORTS_DIR.glob("* - CstAlys.xlsx"))

STATUS_BADGE_MAP = {
    "draft": ("Draft", "grey"),
    "pending_review": ("In Review", "amber"),
    "approved": ("Approved", "green"),
}


@ui.page("/job-intelligence")
async def job_intelligence_page(request: Request):
    state.set("current_path", "/job-intelligence")
    page_layout("Job Intelligence")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header(
            "Job Intelligence",
            "Turn completed job data into estimating intelligence -- rates, benchmarks, and lessons."
        )

        cards = storage.get_all_rate_cards()

        # KPI row — estimating-focused stats, clickable
        total_flagged = sum(c.get("flagged_count", 0) for c in cards)
        with_hour_data = sum(
            1 for c in cards if (c.get("total_actual_hrs") or 0) > 0
        )
        total_hours = sum(c.get("total_actual_hrs") or 0 for c in cards)
        with ui.row().classes("w-full").style("gap: 1rem"):
            with ui.column().classes("flex-1 cursor-pointer") \
                    .on("click", lambda: ui.navigate.to("/job-intelligence?tab=jobs&sort=actual_hrs")):
                metric_card("Jobs with Data", f"{with_hour_data} / {len(cards)}", icon="work")
            with ui.column().classes("flex-1 cursor-pointer") \
                    .on("click", lambda: ui.navigate.to("/job-intelligence?tab=jobs&sort=actual_hrs")):
                metric_card("Total Actual Hours", f"{total_hours:,.0f}", icon="schedule")
            with ui.column().classes("flex-1 cursor-pointer") \
                    .on("click", lambda: ui.navigate.to("/job-intelligence?tab=jobs&sort=flagged")):
                metric_card("Flagged Items", total_flagged, icon="flag")

        # Import section (collapsed when data exists)
        _render_import_section(cards)

        if not cards:
            empty_state("No job data yet. Import jobs above to get started.",
                        icon="cloud_download", action_label=None)
            return

        # Insights panel — cross-job intelligence
        _render_insights_panel(cards)

        # Find selected card from query param (for rate_card / review tabs)
        selected_card = None
        _query_job = request.query_params.get("job")
        if _query_job:
            try:
                card_id = int(_query_job)
                for c in cards:
                    if int(c["card_id"]) == card_id:
                        selected_card = c
                        break
            except (ValueError, TypeError):
                pass

        # Determine active tab and sort preference
        active_tab = request.query_params.get("tab", "jobs")
        sort_field = request.query_params.get("sort", "flagged")

        # Tab bar
        with ui.tabs().classes("w-full") as tabs:
            ui.tab("jobs", label="Jobs", icon="list")
            ui.tab("rate_card", label="Rate Card", icon="receipt_long")
            ui.tab("review", label="PM Review", icon="rate_review")

        with ui.tab_panels(tabs, value=active_tab).classes("w-full"):

            with ui.tab_panel("jobs"):
                _render_jobs_grid(cards, selected_card, sort_field=sort_field)

            with ui.tab_panel("rate_card"):
                if selected_card:
                    _render_rate_card_detail(cards, selected_card)
                else:
                    _render_no_job_selected("Select a job from the Jobs tab to view its rate card.")

            with ui.tab_panel("review"):
                if selected_card:
                    _render_pm_review(cards, selected_card)
                else:
                    _render_no_job_selected("Select a job from the Jobs tab to review its rate card.")


def _render_no_job_selected(message: str):
    """Placeholder when no job is selected."""
    with ui.column().classes("w-full items-center q-pa-xl"):
        ui.icon("touch_app").classes("text-6xl text-grey-4")
        ui.label(message).classes("text-body1 text-grey-6 q-mt-sm")


def _render_import_section(cards):
    """Collapsible data import panel."""
    with ui.expansion("Import Job Data", icon="cloud_download",
                      value=len(cards) == 0).classes("w-full"):
        if is_live:
            ui.label("Live API credentials detected -- connected to HCSS").classes("text-green-9")
        elif has_file_reports:
            report_files = list(REPORTS_DIR.glob("* - CstAlys.xlsx"))
            job_nums = [f.name.split(" - ")[0] for f in report_files]
            ui.label(f"HeavyJob Cost Reports found: {', '.join(sorted(job_nums))}") \
                .classes("text-blue-9")
        else:
            ui.label("No API credentials -- using mock data from Phase B test files") \
                .classes("text-blue-9")

        with ui.row().classes("q-mt-sm").style("gap: 0.5rem"):
            if has_file_reports:
                ui.button("Sync from Files", icon="sync",
                          on_click=lambda: _handle_sync("file")) \
                    .props("color=primary")
                ui.button("Sync Mock Data", icon="science",
                          on_click=lambda: _handle_sync("mock"))
            else:
                ui.button("Sync Mock Data", icon="science",
                          on_click=lambda: _handle_sync("mock")) \
                    .props("color=primary")

        history = storage.get_sync_history(limit=5)
        if history:
            ui.label("Recent imports:").classes("text-weight-bold q-mt-md text-body2")
            for h in history:
                color = {"completed": "text-green-9", "failed": "text-red-9"}.get(h["status"], "")
                # Plain-language timestamp
                ts = _friendly_timestamp(h.get("started_at", ""))
                status_label = "Completed" if h["status"] == "completed" else h["status"].replace("_", " ").title()
                ui.label(
                    f"{ts} -- {h['jobs_processed']} jobs -- {status_label}"
                ).classes(f"text-caption {color}")


def _render_insights_panel(cards):
    """Cross-job intelligence insights — surfaces patterns from the data."""
    insights = storage.get_job_intelligence_insights()

    # Only show if there's meaningful data
    if not insights.get("top_jobs"):
        return

    with ui.expansion("Insights", icon="lightbulb", value=False).classes("w-full"):
        with ui.row().classes("w-full").style("gap: 1rem"):

            # Left: Data-richest jobs
            with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                ui.label("Most Data-Rich Jobs").classes(
                    "text-caption text-grey-7 text-weight-bold uppercase q-mb-xs")
                ui.label("These jobs contribute the most timecard hours to your rate intelligence.").classes(
                    "text-caption text-grey-6 q-mb-sm")
                for j in insights["top_jobs"]:
                    name = j["job_name"]
                    num = j["job_number"]
                    if name.startswith(f"{num} - "):
                        name = name[len(f"{num} - "):]
                    with ui.row().classes("w-full items-center justify-between").style("min-height: 24px"):
                        ui.label(f"{num} -- {name[:35]}").classes("text-caption text-weight-medium")
                        with ui.row().classes("items-center").style("gap: 0.75rem"):
                            ui.label(f"{j['total_hrs']:,.0f} hrs").classes("text-caption text-weight-bold")
                            ui.label(f"{j['cc_with_data']} codes").classes("text-caption text-grey-6")

            # Right: Discipline coverage
            with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                ui.label("Rate Coverage by Discipline").classes(
                    "text-caption text-grey-7 text-weight-bold uppercase q-mb-xs")
                total_items = insights.get("total_rate_items") or 1
                items_actual = insights.get("items_with_actuals") or 0
                ui.label(
                    f"{items_actual} of {total_items} rate items have actual MH/unit data "
                    f"({items_actual / total_items * 100:.0f}% coverage)."
                ).classes("text-caption text-grey-6 q-mb-sm")
                for d in insights["discipline_coverage"]:
                    disc_name = (d["discipline"] or "").replace("_", " ").title()
                    total = d["total_items"]
                    actual = d["with_actuals"]
                    pct = (actual / total * 100) if total > 0 else 0
                    with ui.row().classes("w-full items-center").style("gap: 0.5rem; min-height: 22px"):
                        ui.label(disc_name).classes("text-caption").style("width: 140px; flex-shrink: 0")
                        with ui.element("div").style(
                            "flex: 1; height: 6px; background: #E0E0E0; border-radius: 3px; overflow: hidden"
                        ):
                            if pct > 0:
                                ui.element("div").style(
                                    f"width: {max(pct, 2):.0f}%; height: 100%; "
                                    f"background: {SUCCESS if pct >= 20 else WARNING}; border-radius: 3px"
                                )
                        ui.label(f"{actual}/{total}").classes("text-caption text-grey-6") \
                            .style("width: 55px; text-align: right; flex-shrink: 0")

        # Sync status note
        no_data_count = sum(1 for c in cards if (c.get("total_actual_hrs") or 0) == 0)
        if no_data_count > 0:
            ui.label(
                f"{no_data_count} of {len(cards)} jobs have no timecard data yet. "
                f"As more timecards sync, rate coverage and confidence will improve."
            ).classes("text-caption text-grey-6 q-mt-sm").style("font-style: italic")


async def _handle_sync(source_type: str):
    ui.notify("Syncing...", type="info", spinner=True, timeout=0, close_button=False,
              message="Syncing job data...")
    try:
        if source_type == "file":
            orchestrator = HCSSSyncOrchestrator(
                heavyjob_source=FileHeavyJobSource(REPORTS_DIR),
                heavybid_source=EmptyHeavyBidSource(),
            )
        else:
            orchestrator = HCSSSyncOrchestrator(
                heavyjob_source=MockHeavyJobSource(),
                heavybid_source=MockHeavyBidSource(),
            )
        result = await orchestrator.sync_all_closed_jobs()

        if result["jobs_failed"] == 0:
            ui.notify(f"Sync complete: {result['jobs_processed']} jobs processed",
                      type="positive")
        else:
            ui.notify(
                f"Sync finished: {result['jobs_processed']} processed, {result['jobs_failed']} failed",
                type="warning")
    except Exception as e:
        ui.notify(f"Sync error: {e}", type="negative")

    ui.navigate.to("/job-intelligence")


def _render_jobs_grid(cards, selected_card=None, sort_field="flagged"):
    """Tab 1: AG Grid of all jobs with search and click-to-profile."""

    # Build rows — clean job names, show data that matters for estimating
    rows = []
    for card in cards:
        # Clean redundant "8465 - " prefix from job names
        job_name = card.get("job_name", "")
        job_number = card.get("job_number", "")
        if job_name.startswith(f"{job_number} - "):
            job_name = job_name[len(f"{job_number} - "):]

        rows.append({
            "card_id": card["card_id"],
            "job_id": card.get("job_id", ""),
            "job_number": job_number,
            "job_name": job_name,
            "budget": card.get("total_budget"),
            "cost_codes": card.get("cc_with_actuals") or 0,
            "actual_hrs": card.get("total_actual_hrs") or 0,
            "flagged": card.get("flagged_count", 0),
        })

    # Quick filter search box
    grid_ref = None

    with ui.row().classes("w-full items-center justify-between q-mb-sm"):
        search = ui.input(placeholder="Search jobs...") \
            .props("outlined dense clearable").classes("w-64") \
            .style("min-width: 250px")
        ui.label(f"{len(rows)} jobs").classes("text-caption text-grey-6")

    col_defs = [
        {"headerName": "Job #", "field": "job_number", "sortable": True, "filter": True,
         "width": 100},
        {"headerName": "Job Name", "field": "job_name", "sortable": True, "filter": True,
         "flex": 1, "minWidth": 200},
        {"headerName": "Budget", "field": "budget", "sortable": True, "width": 130,
         ":valueFormatter": "p => p.value != null ? '$' + p.value.toLocaleString('en-US', {maximumFractionDigits: 0}) : '--'",
         "type": "numericColumn"},
        {"headerName": "Cost Codes", "field": "cost_codes", "sortable": True, "width": 120,
         "type": "numericColumn",
         "headerTooltip": "Cost codes with actual labor hours",
         ":valueFormatter": "p => p.value > 0 ? p.value.toLocaleString() : '--'",
         "cellClassRules": {
             "text-green-8": "x >= 20",
             "text-grey-5": "x === 0",
         }},
        {"headerName": "Actual Hours", "field": "actual_hrs", "sortable": True, "width": 130,
         "type": "numericColumn",
         "headerTooltip": "Total actual labor hours from timecards",
         ":valueFormatter": "p => p.value > 0 ? p.value.toLocaleString('en-US', {maximumFractionDigits: 0}) : '--'",
         "cellClassRules": {
             "text-green-8": "x >= 1000",
             "text-grey-5": "x === 0",
         }},
        {"headerName": "Flagged", "field": "flagged", "sortable": True, "width": 90,
         "type": "numericColumn",
         "cellClassRules": {
             "text-red-8 text-weight-bold": "x > 0",
         }},
    ]

    # Apply default sort based on query param
    for col in col_defs:
        if col["field"] == sort_field:
            col["sort"] = "desc"
            break
    else:
        # Fallback: sort flagged desc
        for col in col_defs:
            if col["field"] == "flagged":
                col["sort"] = "desc"

    grid = ui.aggrid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True},
        "rowSelection": "single",
        "animateRows": True,
        "pagination": True,
        "paginationPageSize": 25,
        "paginationPageSizeSelector": [25, 50, 100],
        ":getRowId": "params => String(params.data.card_id)",
    }).classes("w-full").style("height: 500px")

    # Wire up search box to AG Grid quick filter
    search.on("update:model-value", lambda e: None,
              js_handler=f"""(val) => {{
                  const grid = getElement({grid._id});
                  if (grid && grid.gridOptions && grid.gridOptions.api) {{
                      grid.gridOptions.api.setGridOption('quickFilterText', val || '');
                  }}
              }}""")

    # Click a row -> navigate to the dedicated job profile page
    grid.on("cellClicked", lambda e: None,
            js_handler="(e) => { window.location.href = '/job-profile?job=' + e.data.job_id + '&card=' + e.data.card_id; }")


def _friendly_timestamp(ts: str) -> str:
    """Convert ISO timestamp to plain language like 'Today 2:30 PM' or 'Mar 5, 10:15 AM'."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        time_str = dt.strftime("%I:%M %p").lstrip("0")
        if dt.date() == now.date():
            return f"Today {time_str}"
        elif (now.date() - dt.date()).days == 1:
            return f"Yesterday {time_str}"
        else:
            return f"{dt.strftime('%b')} {dt.day}, {time_str}"
    except (ValueError, TypeError):
        return ts[:16]


def _fmt_num(n, prefix="", suffix=""):
    """Format a number with commas, or return '--' if None/0."""
    if not n:
        return "--"
    return f"{prefix}{n:,.0f}{suffix}"


def _fmt_date(d):
    """Format a date string nicely, or '--'."""
    if not d:
        return "--"
    try:
        dt = datetime.strptime(str(d)[:10], "%Y-%m-%d")
        return dt.strftime("%b %Y")
    except (ValueError, TypeError):
        return str(d)[:10]


def _richness_color(score: int) -> str:
    if score >= 70:
        return SUCCESS
    if score >= 40:
        return WARNING
    return DANGER


def _richness_label(score: int) -> str:
    if score >= 70:
        return "Data Rich"
    if score >= 40:
        return "Moderate"
    return "Sparse"



def _mini_stat(label: str, value: str, icon: str, color: str = "grey"):
    """Small metric chip for the job profile."""
    color_map = {
        "green": ("#E8F5E9", "#2E7D32"),
        "amber": ("#FFF8E1", "#F57F17"),
        "grey": ("#F5F5F5", "#757575"),
    }
    bg, fg = color_map.get(color, color_map["grey"])
    with ui.card().classes("q-pa-sm items-center").style(
        f"min-width: 120px; flex: 1; background: {bg}; border: none"
    ):
        with ui.row().classes("items-center").style("gap: 0.4rem"):
            ui.icon(icon).classes("text-lg").style(f"color: {fg}")
            ui.label(value).classes("text-subtitle1 text-weight-bold").style(f"color: {fg}")
        ui.label(label).classes("text-caption").style(f"color: {fg}; opacity: 0.8")


def _go_to_tab(tab_name: str, card_id=None):
    url = f"/job-intelligence?job={card_id}&tab={tab_name}" if card_id else "/job-intelligence"
    ui.navigate.to(url)


# ---------------------------------------------------------------------------
# Dedicated Job Profile page — lightweight, separate from the grid
# ---------------------------------------------------------------------------

@ui.page("/job-profile")
async def job_profile_page(request: Request):
    """Standalone job profile page — reached by clicking a job in the grid."""
    state.set("current_path", "/job-intelligence")
    page_layout("Job Profile")

    job_id_str = request.query_params.get("job")
    card_id_str = request.query_params.get("card")

    if not job_id_str:
        with ui.column().classes("w-full nicegui-content items-center q-pa-xl"):
            ui.icon("error_outline").classes("text-6xl text-grey-4")
            ui.label("No job specified.").classes("text-body1 text-grey-6")
            ui.button("Back to Jobs", icon="arrow_back",
                      on_click=lambda: ui.navigate.to("/job-intelligence")).props("flat")
        return

    try:
        job_id = int(job_id_str)
    except (ValueError, TypeError):
        ui.label("Invalid job ID.").classes("text-red-8")
        return

    card_id = None
    if card_id_str:
        try:
            card_id = int(card_id_str)
        except (ValueError, TypeError):
            pass

    profile = storage.get_job_profile(job_id)
    if not profile:
        with ui.column().classes("w-full nicegui-content items-center q-pa-xl"):
            ui.icon("search_off").classes("text-6xl text-grey-4")
            ui.label(f"No data found for job ID {job_id}.").classes("text-body1 text-grey-6")
            ui.button("Back to Jobs", icon="arrow_back",
                      on_click=lambda: ui.navigate.to("/job-intelligence")).props("flat")
        return

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        # Back button
        ui.button("Back to Jobs", icon="arrow_back",
                  on_click=lambda: ui.navigate.to("/job-intelligence")) \
            .props("flat color=primary size=sm")

        _render_profile_card(profile, card_id)


def _render_profile_card(profile: dict, card_id: int | None = None):
    """Render the full job profile card — used on the dedicated profile page."""
    job = profile["job"]
    tc = profile["timecards"]
    cc = profile["cost_codes"]
    top_codes = profile["top_codes"]
    rc = profile["rate_card"]
    richness = profile["data_richness"]
    r_color = _richness_color(richness)
    r_label = _richness_label(richness)

    # Clean job name (remove "8465 - " prefix duplication)
    job_name = job.get("name", "")
    job_number = job.get("job_number", "")
    if job_name.startswith(f"{job_number} - "):
        job_name = job_name[len(f"{job_number} - "):]

    with ui.card().classes("w-full q-pa-none").style("border: none; overflow: hidden"):

        # Header bar
        with ui.row().classes("w-full items-center justify-between q-pa-md") \
                .style(f"background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_LIGHT} 100%)"):
            with ui.column().classes("gap-0"):
                ui.label(f"Job {job_number}").classes("text-overline text-white").style("opacity: 0.8")
                ui.label(job_name).classes("text-h6 text-white text-weight-bold")
            with ui.row().classes("items-center").style("gap: 1rem"):
                # Data richness badge with tooltip
                with ui.column().classes("items-center gap-0"):
                    ui.label(f"{richness}").classes("text-h5 text-white text-weight-bold")
                    ui.label(r_label).classes("text-caption text-white").style("opacity: 0.8")
                    ui.tooltip(
                        "Data Richness Score (0-100)\n"
                        "25 pts: Has timecards\n"
                        "20 pts: Has budget data\n"
                        "20 pts: Has actual costs\n"
                        "10 pts: 5+ crew members\n"
                        "10 pts: 20+ work days\n"
                        "15 pts: Strong/moderate rate confidence"
                    ).classes("text-caption").style("white-space: pre-line")
                # Action buttons
                if card_id:
                    with ui.row().style("gap: 0.5rem"):
                        ui.button("Rate Card", icon="receipt_long",
                                  on_click=lambda cid=card_id: _go_to_tab("rate_card", cid)) \
                            .props("flat text-color=white size=sm")
                        ui.button("PM Review", icon="rate_review",
                                  on_click=lambda cid=card_id: _go_to_tab("review", cid)) \
                            .props("flat text-color=white size=sm")

        with ui.column().classes("w-full q-pa-md").style("gap: 1rem"):

            # Row 1: Key metrics
            tc_count = tc.get("tc_count") or 0
            cc_count = cc.get("cc_count") or 0
            emp_count = tc.get("employee_count") or 0
            work_days = tc.get("work_days") or 0
            total_hrs = tc.get("total_actual_hrs") or 0
            bgt_hrs = cc.get("total_budget_hrs") or 0
            bgt_cost = cc.get("total_budget_cost") or 0

            with ui.row().classes("w-full").style("gap: 1rem"):
                _mini_stat("Timecards", _fmt_num(tc_count), "receipt_long",
                           "green" if tc_count > 100 else ("amber" if tc_count > 0 else "grey"))
                _mini_stat("Cost Codes", _fmt_num(cc_count), "account_tree",
                           "green" if cc_count > 20 else ("amber" if cc_count > 0 else "grey"))
                _mini_stat("Crew Size", _fmt_num(emp_count), "group",
                           "green" if emp_count >= 10 else ("amber" if emp_count > 0 else "grey"))
                _mini_stat("Work Days", _fmt_num(work_days), "calendar_month",
                           "green" if work_days >= 60 else ("amber" if work_days > 0 else "grey"))
                _mini_stat("Actual Hours", _fmt_num(total_hrs), "schedule",
                           "green" if total_hrs >= 1000 else ("amber" if total_hrs > 0 else "grey"))
                _mini_stat("Budget", _fmt_num(bgt_cost, prefix="$"), "attach_money",
                           "green" if bgt_cost else "grey")

            # Row 2: Timeline + Hours comparison + Confidence
            with ui.row().classes("w-full").style("gap: 1rem"):

                # Timeline (based on timecard activity)
                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 200px"):
                    ui.label("Work Activity").classes("text-caption text-grey-7 text-weight-bold uppercase")
                    first = tc.get("first_date")
                    last = tc.get("last_date")
                    if first and last:
                        ui.label(f"{_fmt_date(first)} -- {_fmt_date(last)}").classes("text-subtitle2")
                        try:
                            d1 = datetime.strptime(str(first)[:10], "%Y-%m-%d")
                            d2 = datetime.strptime(str(last)[:10], "%Y-%m-%d")
                            months = max(1, (d2 - d1).days // 30)
                            ui.label(f"{months} months of timecard activity").classes("text-caption text-grey-6")
                        except (ValueError, TypeError):
                            pass
                        ui.label("Based on first/last timecard dates").classes(
                            "text-caption text-grey-5").style("font-style: italic; margin-top: 2px")
                    else:
                        ui.label("No timecard data").classes("text-caption text-grey-5")

                # Hours: Budget vs Actual
                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 220px"):
                    ui.label("Labor Hours").classes("text-caption text-grey-7 text-weight-bold uppercase")
                    if bgt_hrs and total_hrs:
                        pct = (total_hrs / bgt_hrs) * 100
                        over = pct > 100
                        bar_color = "negative" if over else ("positive" if pct >= 80 else "primary")
                        with ui.row().classes("items-baseline").style("gap: 0.5rem"):
                            ui.label(f"{_fmt_num(total_hrs)}").classes("text-subtitle1 text-weight-bold")
                            ui.label(f"/ {_fmt_num(bgt_hrs)} budget").classes("text-caption text-grey-6")
                        # Custom bar instead of linear_progress to avoid text overlap
                        with ui.element("div").style(
                            "width: 100%; height: 6px; background: #E0E0E0; border-radius: 3px; "
                            "overflow: hidden; margin-top: 4px"
                        ):
                            ui.element("div").style(
                                f"width: {min(pct, 100):.0f}%; height: 100%; "
                                f"background: {'#dc3545' if over else ('#28a745' if pct >= 80 else '#1565C0')}; "
                                f"border-radius: 3px"
                            )
                        variance_label = f"{pct:.0f}% of budget"
                        if over:
                            variance_label += f" (+{pct - 100:.0f}% over)"
                        ui.label(variance_label).classes(
                            f"text-caption {'text-red-8 text-weight-bold' if over else 'text-grey-6'}"
                        )
                    elif total_hrs:
                        ui.label(f"{_fmt_num(total_hrs)} actual hours").classes("text-subtitle2")
                        ui.label("No budget to compare").classes("text-caption text-grey-5")
                    else:
                        ui.label("No hours data").classes("text-caption text-grey-5")

                # Confidence breakdown with legend
                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 240px"):
                    with ui.row().classes("items-center").style("gap: 0.25rem"):
                        ui.label("Rate Confidence").classes("text-caption text-grey-7 text-weight-bold uppercase")
                        with ui.icon("info_outline").classes("text-sm text-grey-5").style("cursor: help"):
                            ui.tooltip(
                                "Strong: Both budget and actual data with consistent results -- safe to use directly\n"
                                "Moderate: Has data but limited samples or some inconsistency -- use with judgment\n"
                                "Limited: Minimal data points -- cross-reference with other jobs before using\n"
                                "None: No usable data -- do not use for estimating"
                            ).classes("text-caption").style("white-space: pre-line; max-width: 320px")
                    if rc:
                        total_items = rc.get("rate_items") or 0
                        strong = rc.get("conf_strong") or 0
                        moderate = rc.get("conf_moderate") or 0
                        limited = rc.get("conf_limited") or 0
                        none_c = rc.get("conf_none") or 0
                        if total_items > 0:
                            # Stacked bar
                            with ui.row().classes("w-full q-mt-xs").style(
                                "height: 8px; border-radius: 4px; overflow: hidden; gap: 0"
                            ):
                                for cnt, color in [
                                    (strong, SUCCESS), (moderate, WARNING),
                                    (limited, DANGER), (none_c, "#E0E0E0"),
                                ]:
                                    if cnt > 0:
                                        pct = (cnt / total_items) * 100
                                        ui.element("div").style(
                                            f"width: {pct}%; height: 100%; background: {color}"
                                        )
                            # Legend counts
                            with ui.row().classes("q-mt-xs").style("gap: 0.75rem"):
                                for cnt, label, color in [
                                    (strong, "Strong", SUCCESS), (moderate, "Moderate", WARNING),
                                    (limited, "Limited", DANGER), (none_c, "None", "#9E9E9E"),
                                ]:
                                    if cnt > 0:
                                        ui.label(f"{cnt} {label}").classes("text-caption") \
                                            .style(f"color: {color}")
                            # Contextual advisory
                            reliable_pct = ((strong + moderate) / total_items) * 100
                            if reliable_pct >= 60:
                                ui.label(f"{reliable_pct:.0f}% of rates are usable for estimating").classes(
                                    "text-caption text-green-8 q-mt-xs")
                            elif reliable_pct >= 30:
                                ui.label(f"Only {reliable_pct:.0f}% of rates are reliable -- review flagged items before using").classes(
                                    "text-caption text-amber-9 q-mt-xs")
                            else:
                                ui.label("Most rates lack sufficient data -- cross-reference with similar jobs").classes(
                                    "text-caption text-red-8 q-mt-xs")
                    else:
                        ui.label("No rate card").classes("text-caption text-grey-5")

            # Row 3: Top cost codes
            if top_codes:
                with ui.card().classes("w-full q-pa-sm"):
                    ui.label("Top Activities by Hours").classes(
                        "text-caption text-grey-7 text-weight-bold uppercase q-mb-xs"
                    )
                    max_hrs = top_codes[0]["actual_hrs"] if top_codes else 1
                    for tc_row in top_codes:
                        code = tc_row["cost_code"]
                        desc = tc_row.get("description") or "N/A"
                        hrs = tc_row["actual_hrs"]
                        workers = tc_row.get("workers") or 0

                        with ui.row().classes("w-full items-center").style("gap: 0.5rem; min-height: 28px"):
                            ui.label(code).classes("text-weight-bold text-caption") \
                                .style("width: 55px; flex-shrink: 0")
                            ui.label(desc).classes("text-caption text-grey-8") \
                                .style("width: 180px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis")
                            # Proportional bar
                            with ui.element("div").style(
                                "flex: 1; height: 14px; background: #F0F0F0; border-radius: 3px; overflow: hidden; position: relative"
                            ):
                                bar_pct = (hrs / max_hrs) if max_hrs else 0
                                ui.element("div").style(
                                    f"width: {bar_pct * 100:.0f}%; height: 100%; "
                                    f"background: linear-gradient(90deg, {PRIMARY} 0%, {PRIMARY_LIGHT} 100%); "
                                    f"border-radius: 3px"
                                )
                            ui.label(f"{hrs:,.0f} hrs").classes("text-caption text-weight-medium") \
                                .style("width: 75px; text-align: right; flex-shrink: 0")
                            ui.label(f"{workers} crew").classes("text-caption text-grey-6") \
                                .style("width: 55px; text-align: right; flex-shrink: 0")


def _render_rate_card_detail(cards, selected_card):
    """Tab 2: Rate card items for the selected job."""
    badge_label = STATUS_BADGE_MAP.get(selected_card["status"], ("?",))[0]

    with ui.row().classes("w-full items-center justify-between q-mb-sm"):
        ui.label(f"Job {selected_card['job_number']} -- {selected_card.get('job_name', '')}") \
            .classes("text-h6 text-weight-bold")
        status_badge(badge_label, STATUS_BADGE_MAP.get(selected_card["status"], ("?", "grey"))[1])

    # Job selector dropdown
    card_options = {c["card_id"]: f"Job {c['job_number']} -- {c['job_name']}" for c in cards}
    ui.select(card_options, value=selected_card["card_id"],
              on_change=lambda e: _select_card_and_stay(e.value, "rate_card")) \
        .classes("w-80 q-mb-sm")

    card_id = selected_card["card_id"]
    items = storage.get_rate_items_for_card(card_id)

    if not items:
        ui.label("No rate items for this card.").classes("text-grey-7 q-mt-sm")
        return

    flagged = storage.get_flagged_items_for_card(card_id)
    disciplines = sorted(set(i.get("discipline", "Unknown") for i in items))

    # Summary metrics
    unmapped_count = sum(1 for i in items if (i.get("discipline") or "").lower() in ("unmapped", ""))
    mapped_disciplines = [d for d in disciplines if d.lower() not in ("unmapped", "")]
    with ui.row().style("gap: 1.5rem"):
        for lbl, val in [
            ("Rate Items", len(items)),
            ("Disciplines", len(mapped_disciplines)),
            ("Flagged", len(flagged)),
        ]:
            with ui.column().classes("items-center"):
                ui.label(str(val)).classes("text-weight-bold text-h6")
                ui.label(lbl).classes("text-caption text-grey-7 uppercase")
    if unmapped_count > 0:
        with ui.row().classes("items-center q-mt-xs").style("gap: 0.25rem"):
            ui.icon("info_outline").classes("text-sm text-amber-8")
            ui.label(
                f"{unmapped_count} items have no discipline mapping -- "
                f"these cost codes couldn't be auto-classified. "
                f"They still have rate data but won't appear in discipline-level summaries."
            ).classes("text-caption text-amber-9")

    # Filter out noise rows: no rates at all AND limited/none confidence
    meaningful_items = [
        i for i in items
        if not (
            (i.get("act_mh_per_unit") is None or i.get("act_mh_per_unit") == 0)
            and (i.get("bgt_mh_per_unit") is None or i.get("bgt_mh_per_unit") == 0)
            and (i.get("confidence") or "none") in ("none", "limited")
        )
    ]
    filtered_count = len(items) - len(meaningful_items)

    # AG Grid — wider columns to prevent header truncation
    col_defs = [
        {"headerName": "Discipline", "field": "discipline", "sortable": True, "filter": True,
         "width": 150, "rowGroup": False,
         ":valueFormatter": "p => p.value === 'unmapped' ? 'Unmapped' : (p.value || '--').replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase())",
         "cellClassRules": {
             "text-amber-8 italic": "x === 'unmapped'",
         }},
        {"headerName": "Cost Code", "field": "activity", "sortable": True, "filter": True, "width": 120},
        {"headerName": "Description", "field": "description", "flex": 1, "minWidth": 180, "filter": True},
        {"headerName": "Unit", "field": "unit", "width": 80},
        {"headerName": "Bgt MH/Unit", "field": "bgt_mh_per_unit", "width": 120,
         "headerTooltip": "Budget Man-Hours per Unit",
         ":valueFormatter": "p => p.value != null && p.value > 0 ? p.value.toFixed(4) : '--'",
         "type": "numericColumn"},
        {"headerName": "Act MH/Unit", "field": "act_mh_per_unit", "width": 120,
         "headerTooltip": "Actual Man-Hours per Unit",
         ":valueFormatter": "p => p.value != null && p.value > 0 ? p.value.toFixed(4) : '--'",
         "type": "numericColumn"},
        {"headerName": "Rec Rate", "field": "rec_rate", "width": 120,
         "headerTooltip": "Recommended Rate for Future Estimates",
         ":valueFormatter": "p => p.value != null && p.value > 0 ? p.value.toFixed(4) : '--'",
         "type": "numericColumn"},
        {"headerName": "Confidence", "field": "confidence", "width": 110,
         "cellClassRules": {
             "bg-green-100 text-green-800": "x === 'strong'",
             "bg-amber-100 text-amber-800": "x === 'moderate'",
             "bg-red-100 text-red-800": "x === 'limited'",
             "bg-gray-100 text-gray-500": "x === 'none'",
         }},
        {"headerName": "Variance", "field": "variance_pct", "width": 110,
         "headerTooltip": "Actual vs Budget Variance %",
         ":valueFormatter": "p => p.value != null ? (p.value > 0 ? '+' : '') + p.value.toFixed(1) + '%' : '--'",
         "cellClassRules": {
             "text-red-8 text-weight-bold": "x != null && x > 5",
             "text-green-8": "x != null && x < -5",
         }},
        {"headerName": "", "field": "variance_flag", "width": 50,
         ":cellRenderer": "p => p.value ? '\u26a0\ufe0f' : ''",
         "headerTooltip": "Flagged for review"},
    ]

    rows = []
    for item in meaningful_items:
        row = dict(item)
        row["confidence"] = (row.get("confidence") or "moderate")
        row["description"] = row.get("description") or "--"
        row["unit"] = row.get("unit") or "--"
        rows.append(row)

    ui.aggrid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True},
        "rowClassRules": {
            "bg-yellow-50": "data.variance_flag",
        },
        "tooltipShowDelay": 200,
    }).classes("w-full q-mt-sm").style("height: 500px")

    if filtered_count > 0:
        ui.label(f"{filtered_count} items with no data hidden").classes("text-caption text-grey-5 q-mt-xs")

    # Flagged items
    if flagged:
        with ui.expansion(f"Flagged Variances ({len(flagged)})", icon="flag").classes("w-full q-mt-md"):
            for f_item in flagged:
                pct = f_item["variance_pct"]
                color = DANGER if pct > 0 else SUCCESS
                direction = "over" if pct > 0 else "under"
                with ui.card().classes("w-full q-pa-sm q-mb-xs").style(f"border-left: 3px solid {color}"):
                    ui.label(
                        f"{f_item['activity']} -- {f_item.get('description') or 'N/A'} -- "
                        f"{abs(pct):.0f}% {direction} budget"
                    ).classes("text-weight-medium")
                    if f_item.get("variance_explanation"):
                        ui.label(f"Explanation: {f_item['variance_explanation']}") \
                            .classes("text-caption text-grey-7")


def _select_card_and_stay(card_id, tab_name):
    ui.navigate.to(f"/job-intelligence?job={card_id}&tab={tab_name}")


def _render_pm_review(cards, selected_card):
    """Tab 3: PM Review for selected job."""
    card_id = selected_card["card_id"]
    current_status = selected_card["status"]
    review = RateCardReview()

    with ui.row().classes("w-full items-center justify-between q-mb-sm"):
        ui.label(f"Job {selected_card['job_number']} -- {selected_card.get('job_name', '')}") \
            .classes("text-h6 text-weight-bold")

    # Job selector
    card_options = {c["card_id"]: f"Job {c['job_number']} -- {c['job_name']}" for c in cards}
    ui.select(card_options, value=selected_card["card_id"],
              on_change=lambda e: _select_card_and_stay(e.value, "review")) \
        .classes("w-80 q-mb-md")

    # Workflow stage indicator
    stages = [
        ("draft", "Draft", "edit_note"),
        ("pending_review", "In Review", "rate_review"),
        ("approved", "Approved", "check_circle"),
    ]
    with ui.row().classes("w-full items-center q-mb-lg").style("gap: 0"):
        for i, (stage_key, stage_label, stage_icon) in enumerate(stages):
            is_current = current_status == stage_key
            is_past = list(dict([(s[0], j) for j, s in enumerate(stages)]).keys()).index(stage_key) < \
                       list(dict([(s[0], j) for j, s in enumerate(stages)]).keys()).index(current_status) \
                       if current_status in [s[0] for s in stages] else False
            if is_current:
                color, bg = PRIMARY, "#E3F2FD"
            elif is_past:
                color, bg = SUCCESS, "#E8F5E9"
            else:
                color, bg = "#BDBDBD", "#FAFAFA"
            with ui.row().classes("items-center").style(f"gap: 0.4rem; padding: 0.4rem 0.75rem; border-radius: 6px; background: {bg}"):
                ui.icon(stage_icon).classes("text-lg").style(f"color: {color}")
                ui.label(stage_label).classes("text-caption text-weight-bold").style(f"color: {color}")
            if i < len(stages) - 1:
                ui.icon("chevron_right").classes("text-lg text-grey-4")

    # Load rate item data for the summary (used by draft and pending_review)
    items = storage.get_rate_items_for_card(card_id)
    flagged = storage.get_flagged_items_for_card(card_id)

    # Review summary card — shown for all statuses
    if items:
        mapped_discs = sorted(set(
            i.get("discipline", "") for i in items
            if (i.get("discipline") or "").lower() not in ("unmapped", "")
        ))
        conf_counts = {}
        for it in items:
            c = it.get("confidence") or "none"
            conf_counts[c] = conf_counts.get(c, 0) + 1

        with ui.card().classes("w-full q-pa-md q-mb-md").style("background: #F5F5F5"):
            ui.label("What's Being Reviewed").classes("text-subtitle2 text-weight-bold q-mb-xs")
            with ui.row().style("gap: 2rem"):
                for lbl, val in [
                    ("Rate Items", len(items)),
                    ("Disciplines", len(mapped_discs)),
                    ("Flagged", len(flagged) if flagged else 0),
                ]:
                    with ui.column().classes("items-center gap-0"):
                        ui.label(str(val)).classes("text-h6 text-weight-bold")
                        ui.label(lbl).classes("text-caption text-grey-7")
            # Confidence breakdown
            with ui.row().classes("q-mt-sm").style("gap: 1rem"):
                for level, label, color in [
                    ("strong", "Strong", SUCCESS), ("moderate", "Moderate", WARNING),
                    ("limited", "Limited", DANGER), ("none", "None", "#9E9E9E"),
                ]:
                    cnt = conf_counts.get(level, 0)
                    if cnt > 0:
                        ui.label(f"{cnt} {label}").classes("text-caption").style(f"color: {color}")
            if flagged:
                ui.label(f"{len(flagged)} items flagged for variance review -- PM should explain these").classes(
                    "text-caption text-amber-9 q-mt-xs")

    if current_status == "draft":
        def submit():
            try:
                review.submit_for_review(card_id)
                ui.notify("Card submitted for PM review", type="positive")
                ui.navigate.to("/job-intelligence")
            except ValueError as e:
                ui.notify(str(e), type="negative")

        ui.label("Submit this rate card for PM review. The PM will be asked to explain flagged "
                 "variances and confirm rate recommendations.") \
            .classes("text-body2 text-grey-7 q-mb-sm")
        ui.button("Submit for PM Review", icon="send",
                  on_click=submit).props("color=primary")

    elif current_status == "pending_review":
        job = storage.get_job_by_number(selected_card["job_number"])
        if not job:
            ui.label("Job data not found.").classes("text-grey-7")
            return

        codes = storage.get_cost_codes_for_job(job["job_id"])
        if not codes:
            ui.label("No cost codes found.").classes("text-grey-7")
            return

        generator = RateCardGenerator()
        card_result = generator.generate_rate_card(
            job_number=selected_card["job_number"],
            job_name=selected_card.get("job_name", ""),
            cost_codes=codes,
        )
        workflow = PMInterviewWorkflow(rate_card=card_result)
        questions = workflow.generate_questions()

        if not questions:
            ui.label("No review questions generated.").classes("text-grey-7")
            return

        responses = state.get("interview_responses", {})

        q_by_type = {}
        for q in questions:
            q_by_type.setdefault(q["type"], []).append(q)

        TYPE_LABELS = {
            "VARIANCE": "Variance Questions",
            "LESSONS": "Lessons Learned",
            "CONTEXT": "Project Context",
            "RATE_CONFIRM": "Rate Confirmation",
        }

        for q_type in ["VARIANCE", "LESSONS", "CONTEXT", "RATE_CONFIRM"]:
            type_qs = q_by_type.get(q_type, [])
            if not type_qs:
                continue

            label = TYPE_LABELS.get(q_type, q_type)
            required = " (required)" if q_type == "VARIANCE" else ""

            with ui.expansion(f"{label}{required}", icon="quiz").classes("w-full"):
                for q in type_qs:
                    def make_handler(qid):
                        def handler(e):
                            responses[qid] = e.value
                            state.set("interview_responses", responses)
                        return handler

                    ui.textarea(q["question_text"],
                                value=responses.get(q["id"], ""),
                                on_change=make_handler(q["id"])) \
                        .classes("w-full")

        pm_name_input = ui.input("PM Name", value="Travis Sparks").classes("w-64 q-mt-md")
        pm_notes_input = ui.textarea("Review Notes (optional)").classes("w-full")

        with ui.row().classes("q-mt-sm").style("gap: 0.5rem"):
            def approve():
                responses_final = state.get("interview_responses", {})
                for q_id, resp in responses_final.items():
                    try:
                        workflow.submit_response(q_id, resp)
                    except ValueError:
                        pass

                if workflow.is_complete():
                    workflow.finalize(pm_name=pm_name_input.value)
                    review.approve(card_id, pm_name=pm_name_input.value,
                                   notes=pm_notes_input.value or None)
                    state.set("interview_responses", {})
                    ui.notify("Rate card approved and knowledge base updated!", type="positive")
                    ui.navigate.to("/job-intelligence")
                else:
                    ui.notify("Please answer all required variance questions.", type="warning")

            ui.button("Approve Rate Card", icon="check",
                      on_click=approve).props("color=positive")

            reject_input = ui.input("Rejection reason").classes("w-64")

            def reject():
                if reject_input.value:
                    review.reject(card_id, reject_input.value)
                    state.set("interview_responses", {})
                    ui.notify("Card rejected and returned to draft.", type="info")
                    ui.navigate.to("/job-intelligence")
                else:
                    ui.notify("Please provide a rejection reason.", type="warning")

            ui.button("Reject -- Back to Draft", icon="close",
                      on_click=reject).props("color=negative outline")

    elif current_status == "approved":
        with ui.card().classes("w-full q-pa-md").style("border-left: 4px solid #28a745"):
            ui.label("Rate Card Approved").classes("text-subtitle2 text-weight-bold text-green-9")
            ui.label(
                f"Approved by {selected_card.get('pm_name', 'N/A')} "
                f"on {_friendly_timestamp(selected_card.get('review_date', '')) or selected_card.get('review_date', 'N/A')}"
            ).classes("text-body2 q-mt-xs")
            if selected_card.get("pm_notes"):
                ui.label(f"Notes: {selected_card['pm_notes']}").classes("text-caption text-grey-7 q-mt-xs")


