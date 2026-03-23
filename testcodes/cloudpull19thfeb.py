#!/usr/bin/env python3
"""
IITDH Attendance System - Cloud Pull Script
Pulls reference and master data from Supabase cloud DB into local SQLite.
Run this BEFORE taking attendance to ensure local DB is up to date.

Tables pulled (cloud → local):
  departments, programs, profs, students, courses, course_enrollments

Tables NOT pulled (local only, pushed to cloud after attendance):
  attendance  (generated locally, pushed via cloud_sync.py)

Usage:
  python cloud_pull.py               # full pull
  python cloud_pull.py --students    # students + enrollments only (quick refresh)
"""

import sqlite3
import os
import sys
from supabase import create_client, Client
import time

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://peagkvkhhsbdytevnhia.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_secret_Q0zxaI4Myb6lY0IWZKgjLw_pXGH5zXj")

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

PAGE_SIZE = 1000  # Supabase max rows per request


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def supabase_to_bytes(template_data):
    """
    Convert Supabase template data back to raw bytes for local SQLite.

    Supabase returns bytea columns in different formats depending on
    how the data was inserted:

      Format 1 — List of ints : [72, 101, 108, ...]
                                 (stored via REST API as JSON array)

      Format 2 — Hex string   : "\\xDEADBEEF"
                                 (native Supabase/Postgres bytea format)

      Format 3 — Plain hex    : "DEADBEEF"
                                 (hex without prefix)

    All three formats are handled here.
    """
    if template_data is None:
        return None

    # Format 1: list of ints [72, 101, 108 ...]
    if isinstance(template_data, list):
        if len(template_data) > 0:
            return bytes(template_data)
        return None

    # Format 2: Supabase hex string "\\x0102abcd..." or "0x..."
    if isinstance(template_data, str):
        if template_data.startswith("\\x") or template_data.startswith("0x"):
            try:
                return bytes.fromhex(template_data[2:])
            except ValueError:
                print(f"    ⚠️  Could not decode hex template: {template_data[:30]}...")
                return None

        # Format 3: plain hex string without prefix
        if len(template_data) > 0:
            try:
                return bytes.fromhex(template_data)
            except ValueError:
                print(f"    ⚠️  Unknown template format: {template_data[:30]}...")
                return None

    return None


def flush_wal(conn, cursor):
    """
    Force WAL checkpoint — merges the WAL file into the main .db file.
    Required so DB Browser for SQLite and other external tools can see
    data that was written during this session.
    """
    try:
        cursor.execute("PRAGMA wal_checkpoint(FULL)")
        conn.commit()
        print("\n✅ WAL checkpoint complete — data flushed to main DB file")
        print("   DB Browser: press Ctrl+R (File → Revert) to refresh the view")
    except Exception as e:
        print(f"\n⚠️  WAL checkpoint failed (data still saved): {e}")


