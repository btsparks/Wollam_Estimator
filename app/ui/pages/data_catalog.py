"""Data Catalog page — browse/delete projects."""

from nicegui import ui
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card, section_header, empty_state, confirm_dialog
from app.ui import state
from app import query
from app.database import delete_project_cascade


@ui.page("/data-catalog")
async def data_catalog_page():
    state.set("current_path", "/data-catalog")
    page_layout("Data Catalog")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Data Catalog", "All loaded projects and their data completeness")

        projects = query.get_all_projects_with_detail()

        # Top metrics
        total_records = sum(p.get("total_records", 0) for p in projects)
        disciplines_count = sum(len(p.get("disciplines_detail", [])) for p in projects)

        with ui.row().classes("w-full").style("gap: 1rem"):
            with ui.column().classes("flex-1"):
                metric_card("Projects Loaded", len(projects), icon="business")
            with ui.column().classes("flex-1"):
                metric_card("Total Records", f"{total_records:,}", icon="storage")
            with ui.column().classes("flex-1"):
                metric_card("Disciplines", disciplines_count, icon="category")

        ui.separator()

        if not projects:
            empty_state(
                "No projects loaded yet. Use Upload JCD to add project data.",
                icon="folder_open",
                action_label="Upload JCD",
                action_url="/upload-jcd",
            )
            return

        # Per-project cards
        for proj in projects:
            quality = proj.get("data_quality", "unknown")
            quality_colors = {"complete": "green", "partial": "amber", "minimal": "red"}
            q_color = quality_colors.get(quality, "grey")

            with ui.expansion(
                f"Job {proj['job_number']} — {proj.get('job_name', 'Unknown')}",
                icon="work",
            ).classes("w-full"):
                # Quality badge
                ui.badge(quality.upper(), color=q_color).classes("q-mb-sm")

                # Info row
                with ui.row().classes("flex-wrap").style("gap: 1.5rem"):
                    for label, val in [
                        ("Owner", proj.get("owner")),
                        ("Type", proj.get("project_type")),
                        ("Cataloged", proj.get("cataloged_date")),
                        ("By", proj.get("cataloged_by")),
                    ]:
                        if val:
                            with ui.column().classes("gap-0"):
                                ui.label(label).classes("text-caption text-grey-6 uppercase")
                                ui.label(str(val)).classes("text-body2 text-weight-medium")

                # Financial metrics
                if proj.get("total_actual_cost"):
                    with ui.row().classes("q-mt-sm flex-wrap").style("gap: 1rem"):
                        for label, val in [
                            ("Actual Cost", f"${proj['total_actual_cost']:,.0f}"),
                            ("Actual MH", f"{proj['total_actual_mh']:,.0f}" if proj.get("total_actual_mh") else None),
                            ("Budget Cost", f"${proj['total_budget_cost']:,.0f}" if proj.get("total_budget_cost") else None),
                        ]:
                            if val:
                                with ui.column().classes("items-center"):
                                    ui.label(val).classes("text-weight-bold")
                                    ui.label(label).classes("text-caption text-grey-7 uppercase")

                ui.separator().classes("my-2")

                # Record counts
                ui.label("Record Counts").classes("text-weight-bold text-body2")
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

                with ui.row().classes("flex-wrap").style("gap: 1rem"):
                    for key, label in table_labels.items():
                        c = counts.get(key, 0)
                        icon = "check_circle" if c > 0 else "radio_button_unchecked"
                        color = "text-green-9" if c > 0 else "text-grey-5"
                        with ui.row().classes("items-center").style("gap: 0.25rem"):
                            ui.icon(icon).classes(f"text-sm {color}")
                            ui.label(f"{label}: {c}").classes("text-caption")

                # Discipline breakdown
                discs = proj.get("disciplines_detail", [])
                if discs:
                    ui.separator().classes("my-2")
                    ui.label("Disciplines").classes("text-weight-bold text-body2")
                    for d in discs:
                        budget = d.get("budget_cost") or 0
                        actual = d.get("actual_cost") or 0
                        variance = d.get("variance_cost") or (actual - budget)
                        var_color = "text-red-9" if variance > 0 else "text-green-9"
                        ui.label(
                            f"{d['discipline_name']} ({d['discipline_code']}) — "
                            f"Budget: ${budget:,.0f} · Actual: ${actual:,.0f} · "
                            f"Variance: ${variance:+,.0f}"
                        ).classes(f"text-caption {var_color}")

                # Data browser
                ui.separator().classes("my-2")
                ui.label("Data Browser").classes("text-weight-bold text-body2")
                ui.label("This is exactly what WEIS sees when answering questions").classes("text-caption text-grey-6")

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
                        with ui.expansion(f"{table_label} ({count} records)").classes("w-full"):
                            columns = []
                            if rows:
                                columns = [
                                    {"name": k, "label": k.replace("_", " ").title(),
                                     "field": k, "sortable": True}
                                    for k in rows[0].keys()
                                ]
                            ui.table(columns=columns, rows=rows).classes("w-full")
                    else:
                        ui.label(f"{table_label} — no records").classes("text-caption text-grey-5")

                # Delete button
                ui.separator().classes("my-2")

                def make_delete(p):
                    def do_delete():
                        deleted = delete_project_cascade(p["id"])
                        total_deleted = sum(deleted.values())
                        ui.notify(f"Removed Job {p['job_number']} — {total_deleted} records deleted.",
                                  type="positive")
                        ui.navigate.to("/data-catalog")
                    return do_delete

                dialog = confirm_dialog(
                    f"Remove Job {proj['job_number']} and all {proj.get('total_records', 0)} records?",
                    make_delete(proj),
                )
                ui.button(f"Remove Project {proj['job_number']}", icon="delete",
                          on_click=dialog.open) \
                    .props("color=negative outline size=sm")
