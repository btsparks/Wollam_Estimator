"""WEIS v2 configuration management."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.getenv("WEIS_DB_PATH", PROJECT_ROOT / "data" / "db" / "weis.db"))
STATIC_DIR = PROJECT_ROOT / "static"
DIARY_DIR = PROJECT_ROOT / "Heavy Job Notes"
COST_REPORT_DIR = PROJECT_ROOT / "Heavy Job Cost Report"
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
BID_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "bid_documents"

# Dropbox (read-only document source)
DROPBOX_ROOT = Path(os.getenv(
    "WEIS_DROPBOX_ROOT",
    r"C:\Users\Travis Sparks\Dropbox (Wollam)"
))

# Dropbox Estimating folder root (for bid folder linking)
ESTIMATING_ROOT = Path(os.getenv(
    "WEIS_ESTIMATING_ROOT",
    DROPBOX_ROOT / "Estimates - Shared"
))

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# HCSS (for sync only)
HCSS_CLIENT_ID = os.getenv("HCSS_CLIENT_ID", "")
HCSS_CLIENT_SECRET = os.getenv("HCSS_CLIENT_SECRET", "")

# ChromaDB vector store
CHROMA_DIR = PROJECT_ROOT / "data" / "chromadb"
VECTOR_SEARCH_ENABLED = os.getenv("WEIS_VECTOR_SEARCH_ENABLED", "true").lower() == "true"
VECTOR_SEARCH_DEFAULT_RESULTS = int(os.getenv("WEIS_VECTOR_SEARCH_DEFAULT_RESULTS", "10"))

# Logging
LOG_LEVEL = os.getenv("WEIS_LOG_LEVEL", "INFO")
