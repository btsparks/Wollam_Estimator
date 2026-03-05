"""WEIS NiceGUI reusable components."""

from nicegui import ui
from app.ui.theme import (
    SUCCESS, DANGER, STATUS_COLORS,
    CONFIDENCE_COLORS,
)


def metric_card(label: str, value, delta: str = None, icon: str = None):
    """Render a styled metric card."""
    with ui.card().classes("q-pa-md w-full").style("border-left: 4px solid var(--q-primary)"):
        with ui.row().classes("items-center w-full").style("gap: 0.75rem"):
            if icon:
                ui.icon(icon).classes("text-2xl text-primary")
            with ui.column().classes("gap-0"):
                ui.label(str(value)).classes("text-h5 text-grey-9 text-weight-bold")
                ui.label(label).classes("text-caption text-grey-7 text-weight-bold uppercase")
                if delta:
                    color = SUCCESS if delta.startswith("+") or delta.startswith("-") and "under" in delta.lower() else DANGER
                    ui.label(delta).classes("text-caption text-weight-medium").style(f"color: {color}")


def status_badge(label: str, color: str = None):
    """Render a colored status badge."""
    q_color = color or "grey"
    ui.badge(label, color=q_color).props("outline")


def section_header(title: str, subtitle: str = None):
    """Render a section header with optional subtitle."""
    with ui.column().classes("gap-0 w-full").style("border-bottom: 2px solid var(--q-primary); padding-bottom: 0.5rem; margin-bottom: 1rem"):
        ui.label(title).classes("text-subtitle1 text-primary text-weight-medium")
        if subtitle:
            ui.label(subtitle).classes("text-caption text-grey-7")


def page_header(title: str, subtitle: str = None):
    """Render the page title and subtitle."""
    with ui.column().classes("gap-0 q-mb-md"):
        ui.label(title).classes("text-h6 text-grey-9 text-weight-bold")
        if subtitle:
            ui.label(subtitle).classes("text-caption text-grey-7")


def empty_state(message: str, icon: str = "inbox", action_label: str = None,
                action_url: str = None):
    """Render an empty state placeholder."""
    with ui.column().classes("empty-state w-full items-center"):
        ui.icon(icon).classes("text-6xl q-mb-sm text-grey-5")
        ui.label(message).classes("text-body1")
        if action_label and action_url:
            ui.button(action_label, on_click=lambda: ui.navigate.to(action_url)) \
                .props("flat color=primary")


def confirm_dialog(message: str, on_confirm):
    """Create a confirm dialog. Returns the dialog so caller can .open() it."""
    with ui.dialog() as dialog, ui.card():
        ui.label(message).classes("text-body1")
        with ui.row().classes("w-full justify-end q-mt-md").style("gap: 0.5rem"):
            ui.button("Cancel", on_click=dialog.close).props("outline color=grey-8")
            ui.button("Confirm", on_click=lambda: _confirm_and_close(dialog, on_confirm)) \
                .props("color=negative")
    return dialog


def _confirm_and_close(dialog, on_confirm):
    dialog.close()
    on_confirm()


def confidence_dot(level: str):
    """Render a colored confidence indicator dot."""
    color = CONFIDENCE_COLORS.get(level, "#CCC")
    ui.icon("circle").classes("text-xs").style(f"color: {color}")


def bid_status_color(status: str) -> str:
    """Return Quasar color name for a bid/card status."""
    return STATUS_COLORS.get(status, "grey")
