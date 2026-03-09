#!/usr/bin/env python3
"""
IITDH Attendance System - Cloud Pull (Cloud → Local)

Fingerprint template decoding:
  Supabase returns : "\\x0303591d..."  (hex string with \\x prefix)
      ↓  strip \\x, bytes.fromhex()
  Raw bytes        : b'\\x03\\x03Y\\x1d...'  (768 bytes)
      ↓  sqlite3.Binary()
  SQLite BLOB      : stored as BLOB type (shows as BLOB in DB Browser)

Source of truth per column:
  template  → LOCAL  (enrolled on Pi — NEVER overwrite if local has data)
  password  → CLOUD  (set via web — cloud password_hash wins)
  all other → CLOUD

Also runs a one-time template migration at startup:
  fixes any legacy-encoded fingerprint BLOBs (JSON array or hex-of-JSON)
  already stored in the local DB.

Usage:
  python cloud_pull.py               # full pull (includes template migration)
  python cloud_pull.py --students    # students + enrollments only
"""

import sqlite3
import json
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

PAGE_SIZE = 1000


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def supabase_to_bytes(value):
    """
    Decode a Supabase bytea value to raw Python bytes.

    Supabase REST API returns bytea columns as a hex string with \\x prefix:
        "\\x0303591d0c013b017900..."

    Decode chain:
        "\\x0303591d..."
            ↓  strip first 2 chars ("\\x"), bytes.fromhex()
        b'\\x03\\x03Y\\x1d...'   ← raw fingerprint bytes

    Also handles legacy formats from before this fix:
        - Plain hex without prefix: "0303591d..."
        - List of ints: [3, 3, 89, 29, ...]  (old JSON array format)

    Always returns bytes or None. Never returns a string.
    """
    if value is None:
        return None

    # Already raw bytes — no decoding needed
    if isinstance(value, (bytes, bytearray, sqlite3.Binary)):
        b = bytes(value)
        return b if len(b) > 0 else None

    # List of ints [3, 3, 89, ...] — old format, still handle gracefully
    if isinstance(value, list):
        return bytes(value) if value else None

    if isinstance(value, str) and value:

        # PRIMARY FORMAT: Supabase hex string "\\x0303591d..."
        if value.startswith("\\x") or value.startswith("0x"):
            try:
                result = bytes.fromhex(value[2:])
                if len(result) > 0:
                    return result
            except ValueError:
                pass

        # FALLBACK: plain hex without prefix "0303591d..."
        try:
            result = bytes.fromhex(value)
            if len(result) > 0:
                return result
        except ValueError:
            pass

        print(f"    ⚠️  Could not decode template value: {value[:40]!r}")

    return None


def to_blob(raw_bytes):
    """
    Wrap raw bytes in sqlite3.Binary() to guarantee BLOB type in SQLite.

    This is CRITICAL — without sqlite3.Binary(), Python's sqlite3 module
    may store bytes as TEXT, which shows as a hex string in DB Browser
    instead of 'BLOB'.

    Returns sqlite3.Binary wrapping the raw bytes, or empty Binary for None.
    """
    if isinstance(raw_bytes, (bytes, bytearray)) and len(raw_bytes) > 0:
        return sqlite3.Binary(bytes(raw_bytes))
    return sqlite3.Binary(b"")


def is_real_blob(value):
    """True if value is non-empty bytes/Binary — i.e. a real enrolled fingerprint."""
    if isinstance(value, (bytes, bytearray, sqlite3.Binary)):
        return len(bytes(value)) > 0
    return False


def flush_wal(conn, cursor):
    """Merge WAL into main .db so DB Browser sees all written data."""
    try:
        cursor.execute("PRAGMA wal_checkpoint(FULL)")
        conn.commit()
        print("\n✅ WAL checkpoint — data visible in DB Browser")
        print("   Press Ctrl+R (File → Revert) in DB Browser to refresh")
    except Exception as e:
        print(f"\n⚠️  WAL checkpoint failed (data still saved): {e}")


def fetch_all_pages(supabase: Client, table: str, columns: str = "*") -> list:
    """Paginate through all rows (Supabase max 1000 per request)."""
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
# TEMPLATE MIGRATION
# ─────────────────────────────────────────────

def decode_template(raw):
    """
    Unwrap any legacy encoding layer and return clean raw fingerprint bytes.

    Handles all historical formats stored in local SQLite:
      Case 1: JSON text   "[3,3,92,...]"       → bytes([3,3,92,...])
      Case 2: hex-of-JSON "5b332c..."           → decode hex → parse JSON → bytes
      Case 3: plain hex   "0303591d..."         → bytes.fromhex()
      Case 4: already raw binary b'\x03\x03...' → returned as-is

    Returns raw bytes or None.
    """
    if raw is None:
        return None
    b = bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode()
    try:
        text = b.decode("utf-8")
        # Case 1: JSON array text "[3,3,92,...]"
        if text.startswith("["):
            lst = json.loads(text)
            if isinstance(lst, list):
                return bytes(lst)
        # Case 2: hex of JSON text "5b332c..."
        if text.startswith("5b"):
            try:
                inner = bytes.fromhex(text).decode("utf-8")
                lst = json.loads(inner)
                if isinstance(lst, list):
                    return bytes(lst)
            except (ValueError, UnicodeDecodeError):
                pass
        # Case 3: plain hex string "0303591d..."
        try:
            return bytes.fromhex(text)
        except ValueError:
            pass
    except UnicodeDecodeError:
        # Case 4: already raw binary — no conversion needed
        return b
    return b


