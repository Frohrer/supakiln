#!/usr/bin/env python3
"""
Database migration script to add webhook-related columns to the execution_logs table.
"""

import sqlite3
import os
from datetime import datetime

def migrate_database():
    """Add missing columns to the execution_logs table."""
    db_path = 'code_executor.db'
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist. No migration needed.")
        return
    
    print(f"Migrating database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the new columns already exist
        cursor.execute("PRAGMA table_info(execution_logs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        migrations_needed = []
        
        if 'webhook_job_id' not in columns:
            migrations_needed.append('webhook_job_id')
        
        if 'request_data' not in columns:
            migrations_needed.append('request_data')
            
        if 'response_data' not in columns:
            migrations_needed.append('response_data')
        
        if not migrations_needed:
            print("✅ Database is already up to date!")
            return
        
        print(f"📝 Adding missing columns: {', '.join(migrations_needed)}")
        
        # Add missing columns
        if 'webhook_job_id' in migrations_needed:
            cursor.execute("ALTER TABLE execution_logs ADD COLUMN webhook_job_id INTEGER")
            print("   ✅ Added webhook_job_id column")
        
        if 'request_data' in migrations_needed:
            cursor.execute("ALTER TABLE execution_logs ADD COLUMN request_data TEXT")
            print("   ✅ Added request_data column")
            
        if 'response_data' in migrations_needed:
            cursor.execute("ALTER TABLE execution_logs ADD COLUMN response_data TEXT")
            print("   ✅ Added response_data column")
        
        # Create webhook_jobs table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_jobs (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                endpoint VARCHAR(200) UNIQUE NOT NULL,
                code TEXT NOT NULL,
                container_id VARCHAR(100),
                packages TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_triggered DATETIME,
                is_active INTEGER DEFAULT 1,
                timeout INTEGER DEFAULT 30,
                description TEXT
            )
        """)
        print("   ✅ Ensured webhook_jobs table exists")
        
        conn.commit()
        print(f"🎉 Migration completed successfully at {datetime.now()}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            conn.close()

def reset_database():
    """Reset the database by deleting and recreating it."""
    db_path = 'code_executor.db'
    
    if os.path.exists(db_path):
        backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.rename(db_path, backup_path)
        print(f"📦 Backed up existing database to {backup_path}")
    
    print("🗑️  Database will be recreated when the application starts")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        print("⚠️  RESETTING DATABASE (all data will be lost)")
        confirm = input("Are you sure? Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            reset_database()
        else:
            print("❌ Reset cancelled")
    else:
        print("🔄 Running database migration...")
        migrate_database()
        print("\n💡 If you continue to have issues, you can reset the database with:")
        print("   python migrate_database.py reset") 