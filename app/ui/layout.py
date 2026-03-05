"""WEIS NiceGUI shared layout — header, drawer nav, sidebar stats."""

from nicegui import ui
from app.ui.theme import PRIMARY, PRIMARY_DARK, apply_theme
from app.ui import state
from app import query


NAV_BIDDING = [
    ("home", "Home", "/home", "home"),
    ("active_bids", "Active Bids", "/active-bids", "gavel"),
    ("bid_sov", "Bid SOV", "/bid-sov", "receipt_long"),
    ("rate_app", "Rate Application", "/rate-application", "price_change"),
    ("qty_register", "Qty Register", "/quantity-register", "straighten"),
    ("bid_review", "Bid Review", "/bid-review", "rate_review"),
    ("bid_chat", "Bid Chat", "/bid-chat", "forum"),
]

NAV_KNOWLEDGE = [
    ("job_intelligence", "Job Intelligence", "/job-intelligence", "insights"),
    ("knowledge_base", "Knowledge Base", "/knowledge-base", "library_books"),
    ("data_catalog", "Data Catalog", "/data-catalog", "folder_open"),
    ("upload_jcd", "Upload JCD", "/upload-jcd", "upload_file"),
]


def page_layout(title: str):
    """Apply shared layout: header bar, left drawer with nav + stats."""
    apply_theme()

    current_path = state.get("current_path", "/home")

    # --- Header bar ---
    with ui.header().classes("items-center justify-between px-6") \
            .style(f"background: linear-gradient(135deg, {PRIMARY_DARK}, {PRIMARY})"):
        with ui.row().classes("items-center").style("gap: 0.75rem"):
            ui.button(icon="menu", on_click=lambda: left_drawer.toggle()) \
                .props("flat round color=white")
            ui.label("WEIS").classes("text-h6 text-weight-bold text-white tracking-wide")
            ui.label("Wollam Estimating Intelligence").classes("text-caption text-white opacity-70 hidden sm:block")

        with ui.row().classes("items-center").style("gap: 0.5rem"):
            # Focus bid indicator
            focus = _get_focus_bid_safe()
            if focus:
                ui.badge(f"Focus: {focus['bid_name']}", color="amber") \
                    .classes("cursor-pointer") \
                    .on("click", lambda: ui.navigate.to("/active-bids"))

    # --- Left Drawer ---
    with ui.left_drawer(value=True, bordered=True).classes("bg-white") as left_drawer:
        # Bidding Workflow
        ui.label("Bidding").classes(
            "text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pt-md q-pb-xs")
        for key, label, path, icon in NAV_BIDDING:
            is_active = current_path == path
            item_classes = "rounded mx-2"
            if is_active:
                item_classes += " bg-blue-1 text-blue-9"
            with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(item_classes):
                with ui.item_section().props("avatar"):
                    ui.icon(icon).classes("text-primary")
                with ui.item_section():
                    ui.label(label)

        ui.separator().classes("my-2")

        # Knowledge Base Workflow
        ui.label("Knowledge Base").classes(
            "text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pb-xs")
        for key, label, path, icon in NAV_KNOWLEDGE:
            is_active = current_path == path
            item_classes = "rounded mx-2"
            if is_active:
                item_classes += " bg-blue-1 text-blue-9"
            with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(item_classes):
                with ui.item_section().props("avatar"):
                    ui.icon(icon).classes("text-primary")
                with ui.item_section():
                    ui.label(label)

        ui.separator().classes("my-3")

        # Database stats
        ui.label("Database").classes("text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pb-xs")
        _render_db_stats()

        ui.separator().classes("my-3")

        # Focus bid selector
        ui.label("Focus Bid").classes("text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pb-xs")
        _render_focus_bid_selector()


def _get_focus_bid_safe():
    try:
        return query.get_focus_bid()
    except Exception:
        return None


def _render_db_stats():
    """Render compact DB stats in the drawer."""
    try:
        overview = query.get_database_overview()
        counts = overview.get("record_counts", {})
        projects = counts.get("projects", 0)
        total = sum(counts.values())
        with ui.column().classes("q-px-md").style("gap: 0.25rem"):
            ui.label(f"{projects} projects, {total:,} records").classes("text-body2 text-grey-8")
    except Exception:
        with ui.column().classes("q-px-md"):
            ui.label("No database").classes("text-body2 text-grey-6")


def _render_focus_bid_selector():
    """Render focus bid selector in the drawer."""
    try:
        bids = query.get_active_bids()
    except Exception:
        bids = []

    if not bids:
        with ui.column().classes("q-px-md"):
            ui.label("No active bids").classes("text-body2 text-grey-6")
        return

    focus = _get_focus_bid_safe()
    current_id = focus["id"] if focus else None

    options = {0: "None"}
    for b in bids:
        label = b["bid_name"]
        if b.get("bid_number"):
            label += f" (#{b['bid_number']})"
        options[b["id"]] = label

    def on_change(e):
        bid_id = e.value
        if bid_id == 0:
            query.clear_focus_bid()
        else:
            query.set_focus_bid(bid_id)
        ui.navigate.to(state.get("current_path", "/home"))

    with ui.column().classes("q-px-md"):
        ui.select(options, value=current_id or 0, on_change=on_change) \
            .classes("w-full")
