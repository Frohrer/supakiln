#!/usr/bin/env python3
"""
Database migration script for supakiln
"""

import sqlite3
import os
from datetime import datetime
from sqlalchemy import text

def migrate_database():
    """Migrate the database to add new execution metrics fields."""
    db_path = 'code_executor.db'
    
    if not os.path.exists(db_path):
        print("Database doesn't exist yet. It will be created with the new schema.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if the new columns already exist
        cursor.execute("PRAGMA table_info(execution_logs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = [
            'cpu_user_time', 'cpu_system_time', 'cpu_percent',
            'memory_usage', 'memory_peak', 'memory_percent', 'memory_limit',
            'block_io_read', 'block_io_write', 'network_io_rx', 'network_io_tx',
            'pids_count', 'exit_code'
        ]
        
        # Add missing columns
        for column in new_columns:
            if column not in columns:
                if column.endswith('_time') or column.endswith('_percent'):
                    cursor.execute(f"ALTER TABLE execution_logs ADD COLUMN {column} REAL")
                else:
                    cursor.execute(f"ALTER TABLE execution_logs ADD COLUMN {column} INTEGER")
                print(f"Added column: {column}")
        
        conn.commit()
        print("Database migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        
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