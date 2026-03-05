"""Active Bids — redirects to Bid Dashboard (/)."""

from nicegui import ui


@ui.page("/active-bids")
async def active_bids_page():
    ui.navigate.to("/")
