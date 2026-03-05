"""Job Intelligence page — sync, job cards, rate card detail, PM review, KB summary."""

import asyncio
from pathlib import Path

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui import state
from app.ui.components import (
    page_header, metric_card, section_header, status_badge,
    empty_state, confirm_dialog, bid_status_color,
)
from app.ui.theme import PRIMARY, SUCCESS, DANGER, WARNING
from app.hcss.auth import HCSSAuth
from app.hcss.sync import HCSSSyncOrchestrator, MockHeavyJobSource, MockHeavyBidSource
from app.hcss.file_source import FileHeavyJobSource, EmptyHeavyBidSource
from app.hcss import storage
from app.catalog.review import RateCardReview
from app.catalog.interview import PMInterviewWorkflow
from app.transform.rate_card import RateCardGenerator
from app.database import get_connection

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


def _get_kb_counts():
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


@ui.page("/job-intelligence")
async def job_intelligence_page():
    state.set("current_path", "/job-intelligence")
    page_layout("Job Intelligence")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header(
            "Job Intelligence",
            "Turn completed job data into estimating intelligence — rates, benchmarks, and lessons."
        )

        # Top KPI row
        cards = storage.get_all_rate_cards()
        rl_count, bm_count, ll_count = _get_kb_counts()

        with ui.row().classes("w-full").style("gap: 1rem"):
            for label, val, icon in [
                ("Jobs Analyzed", len(cards), "work"),
                ("Rate Cards", len(cards), "receipt_long"),
                ("KB Rates", rl_count, "library_books"),
                ("Flagged Items", sum(c.get("flagged_count", 0) for c in cards), "flag"),
            ]:
                with ui.column().classes("flex-1"):
                    metric_card(label, val, icon=icon)

        ui.separator()

        # ═══ Section A: Data Import ═══
        _render_import_section(cards)

        if not cards:
            empty_state("No job data yet. Import jobs above to get started.",
                        icon="cloud_download",
                        action_label=None)
            return

        # ═══ Section B: Job Overview ═══
        _render_job_overview(cards)

        ui.separator()

        # ═══ Section C: Rate Card Detail ═══
        _render_rate_card_detail(cards)

        ui.separator()

        # ═══ Section D: PM Review ═══
        _render_pm_review(cards)

        ui.separator()

        # ═══ Section E: KB Summary ═══
        _render_kb_summary()


def _render_import_section(cards):
    """Section A: Data Import."""
    with ui.expansion("Import Job Data", icon="cloud_download",
                      value=len(cards) == 0).classes("w-full"):
        if is_live:
            ui.label("Live API credentials detected — connected to HCSS").classes("text-green-9")
        elif has_file_reports:
            report_files = list(REPORTS_DIR.glob("* - CstAlys.xlsx"))
            job_nums = [f.name.split(" - ")[0] for f in report_files]
            ui.label(f"HeavyJob Cost Reports found: {', '.join(sorted(job_nums))}") \
                .classes("text-blue-9")
        else:
            ui.label("No API credentials — using mock data from Phase B test files") \
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

        # Sync history
        history = storage.get_sync_history(limit=5)
        if history:
            ui.label("Recent imports:").classes("text-weight-bold q-mt-md text-body2")
            for h in history:
                icon = {"completed": "check_circle", "failed": "error", "running": "hourglass_top"} \
                    .get(h["status"], "help")
                color = {"completed": "text-green-9", "failed": "text-red-9"}.get(h["status"], "")
                ui.label(
                    f"{h['started_at'][:19]} — {h['sync_type']} — "
                    f"{h['jobs_processed']} jobs — {h['status']}"
                ).classes(f"text-caption {color}")


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


