"""Knowledge Base page — browsable rates, benchmarks, lessons."""

from nicegui import ui
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card, section_header, empty_state
from app.ui import state
from app.ui.theme import SUCCESS, WARNING, DANGER
from app.database import get_connection


@ui.page("/knowledge-base")
async def knowledge_base_page():
    state.set("current_path", "/knowledge-base")
    page_layout("Knowledge Base")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header(
            "Knowledge Base",
            "Everything WEIS has learned from your completed jobs — rates, benchmarks, and lessons."
        )

        conn = get_connection()
        try:
            rates = [dict(r) for r in conn.execute(
                "SELECT discipline, activity, description, rate, unit, rate_type, "
                "confidence, jobs_count, source_jobs, rate_low, rate_high "
                "FROM rate_library ORDER BY discipline, activity"
            ).fetchall()]

            benchmarks = [dict(r) for r in conn.execute(
                "SELECT metric, description, value, unit, project_type, "
                "jobs_count, source_jobs, range_low, range_high "
                "FROM benchmark ORDER BY metric"
            ).fetchall()]

            lessons = [dict(r) for r in conn.execute(
                "SELECT l.lesson_id, l.discipline, l.category, l.description, l.impact, "
                "l.recommendation, l.pm_name, l.captured_date, j.job_number, j.name as job_name "
                "FROM lesson_learned l LEFT JOIN job j ON l.job_id = j.job_id "
                "ORDER BY l.captured_date DESC"
            ).fetchall()]
        finally:
            conn.close()

        # Empty state
        if not rates and not benchmarks and not lessons:
            empty_state(
                "No knowledge base data yet. Import jobs and approve rate cards on Job Intelligence.",
                icon="library_books",
                action_label="Go to Job Intelligence",
                action_url="/job-intelligence",
            )
            return

        # Top KPIs
        with ui.row().classes("w-full").style("gap: 1rem"):
            with ui.column().classes("flex-1"):
                metric_card("Rate Library Entries", len(rates), icon="analytics")
            with ui.column().classes("flex-1"):
                metric_card("Benchmarks", len(benchmarks), icon="speed")
            with ui.column().classes("flex-1"):
                metric_card("Lessons Learned", len(lessons), icon="school")

        ui.separator()

        # ═══ Rate Library ═══
        if rates:
            section_header("Rate Library")

            all_disciplines = sorted(set(
                (r["discipline"] or "Other").replace("_", " ").title() for r in rates
            ))
            disc_options = {"all": "All Disciplines"}
            for d in all_disciplines:
                disc_options[d] = d

            disc_filter = ui.select(disc_options, value="all") \
                .classes("w-64")

            @ui.refreshable
            def render_rate_table():
                selected = disc_filter.value
                filtered = []
                for r in rates:
                    disc_display = (r["discipline"] or "Other").replace("_", " ").title()
                    if selected != "all" and disc_display != selected:
                        continue
                    range_text = "—"
                    if r["rate_low"] is not None and r["rate_high"] is not None:
                        range_text = f"{r['rate_low']:.4f} — {r['rate_high']:.4f}"
                    filtered.append({
                        "discipline": disc_display,
                        "activity": r["activity"],
                        "description": r["description"] or "—",
                        "rate": r["rate"],
                        "unit": r["unit"] or "—",
                        "confidence": (r["confidence"] or "moderate"),
                        "jobs_count": r["jobs_count"] or 0,
                        "source_jobs": r["source_jobs"] or "—",
                        "range": range_text,
                    })

                if not filtered:
                    ui.label("No rates match filter.").classes("text-grey-7")
                    return

                col_defs = [
                    {"headerName": "Discipline", "field": "discipline", "sortable": True, "filter": True, "width": 140},
                    {"headerName": "Cost Code", "field": "activity", "sortable": True, "filter": True, "width": 110},
                    {"headerName": "Description", "field": "description", "flex": 1, "minWidth": 150},
                    {"headerName": "Rate", "field": "rate", "width": 100,
                     ":valueFormatter": "p => p.value != null ? p.value.toFixed(4) : '—'"},
                    {"headerName": "Unit", "field": "unit", "width": 80},
                    {"headerName": "Confidence", "field": "confidence", "width": 110,
                     "cellClassRules": {
                         "bg-green-100 text-green-800": "x.value === 'strong'",
                         "bg-amber-100 text-amber-800": "x.value === 'moderate'",
                         "bg-red-100 text-red-800": "x.value === 'limited'",
                     }},
                    {"headerName": "Jobs", "field": "jobs_count", "width": 70},
                    {"headerName": "Source Jobs", "field": "source_jobs", "width": 120},
                    {"headerName": "Range", "field": "range", "width": 150},
                ]

                ui.aggrid({
                    "columnDefs": col_defs,
                    "rowData": filtered,
                    "defaultColDef": {"resizable": True},
                }).classes("w-full").style("height: 500px")
                ui.label(f"Showing {len(filtered)} of {len(rates)} rates").classes("text-caption text-grey-6 q-mt-xs")

            disc_filter.on_value_change(lambda: render_rate_table.refresh())
            render_rate_table()

            ui.separator()

        # ═══ Benchmarks ═══
        if benchmarks:
            section_header("Benchmarks")
            with ui.row().classes("w-full flex-wrap").style("gap: 1rem"):
                for bm in benchmarks:
                    label = (bm["description"] or bm["metric"]).replace("_", " ").title()
                    unit = bm["unit"] or ""
                    with ui.card().classes("q-pa-md min-w-48"):
                        ui.label(f"{bm['value']:.4f} {unit}").classes("text-weight-bold text-h6 text-primary")
                        ui.label(label).classes("text-body2 text-grey-8")
                        details = []
                        if bm["range_low"] is not None and bm["range_high"] is not None:
                            details.append(f"Range: {bm['range_low']:.2f} — {bm['range_high']:.2f}")
                        if bm["project_type"]:
                            details.append(f"Type: {bm['project_type'].replace('_', ' ').title()}")
                        details.append(f"{bm['jobs_count'] or 0} job(s)")
                        if bm["source_jobs"]:
                            details.append(f"Jobs: {bm['source_jobs']}")
                        ui.label(" | ".join(details)).classes("text-caption text-grey-6 q-mt-xs")

            ui.separator()

        # ═══ Lessons Learned ═══
        if lessons:
            section_header("Lessons Learned")

            # Filters
            all_categories = sorted(set(
                (ls["category"] or "general").capitalize() for ls in lessons
            ))
            all_lesson_discs = sorted(set(
                (ls["discipline"] or "General").replace("_", " ").title() for ls in lessons
            ))

            with ui.row().style("gap: 1rem"):
                cat_options = {"all": "All Categories"}
                for c in all_categories:
                    cat_options[c] = c
                cat_filter = ui.select(cat_options, value="all") \
                    .classes("w-48")

                disc_lesson_options = {"all": "All Disciplines"}
                for d in all_lesson_discs:
                    disc_lesson_options[d] = d
                disc_lesson_filter = ui.select(disc_lesson_options, value="all") \
                    .classes("w-48")

            IMPACT_ICON = {"high": "error", "medium": "warning", "low": "check_circle"}

            @ui.refreshable
            def render_lessons():
                shown = 0
                for ls in lessons:
                    cat = (ls["category"] or "general").capitalize()
                    disc = (ls["discipline"] or "General").replace("_", " ").title()

                    if cat_filter.value != "all" and cat != cat_filter.value:
                        continue
                    if disc_lesson_filter.value != "all" and disc != disc_lesson_filter.value:
                        continue

                    shown += 1
                    icon = IMPACT_ICON.get(ls["impact"], "help")

                    with ui.card().classes("w-full q-pa-md"):
                        with ui.row().classes("items-start").style("gap: 0.5rem"):
                            ui.icon(icon).classes("mt-1")
                            with ui.column().classes("gap-0 flex-1"):
                                ui.label(f"[{cat}] [{disc}] {ls['description']}") \
                                    .classes("text-body2 text-weight-medium")
                                if ls["recommendation"]:
                                    ui.label(f"Recommendation: {ls['recommendation']}") \
                                        .classes("text-body2 text-grey-8")
                                meta = []
                                if ls["impact"]:
                                    meta.append(f"Impact: {ls['impact'].capitalize()}")
                                if ls["job_number"]:
                                    meta.append(f"Job {ls['job_number']}")
                                if ls["pm_name"]:
                                    meta.append(f"PM: {ls['pm_name']}")
                                if meta:
                                    ui.label(" | ".join(meta)).classes("text-caption text-grey-6")

                if shown == 0:
                    ui.label("No lessons match the current filters.").classes("text-grey-7")
                else:
                    ui.label(f"Showing {shown} of {len(lessons)} lessons") \
                        .classes("text-caption text-grey-6 q-mt-xs")

            cat_filter.on_value_change(lambda: render_lessons.refresh())
            disc_lesson_filter.on_value_change(lambda: render_lessons.refresh())
            render_lessons()
