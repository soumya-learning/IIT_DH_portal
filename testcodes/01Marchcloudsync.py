#!/usr/bin/env python3
"""
IITDH Attendance System - Cloud Sync (Local → Cloud)

"""

import sqlite3
import os
import sys
import time
from supabase import create_client, Client

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://peagkvkhhsbdytevnhia.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_secret_Q0zxaI4Myb6lY0IWZKgjLw_pXGH5zXj")

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

DEPT_NAME_TO_CODE = {
    "Computer Science":       "CS",
    "Electrical Engineering": "EE",
    "Math & Computing":       "MC",
    "Mechanical Engineering": "ME",
    "Chemical Engineering":   "CH",
    "Civil Engineering":      "CE"
}

PROG_NAME_TO_CODE = {
    "B.Tech": "BT",
    "BSMS":   "IS",
    "M.Tech":  "MT"
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def template_to_hex(template_bytes):
    """
    Convert raw fingerprint bytes to a plain hex string for Supabase upload.

    Encoding chain:
      SQLite BLOB: b'\\x03\\x03Y\\x1d...'  (768 raw bytes)
          ↓  .hex()
      Hex string : "0303591d..."            (sent to Supabase REST API)
          ↓  Supabase stores as bytea
      Supabase   : "\\x0303591d..."         (returned on SELECT)

    Returns None if template is None or empty.
    """
    if template_bytes is None:
        return None
    if isinstance(template_bytes, (bytes, bytearray, sqlite3.Binary)):
        b = bytes(template_bytes)
        if len(b) > 0:
            return b.hex()
    return None


def template_label(template):
    if template and len(template) > 0:
        return f"✓ ({len(template)} bytes)"
    return "✗ no template"


# ─────────────────────────────────────────────
# SYNC FUNCTIONS
# ─────────────────────────────────────────────

def sync_departments(supabase: Client, cursor):
    print("\n📋 Syncing Departments...")
    cursor.execute("SELECT dept_code, dept_name FROM Departments")
    rows = cursor.fetchall()
    synced = 0
    for dept_code, dept_name in rows:
        try:
            supabase.table("departments").upsert({
                "dept_code": dept_code,
                "dept_name": dept_name
            }).execute()
            synced += 1
            print(f"  ✓ {dept_code}: {dept_name}")
        except Exception as e:
            print(f"  ✗ {dept_code}: {e}")
    print(f"✅ Departments: {synced}/{len(rows)} synced")


def sync_programs(supabase: Client, cursor):
    print("\n📋 Syncing Programs...")
    cursor.execute("SELECT program_code, program_name FROM Programs")
    rows = cursor.fetchall()
    synced = 0
    for prog_code, prog_name in rows:
        try:
            supabase.table("programs").upsert({
                "program_code": prog_code,
                "program_name": prog_name
            }).execute()
            synced += 1
            print(f"  ✓ {prog_code}: {prog_name}")
        except Exception as e:
            print(f"  ✗ {prog_code}: {e}")
    print(f"✅ Programs: {synced}/{len(rows)} synced")


def sync_professors(supabase: Client, cursor):
    """
    Sync professors. Template sent as plain hex string.
    Local BLOB b'\\x03\\x03Y...' → sent as "030359..." → stored as bytea in Supabase.
    """
    print("\n👨‍🏫 Syncing Professors...")
    cursor.execute("""
        SELECT prof_id, name, dept_code, email, template, created_at
        FROM profs
    """)
    rows = cursor.fetchall()
    synced = 0
    skipped = 0
    for prof_id, name, dept_code, email, template, created_at in rows:
        try:
            hex_template = template_to_hex(template)
            supabase.table("profs").upsert({
                "prof_id":    prof_id,
                "name":       name,
                "dept_code":  dept_code,
                "email":      email,
                "template":   hex_template,
                "created_at": created_at
            }).execute()
            synced += 1
            print(f"  ✓ {prof_id}: {name} | {template_label(template)}")
        except Exception as e:
            print(f"  ✗ {prof_id}: {e}")
            skipped += 1
    print(f"✅ Professors: {synced}/{len(rows)} synced (skipped: {skipped})")


def sync_students(supabase: Client, cursor):
    """
    Sync students.
    - Template: local BLOB → hex string for Supabase
    - Password: local `password` col → cloud `password_hash` col
    - Dept/program: full names mapped to codes
    """
    print("\n👨‍🎓 Syncing Students...")
    cursor.execute("""
        SELECT student_id, first_name, last_name, dept, year, program,
               email, password, template, created_at
        FROM students
    """)
    rows = cursor.fetchall()
    synced = 0
    skipped = 0
    for student_id, first_name, last_name, dept, year, program, \
            email, password, template, created_at in rows:
        try:
            dept_code = DEPT_NAME_TO_CODE.get(dept, dept)
            prog_code = PROG_NAME_TO_CODE.get(program, program)
            hex_template = template_to_hex(template)
            supabase.table("students").upsert({
                "student_id":    student_id,
                "first_name":    first_name,
                "last_name":     last_name,
                "dept":          dept_code,
                "year":          year,
                "program":       prog_code,
                "email":         email,
                "password_hash": password,
                "template":      hex_template,
                "created_at":    created_at
            }).execute()
            synced += 1
            if synced % 20 == 0:
                print(f"  ... {synced}/{len(rows)} synced")
            else:
                print(f"  ✓ {student_id}: {first_name} {last_name} "
                      f"({dept_code}/{prog_code}) | {template_label(template)}")
        except Exception as e:
            print(f"  ✗ {student_id}: {e}")
            skipped += 1
    print(f"✅ Students: {synced}/{len(rows)} synced (skipped: {skipped})")


def sync_courses(supabase: Client, cursor):
    print("\n📚 Syncing Courses...")
    cursor.execute("""
        SELECT course_code, course_name, prof_id, dept_code,
               semester, year, time_slot, created_at
        FROM courses
    """)
    rows = cursor.fetchall()
    synced = 0
    for course_code, course_name, prof_id, dept_code, \
            semester, year, time_slot, created_at in rows:
        try:
            supabase.table("courses").upsert({
                "course_code": course_code,
                "course_name": course_name,
                "prof_id":     prof_id,
                "dept_code":   dept_code,
                "semester":    semester,
                "year":        year,
                "time_slot":   time_slot,
                "created_at":  created_at
            }).execute()
            synced += 1
            print(f"  ✓ {course_code}: {course_name}")
        except Exception as e:
            print(f"  ✗ {course_code}: {e}")
    print(f"✅ Courses: {synced}/{len(rows)} synced")


def sync_enrollments(supabase: Client, cursor):
    print("\n📝 Syncing Enrollments...")
    cursor.execute("""
        SELECT enrollment_id, student_id, course_code, enrolled_date, status
        FROM course_enrollments
    """)
    rows = cursor.fetchall()
    synced = 0
    skipped = 0
    for enroll_id, student_id, course_code, enrolled_date, status in rows:
        try:
            supabase.table("course_enrollments").upsert({
                "enrollment_id": enroll_id,
                "student_id":    student_id,
                "course_code":   course_code,
                "enrolled_date": enrolled_date,
                "status":        status
            }).execute()
            synced += 1
            if synced % 20 == 0:
                print(f"  ... {synced}/{len(rows)} synced")
        except Exception as e:
            print(f"  ✗ Enrollment {enroll_id}: {e}")
            skipped += 1
    print(f"✅ Enrollments: {synced}/{len(rows)} synced (skipped: {skipped})")


def sync_attendance(supabase: Client, cursor, conn, batch_size=50):
    """Incrementally push unsynced attendance. Upserts on attendance_id — safe to re-run."""
    print("\n📊 Syncing Attendance Records...")
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
    total_unsynced = cursor.fetchone()[0]

    if total_unsynced == 0:
        print("☁️  All attendance records already synced!")
        return

    print(f"📤 Found {total_unsynced} unsynced records")
    synced_count = 0
    failed_count = 0

    while True:
        cursor.execute("""
            SELECT attendance_id, course_code, student_id, student_name,
                   authorized_by, timestamp, session_date
            FROM attendance
            WHERE synced = 0
            LIMIT ?
        """, (batch_size,))
        batch = cursor.fetchall()
        if not batch:
            break

        successful_ids = []
        for att_id, course_code, student_id, student_name, \
                authorized_by, timestamp, session_date in batch:
            try:
                supabase.table("attendance").upsert({
                    "attendance_id": att_id,
                    "course_code":   course_code,
                    "student_id":    student_id,
                    "authorized_by": authorized_by,
                    "session_date":  session_date,
                    "recorded_at":   timestamp
                }).execute()
                successful_ids.append(att_id)
                synced_count += 1
                if synced_count % 10 == 0:
                    print(f"  ✓ {synced_count}/{total_unsynced} synced...")
            except Exception as e:
                print(f"  ✗ Attendance {att_id}: {e}")
                failed_count += 1

        if successful_ids:
            placeholders = ",".join("?" * len(successful_ids))
            cursor.execute(
                f"UPDATE attendance SET synced = 1 WHERE attendance_id IN ({placeholders})",
                successful_ids
            )
            conn.commit()
        time.sleep(0.1)

    print(f"✅ Attendance: {synced_count} synced, {failed_count} failed")


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def full_sync():
    print_header("IITDH ATTENDANCE SYSTEM - FULL CLOUD SYNC")

    print("\n🔌 Connecting to Supabase...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return

    print("\n💾 Connecting to local database...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()
        print("✅ Connected to local database")
    except Exception as e:
        print(f"❌ Local database connection failed: {e}")
        return

    try:
        sync_departments(supabase, cursor)
        sync_programs(supabase, cursor)
        sync_professors(supabase, cursor)
        sync_students(supabase, cursor)
        sync_courses(supabase, cursor)
        sync_enrollments(supabase, cursor)
        sync_attendance(supabase, cursor, conn)

        print_header("SYNC COMPLETE")
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 1")
        print(f"\n📊 Attendance synced  : {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        print(f"   Attendance pending : {cursor.fetchone()[0]}")

    except Exception as e:
        print(f"\n❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        print("\n💾 Local database connection closed")


def attendance_only_sync():
    print_header("ATTENDANCE QUICK SYNC")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()
        sync_attendance(supabase, cursor, conn)
        conn.close()
        print("\n✅ Attendance sync complete")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--attendance-only":
        attendance_only_sync()
    else:
        full_sync()