def fetch_all_pages(supabase: Client, table: str, columns: str = "*") -> list:
    """
    Fetch all rows from a Supabase table using pagination.
    Supabase returns max 1000 rows per request by default.
    """
    all_rows = []
    offset = 0

    while True:
        try:
            response = (
                supabase.table(table)
                .select(columns)
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            batch = response.data
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
            time.sleep(0.05)
        except Exception as e:
            print(f"  ✗ Error fetching {table} at offset {offset}: {e}")
            break

    return all_rows


# ─────────────────────────────────────────────
# PULL FUNCTIONS
# ─────────────────────────────────────────────

def pull_departments(supabase: Client, cursor, conn):
    print("\n📋 Pulling Departments...")
    rows = fetch_all_pages(supabase, "departments")

    if not rows:
        print("  ⚠️  No departments found in cloud")
        return

    cursor.executemany("""
        INSERT INTO Departments (dept_code, dept_name)
        VALUES (:dept_code, :dept_name)
        ON CONFLICT(dept_code) DO UPDATE SET
            dept_name = excluded.dept_name
    """, rows)
    conn.commit()
    print(f"✅ Departments: {len(rows)} pulled")


def pull_programs(supabase: Client, cursor, conn):
    print("\n📋 Pulling Programs...")
    rows = fetch_all_pages(supabase, "programs")

    if not rows:
        print("  ⚠️  No programs found in cloud")
        return

    cursor.executemany("""
        INSERT INTO Programs (program_code, program_name)
        VALUES (:program_code, :program_name)
        ON CONFLICT(program_code) DO UPDATE SET
            program_name = excluded.program_name
    """, rows)
    conn.commit()
    print(f"✅ Programs: {len(rows)} pulled")


def pull_professors(supabase: Client, cursor, conn):
    """
    Sync professors from cloud → local.

    Template priority:
      1. Cloud has template        → use cloud value
      2. Cloud has no template
         + row exists locally      → keep existing local template
      3. Cloud has no template
         + brand new row           → use b"" placeholder
    """
    print("\n👨‍🏫 Pulling Professors...")
    rows = fetch_all_pages(supabase, "profs")

    if not rows:
        print("  ⚠️  No professors found in cloud")
        return

    upserted = 0
    for row in rows:
        try:
            cloud_template = supabase_to_bytes(row.get("template"))

            if cloud_template is not None:
                template_bytes = cloud_template
                t_source = f"cloud ({len(cloud_template)} bytes)"
            else:
                cursor.execute(
                    "SELECT template FROM profs WHERE prof_id = ?", (row["prof_id"],)
                )
                existing = cursor.fetchone()
                if existing and existing[0]:
                    template_bytes = existing[0]
                    t_source = "kept local"
                else:
                    template_bytes = b""
                    t_source = "placeholder (not enrolled)"

            cursor.execute("""
                INSERT INTO profs (prof_id, name, dept_code, email, template, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(prof_id) DO UPDATE SET
                    name       = excluded.name,
                    dept_code  = excluded.dept_code,
                    email      = excluded.email,
                    template   = COALESCE(excluded.template, profs.template),
                    created_at = excluded.created_at
            """, (
                row["prof_id"],
                row["name"],
                row["dept_code"],
                row.get("email"),
                template_bytes,
                row.get("created_at")
            ))
            upserted += 1
            print(f"  ✓ {row['prof_id']}: {row['name']} | template: {t_source}")
        except Exception as e:
            print(f"  ✗ Prof {row.get('prof_id')}: {e}")

    conn.commit()
    print(f"✅ Professors: {upserted}/{len(rows)} pulled")


def pull_students(supabase: Client, cursor, conn):
    """
    Sync students from cloud → local.

    Column mapping:
      cloud password_hash → local password
      cloud template      → local template

    Priority for each:
      1. Cloud value exists        → use it
      2. Cloud null + row exists   → keep local value
      3. Cloud null + new row      → use placeholder
    """
    print("\n👨‍🎓 Pulling Students...")
    rows = fetch_all_pages(supabase, "students")

    if not rows:
        print("  ⚠️  No students found in cloud")
        return

    upserted = 0
    no_template = 0
    no_password = 0

    for row in rows:
        try:
            # Fetch existing local values once (used as fallback for both fields)
            cursor.execute(
                "SELECT password, template FROM students WHERE student_id = ?",
                (row["student_id"],)
            )
            existing = cursor.fetchone()

            # ── Template ────────────────────────────────────────────────
            cloud_template = supabase_to_bytes(row.get("template"))

            if cloud_template is not None:
                template_bytes = cloud_template
                t_source = f"cloud ({len(cloud_template)} bytes)"
            elif existing and existing[1]:
                template_bytes = existing[1]
                t_source = "kept local"
                no_template += 1
            else:
                template_bytes = b""
                t_source = "placeholder (not enrolled)"
                no_template += 1

            # ── Password ─────────────────────────────────────────────────
            # Cloud column is `password_hash`; local column is `password`
            cloud_password = row.get("password_hash") or row.get("password")

            if cloud_password:
                local_password = cloud_password
                p_source = "cloud"
            elif existing and existing[0] and existing[0] != "PENDING_ENROLLMENT":
                local_password = existing[0]
                p_source = "kept local"
                no_password += 1
            else:
                local_password = "PENDING_ENROLLMENT"
                p_source = "placeholder"
                no_password += 1

            cursor.execute("""
                INSERT INTO students
                    (student_id, first_name, last_name, dept, year, program,
                     email, password, template, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name  = excluded.last_name,
                    dept       = excluded.dept,
                    year       = excluded.year,
                    program    = excluded.program,
                    email      = excluded.email,
                    password   = excluded.password,
                    template   = COALESCE(excluded.template, students.template),
                    created_at = excluded.created_at
            """, (
                row["student_id"],
                row["first_name"],
                row["last_name"],
                row["dept"],
                row["year"],
                row["program"],
                row.get("email"),
                local_password,
                template_bytes,
                row.get("created_at")
            ))
            upserted += 1
            print(f"  ✓ {row['student_id']}: {row['first_name']} {row['last_name']} "
                  f"| pwd: {p_source} | template: {t_source}")

        except Exception as e:
            print(f"  ✗ Student {row.get('student_id')}: {e}")

    conn.commit()
    print(f"✅ Students: {upserted}/{len(rows)} pulled "
          f"({no_template} without template, {no_password} without password in cloud)")


def pull_courses(supabase: Client, cursor, conn):
    print("\n📚 Pulling Courses...")
    rows = fetch_all_pages(supabase, "courses")

    if not rows:
        print("  ⚠️  No courses found in cloud")
        return

    cursor.executemany("""
        INSERT INTO courses
            (course_code, course_name, prof_id, dept_code, semester, year, time_slot, created_at)
        VALUES
            (:course_code, :course_name, :prof_id, :dept_code, :semester, :year, :time_slot, :created_at)
        ON CONFLICT(course_code) DO UPDATE SET
            course_name = excluded.course_name,
            prof_id     = excluded.prof_id,
            dept_code   = excluded.dept_code,
            semester    = excluded.semester,
            year        = excluded.year,
            time_slot   = excluded.time_slot,
            created_at  = excluded.created_at
    """, rows)
    conn.commit()
    print(f"✅ Courses: {len(rows)} pulled")


def pull_enrollments(supabase: Client, cursor, conn):
    print("\n📝 Pulling Course Enrollments...")
    rows = fetch_all_pages(supabase, "course_enrollments")

    if not rows:
        print("  ⚠️  No enrollments found in cloud")
        return

    cursor.executemany("""
        INSERT INTO course_enrollments
            (enrollment_id, student_id, course_code, enrolled_date, status)
        VALUES
            (:enrollment_id, :student_id, :course_code, :enrolled_date, :status)
        ON CONFLICT(enrollment_id) DO UPDATE SET
            student_id    = excluded.student_id,
            course_code   = excluded.course_code,
            enrolled_date = excluded.enrolled_date,
            status        = excluded.status
    """, rows)
    conn.commit()
    print(f"✅ Enrollments: {len(rows)} pulled")


# ─────────────────────────────────────────────
# VERIFICATION
# ─────────────────────────────────────────────

def verify_local_db(cursor):
    """Print row counts and data health for all local tables after pull."""
    print("\n📊 Local DB State After Pull:")

    tables = [
        ("Departments",        "Departments"),
        ("Programs",           "Programs"),
        ("Professors",         "profs"),
        ("Students",           "students"),
        ("Courses",            "courses"),
        ("Enrollments",        "course_enrollments"),
        ("Attendance (local)", "attendance"),
    ]

    for label, table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {label:<25} {count:>6} rows")
        except Exception as e:
            print(f"  {label:<25} ERROR: {e}")

    # Template health
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM students WHERE template IS NOT NULL AND template != x''"
        )
        wt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM students")
        total = cursor.fetchone()[0]
        print(f"\n  Students with fingerprint  : {wt}/{total}")
    except Exception:
        pass

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM profs WHERE template IS NOT NULL AND template != x''"
        )
        wt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM profs")
        total = cursor.fetchone()[0]
        print(f"  Profs with fingerprint     : {wt}/{total}")
    except Exception:
        pass

    # Password health
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM students
            WHERE password IS NOT NULL
              AND password != ''
              AND password != 'PENDING_ENROLLMENT'
        """)
        wp = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM students")
        total = cursor.fetchone()[0]
        print(f"  Students with password     : {wp}/{total}")
    except Exception:
        pass

    # Pending attendance sync
    try:
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        pending = cursor.fetchone()[0]
        print(f"  Attendance pending sync    : {pending}")
        if pending > 0:
            print("  ⚠️  Run cloud_sync.py to push pending attendance records!")
    except Exception:
        pass


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def full_pull():
    """Pull all reference and master data from cloud to local."""
    print_header("IITDH ATTENDANCE SYSTEM - CLOUD PULL (Full)")

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
        # Order matters: pull parent tables before child tables
        pull_departments(supabase, cursor, conn)
        pull_programs(supabase, cursor, conn)
        pull_professors(supabase, cursor, conn)
        pull_students(supabase, cursor, conn)
        pull_courses(supabase, cursor, conn)
        pull_enrollments(supabase, cursor, conn)

        verify_local_db(cursor)

        print_header("PULL COMPLETE")
        print("\n✅ Local DB is up to date. Ready for attendance.")

    except Exception as e:
        print(f"\n❌ Pull error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        flush_wal(conn, cursor)   # ← merge WAL into .db so DB Browser sees the data
        conn.close()
        print("💾 Local database connection closed")


def students_only_pull():
    """Quick pull — refresh students and enrollments only."""
    print_header("QUICK PULL: Students & Enrollments")

    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()

        pull_students(supabase, cursor, conn)
        pull_enrollments(supabase, cursor, conn)

        flush_wal(conn, cursor)   # ← merge WAL into .db so DB Browser sees the data
        conn.close()
        print("\n✅ Students and enrollments refreshed")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--students":
        students_only_pull()
    else:
        full_pull()
        