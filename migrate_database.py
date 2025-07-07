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
    
    # TODO: Uncomment this when we have a way to backup the database without creation a million backups
    # if os.path.exists(db_path):
    #     backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    #     import shutil
    #     shutil.copy2(db_path, backup_path)
    #     print(f"Database backed up to: {backup_path}")
    
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
        
        # If version is 0, check if tables already exist with current schema
        # This handles the case where SQLAlchemy created tables before migration runs
        if current_version == 0:
            print("Checking existing table schemas...")
            
            # Check if base tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_jobs'")
            scheduled_jobs_exists = cursor.fetchone() is not None
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='environment_variables'")
            environment_variables_exists = cursor.fetchone() is not None
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='execution_logs'")
            execution_logs_exists = cursor.fetchone() is not None
            
            if scheduled_jobs_exists and environment_variables_exists and execution_logs_exists:
                # Base tables exist, check their schemas
                
                # Check if scheduled_jobs table has timeout column
                cursor.execute("PRAGMA table_info(scheduled_jobs)")
                scheduled_jobs_columns = [row[1] for row in cursor.fetchall()]
                
                # Check if webhook_jobs table exists and has timeout column
                cursor.execute("PRAGMA table_info(webhook_jobs)")
                webhook_jobs_columns = [row[1] for row in cursor.fetchall()]
                
                # Check if persistent_services table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='persistent_services'")
                persistent_services_exists = cursor.fetchone() is not None
                
                # Check if exposed_ports table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exposed_ports'")
                exposed_ports_exists = cursor.fetchone() is not None
                
                # Check if execution_logs has service_id and webhook_job_id columns
                cursor.execute("PRAGMA table_info(execution_logs)")
                execution_logs_columns = [row[1] for row in cursor.fetchall()]
                
                # Check if environment_variables has description column
                cursor.execute("PRAGMA table_info(environment_variables)")
                env_vars_columns = [row[1] for row in cursor.fetchall()]
                
                # Determine the appropriate version based on existing schema
                if ('timeout' in scheduled_jobs_columns and 
                    'timeout' in webhook_jobs_columns and
                    persistent_services_exists and
                    exposed_ports_exists and
                    'service_id' in execution_logs_columns and
                    'webhook_job_id' in execution_logs_columns and
                    'description' in env_vars_columns):
                    # All migrations are already applied, set to latest version
                    current_version = 7
                    print("All tables exist with current schema, setting version to 7")
                elif ('timeout' in webhook_jobs_columns and
                      persistent_services_exists and
                      exposed_ports_exists and
                      'service_id' in execution_logs_columns and
                      'webhook_job_id' in execution_logs_columns and
                      'description' in env_vars_columns):
                    # Need to add timeout to scheduled_jobs
                    current_version = 6
                    print("Missing timeout column in scheduled_jobs, setting version to 6")
                elif (len(webhook_jobs_columns) > 0 and
                      persistent_services_exists and
                      exposed_ports_exists and
                      'service_id' in execution_logs_columns and
                      'webhook_job_id' in execution_logs_columns and
                      'description' in env_vars_columns):
                    # webhook_jobs exists but might be missing timeout, other tables complete
                    current_version = 5
                    print("Tables exist but schema incomplete, setting version to 5")
                else:
                    # Base tables exist but schema is incomplete, start from version 1
                    current_version = 1
                    print("Base tables exist but schema incomplete, setting version to 1")
            else:
                # Base tables don't exist, start from version 0
                print("Base tables don't exist, starting from version 0")
            
        # Migration 1: Create base tables and schema_info table
        if current_version < 1:
            print("Applying migration 1: Creating base tables and schema_info table...")
            
            # Create schema_info table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create environment_variables table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS environment_variables (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create scheduled_jobs table (without timeout column initially)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    code TEXT NOT NULL,
                    cron_expression VARCHAR(100) NOT NULL,
                    container_id VARCHAR(100),
                    packages TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_run TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            
            # Create execution_logs table (without additional columns initially)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
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
        
        # Migration 6: Add exposed_ports table
        if current_version < 6:
            print("Applying migration 6: Creating exposed_ports table...")
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
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '6')")
            current_version = 6
        
        # Migration 7: Add timeout column to scheduled_jobs table
        if current_version < 7:
            print("Applying migration 7: Adding timeout column to scheduled_jobs table...")
            try:
                cursor.execute("ALTER TABLE scheduled_jobs ADD COLUMN timeout INTEGER DEFAULT 30")
                print("Added timeout column to scheduled_jobs table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("timeout column already exists in scheduled_jobs table")
            
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', '7')")
            current_version = 7
        
        # Ensure schema_info table is created and version is set correctly
        if current_version >= 1:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', ?)", (str(current_version),))
        
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