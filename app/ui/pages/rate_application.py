"""Rate Application page — apply KB historical rates to activity-level estimates."""

from nicegui import ui
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card, section_header, empty_state
from app.ui import state
from app import query


DEFAULT_LABOR_RATE = 85.0  # $/MH blended labor rate


@ui.page("/rate-application")
async def rate_application_page():
    state.set("current_path", "/rate-application")
    page_layout("Rate Application")

    focus = query.get_focus_bid()
    if not focus:
        with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
            page_header("Rate Application",
                        "Apply Knowledge Base rates to estimating activities")
            empty_state(
                "Select a bid from the dashboard to get started.",
                icon="price_change",
                action_label="Go to Dashboard",
                action_url="/",
            )
        return

    bid_id = focus["id"]
    bid_name = focus["bid_name"]
    labor_rate_val = {"value": DEFAULT_LABOR_RATE}

    activities = query.get_activity_rate_data(bid_id, labor_rate_val["value"])
    summary = query.get_activity_rate_summary(bid_id, labor_rate_val["value"])
    rollup = query.get_bid_activity_rollup(bid_id)

    if not activities:
        with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
            page_header("Rate Application",
                        "Apply Knowledge Base rates to estimating activities")
            ui.label(f"Bid: {bid_name}").classes("text-caption text-grey-7")
            empty_state(
                "No activities yet. Build the SOV and add activities to bid items first.",
                icon="price_change",
                action_label="Go to Bid SOV",
                action_url="/bid-sov",
            )
        return

    coded_count = sum(1 for a in activities if a.get("cost_code"))

    # ═══ Main Content ═══
    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Rate Application",
                     "Apply Knowledge Base rates to estimating activities")
        ui.label(f"Bid: {bid_name}").classes("text-caption text-grey-7")

        # KPI Row
        with ui.row().classes("w-full").style("gap: 1rem"):
            with ui.column().classes("flex-1"):
                metric_card("Activities", summary["total_activities"], icon="list_alt")
            with ui.column().classes("flex-1"):
                metric_card("KB Rates Found", summary["has_kb_rate"], icon="library_books")
            with ui.column().classes("flex-1"):
                metric_card("Rates Applied", summary["rates_applied"], icon="check_circle")
            with ui.column().classes("flex-1"):
                est = f"${summary['est_total']:,.0f}" if summary["est_total"] else "$0"
                metric_card("Estimate Total", est, icon="calculate")

        # Labor Rate Config
        with ui.card().classes("w-full"):
            with ui.row().classes("items-end").style("gap: 1rem"):
                ui.icon("engineering").classes("text-2xl text-primary")
                with ui.column().classes("gap-0"):
                    ui.label("Blended Labor Rate").classes("text-body2 text-weight-bold")
                    ui.label("KB rates are in MH/unit — multiply by $/MH to get dollar estimates"
                             ).classes("text-caption text-grey-7")
                labor_input = ui.number("$/MH", value=DEFAULT_LABOR_RATE, step=5,
                                        min=0).classes("w-28")

                def recalc():
                    labor_rate_val["value"] = labor_input.value or DEFAULT_LABOR_RATE
                    ui.navigate.to("/rate-application")
                ui.button("Recalculate", icon="refresh", on_click=recalc).props(
                    "color=primary outline size=sm")

                # Apply All button
                def apply_all():
                    rate = labor_rate_val["value"]
                    count = query.apply_all_activity_rates(bid_id, rate)
                    if count:
                        ui.notify(f"Applied rates to {count} activities", type="positive")
                    else:
                        ui.notify("No coded activities with KB rates to apply", type="warning")
                    ui.navigate.to("/rate-application")
                ui.button("Apply All Rates", icon="bolt",
                          on_click=apply_all).props("color=primary")

        if not coded_count:
            ui.separator()
            empty_state(
                "No activities have cost codes yet. Assign cost codes on the Bid SOV page first.",
                icon="link_off",
                action_label="Go to Bid SOV",
                action_url="/bid-sov",
            )
        else:
            ui.separator()

            # ═══ Rate Grid ═══
            section_header("Activity Rate Lookup",
                           "KB rates matched to coded activities")
            _render_rate_grid(activities)

            # ═══ Bid Item Rollup ═══
            ui.separator()
            _render_item_rollup(bid_id)


