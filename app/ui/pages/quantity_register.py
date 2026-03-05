"""Quantity Register page — bid item quantities vs PM-verified quantities."""

from nicegui import ui
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card, section_header, empty_state
from app.ui import state
from app import query

QUANTITY_STATUSES = ["pending", "verified", "flagged", "accepted"]


@ui.page("/quantity-register")
async def quantity_register_page():
    state.set("current_path", "/quantity-register")
    page_layout("Quantity Register")

    # Require focus bid
    focus = query.get_focus_bid()
    if not focus:
        with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
            page_header("Quantity Register",
                        "Compare owner-provided vs PM-verified quantities")
            empty_state(
                "Select a bid from the dashboard to get started.",
                icon="straighten",
                action_label="Go to Dashboard",
                action_url="/",
            )
        return

    bid_id = focus["id"]
    bid_name = focus["bid_name"]
    items = query.get_quantity_register(bid_id)
    summary = query.get_quantity_summary(bid_id)

    if not items:
        with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
            page_header("Quantity Register",
                        "Compare owner-provided vs PM-verified quantities")
            ui.label(f"Bid: {bid_name}").classes("text-caption text-grey-7")
            empty_state(
                "No SOV items yet. Build the SOV first, then verify quantities here.",
                icon="straighten",
                action_label="Go to Bid SOV",
                action_url="/bid-sov",
            )
        return

    # ═══ Edit Dialog ═══
    ed_item_id = {"value": None}

    with ui.dialog() as edit_dialog, ui.card().style("min-width: 480px"):
        ui.label("Verify Quantity").classes("text-h6 text-weight-bold text-primary")
        ed_desc_label = ui.label("").classes("text-body2 text-grey-8")

        with ui.column().classes("w-full q-mt-sm").style("gap: 0.75rem"):
            with ui.row().classes("w-full").style("gap: 1rem"):
                with ui.column().classes("flex-1"):
                    ui.label("Owner Quantity").classes("text-caption text-weight-bold text-grey-6 uppercase")
                    ed_owner_qty = ui.label("").classes("text-h6 text-weight-medium")
                    ed_owner_unit = ui.label("").classes("text-body2 text-grey-7")
                with ui.column().classes("flex-1"):
                    ui.label("PM Quantity").classes("text-caption text-weight-bold text-grey-6 uppercase")
                    ed_pm_qty = ui.number("PM Qty", value=None).classes("w-full")
                    ed_pm_unit = ui.input("PM Unit").classes("w-full")

            ed_status = ui.select(
                {s: s.title() for s in QUANTITY_STATUSES},
                value="verified", label="Status",
            ).classes("w-full")
            ed_notes = ui.input("Notes").classes("w-full")

        with ui.row().classes("w-full justify-end q-mt-md").style("gap: 0.5rem"):
            ui.button("Cancel", on_click=edit_dialog.close).props("outline color=grey-8")

            def save_qty():
                iid = ed_item_id["value"]
                if not iid:
                    return
                query.update_pm_quantity(
                    iid,
                    pm_quantity=ed_pm_qty.value if ed_pm_qty.value else None,
                    pm_unit=ed_pm_unit.value or None,
                    quantity_status=ed_status.value,
                    quantity_notes=ed_notes.value or None,
                )
                ui.notify("Quantity updated", type="positive")
                edit_dialog.close()
                ui.navigate.to("/quantity-register")
            ui.button("Save", icon="save", on_click=save_qty).props("color=primary")

    # ═══ Main Content ═══
    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Quantity Register",
                     "Compare owner-provided vs PM-verified quantities")
        ui.label(f"Bid: {bid_name}").classes("text-caption text-grey-7")

        # KPI Row
        with ui.row().classes("w-full").style("gap: 1rem"):
            with ui.column().classes("flex-1"):
                metric_card("Line Items", summary["total_items"], icon="straighten")
            with ui.column().classes("flex-1"):
                metric_card("Verified", summary["verified"], icon="check_circle")
            with ui.column().classes("flex-1"):
                metric_card("Flagged", summary["flagged"], icon="flag")
            with ui.column().classes("flex-1"):
                pct = (f"{summary['has_pm_qty']}/{summary['total_items']}"
                       if summary["total_items"] else "0/0")
                metric_card("PM Qty Entered", pct, icon="edit_note")

        ui.separator()

        # ═══ Quantity Grid ═══
        section_header("Owner vs PM Quantities", "Click a row to enter/edit PM quantity")

        _render_quantity_grid(items, edit_dialog, ed_item_id, ed_desc_label,
                              ed_owner_qty, ed_owner_unit, ed_pm_qty, ed_pm_unit,
                              ed_status, ed_notes)

        # ═══ Variance Summary ═══
        flagged = [i for i in items if i.get("variance_pct") is not None
                   and abs(i["variance_pct"]) > 10]
        if flagged:
            ui.separator()
            _render_variance_alerts(flagged)


