#!/usr/bin/env python3
"""
Database Migration Script - Add Sync Support
Adds 'synced' column to attendance table for cloud synchronization
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'
BACKUP_DIR = '/home/bio_user_iitdh/new_env/DB/backups'

def create_backup():
    """Create backup before migration"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/college_backup_{timestamp}.db"
    
    print(f"📦 Creating backup: {backup_path}")
    
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    dest.close()
    source.close()
    
    print("✅ Backup created successfully")
    return backup_path

def add_sync_column():
    """Add synced column to attendance table"""
    print("\n🔧 Adding 'synced' column to attendance table...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(attendance)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'synced' in columns:
            print("⚠️  'synced' column already exists - skipping")
        else:
            # Add synced column (0 = not synced, 1 = synced)
            cursor.execute("""
                ALTER TABLE attendance 
                ADD COLUMN synced INTEGER DEFAULT 0
            """)
            conn.commit()
            print("✅ 'synced' column added successfully")
            
            # Show count of unsynced records
            cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
            unsynced = cursor.fetchone()[0]
            print(f"📊 Unsynced records: {unsynced}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

def verify_schema():
    """Verify the database schema"""
    print("\n🔍 Verifying database schema...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check attendance table
    cursor.execute("PRAGMA table_info(attendance)")
    columns = cursor.fetchall()
    
    print("\n📋 Attendance Table Schema:")
    for col in columns:
        col_id, name, col_type, not_null, default, pk = col
        print(f"  {name:20s} {col_type:15s} {'PRIMARY KEY' if pk else ''}")
    
    conn.close()

def show_sync_status():
    """Show current sync status"""
    print("\n📊 Sync Status:")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total records
    cursor.execute("SELECT COUNT(*) FROM attendance")
    total = cursor.fetchone()[0]
    
    # Synced records
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 1")
    synced = cursor.fetchone()[0]
    
    # Unsynced records
    unsynced = total - synced
    
    print(f"  Total records:    {total}")
    print(f"  Synced:           {synced}")
    print(f"  Pending sync:     {unsynced}")
    
    if unsynced > 0:
        print(f"\n💡 Run the sync script to upload {unsynced} records to cloud")
    
    conn.close()

def main():
    print("="*70)
    print("  DATABASE MIGRATION - Add Cloud Sync Support")
    print("="*70)
    
    if not os.path.exists(DB_PATH):
        print(f"\n❌ Database not found: {DB_PATH}")
        print("💡 Run setup_database.py first")
        return
    
    # Create backup
    backup_path = create_backup()
    
    # Add sync column
    add_sync_column()
    
    # Verify schema
    verify_schema()
    
    # Show status
    show_sync_status()
    
    print("\n" + "="*70)
    print("✅ Migration Complete!")
    print("="*70)
    print(f"\n📦 Backup saved: {backup_path}")
    print("\n📝 Next Steps:")
    print("  1. Configure your Supabase credentials in sync_to_cloud.py")
    print("  2. Run: python3 sync_to_cloud.py")

if __name__ == "__main__":
    main()