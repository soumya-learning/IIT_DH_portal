#!/usr/bin/env python3
"""
IITDH Attendance System - Cloud Sync Script
Syncs local SQLite database to Supabase cloud database
- Maps department/program names to codes automatically
- Syncs fingerprint templates for both students and professors
- Uses upsert throughout to prevent duplicates
- Handles RLS with anon key (ensure SQL grants are applied first)
"""

import sqlite3
import os
from supabase import create_client, Client
import time

# --- SUPABASE CONFIGURATION ---
# Use env vars in production: export SUPABASE_URL=... and export SUPABASE_KEY=...
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://peagkvkhhsbdytevnhia.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBlYWdrdmtoaHNiZHl0ZXZuaGlhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEwOTU3MDUsImV4cCI6MjA4NjY3MTcwNX0.ah3IW3O8AJG_Aki0jKmeRkhcU_8dsKNGG3LazFFJIJ4")

# --- LOCAL DATABASE ---
DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# --- MAPPING DICTIONARIES ---
DEPT_NAME_TO_CODE = {
    "Computer Science": "CS",
    "Electrical Engineering": "EE",
    "Math & Computing": "MC",
    "Mechanical Engineering": "ME",
    "Chemical Engineering": "CH",
    "Civil Engineering": "CE"
}

