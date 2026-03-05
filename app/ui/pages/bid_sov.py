"""Bid Schedule of Values (SOV) page — bid item structure + activity breakdown."""

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card, section_header, empty_state, confirm_dialog
from app.ui import state
from app import query, ai_engine

# Common construction units
UNITS = ["LS", "EA", "CY", "SF", "LF", "LB", "TON", "GAL", "HR", "MH", "DAY", "MO"]

@ui.page("/bid-sov")
async def bid_sov_page(item: str = ""):
    page_layout("Bid SOV")
    await ui.context.client.connected()
    state.set("current_path", "/bid-sov")
    # Parse focused item ID from URL query param (?item=5)
    try:
        _qp_item = int(item) if item else None
    except (ValueError, TypeError):
        _qp_item = None

    def _nav_sov(item_id=None):
        """Navigate to bid-sov, optionally focusing an item."""
        if item_id:
            ui.navigate.to(f"/bid-sov?item={item_id}")
        else:
            ui.navigate.to("/bid-sov")

    # Require focus bid
    focus = query.get_focus_bid()
    if not focus:
        with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
            page_header("Schedule of Values",
                        "Define bid items and break them down into estimating activities")
            empty_state(
                "Set a focus bid on the Active Bids page to build its SOV.",
                icon="receipt_long",
                action_label="Go to Active Bids",
                action_url="/active-bids",
            )
        return

    bid_id = focus["id"]
    bid_name = focus["bid_name"]
    items = query.get_sov_items(bid_id)
    rollup = query.get_bid_activity_rollup(bid_id)

    # ═══ Edit SOV Item Dialog ═══
    ed_item_id = {"value": None}

    with ui.dialog() as edit_dialog, ui.card().style("min-width: 500px"):
        ui.label("Edit Bid Item").classes("text-h6 text-weight-bold text-primary")
        with ui.column().classes("w-full").style("gap: 0.75rem"):
            ed_num = ui.input("Item #").classes("w-full")
            ed_desc = ui.input("Description").classes("w-full")
            with ui.row().classes("w-full").style("gap: 0.75rem"):
                ed_qty = ui.number("Qty", value=None).classes("flex-1")
                ed_unit = ui.select(
                    {u: u for u in UNITS}, value=None, label="Unit",
                    with_input=True, new_value_mode="add-unique",
                ).classes("flex-1")
            ed_notes = ui.input("Notes").classes("w-full")

        with ui.row().classes("w-full justify-between q-mt-md"):
            def delete_item():
                iid = ed_item_id["value"]
                if iid:
                    query.delete_activities_for_item(iid)
                    query.delete_sov_item(iid)
                    ui.notify("Item deleted", type="positive")
                    edit_dialog.close()
                    _nav_sov()
            ui.button("Delete", icon="delete", on_click=delete_item).props("color=negative flat")

            with ui.row().style("gap: 0.5rem"):
                ui.button("Cancel", on_click=edit_dialog.close).props("outline color=grey-8")

                def save_item():
                    iid = ed_item_id["value"]
                    if not iid:
                        return
                    query.update_sov_item(
                        iid,
                        item_number=ed_num.value or None,
                        description=ed_desc.value or "",
                        quantity=ed_qty.value if ed_qty.value else None,
                        unit=ed_unit.value if ed_unit.value else None,
                        notes=ed_notes.value or None,
                    )
                    ui.notify("Item updated", type="positive")
                    edit_dialog.close()
                    _nav_sov(iid)
                ui.button("Save", icon="save", on_click=save_item).props("color=primary")

    # ═══ Add Activity Dialog ═══
    act_parent_id = {"value": None}

    with ui.dialog() as add_act_dialog, ui.card().style("min-width: 560px"):
        ui.label("Add Activity").classes("text-h6 text-weight-bold text-primary")
        act_parent_display = ui.label("").classes("text-caption text-grey-7")

        with ui.column().classes("w-full q-mt-sm").style("gap: 0.75rem"):
            with ui.row().classes("w-full").style("gap: 0.75rem"):
                act_num = ui.input("Activity #").classes("w-24")
                act_desc = ui.input("Description *", placeholder="e.g., Excavate footings") \
                    .classes("flex-1")
            with ui.row().classes("w-full").style("gap: 0.75rem"):
                act_qty = ui.number("Qty", value=None).classes("flex-1")
                act_unit = ui.select(
                    {u: u for u in UNITS}, value=None, label="Unit",
                    with_input=True, new_value_mode="add-unique",
                ).classes("flex-1")
            act_notes = ui.input("Notes").classes("w-full")

        with ui.row().classes("w-full justify-end q-mt-md").style("gap: 0.5rem"):
            ui.button("Cancel", on_click=add_act_dialog.close).props("outline color=grey-8")

            def save_new_activity():
                pid = act_parent_id["value"]
                if not pid or not act_desc.value:
                    ui.notify("Description is required", type="warning")
                    return
                existing = query.get_activities_for_item(pid)
                next_order = max((a.get("sort_order", 0) for a in existing), default=0) + 1
                query.insert_activity(
                    bid_sov_item_id=pid,
                    activity_number=act_num.value or None,
                    description=act_desc.value,
                    quantity=act_qty.value if act_qty.value else None,
                    unit=act_unit.value if act_unit.value else None,
                    notes=act_notes.value or None,
                    sort_order=next_order,
                )
                ui.notify("Activity added", type="positive")
                add_act_dialog.close()
                _nav_sov(pid)
            ui.button("Add Activity", icon="add", on_click=save_new_activity).props("color=primary")

    # ═══ Edit Activity Dialog ═══
    ed_act_id = {"value": None}
    ed_act_parent_id = {"value": None}

    with ui.dialog() as edit_act_dialog, ui.card().style("min-width: 560px"):
        ui.label("Edit Activity").classes("text-h6 text-weight-bold text-primary")
        ea_parent_display = ui.label("").classes("text-caption text-grey-7")

        with ui.column().classes("w-full q-mt-sm").style("gap: 0.75rem"):
            with ui.row().classes("w-full").style("gap: 0.75rem"):
                ea_num = ui.input("Activity #").classes("w-24")
                ea_desc = ui.input("Description").classes("flex-1")
            with ui.row().classes("w-full").style("gap: 0.75rem"):
                ea_qty = ui.number("Qty", value=None).classes("flex-1")
                ea_unit = ui.select(
                    {u: u for u in UNITS}, value=None, label="Unit",
                    with_input=True, new_value_mode="add-unique",
                ).classes("flex-1")
            ea_notes = ui.input("Notes").classes("w-full")

        with ui.row().classes("w-full justify-between q-mt-md"):
            def delete_activity():
                aid = ed_act_id["value"]
                if aid:
                    query.delete_activity(aid)
                    ui.notify("Activity deleted", type="positive")
                    edit_act_dialog.close()
                    _nav_sov(ed_act_parent_id["value"])
            ui.button("Delete", icon="delete", on_click=delete_activity).props("color=negative flat")

            with ui.row().style("gap: 0.5rem"):
                ui.button("Cancel", on_click=edit_act_dialog.close).props("outline color=grey-8")

                def save_activity_edit():
                    aid = ed_act_id["value"]
                    if not aid:
                        return
                    query.update_activity(
                        aid,
                        activity_number=ea_num.value or None,
                        description=ea_desc.value or "",
                        quantity=ea_qty.value if ea_qty.value else None,
                        unit=ea_unit.value if ea_unit.value else None,
                        notes=ea_notes.value or None,
                    )
                    ui.notify("Activity updated", type="positive")
                    edit_act_dialog.close()
                    _nav_sov(ed_act_parent_id["value"])
                ui.button("Save", icon="save", on_click=save_activity_edit).props("color=primary")

    # ═══ Main Content ═══
    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Schedule of Values",
                     "Define bid items and break them down into estimating activities")
        ui.label(f"Building SOV for: {bid_name}").classes("text-caption text-grey-7")
        # KPI Row
        with ui.row().classes("w-full").style("gap: 1rem"):
            with ui.column().classes("flex-1"):
                metric_card("Bid Items", len(items), icon="receipt_long")
            with ui.column().classes("flex-1"):
                metric_card("Activities", rollup["total_activities"], icon="list_alt")
            with ui.column().classes("flex-1"):
                metric_card("Items w/ Activities",
                            f"{rollup['items_with_activities']}/{len(items)}" if items else "0/0",
                            icon="account_tree")
            with ui.column().classes("flex-1"):
                gt = f"${rollup['grand_total']:,.0f}" if rollup.get("grand_total") else "$0"
                metric_card("Estimate Total", gt, icon="calculate")

        ui.separator()

        # ═══ Add Bid Item ═══
        next_order = max((i.get("sort_order", 0) for i in items), default=0) + 1

        with ui.expansion("Add Bid Item", icon="add_circle").classes("w-full"):
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full flex-wrap items-end").style("gap: 0.75rem"):
                    item_num = ui.input("Item #", value=str(len(items) + 1)) \
                        .classes("w-20")
                    desc_in = ui.input("Description *", placeholder="e.g., Concrete Foundations") \
                        .classes("flex-1 min-w-48")
                    qty_in = ui.number("Qty", value=None, step=1) \
                        .classes("w-24")
                    unit_in = ui.select(
                        {u: u for u in UNITS}, value=None, label="Unit",
                        with_input=True, new_value_mode="add-unique",
                    ).classes("w-24")

                    def add_item():
                        if not desc_in.value:
                            ui.notify("Description is required", type="warning")
                            return
                        new_id = query.insert_sov_item(
                            bid_id=bid_id,
                            item_number=item_num.value or None,
                            description=desc_in.value,
                            quantity=qty_in.value if qty_in.value else None,
                            unit=unit_in.value if unit_in.value else None,
                            sort_order=next_order,
                        )
                        ui.notify(f"Added: {desc_in.value}", type="positive")
                        _nav_sov(new_id)
                    ui.button("Add", icon="add", on_click=add_item).props("color=primary")

        # ═══ Bulk Paste ═══
        with ui.expansion("Bulk Paste (from spreadsheet)", icon="content_paste").classes("w-full"):
            ui.label("Paste tab-separated: Item# | Description | Qty | Unit") \
                .classes("text-caption text-grey-7")
            paste_area = ui.textarea(placeholder="Paste rows here...") \
                .classes("w-full").props("rows=5")

            def process_paste():
                text = paste_area.value
                if not text or not text.strip():
                    ui.notify("Nothing to paste", type="warning")
                    return
                lines = [ln for ln in text.strip().split("\n") if ln.strip()]
                existing = query.get_sov_items(bid_id)
                base_order = max((i.get("sort_order", 0) for i in existing), default=0) + 1
                count, last_id = 0, None
                for i, line in enumerate(lines):
                    parts = line.split("\t")
                    if len(parts) == 1:
                        desc = parts[0].strip()
                        inum, qty, unit = None, None, None
                    elif len(parts) == 2:
                        inum, desc = parts[0].strip(), parts[1].strip()
                        qty, unit = None, None
                    else:
                        inum = parts[0].strip() or None
                        desc = parts[1].strip() if len(parts) > 1 else ""
                        try:
                            qty = float(parts[2].replace(",", "")) if len(parts) > 2 and parts[2].strip() else None
                        except ValueError:
                            qty = None
                        unit = parts[3].strip() if len(parts) > 3 and parts[3].strip() else None
                    if not desc:
                        continue
                    last_id = query.insert_sov_item(
                        bid_id=bid_id, item_number=inum, description=desc,
                        quantity=qty, unit=unit, sort_order=base_order + i,
                    )
                    count += 1
                ui.notify(f"Added {count} bid items", type="positive")
                _nav_sov(last_id if count and last_id else None)
            ui.button("Import Lines", icon="upload", on_click=process_paste) \
                .props("color=primary").classes("q-mt-sm")

        ui.separator()

        # ═══ SOV Items + Activities (Focus Mode) ═══
        section_header("Bid Items & Activities",
                       "Select a bid item to view its activities and scope analysis.")

        if not items:
            empty_state(
                "No bid items yet. Add items above or paste from a spreadsheet.",
                icon="table_chart",
            )
        else:
            # Resolve focused item from query param
            item_ids = [i["id"] for i in items]
            focused_id = _qp_item if _qp_item in item_ids else item_ids[0]
            focused_idx = item_ids.index(focused_id)
            focused_item = items[focused_idx]

            # Build selector options: #{num} Description (3 act, $18K, AI)
            selector_options = {}
            for it in items:
                s = query.get_activity_summary_for_item(it["id"])
                num_str = f"#{it['item_number']} " if it.get("item_number") else ""
                parts = []
                if s["activity_count"]:
                    parts.append(f"{s['activity_count']} act")
                if s["total_price"]:
                    tp = s["total_price"]
                    parts.append(f"${tp / 1000:.0f}K" if tp >= 1000 else f"${tp:,.0f}")
                if state.get(f"scope_analysis_{it['id']}"):
                    parts.append("AI")
                suffix = f" ({', '.join(parts)})" if parts else ""
                selector_options[it["id"]] = f"{num_str}{it['description']}{suffix}"

            # ── Item Selector Bar ──
            with ui.row().classes("w-full items-center").style("gap: 0.5rem"):
                def go_prev():
                    if focused_idx > 0:
                        _nav_sov(item_ids[focused_idx - 1])

                def go_next():
                    if focused_idx < len(item_ids) - 1:
                        _nav_sov(item_ids[focused_idx + 1])

                ui.button(icon="chevron_left", on_click=go_prev) \
                    .props(f"flat round size=sm {'disable' if focused_idx == 0 else ''}")

                def on_select_change(e):
                    new_id = e.value
                    if new_id and new_id != focused_id:
                        _nav_sov(new_id)

                ui.select(
                    selector_options, value=focused_id,
                    on_change=on_select_change, with_input=True,
                ).classes("flex-1")

                ui.button(icon="chevron_right", on_click=go_next) \
                    .props(f"flat round size=sm {'disable' if focused_idx >= len(item_ids) - 1 else ''}")

                ui.label(f"{focused_idx + 1} / {len(items)}") \
                    .classes("text-caption text-grey-7 whitespace-nowrap")

            # ── Focused Item Card ──
            _render_focused_item(
                focused_item, bid_id,
                edit_dialog, ed_item_id, ed_num, ed_desc, ed_qty, ed_unit, ed_notes,
                add_act_dialog, act_parent_id, act_parent_display,
                act_num, act_desc, act_qty, act_unit, act_notes,
                edit_act_dialog, ed_act_id, ed_act_parent_id,
                ea_parent_display,
                ea_num, ea_desc, ea_qty, ea_unit, ea_notes,
            )

            with ui.row().classes("q-mt-md").style("gap: 0.5rem"):
                def do_clear_all():
                    for item in items:
                        query.delete_activities_for_item(item["id"])
                    query.delete_all_sov_items(bid_id)
                    ui.notify("All bid items cleared", type="positive")
                    _nav_sov()
                clear_dlg = confirm_dialog(
                    f"Delete all {len(items)} bid items and their activities for {bid_name}?",
                    do_clear_all,
                )
                ui.button("Clear All", icon="delete_sweep", on_click=clear_dlg.open) \
                    .props("color=negative outline size=sm")


