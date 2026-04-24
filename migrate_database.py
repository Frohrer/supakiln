#!/usr/bin/env python3
"""
Database migration script for supakiln
"""

import sqlite3
import os
from datetime import datetime

def migrate_database():
    db_path = "code_executor.db"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if any tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        if not existing_tables or 'schema_info' not in existing_tables:
            # No tables exist (or no schema_info), create complete database schema
            print("🆕 Creating complete database schema...")
            create_complete_schema(cursor)
            current_version = 10
            print(f"✅ Database created with version {current_version}")
        else:
            # Tables exist, check version and apply migrations
            print("🔍 Existing database found, checking version...")

            try:
                cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
                current_version = cursor.fetchone()
                current_version = int(current_version[0]) if current_version else 0
            except sqlite3.OperationalError:
                current_version = 0

            print(f"Current database version: {current_version}")

            # Apply migrations if needed
            if current_version < 10:
                print(f"⬆️  Upgrading database from version {current_version} to 10...")
                apply_migrations(cursor, current_version)
                current_version = 10
                print(f"✅ Database upgraded to version {current_version}")
        
        # Verify the final schema
        verify_schema(cursor)
        
        conn.commit()
        print(f"✅ Database migration completed successfully. Version: {current_version}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

def create_complete_schema(cursor):
    """Create all tables with the current complete schema."""

    # Create schema_info table
    cursor.execute("""
        CREATE TABLE schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create users table. The `system` pseudo-user (id=1) owns every row
    # that predates auth, and any row created while anonymous access is
    # enabled. It has no password_hash so nobody can log in as it.
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "INSERT INTO users (id, email, password_hash, is_admin) "
        "VALUES (1, 'system@supakiln.local', NULL, 0)"
    )

    # Create api_keys table (kind = 'api' for user-managed tokens,
    # 'session' for login-issued cookies).
    cursor.execute("""
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            hashed_key VARCHAR(64) UNIQUE NOT NULL,
            prefix VARCHAR(32) NOT NULL,
            label VARCHAR(100),
            kind VARCHAR(20) NOT NULL DEFAULT 'api',
            expires_at TIMESTAMP,
            last_used_at TIMESTAMP,
            revoked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX idx_api_keys_hashed_key ON api_keys(hashed_key)"
    )
    cursor.execute(
        "CREATE INDEX idx_api_keys_user_id ON api_keys(user_id)"
    )

    # Create environment_variables table. UNIQUE is composite so two
    # different users can have the same variable name (e.g. SECRET_KEY).
    cursor.execute("""
        CREATE TABLE environment_variables (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            owner_user_id INTEGER REFERENCES users(id) DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_user_id, name)
        )
    """)

    # Create scheduled_jobs table with timeout column
    cursor.execute("""
        CREATE TABLE scheduled_jobs (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            code TEXT NOT NULL,
            cron_expression VARCHAR(100) NOT NULL,
            container_id VARCHAR(100),
            packages TEXT,
            owner_user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_run TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            timeout INTEGER DEFAULT 30,
            language VARCHAR(20) DEFAULT 'python'
        )
    """)

    # Create webhook_jobs table with timeout column
    cursor.execute("""
        CREATE TABLE webhook_jobs (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            endpoint VARCHAR(200) UNIQUE NOT NULL,
            code TEXT NOT NULL,
            container_id VARCHAR(100),
            packages TEXT,
            owner_user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_triggered TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            timeout INTEGER DEFAULT 30,
            description TEXT,
            language VARCHAR(20) DEFAULT 'python'
        )
    """)

    # Create persistent_services table
    cursor.execute("""
        CREATE TABLE persistent_services (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            code TEXT NOT NULL,
            container_id VARCHAR(100),
            packages TEXT,
            owner_user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            last_restart TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            status VARCHAR(20) DEFAULT 'stopped',
            restart_policy VARCHAR(20) DEFAULT 'always',
            description TEXT,
            process_id VARCHAR(100),
            auto_start INTEGER DEFAULT 1,
            language VARCHAR(20) DEFAULT 'python'
        )
    """)

    # Create exposed_ports table
    cursor.execute("""
        CREATE TABLE exposed_ports (
            id INTEGER PRIMARY KEY,
            container_id VARCHAR(100) NOT NULL,
            internal_port INTEGER NOT NULL,
            external_port INTEGER NOT NULL,
            service_name VARCHAR(100),
            service_type VARCHAR(50),
            proxy_path VARCHAR(200) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            description TEXT
        )
    """)

    # Create execution_logs table with all columns
    cursor.execute("""
        CREATE TABLE execution_logs (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            webhook_job_id INTEGER,
            service_id INTEGER,
            owner_user_id INTEGER REFERENCES users(id) DEFAULT 1,
            code TEXT NOT NULL,
            output TEXT,
            error TEXT,
            container_id VARCHAR(100),
            execution_time REAL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20),
            request_data TEXT,
            response_data TEXT
        )
    """)

    # Set version to latest
    cursor.execute("INSERT INTO schema_info (key, value) VALUES ('version', '10')")

def apply_migrations(cursor, current_version):
    """Apply migrations from current_version to latest."""
    
    # Ensure schema_info table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Migration: Add timeout column to scheduled_jobs if missing
    if current_version < 7:
        print("Adding timeout column to scheduled_jobs table...")
        try:
            cursor.execute("ALTER TABLE scheduled_jobs ADD COLUMN timeout INTEGER DEFAULT 30")
            print("✅ Added timeout column to scheduled_jobs table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            print("✅ timeout column already exists in scheduled_jobs table")
    
    # Migration: Add timeout column to webhook_jobs if missing
    if current_version < 7:
        print("Adding timeout column to webhook_jobs table...")
        try:
            cursor.execute("ALTER TABLE webhook_jobs ADD COLUMN timeout INTEGER DEFAULT 30")
            print("✅ Added timeout column to webhook_jobs table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            print("✅ timeout column already exists in webhook_jobs table")
    
    # Migration: Add description column to environment_variables if missing
    if current_version < 7:
        print("Adding description column to environment_variables table...")
        try:
            cursor.execute("ALTER TABLE environment_variables ADD COLUMN description TEXT")
            print("✅ Added description column to environment_variables table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            print("✅ description column already exists in environment_variables table")
    
    # Migration: Add service_id column to execution_logs if missing
    if current_version < 7:
        print("Adding service_id column to execution_logs table...")
        try:
            cursor.execute("ALTER TABLE execution_logs ADD COLUMN service_id INTEGER")
            print("✅ Added service_id column to execution_logs table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            print("✅ service_id column already exists in execution_logs table")
    
    # Migration: Add webhook_job_id column to execution_logs if missing
    if current_version < 7:
        print("Adding webhook_job_id column to execution_logs table...")
        try:
            cursor.execute("ALTER TABLE execution_logs ADD COLUMN webhook_job_id INTEGER")
            print("✅ Added webhook_job_id column to execution_logs table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            print("✅ webhook_job_id column already exists in execution_logs table")
    
    # Create missing tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persistent_services (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            code TEXT NOT NULL,
            container_id VARCHAR(100),
            packages TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            last_restart TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            status VARCHAR(20) DEFAULT 'stopped',
            restart_policy VARCHAR(20) DEFAULT 'always',
            description TEXT,
            process_id VARCHAR(100),
            auto_start INTEGER DEFAULT 1
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exposed_ports (
            id INTEGER PRIMARY KEY,
            container_id VARCHAR(100) NOT NULL,
            internal_port INTEGER NOT NULL,
            external_port INTEGER NOT NULL,
            service_name VARCHAR(100),
            service_type VARCHAR(50),
            proxy_path VARCHAR(200) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            description TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_jobs (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            endpoint VARCHAR(200) UNIQUE NOT NULL,
            code TEXT NOT NULL,
            container_id VARCHAR(100),
            packages TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_triggered TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            timeout INTEGER DEFAULT 30,
            description TEXT
        )
    """)
    
    # Migration v7 -> v8: add `language` column to code-bearing tables
    if current_version < 8:
        for table in ("scheduled_jobs", "webhook_jobs", "persistent_services"):
            print(f"Adding language column to {table}...")
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN language VARCHAR(20) DEFAULT 'python'"
                )
                print(f"✅ Added language column to {table}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print(f"✅ language column already exists in {table}")

    # Migration v8 -> v9: introduce users + api_keys, and attribute
    # existing rows to the `system` user (id=1).
    if current_version < 9:
        print("Creating users table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Reserve id=1 for the system user if the table is empty.
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO users (id, email, password_hash, is_admin) "
                "VALUES (1, 'system@supakiln.local', NULL, 0)"
            )
            print("✅ Seeded system user (id=1)")

        print("Creating api_keys table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                hashed_key VARCHAR(64) UNIQUE NOT NULL,
                prefix VARCHAR(32) NOT NULL,
                label VARCHAR(100),
                kind VARCHAR(20) NOT NULL DEFAULT 'api',
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                revoked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_hashed_key "
            "ON api_keys(hashed_key)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id "
            "ON api_keys(user_id)"
        )

        # Add owner_user_id to every user-owned table. Default 1 so
        # existing rows are attributed to the system user — SQLite
        # does not support setting a DEFAULT via ALTER TABLE with a
        # non-constant, but CURRENT_TIMESTAMP-style constants are fine
        # and so is a literal integer. Backfill explicitly regardless.
        for table in (
            "environment_variables",
            "scheduled_jobs",
            "webhook_jobs",
            "persistent_services",
        ):
            print(f"Adding owner_user_id column to {table}...")
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN owner_user_id INTEGER "
                    f"REFERENCES users(id) DEFAULT 1"
                )
                print(f"✅ Added owner_user_id column to {table}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print(f"✅ owner_user_id already exists in {table}")
            cursor.execute(
                f"UPDATE {table} SET owner_user_id = 1 "
                f"WHERE owner_user_id IS NULL"
            )

    # Migration v9 -> v10: attribute log rows to owner, move env-var
    # uniqueness from global-on-name to per-user-on-name.
    if current_version < 10:
        print("Adding owner_user_id column to execution_logs...")
        try:
            cursor.execute(
                "ALTER TABLE execution_logs ADD COLUMN owner_user_id INTEGER "
                "REFERENCES users(id) DEFAULT 1"
            )
            print("✅ Added owner_user_id column to execution_logs")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            print("✅ owner_user_id already exists in execution_logs")
        cursor.execute(
            "UPDATE execution_logs SET owner_user_id = 1 "
            "WHERE owner_user_id IS NULL"
        )

        # SQLite can't DROP a UNIQUE constraint in-place. Rebuild the
        # table: rename the old one, recreate with composite unique,
        # copy rows over, drop the old. Safe because nobody's writing
        # to this table during startup migration.
        print("Rebuilding environment_variables with composite unique...")
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='environment_variables'"
        )
        row = cursor.fetchone()
        current_sql = row[0] if row else ""
        # Only rebuild if the old-style global UNIQUE on name is still
        # present (or if the new composite unique is absent). Looking
        # for "UNIQUE(owner_user_id" avoids rebuilding twice.
        needs_rebuild = "UNIQUE(owner_user_id" not in (current_sql or "")
        if needs_rebuild:
            cursor.execute(
                "ALTER TABLE environment_variables RENAME TO "
                "environment_variables_old_v9"
            )
            cursor.execute("""
                CREATE TABLE environment_variables (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    owner_user_id INTEGER REFERENCES users(id) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(owner_user_id, name)
                )
            """)
            cursor.execute("""
                INSERT INTO environment_variables
                    (id, name, value, description, owner_user_id,
                     created_at, updated_at)
                SELECT id, name, value, description,
                       COALESCE(owner_user_id, 1),
                       created_at, updated_at
                FROM environment_variables_old_v9
            """)
            cursor.execute("DROP TABLE environment_variables_old_v9")
            print("✅ Rebuilt environment_variables with UNIQUE(owner_user_id, name)")
        else:
            print("✅ environment_variables already has composite unique")

    # Update version
    cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '10')")

def verify_schema(cursor):
    """Verify that all required tables and columns exist."""
    
    # Check scheduled_jobs has timeout column
    cursor.execute("PRAGMA table_info(scheduled_jobs)")
    scheduled_jobs_columns = [row[1] for row in cursor.fetchall()]
    
    if 'timeout' not in scheduled_jobs_columns:
        raise Exception("Verification failed: timeout column missing from scheduled_jobs table")
    
    # Check webhook_jobs has timeout column
    cursor.execute("PRAGMA table_info(webhook_jobs)")
    webhook_jobs_columns = [row[1] for row in cursor.fetchall()]
    
    if 'timeout' not in webhook_jobs_columns:
        raise Exception("Verification failed: timeout column missing from webhook_jobs table")
    
    # Check required tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = [
        'schema_info', 'environment_variables', 'scheduled_jobs',
        'webhook_jobs', 'persistent_services', 'exposed_ports',
        'execution_logs', 'users', 'api_keys'
    ]
    
    for table in required_tables:
        if table not in existing_tables:
            raise Exception(f"Verification failed: required table {table} not found")
    
    print("✅ Schema verification passed")

def upgrade(db_session):
    """Legacy function for SQLAlchemy-based upgrades."""
    try:
        from sqlalchemy import text
        result = db_session.execute(text("PRAGMA table_info(environment_variables)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'description' not in columns:
            print("Adding description column to environment_variables table...")
            db_session.execute(text("ALTER TABLE environment_variables ADD COLUMN description TEXT"))
            db_session.commit()
            print("Successfully added description column")
        else:
            print("Description column already exists")
            
    except ImportError:
        print("SQLAlchemy not available for upgrade function")
    except Exception as e:
        print(f"Error during migration: {e}")
        db_session.rollback()
        raise

if __name__ == "__main__":
    migrate_database() 