def _render_job_overview(cards):
    """Section B: Job Overview."""
    section_header("Job Overview")

    for card in cards:
        badge_label, badge_color = STATUS_BADGE_MAP.get(card["status"], ("Unknown", "grey"))
        items = storage.get_rate_items_for_card(card["card_id"])
        flagged_count = card.get("flagged_count", 0)
        cpi = card.get("cpi")

        with ui.card().classes("w-full"):
            # Header
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Job {card['job_number']} — {card['job_name']}") \
                    .classes("text-h6 text-weight-bold")
                status_badge(badge_label, badge_color)

            # Metrics row
            with ui.row().classes("w-full q-mt-sm").style("gap: 1rem"):
                for lbl, val in [
                    ("CPI", f"{cpi:.3f}" if cpi else "N/A"),
                    ("Cost Codes", len(items)),
                    ("Flagged", flagged_count),
                    ("Budget", f"${card.get('total_budget', 0):,.0f}" if card.get("total_budget") else "N/A"),
                    ("Actual", f"${card.get('total_actual', 0):,.0f}" if card.get("total_actual") else "N/A"),
                ]:
                    with ui.column().classes("items-center"):
                        ui.label(str(val)).classes("text-weight-bold text-h6")
                        ui.label(lbl).classes("text-caption text-grey-7 uppercase")

            # CPI interpretation
            if cpi is not None:
                if cpi >= 1.0:
                    ui.label(f"CPI: {cpi:.3f} — Under budget").classes("text-body2 q-mt-xs") \
                        .style(f"color: {SUCCESS}")
                else:
                    ui.label(f"CPI: {cpi:.3f} — Over budget").classes("text-body2 q-mt-xs") \
                        .style(f"color: {DANGER}")

            ui.button("View Details", icon="visibility",
                      on_click=lambda cid=card["card_id"]: _select_card(cid)) \
                .props("flat color=primary size=sm").classes("q-mt-sm")


def _select_card(card_id):
    state.set("ji_selected_card_id", card_id)
    ui.navigate.to("/job-intelligence")


def _render_rate_card_detail(cards):
    """Section C: Rate Card Detail."""
    selected_id = state.get("ji_selected_card_id")
    selected_card = None
    if selected_id:
        for c in cards:
            if c["card_id"] == selected_id:
                selected_card = c
                break

    if selected_card is None:
        selected_card = cards[0]

    badge_label = STATUS_BADGE_MAP.get(selected_card["status"], ("?",))[0]
    section_header(f"Rate Card — Job {selected_card['job_number']} ({badge_label})")

    # Job selector
    card_options = {c["card_id"]: f"Job {c['job_number']} — {c['job_name']}" for c in cards}
    ui.select(card_options, value=selected_card["card_id"],
              on_change=lambda e: _select_card(e.value)) \
        .classes("w-64")

    card_id = selected_card["card_id"]
    items = storage.get_rate_items_for_card(card_id)

    if not items:
        ui.label("No rate items for this card.").classes("text-grey-7 q-mt-sm")
        return

    # Summary metrics
    flagged = storage.get_flagged_items_for_card(card_id)
    disciplines = set(i.get("discipline", "Unknown") for i in items)

    with ui.row().classes("q-mt-sm").style("gap: 1rem"):
        for lbl, val in [
            ("Rate Items", len(items)),
            ("Disciplines", len(disciplines)),
            ("Flagged Variances", len(flagged)),
        ]:
            with ui.column().classes("items-center"):
                ui.label(str(val)).classes("text-weight-bold text-h6")
                ui.label(lbl).classes("text-caption text-grey-7 uppercase")

    # AG Grid table
    col_defs = [
        {"headerName": "Discipline", "field": "discipline", "sortable": True, "filter": True, "width": 130},
        {"headerName": "Cost Code", "field": "activity", "sortable": True, "filter": True, "width": 110},
        {"headerName": "Description", "field": "description", "flex": 1, "minWidth": 150},
        {"headerName": "Unit", "field": "unit", "width": 80},
        {"headerName": "Budget Rate", "field": "bgt_mh_per_unit", "width": 110,
         ":valueFormatter": "p => p.value != null ? p.value.toFixed(4) : (p.data.confidence === 'none' ? 'Needs data' : '—')",
         "cellClassRules": {"text-gray-400 italic": "x.value == null && x.data.confidence === 'none'"}},
        {"headerName": "Actual Rate", "field": "act_mh_per_unit", "width": 110,
         ":valueFormatter": "p => p.value != null ? p.value.toFixed(4) : (p.data.confidence === 'none' ? 'Needs data' : '—')",
         "cellClassRules": {"text-gray-400 italic": "x.value == null && x.data.confidence === 'none'"}},
        {"headerName": "Recommended", "field": "rec_rate", "width": 120,
         ":valueFormatter": "p => p.value != null ? p.value.toFixed(4) : (p.data.confidence === 'none' ? 'Needs data' : '—')",
         "cellClassRules": {"text-gray-400 italic": "x.value == null && x.data.confidence === 'none'"}},
        {"headerName": "Confidence", "field": "confidence", "width": 110,
         "cellClassRules": {
             "bg-green-100 text-green-800": "x.value === 'strong'",
             "bg-amber-100 text-amber-800": "x.value === 'moderate'",
             "bg-red-100 text-red-800": "x.value === 'limited'",
             "bg-gray-100 text-gray-500": "x.value === 'none'",
         }},
        {"headerName": "Variance %", "field": "variance_pct", "width": 110,
         ":valueFormatter": "p => p.value != null ? (p.value > 0 ? '+' : '') + p.value.toFixed(1) + '%' : '—'"},
        {"headerName": "Flagged", "field": "variance_flag", "width": 90,
         ":cellRenderer": "p => p.value ? '⚠️' : ''"},
    ]

    # Clean data for grid
    rows = []
    for item in items:
        row = dict(item)
        row["confidence"] = (row.get("confidence") or "moderate")
        row["description"] = row.get("description") or "—"
        row["unit"] = row.get("unit") or "—"
        rows.append(row)

    ui.aggrid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True},
        "rowClassRules": {
            "bg-yellow-50": "data.variance_flag",
        },
    }).classes("w-full q-mt-sm").style("height: 500px")

    # Flagged items alerts
    if flagged:
        ui.label(f"Flagged Variances ({len(flagged)})").classes("text-weight-bold q-mt-md")
        for f_item in flagged:
            pct = f_item["variance_pct"]
            color = DANGER if pct > 0 else SUCCESS
            direction = "over" if pct > 0 else "under"
            with ui.card().classes("w-full q-pa-sm").style(f"border-left: 3px solid {color}"):
                ui.label(
                    f"{f_item['activity']} — {f_item.get('description') or 'N/A'} — "
                    f"{abs(pct):.0f}% {direction} budget"
                ).classes("text-weight-medium")
                if f_item.get("variance_explanation"):
                    ui.label(f"Explanation: {f_item['variance_explanation']}").classes("text-caption text-grey-7")