def _render_focused_item(item, bid_id,
                         edit_dialog, ed_item_id, ed_num, ed_desc, ed_qty, ed_unit, ed_notes,
                         add_act_dialog, act_parent_id, act_parent_display,
                         act_num, act_desc, act_qty, act_unit, act_notes,
                         edit_act_dialog, ed_act_id, ed_act_parent_id,
                         ea_parent_display,
                         ea_num, ea_desc, ea_qty, ea_unit, ea_notes):
    """Render a single focused bid item as a prominent card with activities and scope."""
    activities = query.get_activities_for_item(item["id"])
    act_summary = query.get_activity_summary_for_item(item["id"])
    act_count = act_summary["activity_count"]
    act_total = act_summary["total_price"]

    num_display = f"#{item['item_number']} " if item.get("item_number") else ""
    badge_text = f"{act_count} activit{'ies' if act_count != 1 else 'y'}"

    with ui.card().classes("w-full"):
        # ── Header row ──
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center").style("gap: 0.75rem"):
                ui.icon("receipt_long").classes("text-2xl text-primary")
                with ui.column().classes("gap-0"):
                    ui.label(f"{num_display}{item['description']}") \
                        .classes("text-h6 text-weight-bold text-primary")
                    sub_parts = []
                    if item.get("quantity"):
                        sub_parts.append(f"{item['quantity']:,.0f} {item.get('unit') or ''}")
                    if act_total:
                        sub_parts.append(f"${act_total:,.0f}")
                    if item.get("notes"):
                        sub_parts.append(item["notes"])
                    if sub_parts:
                        ui.label(" · ".join(sub_parts)).classes("text-caption text-grey-7")

            with ui.row().classes("items-center").style("gap: 0.5rem"):
                if act_count:
                    color = "green" if act_total else "amber"
                    ui.badge(badge_text, color=color).props("outline")

                def open_edit(item_id=item["id"], item_data=item):
                    ed_item_id["value"] = item_id
                    ed_num.value = item_data.get("item_number", "")
                    ed_desc.value = item_data.get("description", "")
                    ed_qty.value = item_data.get("quantity")
                    ed_unit.value = item_data.get("unit") or None
                    ed_notes.value = item_data.get("notes", "")
                    edit_dialog.open()
                ui.button("Edit Item", icon="edit", on_click=open_edit) \
                    .props("flat size=sm color=primary")

        ui.separator()

        # ── Activities ──
        if activities:
            _render_activity_grid(
                activities, item,
                edit_act_dialog, ed_act_id, ed_act_parent_id,
                ea_parent_display,
                ea_num, ea_desc, ea_qty, ea_unit, ea_notes,
            )
        else:
            ui.label("No activities yet. Add the first activity below.") \
                .classes("text-caption text-grey-6 italic py-2")

        with ui.row().classes("q-mt-sm"):
            def open_add_act(item_id=item["id"], item_data=item):
                act_parent_id["value"] = item_id
                num_str = f"#{item_data.get('item_number', '')} " if item_data.get("item_number") else ""
                act_parent_display.text = f"Under: {num_str}{item_data['description']}"
                act_num.value = ""
                act_desc.value = ""
                act_qty.value = None
                act_unit.value = None
                act_notes.value = ""
                add_act_dialog.open()
            ui.button("Add Activity", icon="add", on_click=open_add_act) \
                .props("color=primary outline size=sm")

        # ── Scope Intelligence ──
        ui.separator().classes("my-2")
        _render_scope_section(item, bid_id)


