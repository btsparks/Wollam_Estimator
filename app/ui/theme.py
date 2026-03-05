"""WEIS NiceGUI theme — colors, fonts, global CSS."""

from nicegui import ui

# Brand colors
PRIMARY = "#1565C0"
PRIMARY_LIGHT = "#1E88E5"
PRIMARY_DARK = "#0D47A1"
ACCENT = "#F39C12"
SUCCESS = "#28a745"
WARNING = "#f0ad4e"
DANGER = "#dc3545"
SURFACE = "#F8F9FA"
TEXT = "#2C3E50"

CONFIDENCE_COLORS = {
    "strong": SUCCESS,
    "moderate": WARNING,
    "limited": DANGER,
}

RISK_COLORS = {
    "LOW": SUCCESS,
    "MEDIUM": WARNING,
    "HIGH": DANGER,
    "DO_NOT_BID": DANGER,
}

STATUS_COLORS = {
    "draft": "grey",
    "pending_review": "amber",
    "approved": "green",
    "active": "blue",
    "awarded": "green",
    "lost": "red",
    "no_bid": "grey",
    "archived": "grey",
}

GLOBAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

body {
    font-family: 'Inter', sans-serif !important;
}

.q-page {
    background-color: #fafafa !important;
}

.nicegui-content {
    max-width: 1400px;
    margin: 0 auto;
    padding: 1.5rem;
}

.empty-state {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--q-grey-7);
}

.chat-user {
    background-color: #E3F2FD !important;
    border-radius: 12px !important;
}

.chat-assistant {
    background-color: #FFFFFF !important;
    border: 1px solid #E0E0E0 !important;
    border-radius: 12px !important;
}

/* Fix Quasar dialog backdrop rendering behind page content */
.q-dialog__backdrop {
    background-color: rgba(0, 0, 0, 0.4) !important;
    z-index: 5999 !important;
}
.q-dialog__inner {
    z-index: 6000 !important;
}

/* Fix AG Grid stuck delay-render animation */
.ag-delay-render .ag-cell,
.ag-delay-render .ag-header-cell,
.ag-delay-render .ag-header-group-cell,
.ag-delay-render .ag-row,
.ag-delay-render .ag-spanned-cell-wrapper {
    visibility: visible !important;
}
"""


def configure_defaults():
    """Set global widget defaults — flat cards, unelevated buttons, outlined inputs."""
    ui.card.default_classes('no-shadow bordered rounded-borders bg-white')
    ui.button.default_props('unelevated')
    ui.input.default_props('outlined dense')
    ui.select.default_props('outlined dense')
    ui.textarea.default_props('outlined')
    ui.table.default_props('flat bordered')


def apply_theme():
    """Apply WEIS brand theme to the current page."""
    configure_defaults()
    ui.colors(primary=PRIMARY, secondary=PRIMARY_LIGHT, accent=ACCENT,
              positive=SUCCESS, negative=DANGER, warning=WARNING)
    ui.add_css(GLOBAL_CSS)
