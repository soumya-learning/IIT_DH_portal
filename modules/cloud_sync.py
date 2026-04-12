"""
modules/cloud_sync.py
IITDH Attendance System — Cloud Sync (Local → Cloud)

Overwrite policy:
  departments        → upsert  (safe reference data)
  programs           → upsert  (safe reference data)
  profs              → INSERT only  (ignore_duplicates=True)
  students           → INSERT only  (ignore_duplicates=True)
  courses            → upsert
  course_enrollments → upsert
  attendance         → upsert on attendance_id (PK) only
                       multiple scans per student/course/day all kept

Called from main menu via run_full_sync() or run_attendance_sync().
All detailed output goes to terminal; OLED shows brief status.
"""

import sqlite3
import os
import time
import modules.hardware as hw
from modules.config import DB_PATH, SUPABASE_URL, SUPABASE_KEY, DEPT_NAME_TO_CODE, PROG_NAME_TO_CODE

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

# When True, all _oled() calls are suppressed (background sync mode).
# Set via run_attendance_sync(silent=True) — never touch directly.
_silent = False

def _oled(line1, line2="", line3=""):
    if not _silent:
        hw.display_msg(line1, line2, line3)


def _connect_supabase():
    if not SUPABASE_AVAILABLE:
        print("❌ supabase-py not installed. Run: pip install supabase")
        _oled("SYNC FAILED", "supabase not", "installed")
        return None
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return client
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        _oled("CONN FAILED", "Check network", str(e)[:16])
        return None


def _connect_local():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except Exception as e:
        print(f"❌ Local DB connection failed: {e}")
        _oled("DB ERROR", "Local DB locked", str(e)[:16])
        return None


def template_to_hex(template_bytes):
    if template_bytes is None:
        return None
    if isinstance(template_bytes, (bytes, bytearray, sqlite3.Binary)):
        b = bytes(template_bytes)
        if len(b) > 0:
            return b.hex()
    return None


def template_label(template):
    if template and len(bytes(template)) > 0:
        return f"✓ ({len(bytes(template))} bytes)"
    return "✗ no template"


# ─────────────────────────────────────────────
# SYNC FUNCTIONS
# ─────────────────────────────────────────────

def sync_departments(supabase, cursor):
    print("\n📋 Syncing Departments...")
    _oled("SYNCING", "Departments", "")
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


def sync_programs(supabase, cursor):
    print("\n📋 Syncing Programs...")
    _oled("SYNCING", "Programs", "")
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


def sync_professors(supabase, cursor):
    print("\n👨‍🏫 Syncing Professors...")
    _oled("SYNCING", "Professors", "")
    cursor.execute("""
        SELECT prof_id, name, dept_code, email, template, created_at
        FROM profs
    """)
    rows = cursor.fetchall()
    synced = 0
    skipped = 0
    for prof_id, name, dept_code, email, template, created_at in rows:
        try:
            supabase.table("profs").upsert(
                {
                    "prof_id":    prof_id,
                    "name":       name,
                    "dept_code":  dept_code,
                    "email":      email,
                    "template":   template_to_hex(template),
                    "created_at": created_at
                },
                ignore_duplicates=True
            ).execute()
            synced += 1
            print(f"  ✓ {prof_id}: {name} | {template_label(template)}")
        except Exception as e:
            print(f"  ✗ {prof_id}: {e}")
            skipped += 1
    print(f"✅ Professors: {synced}/{len(rows)} synced (skipped: {skipped})")


def sync_students(supabase, cursor):
    print("\n👨‍🎓 Syncing Students...")
    _oled("SYNCING", "Students", "Please wait...")
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
            supabase.table("students").upsert(
                {
                    "student_id":    student_id,
                    "first_name":    first_name,
                    "last_name":     last_name,
                    "dept":          dept_code,
                    "year":          year,
                    "program":       prog_code,
                    "email":         email,
                    "password_hash": password,
                    "template":      template_to_hex(template),
                    "created_at":    created_at
                },
                ignore_duplicates=True
            ).execute()
            synced += 1
            if synced % 20 == 0:
                print(f"  ... {synced}/{len(rows)} synced")
                _oled("SYNCING", "Students", f"{synced}/{len(rows)}")
            else:
                print(f"  ✓ {student_id}: {first_name} {last_name} "
                      f"({dept_code}/{prog_code}) | {template_label(template)}")
        except Exception as e:
            print(f"  ✗ {student_id}: {e}")
            skipped += 1
    print(f"✅ Students: {synced}/{len(rows)} synced (skipped: {skipped})")


def sync_courses(supabase, cursor):
    print("\n📚 Syncing Courses...")
    _oled("SYNCING", "Courses", "")
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


def sync_enrollments(supabase, cursor):
    print("\n📝 Syncing Enrollments...")
    _oled("SYNCING", "Enrollments", "")
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