def _render_activity_grid(activities, parent_item,
                          edit_act_dialog, ed_act_id, ed_act_parent_id,
                          ea_parent_display,
                          ea_num, ea_desc, ea_qty, ea_unit, ea_notes):
    """Render AG Grid for activities under a bid item."""
    rows = []
    for act in activities:
        rows.append({
            "id": act["id"],
            "activity_number": act["activity_number"] or "",
            "description": act["description"],
            "quantity": act["quantity"],
            "unit": act["unit"] or "",
            "unit_rate_mh": act["unit_rate_mh"],
            "unit_price": act["unit_price"],
            "total_price": act["total_price"],
            "notes": act["notes"] or "",
        })

    col_defs = [
        {"headerName": "#", "field": "activity_number", "width": 55},
        {"headerName": "Activity", "field": "description", "flex": 1, "minWidth": 200,
         "filter": True},
        {"headerName": "Qty", "field": "quantity", "width": 90,
         ":valueFormatter": "p => p.value != null ? Number(p.value).toLocaleString() : '—'"},
        {"headerName": "Unit", "field": "unit", "width": 70},
        {"headerName": "MH/Unit", "field": "unit_rate_mh", "width": 90,
         ":valueFormatter": "p => p.value != null ? p.value.toFixed(4) : '—'"},
        {"headerName": "$/Unit", "field": "unit_price", "width": 90,
         ":valueFormatter": "p => p.value != null ? '$' + p.value.toFixed(2) : '—'"},
        {"headerName": "Total", "field": "total_price", "width": 110,
         ":valueFormatter": "p => p.value != null ? '$' + Number(p.value).toLocaleString() : '—'",
         "cellClassRules": {"font-bold": "p.value != null"}},
        {"headerName": "Notes", "field": "notes", "width": 120},
    ]

    grid = ui.aggrid({
        "columnDefs": col_defs,
        "rowData": rows,
        "defaultColDef": {"resizable": True, "sortable": True},
        "rowSelection": "single",
        "domLayout": "autoHeight",
    }).classes("w-full")

    def on_act_click(e, parent=parent_item):
        row = e.args["data"]
        if not row:
            return
        ed_act_id["value"] = row["id"]
        ed_act_parent_id["value"] = parent["id"]
        num_str = f"#{parent.get('item_number', '')} " if parent.get("item_number") else ""
        ea_parent_display.text = f"Under: {num_str}{parent['description']}"
        ea_num.value = row.get("activity_number", "")
        ea_desc.value = row.get("description", "")
        ea_qty.value = row.get("quantity")
        ea_unit.value = row.get("unit") or None
        ea_notes.value = row.get("notes", "")
        edit_act_dialog.open()

    grid.on("cellClicked", on_act_click)