def _render_pm_review(cards):
    """Section D: PM Review."""
    selected_id = state.get("ji_selected_card_id")
    selected_card = None
    if selected_id:
        for c in cards:
            if c["card_id"] == selected_id:
                selected_card = c
                break
    if selected_card is None:
        selected_card = cards[0]

    card_id = selected_card["card_id"]
    current_status = selected_card["status"]
    review = RateCardReview()

    if current_status == "draft":
        section_header("Review")
        def submit():
            try:
                review.submit_for_review(card_id)
                ui.notify("Card submitted for PM review", type="positive")
                ui.navigate.to("/job-intelligence")
            except ValueError as e:
                ui.notify(str(e), type="negative")

        ui.button("Submit for PM Review", icon="send",
                  on_click=submit).props("color=primary")

    elif current_status == "pending_review":
        section_header("PM Review",
                       f"Review rate card for Job {selected_card['job_number']}")

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

        # Store responses in tab state
        responses = state.get("interview_responses", {})

        # Group by type
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

        # PM name and actions
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

            ui.button("Reject — Back to Draft", icon="close",
                      on_click=reject).props("color=negative outline")

    elif current_status == "approved":
        section_header("Review")
        ui.label(
            f"Approved by {selected_card.get('pm_name', 'N/A')} "
            f"on {selected_card.get('review_date', 'N/A')}"
        ).classes("text-green-9 text-weight-medium")
        if selected_card.get("pm_notes"):
            ui.label(f"Notes: {selected_card['pm_notes']}").classes("text-body2 text-grey-7")


