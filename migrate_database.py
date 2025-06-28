#!/usr/bin/env python3
"""
Database migration script for supakiln
"""

import sqlite3
import os
from datetime import datetime
from sqlalchemy import text

def migrate_database():
    db_path = "code_executor.db"
    
    # Create backup
    if os.path.exists(db_path):
        backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"Database backed up to: {backup_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current schema version
        try:
            cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
            current_version = cursor.fetchone()
            current_version = int(current_version[0]) if current_version else 0
        except sqlite3.OperationalError:
            # schema_info table doesn't exist, this is version 0
            current_version = 0
            
        print(f"Current database version: {current_version}")
        
        # Migration 1: Create schema_info table
        if current_version < 1:
            print("Applying migration 1: Creating schema_info table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '1')")
            current_version = 1
        
        # Migration 2: Add webhook_jobs table (if it doesn't exist)
        if current_version < 2:
            print("Applying migration 2: Creating webhook_jobs table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_jobs (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    endpoint VARCHAR(200) UNIQUE NOT NULL,
                    code TEXT NOT NULL,
                    container_id VARCHAR(100),
                    packages TEXT,
                    created_at TIMESTAMP,
                    last_triggered TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    timeout INTEGER DEFAULT 30,
                    description TEXT
                )
            """)
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '2')")
            current_version = 2
        
        # Migration 3: Add persistent_services table and update execution_logs
        if current_version < 3:
            print("Applying migration 3: Creating persistent_services table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS persistent_services (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    code TEXT NOT NULL,
                    container_id VARCHAR(100),
                    packages TEXT,
                    created_at TIMESTAMP,
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
            
            # Add service_id column to execution_logs if it doesn't exist
            try:
                cursor.execute("ALTER TABLE execution_logs ADD COLUMN service_id INTEGER")
                print("Added service_id column to execution_logs")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("service_id column already exists in execution_logs")
            
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '3')")
            current_version = 3
        
        # Migration 4: Add webhook_job_id column to execution_logs
        if current_version < 4:
            print("Applying migration 4: Adding webhook_job_id column to execution_logs...")
            try:
                cursor.execute("ALTER TABLE execution_logs ADD COLUMN webhook_job_id INTEGER")
                print("Added webhook_job_id column to execution_logs")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("webhook_job_id column already exists in execution_logs")
            
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '4')")
            current_version = 4
        
        # Migration 5: Add description column to environment_variables table
        if current_version < 5:
            print("Applying migration 5: Adding description column to environment_variables table...")
            try:
                cursor.execute("ALTER TABLE environment_variables ADD COLUMN description TEXT")
                print("Added description column to environment_variables table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("description column already exists in environment_variables table")
            
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '5')")
            current_version = 5
        
        conn.commit()
        print(f"Database migration completed. Current version: {current_version}")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

def upgrade(db_session):
    try:
        # Check if description column already exists
        result = db_session.execute(text("PRAGMA table_info(environment_variables)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'description' not in columns:
            print("Adding description column to environment_variables table...")
            db_session.execute(text("ALTER TABLE environment_variables ADD COLUMN description TEXT"))
            db_session.commit()
            print("Successfully added description column")
        else:
            print("Description column already exists")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        db_session.rollback()
        raise

if __name__ == "__main__":
    migrate_database() 