def _render_rate_grid(activities):
    """Render AG Grid with activity-level rate application data."""
    rows = []
    for act in activities:
        rows.append({
            "parent_item": f"#{act.get('parent_item_number', '')} {act.get('parent_description', '')}".strip(),
            "activity_number": act["activity_number"] or "",
            "description": act["description"],
            "quantity": act.get("quantity"),
            "unit": act["unit"] or "",
            "cost_code": act["cost_code"] or "",
            "kb_rate": act.get("kb_rate"),
            "kb_confidence": (act.get("kb_confidence") or "").title(),
            "est_mh": act.get("est_mh"),
            "est_unit_price": act.get("est_unit_price"),
            "est_total": act.get("est_total"),
            "applied_total": act.get("total_price"),
            "source": (act.get("source") or "manual").title(),
        })

    col_defs = [
        {"headerName": "Bid Item", "field": "parent_item", "width": 160,
         "rowGroup": False, "filter": True},
        {"headerName": "#", "field": "activity_number", "width": 50},
        {"headerName": "Activity", "field": "description", "flex": 1, "minWidth": 160,
         "filter": True},
        {"headerName": "Qty", "field": "quantity", "width": 80,
         ":valueFormatter": "p => p.value != null ? Number(p.value).toLocaleString() : '—'"},
        {"headerName": "Code", "field": "cost_code", "width": 75,
         "cellClassRules": {
             "text-green-700 font-medium": "x.value && x.value.length > 0",
             "text-gray-400 italic": "!x.value",
         }},
        {"headerName": "KB Rate", "field": "kb_rate", "width": 90,
         ":valueFormatter": "p => p.value != null ? p.value.toFixed(4) + ' MH' : '—'",
         "cellClassRules": {
             "font-medium": "p.value != null",
             "text-gray-400": "p.value == null",
         }},
        {"headerName": "Confidence", "field": "kb_confidence", "width": 95,
         "cellClassRules": {
             "bg-green-100 text-green-800": "x.value === 'Strong'",
             "bg-amber-100 text-amber-800": "x.value === 'Moderate'",
             "bg-red-100 text-red-800": "x.value === 'Limited'",
         }},
        {"headerName": "Est MH", "field": "est_mh", "width": 80,
         ":valueFormatter": "p => p.value != null ? Number(p.value).toLocaleString() : '—'"},
        {"headerName": "Est $/Unit", "field": "est_unit_price", "width": 90,
         ":valueFormatter": "p => p.value != null ? '$' + p.value.toFixed(2) : '—'"},
        {"headerName": "Est Total", "field": "est_total", "width": 100,
         ":valueFormatter": "p => p.value != null ? '$' + Number(p.value).toLocaleString() : '—'",
         "cellClassRules": {"font-bold": "p.value != null"}},
        {"headerName": "Applied $", "field": "applied_total", "width": 100,
         ":valueFormatter": "p => p.value != null ? '$' + Number(p.value).toLocaleString() : '—'",
         "cellClassRules": {
             "bg-green-100 text-green-800 font-bold": "p.value != null",
         }},
    ]

    ui.aggrid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True, "sortable": True},
    }).classes("w-full").style("height: 380px")

    ui.label(f"{len(rows)} activities — {sum(1 for r in rows if r['kb_rate'])} with KB rates"
             ).classes("text-caption text-grey-6 q-mt-xs")


def _render_item_rollup(bid_id: int):
    """Render bid item rollup showing activity totals per bid item."""
    section_header("Bid Item Rollup", "Sum of activities per bid item")

    items = query.get_sov_items(bid_id)
    grand_total = 0
    total_mh = 0

    with ui.row().classes("w-full flex-wrap").style("gap: 1rem"):
        for item in items:
            act_summary = query.get_activity_summary_for_item(item["id"])
            act_count = act_summary["activity_count"]
            act_total = act_summary["total_price"] or 0
            act_mh = act_summary["total_mh"] or 0
            grand_total += act_total
            total_mh += act_mh

            if act_count == 0:
                continue

            num_str = f"#{item['item_number']} " if item.get("item_number") else ""
            with ui.card().classes("q-pa-md min-w-56"):
                ui.label(f"{num_str}{item['description']}").classes(
                    "text-weight-bold text-body2 text-primary")
                with ui.row().classes("q-mt-xs").style("gap: 1rem"):
                    with ui.column().classes("gap-0"):
                        ui.label("Activities").classes("text-caption text-grey-6 uppercase")
                        ui.label(str(act_count)).classes("text-body2 text-weight-medium")
                    with ui.column().classes("gap-0"):
                        ui.label("Total MH").classes("text-caption text-grey-6 uppercase")
                        ui.label(f"{act_mh:,.0f}").classes("text-body2 text-weight-medium")
                    with ui.column().classes("gap-0"):
                        ui.label("Total $").classes("text-caption text-grey-6 uppercase")
                        ui.label(f"${act_total:,.0f}" if act_total else "—") \
                            .classes("text-body2 text-weight-bold")

    # Grand total
    if grand_total:
        with ui.card().classes("w-full q-pa-lg text-center q-mt-sm").style("border: 2px solid var(--q-primary)"):
            ui.label("Wollam Estimate Total").classes(
                "text-body2 text-weight-bold uppercase text-primary")
            with ui.row().classes("justify-center q-mt-sm").style("gap: 2rem"):
                with ui.column().classes("text-center"):
                    ui.label(f"${grand_total:,.0f}").classes(
                        "text-h4 text-weight-bold text-primary")
                with ui.column().classes("text-center"):
                    ui.label(f"{total_mh:,.0f} MH").classes("text-h6 text-weight-medium text-grey-8")

    # Note
    with ui.row().classes("q-mt-sm"):
        ui.icon("info").classes("text-grey-6")
        ui.label(
            "Estimates based on KB historical MH rates × blended labor rate. "
            "Only activities with cost codes and KB rates are included."
        ).classes("text-caption text-grey-6")
