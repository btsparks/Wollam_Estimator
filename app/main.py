"""WEIS entry point."""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.chat import main

if __name__ == "__main__":
    main()