def _render_scope_section(item: dict, bid_id: int):
    """Render scope intelligence section inside a bid item expansion."""
    item_id = item["id"]
    description = item["description"]
    item_number = item.get("item_number", "")
    cache_key = f"scope_analysis_{item_id}"
    chat_key = f"scope_chat_{item_id}"

    cached_analysis = state.get(cache_key)
    chat_history = state.get(chat_key, [])

    with ui.row().classes("items-center").style("gap: 0.5rem"):
        ui.icon("psychology").classes("text-lg text-primary")
        ui.label("Scope Intelligence").classes("text-body2 text-weight-bold text-primary")
        if cached_analysis:
            ui.badge("Analyzed", color="green").props("outline")

    if not cached_analysis:
        # Show analyze button
        with ui.row().classes("items-center q-mt-xs").style("gap: 0.75rem"):
            ui.label(
                "AI-powered analysis of bid documents for this line item"
            ).classes("text-caption text-grey-7")

            async def run_analysis(bid=bid_id, desc=description, num=item_number,
                                   key=cache_key, iid=item_id):
                analyze_btn.set_visibility(False)
                spinner_row.set_visibility(True)
                try:
                    result = await run.io_bound(
                        ai_engine.analyze_bid_item_scope, bid, desc, num
                    )
                    state.set(key, result)
                    ui.navigate.to(f"/bid-sov?item={iid}")
                except Exception as exc:
                    spinner_row.set_visibility(False)
                    analyze_btn.set_visibility(True)
                    ui.notify(f"Analysis failed: {exc}", type="negative")

            analyze_btn = ui.button(
                "Analyze Scope", icon="psychology", on_click=run_analysis
            ).props("color=primary outline size=sm")

        spinner_row = ui.row().classes("items-center q-mt-xs").style("gap: 0.5rem")
        spinner_row.set_visibility(False)
        with spinner_row:
            ui.spinner("dots", size="md").classes("text-primary")
            ui.label("Analyzing bid documents...").classes("text-body2 text-grey-8")
    else:
        # Show cached analysis
        with ui.card().classes("w-full q-mt-sm bg-blue-1"):
            ui.markdown(cached_analysis).classes("text-body2 scope-analysis")

            # Clear analysis button
            with ui.row().classes("justify-end q-mt-xs"):
                def clear_analysis(key=cache_key, ckey=chat_key, iid=item_id):
                    state.pop(key)
                    state.pop(ckey)
                    ui.navigate.to(f"/bid-sov?item={iid}")
                ui.button("Clear Analysis", icon="refresh",
                          on_click=clear_analysis).props("flat size=xs color=grey")

        # Follow-up chat
        with ui.column().classes("w-full q-mt-sm").style("gap: 0.25rem"):
            if chat_history:
                for msg in chat_history:
                    if msg["role"] == "user":
                        with ui.row().classes("justify-end"):
                            ui.chat_message(
                                msg["content"], name="You", sent=True
                            ).classes("max-w-lg")
                    else:
                        with ui.row():
                            ui.chat_message(
                                msg["content"], name="WEIS", sent=False
                            ).classes("max-w-lg")

            with ui.row().classes("w-full items-end").style("gap: 0.5rem"):
                scope_input = ui.input(
                    placeholder="Ask about this bid item's scope..."
                ).classes("flex-1")

                async def send_question(
                    bid=bid_id, desc=description, analysis=cached_analysis,
                    ckey=chat_key, inp=scope_input, iid=item_id
                ):
                    q = inp.value
                    if not q or not q.strip():
                        return
                    inp.value = ""
                    history = state.get(ckey, [])
                    # Build API-compatible history (only role/content pairs)
                    api_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in history
                    ]
                    answer = await run.io_bound(
                        ai_engine.ask_bid_item_question,
                        bid, desc, analysis, q.strip(), api_history
                    )
                    history.append({"role": "user", "content": q.strip()})
                    history.append({"role": "assistant", "content": answer})
                    state.set(ckey, history)
                    ui.navigate.to(f"/bid-sov?item={iid}")

                scope_input.on("keydown.enter", send_question)
                ui.button(icon="send", on_click=send_question).props(
                    "color=primary round size=sm"
                )