PROG_NAME_TO_CODE = {
    "B.Tech": "BT",
    "BSMS": "IS",
    "M.Tech": "MT"
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def template_to_list(template_bytes):
    """Convert raw bytes fingerprint template to list of ints for JSON.
    Returns None if template is None or empty."""
    if template_bytes is None:
        return None
    if isinstance(template_bytes, (bytes, bytearray)) and len(template_bytes) > 0:
        return list(template_bytes)
    return None


# ─────────────────────────────────────────────
# SYNC FUNCTIONS
# ─────────────────────────────────────────────

def sync_departments(supabase: Client, cursor):
    print("\n📋 Syncing Departments...")
    cursor.execute("SELECT dept_code, dept_name FROM Departments")
    departments = cursor.fetchall()

    synced = 0
    for dept_code, dept_name in departments:
        try:
            supabase.table("departments").upsert({
                "dept_code": dept_code,
                "dept_name": dept_name
            }).execute()
            synced += 1
            print(f"  ✓ {dept_code}: {dept_name}")
        except Exception as e:
            print(f"  ✗ {dept_code}: {e}")

    print(f"✅ Departments: {synced}/{len(departments)} synced")


def sync_programs(supabase: Client, cursor):
    print("\n📋 Syncing Programs...")
    cursor.execute("SELECT program_code, program_name FROM Programs")
    programs = cursor.fetchall()

    synced = 0
    for prog_code, prog_name in programs:
        try:
            supabase.table("programs").upsert({
                "program_code": prog_code,
                "program_name": prog_name
            }).execute()
            synced += 1
            print(f"  ✓ {prog_code}: {prog_name}")
        except Exception as e:
            print(f"  ✗ {prog_code}: {e}")

    print(f"✅ Programs: {synced}/{len(programs)} synced")


def sync_professors(supabase: Client, cursor):
    """Sync professors including fingerprint template."""
    print("\n👨‍🏫 Syncing Professors...")
    cursor.execute("""
        SELECT prof_id, name, dept_code, email, template, created_at
        FROM profs
    """)
    profs = cursor.fetchall()

    synced = 0
    skipped = 0
    for prof_id, name, dept_code, email, template, created_at in profs:
        try:
            supabase.table("profs").upsert({
                "prof_id": prof_id,
                "name": name,
                "dept_code": dept_code,
                "email": email,
                "template": template_to_list(template),
                "created_at": created_at
            }).execute()
            synced += 1
            template_status = "✓ template" if template else "- no template"
            print(f"  ✓ {prof_id}: {name} ({template_status})")
        except Exception as e:
            print(f"  ✗ {prof_id}: {e}")
            skipped += 1

    print(f"✅ Professors: {synced}/{len(profs)} synced (skipped: {skipped})")


def sync_students(supabase: Client, cursor):
    """Sync students including fingerprint template, mapping dept/program names to codes."""
    print("\n👨‍🎓 Syncing Students...")
    cursor.execute("""
        SELECT student_id, first_name, last_name, dept, year, program,
               email, template, created_at
        FROM students
    """)
    students = cursor.fetchall()

    synced = 0
    skipped = 0
    for student_id, first_name, last_name, dept, year, program, email, template, created_at in students:
        try:
            dept_code = DEPT_NAME_TO_CODE.get(dept, dept)
            prog_code = PROG_NAME_TO_CODE.get(program, program)

            supabase.table("students").upsert({
                "student_id": student_id,
                "first_name": first_name,
                "last_name": last_name,
                "dept": dept_code,
                "year": year,
                "program": prog_code,
                "email": email,
                "template": template_to_list(template),
                "created_at": created_at
            }).execute()
            synced += 1

            template_status = "✓ template" if template else "- no template"
            if synced % 20 == 0:
                print(f"  Synced {synced}/{len(students)} students...")
            else:
                print(f"  ✓ {student_id}: {first_name} {last_name} ({dept_code}/{prog_code}, {template_status})")
        except Exception as e:
            print(f"  ✗ {student_id}: {e}")
            skipped += 1

    print(f"✅ Students: {synced}/{len(students)} synced (skipped: {skipped})")


def sync_courses(supabase: Client, cursor):
    print("\n📚 Syncing Courses...")
    cursor.execute("""
        SELECT course_code, course_name, prof_id, dept_code,
               semester, year, time_slot, created_at
        FROM courses
    """)
    courses = cursor.fetchall()

    synced = 0
    for course_code, course_name, prof_id, dept_code, semester, year, time_slot, created_at in courses:
        try:
            supabase.table("courses").upsert({
                "course_code": course_code,
                "course_name": course_name,
                "prof_id": prof_id,
                "dept_code": dept_code,
                "semester": semester,
                "year": year,
                "time_slot": time_slot,
                "created_at": created_at
            }).execute()
            synced += 1
            print(f"  ✓ {course_code}: {course_name}")
        except Exception as e:
            print(f"  ✗ {course_code}: {e}")

    print(f"✅ Courses: {synced}/{len(courses)} synced")


def sync_enrollments(supabase: Client, cursor):
    print("\n📝 Syncing Course Enrollments...")
    cursor.execute("""
        SELECT enrollment_id, student_id, course_code, enrolled_date, status
        FROM course_enrollments
    """)
    enrollments = cursor.fetchall()

    synced = 0
    skipped = 0
    for enroll_id, student_id, course_code, enrolled_date, status in enrollments:
        try:
            supabase.table("course_enrollments").upsert({
                "enrollment_id": enroll_id,
                "student_id": student_id,
                "course_code": course_code,
                "enrolled_date": enrolled_date,
                "status": status
            }).execute()
            synced += 1
            if synced % 20 == 0:
                print(f"  Synced {synced}/{len(enrollments)} enrollments...")
        except Exception as e:
            print(f"  ✗ Enrollment {enroll_id}: {e}")
            skipped += 1

    print(f"✅ Enrollments: {synced}/{len(enrollments)} synced (skipped: {skipped})")


def sync_attendance(supabase: Client, cursor, conn, batch_size=50):
    """Sync attendance records incrementally using upsert to prevent duplicates."""
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

        # Collect IDs that succeed so we mark them all at once per batch
        successful_ids = []

        for record in batch:
            att_id, course_code, student_id, student_name, authorized_by, timestamp, session_date = record
            try:
                # Use upsert with attendance_id as PK to prevent duplicates on re-run
                supabase.table("attendance").upsert({
                    "attendance_id": att_id,
                    "course_code": course_code,
                    "student_id": student_id,
                    "authorized_by": authorized_by,
                    "session_date": session_date,
                    "recorded_at": timestamp
                }).execute()

                successful_ids.append(att_id)
                synced_count += 1

                if synced_count % 10 == 0:
                    print(f"  ✓ Synced {synced_count}/{total_unsynced}...")

            except Exception as e:
                print(f"  ✗ Attendance {att_id} failed: {e}")
                failed_count += 1

        # Bulk mark successful records as synced
        if successful_ids:
            placeholders = ",".join("?" * len(successful_ids))
            cursor.execute(f"""
                UPDATE attendance
                SET synced = 1
                WHERE attendance_id IN ({placeholders})
            """, successful_ids)
            conn.commit()

        # Avoid hitting Supabase rate limits
        time.sleep(0.1)

    print(f"✅ Attendance: {synced_count} synced, {failed_count} failed")


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def full_sync():
    """Sync all tables: reference → master → transactional."""
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        print("✅ Connected to local database")
    except Exception as e:
        print(f"❌ Local database connection failed: {e}")
        return

    try:
        # 1. Reference tables (no FK dependencies)
        sync_departments(supabase, cursor)
        sync_programs(supabase, cursor)

        # 2. Master tables (FK → departments, programs)
        sync_professors(supabase, cursor)
        sync_students(supabase, cursor)

        # 3. Courses (FK → profs, departments)
        sync_courses(supabase, cursor)

        # 4. Transactional tables (FK → students, courses)
        sync_enrollments(supabase, cursor)
        sync_attendance(supabase, cursor, conn)

        print_header("SYNC COMPLETE")

        # Final stats
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 1")
        total_synced = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        total_pending = cursor.fetchone()[0]

        print(f"\n📊 Attendance records synced : {total_synced}")
        print(f"   Attendance records pending : {total_pending}")

    except Exception as e:
        print(f"\n❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        print("\n💾 Local database connection closed")


def attendance_only_sync():
    """Quick sync — attendance records only."""
    print_header("ATTENDANCE QUICK SYNC")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        conn = sqlite3.connect(DB_PATH)
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