def _render_kb_summary():
    """Section E: Knowledge Base Summary."""
    section_header("Your Rate Library")

    rl_count, bm_count, ll_count = _get_kb_counts()

    if rl_count == 0 and bm_count == 0 and ll_count == 0:
        ui.label("Approve rate cards to build your knowledge base.").classes("text-grey-7")
        return

    conn = get_connection()
    try:
        # Rates by discipline
        rates = conn.execute(
            "SELECT discipline, activity, description, rate, unit, confidence, "
            "jobs_count, source_jobs, rate_low, rate_high "
            "FROM rate_library ORDER BY discipline, activity"
        ).fetchall()

        if rates:
            ui.label(f"Rates ({len(rates)})").classes("text-weight-bold q-mt-sm")

            by_disc = {}
            for r in rates:
                disc = (r["discipline"] or "Other").replace("_", " ").title()
                by_disc.setdefault(disc, []).append(r)

            for disc, disc_rates in by_disc.items():
                with ui.expansion(f"{disc} ({len(disc_rates)} rates)").classes("w-full"):
                    for r in disc_rates:
                        conf_icon = {"strong": "verified", "moderate": "info", "limited": "warning"} \
                            .get(r["confidence"], "help")
                        range_text = ""
                        if r["rate_low"] is not None and r["rate_high"] is not None:
                            range_text = f" (range: {r['rate_low']:.4f} — {r['rate_high']:.4f})"
                        jobs_text = f" from {r['jobs_count']} job(s)" if r["jobs_count"] else ""
                        if r["source_jobs"]:
                            jobs_text += f": {r['source_jobs']}"

                        with ui.row().classes("items-start").style("gap: 0.5rem"):
                            ui.icon(conf_icon).classes("text-sm mt-1")
                            with ui.column().classes("gap-0"):
                                ui.label(f"{r['activity']} — {r['description'] or 'N/A'}") \
                                    .classes("text-weight-medium text-body2")
                                ui.label(f"Rate: {r['rate']:.4f} {r['unit']}{range_text}{jobs_text}") \
                                    .classes("text-caption text-grey-7")

        # Benchmarks
        benchmarks = conn.execute(
            "SELECT metric, description, value, unit, jobs_count, source_jobs, "
            "range_low, range_high FROM benchmark ORDER BY metric"
        ).fetchall()

        if benchmarks:
            ui.label(f"Benchmarks ({len(benchmarks)})").classes("text-weight-bold q-mt-md")
            with ui.row().classes("flex-wrap").style("gap: 1rem"):
                for bm in benchmarks:
                    label = (bm["description"] or bm["metric"]).replace("_", " ").title()
                    range_text = ""
                    if bm["range_low"] is not None and bm["range_high"] is not None:
                        range_text = f"Range: {bm['range_low']:.2f} — {bm['range_high']:.2f}"
                    with ui.card().classes("q-pa-md"):
                        ui.label(f"{bm['value']:.4f} {bm['unit'] or ''}").classes("text-weight-bold text-h6")
                        ui.label(label).classes("text-body2 text-grey-8")
                        if range_text:
                            ui.label(range_text).classes("text-caption text-grey-6")
                        ui.label(f"{bm['jobs_count'] or 0} job(s)").classes("text-caption text-grey-6")

        # Lessons
        lessons = conn.execute(
            "SELECT l.discipline, l.category, l.description, l.impact, "
            "l.recommendation, l.pm_name, j.job_number "
            "FROM lesson_learned l LEFT JOIN job j ON l.job_id = j.job_id "
            "ORDER BY l.captured_date DESC"
        ).fetchall()

        if lessons:
            ui.label(f"Lessons Learned ({len(lessons)})").classes("text-weight-bold q-mt-md")
            for ls in lessons:
                impact_icon = {"high": "error", "medium": "warning", "low": "check_circle"} \
                    .get(ls["impact"], "help")
                cat = (ls["category"] or "general").capitalize()
                disc = (ls["discipline"] or "General").replace("_", " ").title()

                with ui.card().classes("w-full q-pa-sm"):
                    with ui.row().classes("items-start").style("gap: 0.5rem"):
                        ui.icon(impact_icon).classes("text-sm mt-1")
                        with ui.column().classes("gap-0"):
                            ui.label(f"[{cat}] {ls['description']}").classes("text-body2")
                            meta = []
                            if ls["recommendation"]:
                                meta.append(f"Recommendation: {ls['recommendation']}")
                            if ls["job_number"]:
                                meta.append(f"Job {ls['job_number']}")
                            if ls["pm_name"]:
                                meta.append(f"PM: {ls['pm_name']}")
                            if meta:
                                ui.label(" | ".join(meta)).classes("text-caption text-grey-6")
    finally:
        conn.close()
