"""WEIS NiceGUI Application — Entry Point.

Run with: python app/nicegui_app.py
Serves on: http://localhost:8080
"""

import sys
from pathlib import Path

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nicegui import app, ui
from nicegui.nicegui import sio

# Increase Socket.IO engine max buffer (default 1MB too small for 197-job grid)
sio.eio.max_http_buffer_size = 10 * 1024 * 1024  # 10MB

# Import all page modules (registers @ui.page routes)
import app.ui.pages.home  # noqa: F401
import app.ui.pages.ask_weis  # noqa: F401
import app.ui.pages.job_intelligence  # noqa: F401
import app.ui.pages.active_bids  # noqa: F401
import app.ui.pages.bid_review  # noqa: F401
import app.ui.pages.bid_chat  # noqa: F401
import app.ui.pages.bid_sov  # noqa: F401
import app.ui.pages.quantity_register  # noqa: F401
import app.ui.pages.rate_application  # noqa: F401

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="WEIS — Wollam Estimating Intelligence System",
        port=8081,
        storage_secret="weis-nicegui-storage-2026",
        favicon="🏗️",
        show=False,
    )