def sync_attendance(supabase, cursor, conn):
    """
    Push unsynced attendance to cloud.
    Upserts on attendance_id (PK) only — multiple records per
    student/course/day are all kept as separate rows.
    Failed records marked synced=-1 to prevent infinite retry.
    """
    print("\n📊 Syncing Attendance Records...")
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
    total_unsynced = cursor.fetchone()[0]

    if total_unsynced == 0:
        print("☁️  All attendance records already synced!")
        _oled("ATTENDANCE", "Already synced", "Nothing to do")
        if not _silent:
            time.sleep(1)
        return

    print(f"📤 Found {total_unsynced} unsynced records")
    _oled("SYNCING", "Attendance", f"{total_unsynced} records")

    cursor.execute("""
        SELECT attendance_id, course_code, student_id, student_name,
               authorized_by, timestamp, session_date
        FROM attendance
        WHERE synced = 0
        ORDER BY attendance_id
    """)
    all_records = cursor.fetchall()

    synced_count  = 0
    failed_count  = 0
    already_count = 0

    for att_id, course_code, student_id, student_name, \
            authorized_by, timestamp, session_date in all_records:
        try:
            supabase.table("attendance").upsert(
                {
                    "attendance_id": att_id,
                    "course_code":   course_code,
                    "student_id":    student_id,
                    "authorized_by": authorized_by,
                    "session_date":  session_date,
                    "recorded_at":   timestamp
                },
                on_conflict="attendance_id"
            ).execute()
            cursor.execute(
                "UPDATE attendance SET synced = 1 WHERE attendance_id = ?",
                (att_id,)
            )
            conn.commit()
            synced_count += 1
            print(f"  ✓ {att_id}: {student_id} | {course_code} | {session_date}")

        except Exception as e:
            err_str = str(e)
            if "duplicate key" in err_str and f'"{att_id}"' in err_str:
                cursor.execute(
                    "UPDATE attendance SET synced = 1 WHERE attendance_id = ?",
                    (att_id,)
                )
                conn.commit()
                already_count += 1
                print(f"  ~ {att_id}: already in cloud (marked synced)")
            else:
                print(f"  ✗ Attendance {att_id}: {e}")
                cursor.execute(
                    "UPDATE attendance SET synced = -1 WHERE attendance_id = ?",
                    (att_id,)
                )
                conn.commit()
                failed_count += 1

        time.sleep(0.05)

    print(f"\n✅ Attendance: {synced_count} synced, "
          f"{already_count} already existed, {failed_count} failed")

    if failed_count > 0:
        print(f"   ⚠️  {failed_count} records in error state (synced=-1)")
        print(f"   To retry: UPDATE attendance SET synced=0 WHERE synced=-1;")

    _oled("ATTENDANCE DONE",
          f"OK:{synced_count} Err:{failed_count}",
          f"Dup:{already_count}")
    if not _silent:
        time.sleep(2)


# ─────────────────────────────────────────────
# PUBLIC ENTRY POINTS — called from main menu
# ─────────────────────────────────────────────

def run_full_sync():
    """Full sync: all tables. Called from main menu."""
    print("\n" + "=" * 70)
    print("  IITDH ATTENDANCE SYSTEM - FULL CLOUD SYNC")
    print("=" * 70)

    _oled("CLOUD SYNC", "Connecting...", "")

    supabase = _connect_supabase()
    if not supabase:
        time.sleep(3)
        return

    conn = _connect_local()
    if not conn:
        time.sleep(3)
        return

    cursor = conn.cursor()
    _oled("CLOUD SYNC", "Connected", "Starting...")
    time.sleep(0.5)

    try:
        sync_departments(supabase, cursor)
        sync_programs(supabase, cursor)
        sync_professors(supabase, cursor)
        sync_students(supabase, cursor)
        sync_courses(supabase, cursor)
        sync_enrollments(supabase, cursor)
        sync_attendance(supabase, cursor, conn)

        # Summary
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 1")
        ok = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = -1")
        errors = cursor.fetchone()[0]

        print("\n" + "=" * 70)
        print("  SYNC COMPLETE")
        print("=" * 70)
        print(f"\n  Attendance synced  : {ok}")
        print(f"  Attendance pending : {pending}")
        print(f"  Attendance errors  : {errors}")

        _oled("SYNC COMPLETE",
              f"Att OK: {ok}",
              f"Err:{errors} Pend:{pending}")
        time.sleep(3)

    except Exception as e:
        print(f"\n❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
        _oled("SYNC ERROR", str(e)[:20], "Check terminal")
        time.sleep(3)
    finally:
        conn.close()
        print("💾 Local database connection closed")


def run_attendance_sync(silent=False):
    """
    Attendance-only quick sync.
    silent=True  → no OLED writes, no time.sleep() pauses (background use).
    silent=False → full OLED feedback (manual/menu use).
    """
    global _silent
    _silent = silent

    print("\n" + "=" * 70)
    print("  ATTENDANCE QUICK SYNC" + (" [silent]" if silent else ""))
    print("=" * 70)

    _oled("ATT SYNC", "Connecting...", "")

    supabase = _connect_supabase()
    if not supabase:
        if not silent:
            time.sleep(3)
        return

    conn = _connect_local()
    if not conn:
        if not silent:
            time.sleep(3)
        return

    cursor = conn.cursor()
    try:
        sync_attendance(supabase, cursor, conn)
    except Exception as e:
        print(f"❌ Error: {e}")
        _oled("SYNC ERROR", str(e)[:20], "")
        if not silent:
            time.sleep(3)
    finally:
        _silent = False   # always restore
        conn.close()