"""Initialize the WEIS database with schema and verify tables."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, get_connection, get_table_counts, DB_PATH


def seed():
    """Create the database and verify all tables exist."""
    print("=" * 60)
    print("WEIS Database Initialization")
    print("=" * 60)

    # Initialize schema
    init_db()

    # Verify tables
    conn = get_connection()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print(f"\nCreated {len(tables)} tables:")
        for t in tables:
            print(f"  - {t['name']}")

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        print(f"\nCreated {len(indexes)} indexes:")
        for idx in indexes:
            print(f"  - {idx['name']}")

        # Verify row counts (should all be 0)
        counts = get_table_counts()
        print(f"\nRow counts (all should be 0):")
        for table, count in counts.items():
            print(f"  {table}: {count}")

        version = conn.execute("SELECT version FROM schema_version").fetchone()
        print(f"\nSchema version: {version['version']}")
        print(f"Database path: {DB_PATH}")
        print("\nDatabase ready for data ingestion.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
