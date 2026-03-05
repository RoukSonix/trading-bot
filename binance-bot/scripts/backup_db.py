#!/usr/bin/env python3
"""Database backup script for Trading Bot.

Creates compressed backups of the SQLite database with rotation.
Can be run via cron for automated backups.

Usage:
    python scripts/backup_db.py [--keep N] [--db PATH] [--output DIR]

Examples:
    # Basic backup (keeps last 7)
    python scripts/backup_db.py

    # Keep last 30 backups
    python scripts/backup_db.py --keep 30

    # Custom paths
    python scripts/backup_db.py --db data/trading.db --output /backups

Cron example (daily at 3 AM):
    0 3 * * * cd /path/to/trading-bot && python scripts/backup_db.py >> logs/backup.log 2>&1
"""

import argparse
import gzip
import shutil
import sys
from datetime import datetime
from pathlib import Path


def get_default_db_path() -> Path:
    """Get the default database path."""
    # Try common locations
    candidates = [
        Path("data/trading.db"),
        Path("data/bot.db"),
        Path("trading.db"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]  # Default to first option


def backup_database(
    db_path: Path,
    output_dir: Path,
    keep_count: int = 7,
) -> Path | None:
    """Create a compressed backup of the SQLite database.

    Args:
        db_path: Path to the SQLite database file
        output_dir: Directory to store backups
        keep_count: Number of backups to keep (older ones are deleted)

    Returns:
        Path to the created backup file, or None if backup failed
    """
    # Validate database exists
    if not db_path.exists():
        print(f"ERROR: Database file not found: {db_path}")
        return None

    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{db_path.stem}_backup_{timestamp}.db.gz"
    backup_path = output_dir / backup_name

    try:
        # Create compressed backup
        print(f"Creating backup: {backup_path}")
        with open(db_path, "rb") as f_in:
            with gzip.open(backup_path, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Get file sizes for logging
        original_size = db_path.stat().st_size
        backup_size = backup_path.stat().st_size
        compression_ratio = (1 - backup_size / original_size) * 100 if original_size > 0 else 0

        print(f"Backup complete:")
        print(f"  Original size: {original_size:,} bytes")
        print(f"  Backup size:   {backup_size:,} bytes")
        print(f"  Compression:   {compression_ratio:.1f}%")

    except Exception as e:
        print(f"ERROR: Failed to create backup: {e}")
        return None

    # Rotate old backups
    rotate_backups(output_dir, db_path.stem, keep_count)

    return backup_path


def rotate_backups(output_dir: Path, db_name: str, keep_count: int) -> None:
    """Delete old backups, keeping only the most recent ones.

    Args:
        output_dir: Directory containing backups
        db_name: Database name (used to match backup files)
        keep_count: Number of backups to keep
    """
    # Find all backups for this database
    pattern = f"{db_name}_backup_*.db.gz"
    backups = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    # Delete old backups
    if len(backups) > keep_count:
        old_backups = backups[keep_count:]
        print(f"\nRotating backups (keeping {keep_count}):")
        for backup in old_backups:
            print(f"  Deleting: {backup.name}")
            backup.unlink()
        print(f"  Deleted {len(old_backups)} old backup(s)")


def restore_database(backup_path: Path, db_path: Path, force: bool = False) -> bool:
    """Restore a database from a compressed backup.

    Args:
        backup_path: Path to the backup file (.db.gz)
        db_path: Path where the database should be restored
        force: Overwrite existing database without confirmation

    Returns:
        True if restore was successful, False otherwise
    """
    if not backup_path.exists():
        print(f"ERROR: Backup file not found: {backup_path}")
        return False

    if db_path.exists() and not force:
        response = input(f"Database {db_path} already exists. Overwrite? [y/N]: ")
        if response.lower() != "y":
            print("Restore cancelled.")
            return False

    try:
        print(f"Restoring from: {backup_path}")
        print(f"Restoring to:   {db_path}")

        # Create parent directory if needed
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Decompress backup
        with gzip.open(backup_path, "rb") as f_in:
            with open(db_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        print(f"Restore complete: {db_path.stat().st_size:,} bytes")
        return True

    except Exception as e:
        print(f"ERROR: Failed to restore backup: {e}")
        return False


def list_backups(output_dir: Path, db_name: str = "") -> None:
    """List all available backups.

    Args:
        output_dir: Directory containing backups
        db_name: Optional database name filter
    """
    pattern = f"{db_name}_backup_*.db.gz" if db_name else "*_backup_*.db.gz"
    backups = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not backups:
        print(f"No backups found in {output_dir}")
        return

    print(f"\nAvailable backups in {output_dir}:")
    print("-" * 70)
    for backup in backups:
        mtime = datetime.fromtimestamp(backup.stat().st_mtime)
        size = backup.stat().st_size
        print(f"  {backup.name:<45} {size:>10,} bytes  {mtime:%Y-%m-%d %H:%M}")
    print(f"\nTotal: {len(backups)} backup(s)")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backup and restore SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Backup command (default)
    backup_parser = subparsers.add_parser("backup", help="Create a backup")
    backup_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to database file",
    )
    backup_parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/backups"),
        help="Backup output directory (default: data/backups)",
    )
    backup_parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Number of backups to keep (default: 7)",
    )

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument(
        "backup",
        type=Path,
        help="Path to backup file (.db.gz)",
    )
    restore_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to restore database to",
    )
    restore_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing database without confirmation",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available backups")
    list_parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/backups"),
        help="Backup directory to search",
    )

    args = parser.parse_args()

    # Default to backup if no command specified
    if args.command is None:
        args.command = "backup"
        args.db = None
        args.output = Path("data/backups")
        args.keep = 7

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 50}")
    print(f"Trading Bot Database Backup - {timestamp}")
    print(f"{'=' * 50}\n")

    if args.command == "backup":
        db_path = args.db or get_default_db_path()
        result = backup_database(db_path, args.output, args.keep)
        return 0 if result else 1

    elif args.command == "restore":
        db_path = args.db or get_default_db_path()
        success = restore_database(args.backup, db_path, args.force)
        return 0 if success else 1

    elif args.command == "list":
        list_backups(args.output)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
