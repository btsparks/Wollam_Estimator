"""WEIS configuration management."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.getenv("WEIS_DB_PATH", PROJECT_ROOT / "data" / "db" / "weis.db"))
JCD_DIR = Path(os.getenv("WEIS_JCD_DIR", PROJECT_ROOT / "data" / "jcd"))

# API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Logging
LOG_LEVEL = os.getenv("WEIS_LOG_LEVEL", "INFO")
