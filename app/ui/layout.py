"""WEIS NiceGUI shared layout — header, conditional drawer nav, sidebar stats."""

from nicegui import ui
from app.ui.theme import PRIMARY, PRIMARY_DARK, apply_theme
from app.ui import state
from app import query


NAV_WORKFLOW = [
    ("bid_sov", "Bid SOV", "/bid-sov", "receipt_long"),
    ("rate_app", "Rate Application", "/rate-application", "price_change"),
    ("qty_register", "Qty Register", "/quantity-register", "straighten"),
    ("bid_review", "Bid Review", "/bid-review", "rate_review"),
    ("bid_chat", "Bid Chat", "/bid-chat", "forum"),
]

NAV_KNOWLEDGE = [
    ("ask_weis", "Ask WEIS", "/ask-weis", "smart_toy"),
    ("job_intelligence", "Job Intelligence", "/job-intelligence", "insights"),
    ("knowledge_base", "Knowledge Base", "/knowledge-base", "library_books"),
    ("data_catalog", "Data Catalog", "/data-catalog", "folder_open"),
    ("upload_jcd", "Upload JCD", "/upload-jcd", "upload_file"),
]


def page_layout(title: str):
    """Apply shared layout: header bar, left drawer with conditional nav + stats."""
    apply_theme()

    current_path = state.get("current_path", "/")

    # --- Header bar ---
    with ui.header().classes("items-center justify-between px-6") \
            .style(f"background: linear-gradient(135deg, {PRIMARY_DARK}, {PRIMARY})"):
        with ui.row().classes("items-center").style("gap: 0.75rem"):
            ui.button(icon="menu", on_click=lambda: left_drawer.toggle()) \
                .props("flat round color=white")
            ui.label("WEIS").classes("text-h6 text-weight-bold text-white tracking-wide cursor-pointer") \
                .on("click", lambda: ui.navigate.to("/"))
            ui.label("Wollam Estimating Intelligence").classes("text-caption text-white opacity-70 hidden sm:block")

        with ui.row().classes("items-center").style("gap: 0.5rem"):
            # Focus bid indicator
            focus = _get_focus_bid_safe()
            if focus:
                ui.badge(f"Focus: {focus['bid_name']}", color="amber") \
                    .classes("cursor-pointer") \
                    .on("click", lambda: ui.navigate.to("/"))

    # --- Left Drawer ---
    with ui.left_drawer(value=True, bordered=True).classes("bg-white") as left_drawer:
        focus = _get_focus_bid_safe()

        if focus:
            _render_bid_switcher(focus, current_path)
            ui.separator().classes("my-2")

            # Estimate Workflow section
            ui.label("Estimate Workflow").classes(
                "text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pb-xs")
            for key, label, path, icon in NAV_WORKFLOW:
                _render_nav_item(key, label, path, icon, current_path)

            ui.separator().classes("my-2")

        # Knowledge Base section (always visible)
        ui.label("Knowledge Base").classes(
            "text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pt-md q-pb-xs" if not focus
            else "text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pb-xs")
        for key, label, path, icon in NAV_KNOWLEDGE:
            _render_nav_item(key, label, path, icon, current_path)

        ui.separator().classes("my-3")

        # Database stats
        ui.label("Database").classes("text-caption text-grey-7 text-weight-bold uppercase q-px-md q-pb-xs")
        _render_db_stats()


def _render_nav_item(key, label, path, icon, current_path):
    """Render a single nav item in the sidebar."""
    is_active = current_path == path
    item_classes = "rounded mx-2"
    if is_active:
        item_classes += " bg-blue-1 text-blue-9"
    with ui.item(on_click=lambda p=path: ui.navigate.to(p)).classes(item_classes):
        with ui.item_section().props("avatar"):
            ui.icon(icon).classes("text-primary")
        with ui.item_section():
            ui.label(label)


def _render_bid_switcher(focus, current_path):
    """Render the bid switcher dropdown + back to dashboard link."""
    try:
        bids = query.get_active_bids()
    except Exception:
        bids = []

    current_id = focus["id"] if focus else None

    options = {}
    for b in bids:
        lbl = b["bid_name"]
        if b.get("bid_number"):
            lbl += f" (#{b['bid_number']})"
        options[b["id"]] = lbl

    def on_change(e):
        bid_id = e.value
        if bid_id:
            query.set_focus_bid(bid_id)
            ui.navigate.to(current_path or "/")

    with ui.column().classes("q-px-md q-pt-md").style("gap: 0.25rem"):
        ui.label("Active Bid").classes("text-caption text-grey-7 text-weight-bold uppercase")
        ui.select(options, value=current_id, on_change=on_change) \
            .classes("w-full")

        def back_to_dashboard():
            query.clear_focus_bid()
            ui.navigate.to("/")

        ui.button("Back to Dashboard", icon="arrow_back", on_click=back_to_dashboard) \
            .props("flat dense size=sm color=primary no-caps")


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
