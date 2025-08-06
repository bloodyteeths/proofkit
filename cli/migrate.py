"""
Simple migration runner for PostgreSQL

Executes SQL migration files in order without Alembic
Tracks applied migrations in a migrations table
"""

import os
import sys
import asyncio
from pathlib import Path
import asyncpg
from datetime import datetime
from typing import List, Tuple


async def get_db_connection():
    """Get PostgreSQL connection from DATABASE_URL"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    # Convert to asyncpg format
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgres://", 1)
    
    return await asyncpg.connect(database_url)


async def create_migrations_table(conn):
    """Create migrations tracking table if not exists"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


async def get_applied_migrations(conn) -> List[str]:
    """Get list of already applied migrations"""
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return [row['version'] for row in rows]


async def get_migration_files() -> List[Tuple[str, Path]]:
    """Get all migration SQL files in order"""
    migrations_dir = Path("migrations")
    if not migrations_dir.exists():
        print(f"Creating migrations directory: {migrations_dir}")
        migrations_dir.mkdir(exist_ok=True)
        return []
    
    migration_files = []
    for file in sorted(migrations_dir.glob("*.sql")):
        version = file.stem  # filename without .sql extension
        migration_files.append((version, file))
    
    return migration_files


async def apply_migration(conn, version: str, file_path: Path):
    """Apply a single migration file"""
    print(f"Applying migration: {version}")
    
    # Read migration SQL
    with open(file_path, 'r') as f:
        sql = f.read()
    
    # Execute migration in transaction
    async with conn.transaction():
        # Execute the migration SQL
        await conn.execute(sql)
        
        # Record migration as applied
        await conn.execute(
            "INSERT INTO schema_migrations (version) VALUES ($1)",
            version
        )
    
    print(f"✓ Applied migration: {version}")


async def run_migrations():
    """Run all pending migrations"""
    conn = None
    try:
        # Connect to database
        print("Connecting to database...")
        conn = await get_db_connection()
        
        # Create migrations table
        await create_migrations_table(conn)
        
        # Get applied migrations
        applied = await get_applied_migrations(conn)
        print(f"Found {len(applied)} applied migrations")
        
        # Get all migration files
        migration_files = await get_migration_files()
        print(f"Found {len(migration_files)} migration files")
        
        # Apply pending migrations
        pending_count = 0
        for version, file_path in migration_files:
            if version not in applied:
                await apply_migration(conn, version, file_path)
                pending_count += 1
        
        if pending_count == 0:
            print("No pending migrations to apply")
        else:
            print(f"\n✓ Successfully applied {pending_count} migration(s)")
        
    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            await conn.close()


async def rollback_migration(version: str):
    """Rollback a specific migration (marks as not applied)"""
    conn = None
    try:
        conn = await get_db_connection()
        
        # Remove from migrations table
        result = await conn.execute(
            "DELETE FROM schema_migrations WHERE version = $1",
            version
        )
        
        if result == "DELETE 1":
            print(f"✓ Rolled back migration: {version}")
            print("Note: This only marks the migration as not applied.")
            print("Manual database changes may be required to reverse the migration.")
        else:
            print(f"Migration {version} was not applied")
        
    except Exception as e:
        print(f"ERROR: Rollback failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            await conn.close()


async def status():
    """Show migration status"""
    conn = None
    try:
        conn = await get_db_connection()
        await create_migrations_table(conn)
        
        # Get applied migrations
        applied = await get_applied_migrations(conn)
        
        # Get all migration files
        migration_files = await get_migration_files()
        
        print("\nMigration Status:")
        print("-" * 50)
        
        for version, file_path in migration_files:
            if version in applied:
                print(f"✓ {version} (applied)")
            else:
                print(f"  {version} (pending)")
        
        print("-" * 50)
        print(f"Total: {len(migration_files)} migrations")
        print(f"Applied: {len(applied)}")
        print(f"Pending: {len(migration_files) - len(applied)}")
        
    except Exception as e:
        print(f"ERROR: Status check failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            await conn.close()


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ProofKit database migration tool")
    parser.add_argument(
        "command",
        choices=["migrate", "status", "rollback"],
        help="Migration command to run"
    )
    parser.add_argument(
        "--version",
        help="Migration version (for rollback command)"
    )
    
    args = parser.parse_args()
    
    if args.command == "migrate":
        asyncio.run(run_migrations())
    elif args.command == "status":
        asyncio.run(status())
    elif args.command == "rollback":
        if not args.version:
            print("ERROR: --version required for rollback command")
            sys.exit(1)
        asyncio.run(rollback_migration(args.version))


if __name__ == "__main__":
    main()