def migrate_templates(cursor, conn):
    """
    One-time migration: fix any legacy-encoded templates in local DB.

    Runs automatically at the start of every pull.
    If templates are already correct raw bytes — this is a no-op (safe to run repeatedly).
    """
    print("\n🔧 Checking & migrating fingerprint templates...")
    fixed_count = 0
    already_ok  = 0
    empty_count = 0

    for table, id_col in [("students", "student_id"), ("profs", "prof_id")]:
        cursor.execute(f"SELECT {id_col}, template FROM {table}")
        rows = cursor.fetchall()
        for row_id, template in rows:
            if template is None or len(bytes(template)) == 0:
                empty_count += 1
                continue

            raw = bytes(template)

            # Quick check: if first byte is 0x03 it's already correct raw fingerprint
            if raw[0] == 0x03:
                already_ok += 1
                continue

            fixed = decode_template(template)

            if fixed and fixed != raw:
                cursor.execute(
                    f"UPDATE {table} SET template = ? WHERE {id_col} = ?",
                    (sqlite3.Binary(fixed), row_id)
                )
                fixed_count += 1
                print(f"  ✓ Fixed {table}.{row_id}: {len(raw)}B legacy → {len(fixed)}B raw bytes")
            else:
                already_ok += 1

    if fixed_count > 0:
        conn.commit()
        print(f"  ✅ Migrated {fixed_count} templates to raw bytes")
    else:
        print(f"  ✅ All {already_ok} templates already correct — no migration needed")

    if empty_count > 0:
        print(f"  ℹ️  {empty_count} empty templates (students/profs not yet enrolled)")


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
    Pull professors. Template rule:
      - Local has real BLOB  → keep it, never overwrite (Pi is source of truth)
      - Local is empty       → use cloud value decoded to raw bytes
      - Both empty           → store empty BLOB placeholder

    Template is fully resolved in Python before any SQL runs.
    No COALESCE in SQL — that strips the sqlite3.Binary type hint.
    """
    print("\n👨‍🏫 Pulling Professors...")
    rows = fetch_all_pages(supabase, "profs")
    if not rows:
        print("  ⚠️  No professors found in cloud")
        return

    upserted = 0
    for row in rows:
        try:
            # Read existing local template first
            cursor.execute(
                "SELECT template FROM profs WHERE prof_id = ?", (row["prof_id"],)
            )
            existing = cursor.fetchone()
            local_template = existing[0] if existing else None

            # Resolve template entirely in Python
            if is_real_blob(local_template):
                final_template = to_blob(local_template)
                t_src = f"kept local ({len(bytes(local_template))} bytes) ← protected"
            else:
                cloud_raw = supabase_to_bytes(row.get("template"))
                if cloud_raw:
                    final_template = to_blob(cloud_raw)
                    t_src = f"cloud ({len(cloud_raw)} bytes)"
                else:
                    final_template = to_blob(b"")
                    t_src = "placeholder (not enrolled)"

            cursor.execute("""
                INSERT INTO profs (prof_id, name, dept_code, email, template, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(prof_id) DO UPDATE SET
                    name       = excluded.name,
                    dept_code  = excluded.dept_code,
                    email      = excluded.email,
                    template   = excluded.template,
                    created_at = excluded.created_at
            """, (
                row["prof_id"],
                row["name"],
                row["dept_code"],
                row.get("email"),
                final_template,         # always sqlite3.Binary → BLOB
                row.get("created_at")
            ))
            upserted += 1
            print(f"  ✓ {row['prof_id']}: {row['name']} | {t_src}")
        except Exception as e:
            print(f"  ✗ Prof {row.get('prof_id')}: {e}")

    conn.commit()
    print(f"✅ Professors: {upserted}/{len(rows)} pulled")


def pull_students(supabase: Client, cursor, conn):
    """
    Pull students.

    Template  → local is source of truth (Pi enrolled fingerprints)
    Password  → cloud is source of truth (set via web app)

    Both resolved in Python before SQL — no COALESCE for templates.
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
            # Fetch existing local values
            cursor.execute(
                "SELECT password, template FROM students WHERE student_id = ?",
                (row["student_id"],)
            )
            existing = cursor.fetchone()
            local_password = existing[0] if existing else None
            local_template = existing[1] if existing else None

            # ── Template (local wins if present) ──────────────────────────
            if is_real_blob(local_template):
                final_template = to_blob(local_template)
                t_src = f"kept local ({len(bytes(local_template))} bytes) ← protected"
            else:
                cloud_raw = supabase_to_bytes(row.get("template"))
                if cloud_raw:
                    final_template = to_blob(cloud_raw)
                    t_src = f"cloud ({len(cloud_raw)} bytes)"
                else:
                    final_template = to_blob(b"")
                    t_src = "placeholder (not enrolled)"
                    no_template += 1

            # ── Password (cloud wins) ──────────────────────────────────────
            # Cloud column is `password_hash`, maps to local `password`
            cloud_pw = row.get("password_hash") or row.get("password")
            if cloud_pw:
                final_password = cloud_pw
                p_src = "cloud"
            elif local_password and local_password != "PENDING_ENROLLMENT":
                final_password = local_password
                p_src = "kept local"
                no_password += 1
            else:
                final_password = "PENDING_ENROLLMENT"
                p_src = "placeholder"
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
                    template   = excluded.template,
                    created_at = excluded.created_at
            """, (
                row["student_id"],
                row["first_name"],
                row["last_name"],
                row["dept"],
                row["year"],
                row["program"],
                row.get("email"),
                final_password,
                final_template,         # always sqlite3.Binary → BLOB
                row.get("created_at")
            ))
            upserted += 1
            print(f"  ✓ {row['student_id']}: {row['first_name']} {row['last_name']} "
                  f"| pwd: {p_src} | template: {t_src}")

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
    print("\n📝 Pulling Enrollments...")
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
    print("\n📊 Local DB State After Pull:")

    for label, table in [
        ("Departments",        "Departments"),
        ("Programs",           "Programs"),
        ("Professors",         "profs"),
        ("Students",           "students"),
        ("Courses",            "courses"),
        ("Enrollments",        "course_enrollments"),
        ("Attendance (local)", "attendance"),
    ]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {label:<25} {cursor.fetchone()[0]:>6} rows")
        except Exception as e:
            print(f"  {label:<25} ERROR: {e}")

    # Per-row template type diagnostic
    print("\n  Template storage (must show 'blob'):")
    for table, id_col in [("students", "student_id"), ("profs", "prof_id")]:
        try:
            cursor.execute(
                f"SELECT {id_col}, typeof(template), length(template) FROM {table}"
            )
            for row_id, ttype, tlen in cursor.fetchall():
                status = "✓ blob" if ttype == "blob" else f"✗ {ttype} ← WRONG"
                print(f"    {table}.{row_id:<20} {status} ({tlen or 0} bytes)")
        except Exception as e:
            print(f"    {table}: ERROR {e}")

    # Password check
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM students
            WHERE password IS NOT NULL AND password != '' AND password != 'PENDING_ENROLLMENT'
        """)
        wp = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM students")
        total = cursor.fetchone()[0]
        print(f"\n  Students with password     : {wp}/{total}")
    except Exception:
        pass

    # Pending attendance
    try:
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        pending = cursor.fetchone()[0]
        print(f"  Attendance pending sync    : {pending}")
        if pending > 0:
            print("  ⚠️  Run cloud_sync.py to push pending attendance!")
    except Exception:
        pass


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def full_pull():
    print_header("IITDH ATTENDANCE SYSTEM - CLOUD PULL (Full)")

    print("\n🔌 Connecting to Supabase...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return

    print("\n💾 Connecting to local database...")
    conn = None
    try:
        # timeout=60 → wait up to 60s for any lock to clear before failing
        conn = sqlite3.connect(DB_PATH, timeout=60)
        # busy_timeout MUST be set before any read/write — 60 seconds
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        print("✅ Connected to local database")
    except Exception as e:
        print(f"❌ Local database connection failed: {e}")
        print("   Is another script or the attendance app still running?")
        print(f"   Run: fuser {DB_PATH}")
        return

    try:
        migrate_templates(cursor, conn)
        pull_departments(supabase, cursor, conn)
        pull_programs(supabase, cursor, conn)
        pull_professors(supabase, cursor, conn)
        pull_students(supabase, cursor, conn)
        pull_courses(supabase, cursor, conn)
        pull_enrollments(supabase, cursor, conn)
        verify_local_db(cursor)
        print_header("PULL COMPLETE")
        print("\n✅ Local DB is up to date. Ready for attendance.")
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"\n❌ Database is locked by another process.")
            print(f"   Run: fuser {DB_PATH}")
            print(f"   Then kill the process and re-run this script.")
        else:
            print(f"\n❌ Pull error: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ Pull error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            flush_wal(conn, cursor)
            conn.close()
            print("💾 Local database connection closed")


def students_only_pull():
    print_header("QUICK PULL: Students & Enrollments")
    conn = None
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        conn = sqlite3.connect(DB_PATH, timeout=60)
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        pull_students(supabase, cursor, conn)
        pull_enrollments(supabase, cursor, conn)
        flush_wal(conn, cursor)
        conn.close()
        print("\n✅ Students and enrollments refreshed")
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"❌ Database is locked. Run: fuser {DB_PATH}")
        else:
            print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--students":
        students_only_pull()
    else:
        full_pull()