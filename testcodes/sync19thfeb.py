#!/usr/bin/env python3
"""
IITDH Attendance System - Cloud Sync Script (FIXED)
Syncs local SQLite database to Supabase cloud database

Fixes:
  - Syncs fingerprint templates for both students and professors
  - Maps local `password` column → cloud `password_hash` column
  - Uses upsert throughout to prevent duplicates on re-run
  - Bulk commit for attendance (crash-safe)
"""

import sqlite3
import os
import time
from supabase import create_client, Client

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://peagkvkhhsbdytevnhia.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_secret_Q0zxaI4Myb6lY0IWZKgjLw_pXGH5zXj")

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# Local dept/program full names → cloud codes
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


def template_to_list(template_bytes):
    """
    Convert raw bytes fingerprint template → list of ints for Supabase JSON.
    Supabase stores bytea columns as JSON arrays when sent via the REST API.
    Returns None if template is None or empty.
    """
    if template_bytes is None:
        return None
    if isinstance(template_bytes, (bytes, bytearray)) and len(template_bytes) > 0:
        return list(template_bytes)
    return None


def template_label(template):
    """Human-readable template status for logging."""
    if template:
        return f"✓ template ({len(template)} bytes)"
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
    Sync professors including fingerprint template.
    Cloud column: `template` (bytea, nullable).
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
            supabase.table("profs").upsert({
                "prof_id":    prof_id,
                "name":       name,
                "dept_code":  dept_code,
                "email":      email,
                "template":   template_to_list(template),  # None → null (cloud col must be nullable)
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
    Sync students including:
      - fingerprint template  (bytes → JSON list of ints)
      - password              (local col `password` → cloud col `password_hash`)
      - dept/program          (full names mapped to codes)
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

            supabase.table("students").upsert({
                "student_id":    student_id,
                "first_name":    first_name,
                "last_name":     last_name,
                "dept":          dept_code,
                "year":          year,
                "program":       prog_code,
                "email":         email,
                "password_hash": password,               # local `password` → cloud `password_hash`
                "template":      template_to_list(template),
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
    print("\n📝 Syncing Course Enrollments...")
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
    """
    Incrementally sync unsynced attendance records to cloud.
    - Upserts on attendance_id so re-runs are safe.
    - Only marks synced=1 after confirmed cloud write (crash-safe).
    """
    print("\n📊 Syncing Attendance Records...")

    cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
    total_unsynced = cursor.fetchone()[0]

    if total_unsynced == 0:
        print("☁️  All attendance records already synced!")
        return

    print(f"📤 Found {total_unsynced} unsynced records")
    print(f"📦 Processing in batches of {batch_size}...")

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

        for record in batch:
            att_id, course_code, student_id, student_name, \
                authorized_by, timestamp, session_date = record
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

        # Bulk-mark confirmed successes — one commit per batch (crash-safe)
        if successful_ids:
            placeholders = ",".join("?" * len(successful_ids))
            cursor.execute(f"""
                UPDATE attendance SET synced = 1
                WHERE attendance_id IN ({placeholders})
            """, successful_ids)
            conn.commit()

        time.sleep(0.1)  # Avoid Supabase rate limits

    print(f"✅ Attendance: {synced_count} synced, {failed_count} failed")


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def full_sync():
    """Sync all tables in dependency order: reference → master → courses → transactional."""
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
        sync_departments(supabase, cursor)          # no FK dependencies
        sync_programs(supabase, cursor)             # no FK dependencies
        sync_professors(supabase, cursor)           # FK → departments
        sync_students(supabase, cursor)             # FK → departments, programs
        sync_courses(supabase, cursor)              # FK → profs, departments
        sync_enrollments(supabase, cursor)          # FK → students, courses
        sync_attendance(supabase, cursor, conn)     # FK → students, courses

        print_header("SYNC COMPLETE")

        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 1")
        total_synced = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        total_pending = cursor.fetchone()[0]
        print(f"\n📊 Attendance synced  : {total_synced}")
        print(f"   Attendance pending : {total_pending}")

    except Exception as e:
        print(f"\n❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        print("\n💾 Local database connection closed")


def attendance_only_sync():
    """Quick sync — push only unsynced attendance records to cloud."""
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
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--attendance-only":
        attendance_only_sync()
    else:
        full_sync()