def _render_quantity_grid(items, edit_dialog, ed_item_id, ed_desc_label,
                          ed_owner_qty, ed_owner_unit, ed_pm_qty, ed_pm_unit,
                          ed_status, ed_notes):
    """Render the AG Grid with quantity comparison."""
    rows = []
    for item in items:
        var_pct = item.get("variance_pct")
        rows.append({
            "id": item["id"],
            "item_number": item["item_number"] or "",
            "description": item["description"],
            "owner_qty": item["quantity"],
            "owner_unit": item["unit"] or "",
            "pm_qty": item["pm_quantity"],
            "pm_unit": item["pm_unit"] or item["unit"] or "",
            "variance": item["variance"],
            "variance_pct": round(var_pct, 1) if var_pct is not None else None,
            "status": (item["quantity_status"] or "pending").title(),
            "cost_code": item["cost_code"] or "",
            "owner_amount": item["owner_amount"],
            "notes": item["quantity_notes"] or "",
        })

    col_defs = [
        {"headerName": "#", "field": "item_number", "width": 60, "sortable": True},
        {"headerName": "Description", "field": "description", "flex": 1, "minWidth": 180,
         "sortable": True, "filter": True},
        {"headerName": "Owner Qty", "field": "owner_qty", "width": 110,
         ":valueFormatter": "p => p.value != null ? Number(p.value).toLocaleString() : '—'"},
        {"headerName": "Unit", "field": "owner_unit", "width": 70},
        {"headerName": "PM Qty", "field": "pm_qty", "width": 110,
         ":valueFormatter": "p => p.value != null ? Number(p.value).toLocaleString() : '—'",
         "cellClassRules": {
             "font-bold": "p.value != null",
             "text-gray-400 italic": "p.value == null",
         }},
        {"headerName": "Variance", "field": "variance", "width": 110,
         ":valueFormatter": "p => p.value != null ? (p.value >= 0 ? '+' : '') + Number(p.value).toLocaleString() : '—'",
         "cellClassRules": {
             "text-red-700 font-medium": "p.value != null && Math.abs(p.value) > 0",
         }},
        {"headerName": "Var %", "field": "variance_pct", "width": 90,
         ":valueFormatter": "p => p.value != null ? (p.value >= 0 ? '+' : '') + p.value + '%' : '—'",
         "cellClassRules": {
             "bg-red-100 text-red-800 font-bold": "p.value != null && Math.abs(p.value) > 10",
             "bg-amber-100 text-amber-800": "p.value != null && Math.abs(p.value) > 5 && Math.abs(p.value) <= 10",
             "text-green-700": "p.value != null && Math.abs(p.value) <= 5",
         }},
        {"headerName": "Status", "field": "status", "width": 100,
         "cellClassRules": {
             "bg-green-100 text-green-800": "x.value === 'Verified' || x.value === 'Accepted'",
             "bg-amber-100 text-amber-800": "x.value === 'Pending'",
             "bg-red-100 text-red-800": "x.value === 'Flagged'",
         }},
    ]

    grid = ui.aggrid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True},
        "rowSelection": "single",
    }).classes("w-full").style("height: 420px")

    ui.label(f"{len(rows)} line items").classes("text-caption text-grey-6 q-mt-xs")

    def on_row_click(e):
        row = e.args["data"]
        if not row:
            return
        ed_item_id["value"] = row["id"]
        ed_desc_label.text = f"{row.get('item_number', '')} — {row['description']}"
        ed_owner_qty.text = (f"{row['owner_qty']:,.1f}" if row.get("owner_qty")
                             else "Not provided")
        ed_owner_unit.text = row.get("owner_unit", "")
        ed_pm_qty.value = row.get("pm_qty")
        ed_pm_unit.value = row.get("pm_unit") or row.get("owner_unit") or ""
        ed_status.value = (row.get("status") or "Pending").lower()
        ed_notes.value = row.get("notes", "")
        edit_dialog.open()

    grid.on("cellClicked", on_row_click)


def _render_variance_alerts(flagged: list):
    """Render variance alert cards for items with >10% difference."""
    section_header("Variance Alerts", "Items with >10% quantity difference")
    with ui.row().classes("w-full flex-wrap").style("gap: 1rem"):
        for item in sorted(flagged, key=lambda x: abs(x.get("variance_pct", 0)), reverse=True):
            pct = item["variance_pct"]
            color = "red" if abs(pct) > 20 else "amber"
            with ui.card().classes(f"q-pa-md min-w-64 border-{color}-300 border-2"):
                with ui.row().classes("items-center").style("gap: 0.5rem"):
                    ui.icon("warning").classes(f"text-{color}-9")
                    ui.label(item["description"]).classes("text-weight-bold text-body2")
                with ui.row().classes("q-mt-sm").style("gap: 1.5rem"):
                    with ui.column():
                        ui.label("Owner").classes("text-caption text-grey-6 uppercase")
                        ui.label(f"{item['quantity']:,.0f} {item['unit'] or ''}"
                                 if item.get("quantity") else "—").classes("text-body2")
                    with ui.column():
                        ui.label("PM").classes("text-caption text-grey-6 uppercase")
                        ui.label(f"{item['pm_quantity']:,.0f} {item.get('pm_unit') or item.get('unit') or ''}"
                                 if item.get("pm_quantity") else "—").classes("text-body2")
                    with ui.column():
                        ui.label("Variance").classes("text-caption text-grey-6 uppercase")
                        sign = "+" if pct > 0 else ""
                        ui.label(f"{sign}{pct:.1f}%").classes(
                            f"text-body2 text-weight-bold text-{color}-9")
                if item.get("quantity_notes"):
                    ui.label(item["quantity_notes"]).classes("text-caption text-grey-7 q-mt-xs italic")
