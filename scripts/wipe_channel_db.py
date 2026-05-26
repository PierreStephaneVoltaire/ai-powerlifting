#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


TABLES = ["webhooks", "routing_cache", "activity_log"]


def _find_db_path() -> Path:
    env_path = os.environ.get("STORAGE_DB_PATH", "")
    if env_path:
        return Path(env_path)
    candidates = [
        Path("app/src/data/store.db"),
        Path("data/store.db"),
        Path("./data/store.db"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("app/src/data/store.db")


def _count_rows(conn, table: str) -> int:
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]
    except Exception:
        return -1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wipe the IF channel SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually perform the wipe (required unless --dry-run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be deleted without touching anything",
    )
    parser.add_argument(
        "--delete-file", action="store_true",
        help="Delete the entire database file instead of truncating tables",
    )
    parser.add_argument(
        "--db-path", default="",
        help="Override the database file path",
    )
    args = parser.parse_args()

    if not args.confirm and not args.dry_run:
        print("ERROR: Pass --confirm to wipe, or --dry-run to preview.", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    db_path = Path(args.db_path) if args.db_path else _find_db_path()
    print(f"Database: {db_path.resolve()}")

    if not db_path.exists():
        print("Database file does not exist. Nothing to wipe.")
        return 0

    if args.delete_file:
        size_kb = db_path.stat().st_size // 1024
        print(f"File size: {size_kb} KB")
        if args.dry_run:
            print(f"[DRY RUN] Would delete file: {db_path}")
            return 0
        db_path.unlink()
        for ext in ("-wal", "-shm"):
            sidecar = db_path.parent / (db_path.name + ext)
            if sidecar.exists():
                sidecar.unlink()
                print(f"Deleted sidecar: {sidecar.name}")
        print(f"Deleted: {db_path}")
        return 0

    import sqlite3
    conn = sqlite3.connect(str(db_path))

    print("\nCurrent row counts:")
    for table in TABLES:
        count = _count_rows(conn, table)
        label = str(count) if count >= 0 else "(table not found)"
        print(f"  {table:<22} {label}")

    if args.dry_run:
        print("\n[DRY RUN] Would DELETE FROM each table above. No changes made.")
        conn.close()
        return 0

    print("\nWiping tables...")
    for table in TABLES:
        try:
            conn.execute(f"DELETE FROM {table}")
            print(f"  Cleared: {table}")
        except Exception as e:
            print(f"  SKIP    {table}: {e}")

    conn.execute("VACUUM")
    conn.commit()
    conn.close()

    print("\nDone. All channel/routing state wiped.")
    print("Restart the IF agent API to re-register channels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
