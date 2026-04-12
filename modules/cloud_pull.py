"""
modules/cloud_pull.py
IITDH Attendance System — Cloud Pull (Cloud → Local)

Source of truth per column:
  template  → LOCAL  (enrolled on Pi — NEVER overwrite if local has data)
  password  → CLOUD  (set via web — cloud password_hash wins)
  all other → CLOUD

Also runs a template migration at start of every pull — no-op if templates
are already correct raw bytes.

Called from main menu via run_full_pull() or run_students_pull().
All detailed output goes to terminal; OLED shows brief status per step.
"""

import sqlite3
import json
import time
import modules.hardware as hw
from modules.config import DB_PATH, SUPABASE_URL, SUPABASE_KEY

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

PAGE_SIZE = 1000


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

# When True, all _oled() calls are suppressed (background/silent mode).
_silent = False

def _oled(line1, line2="", line3=""):
    if not _silent:
        hw.display_msg(line1, line2, line3)


def _connect_supabase():
    if not SUPABASE_AVAILABLE:
        print("❌ supabase-py not installed. Run: pip install supabase")
        _oled("PULL FAILED", "supabase not", "installed")
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
        conn = sqlite3.connect(DB_PATH, timeout=60)
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except Exception as e:
        print(f"❌ Local DB connection failed: {e}")
        _oled("DB ERROR", "Local DB locked", str(e)[:16])
        return None


def supabase_to_bytes(value):
    """Decode Supabase bytea to raw Python bytes. Handles all legacy formats."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, sqlite3.Binary)):
        b = bytes(value)
        return b if len(b) > 0 else None
    if isinstance(value, list):
        return bytes(value) if value else None
    if isinstance(value, str) and value:
        # Primary: "\\x0303591d..."
        if value.startswith("\\x") or value.startswith("0x"):
            try:
                result = bytes.fromhex(value[2:])
                if len(result) > 0:
                    return result
            except ValueError:
                pass
        # Fallback: plain hex "0303591d..."
        try:
            result = bytes.fromhex(value)
            if len(result) > 0:
                return result
        except ValueError:
            pass
        print(f"    ⚠️  Could not decode template: {value[:40]!r}")
    return None


def to_blob(raw_bytes):
    """sqlite3.Binary wrapper — guarantees BLOB type in SQLite."""
    if isinstance(raw_bytes, (bytes, bytearray)) and len(raw_bytes) > 0:
        return sqlite3.Binary(bytes(raw_bytes))
    return sqlite3.Binary(b"")


def is_real_blob(value):
    if isinstance(value, (bytes, bytearray, sqlite3.Binary)):
        return len(bytes(value)) > 0
    return False


def flush_wal(conn, cursor):
    try:
        cursor.execute("PRAGMA wal_checkpoint(FULL)")
        conn.commit()
        print("\n✅ WAL checkpoint complete — DB Browser can now see changes")
    except Exception as e:
        print(f"\n⚠️  WAL checkpoint failed (data still saved): {e}")


def fetch_all_pages(supabase, table, columns="*"):
    all_rows = []
    offset   = 0
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
    """Convert any legacy encoding to clean raw fingerprint bytes."""
    if raw is None:
        return None
    b = bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode()
    try:
        text = b.decode("utf-8")
        if text.startswith("["):
            lst = json.loads(text)
            if isinstance(lst, list):
                return bytes(lst)
        if text.startswith("5b"):
            try:
                inner = bytes.fromhex(text).decode("utf-8")
                lst   = json.loads(inner)
                if isinstance(lst, list):
                    return bytes(lst)
            except (ValueError, UnicodeDecodeError):
                pass
        try:
            return bytes.fromhex(text)
        except ValueError:
            pass
    except UnicodeDecodeError:
        return b
    return b


def migrate_templates(cursor, conn):
    """
    Fix any legacy-encoded fingerprint BLOBs in local DB.
    Safe to run repeatedly — no-op if templates already correct.
    """
    print("\n🔧 Checking & migrating fingerprint templates...")
    _oled("PULL", "Checking", "templates...")

    fixed_count = 0
    already_ok  = 0
    empty_count = 0

    for table, id_col in [("students", "student_id"), ("profs", "prof_id")]:
        cursor.execute(f"SELECT {id_col}, template FROM {table}")
        for row_id, template in cursor.fetchall():
            if template is None or len(bytes(template)) == 0:
                empty_count += 1
                continue
            raw = bytes(template)
            if raw[0] == 0x03:          # already correct raw fingerprint
                already_ok += 1
                continue
            fixed = decode_template(template)
            if fixed and fixed != raw:
                cursor.execute(
                    f"UPDATE {table} SET template = ? WHERE {id_col} = ?",
                    (sqlite3.Binary(fixed), row_id)
                )
                fixed_count += 1
                print(f"  ✓ Fixed {table}.{row_id}: {len(raw)}B → {len(fixed)}B")
            else:
                already_ok += 1

    if fixed_count > 0:
        conn.commit()
        print(f"  ✅ Migrated {fixed_count} templates")
    else:
        print(f"  ✅ All {already_ok} templates OK — no migration needed")
    if empty_count > 0:
        print(f"  ℹ️  {empty_count} empty templates (not yet enrolled)")


# ─────────────────────────────────────────────
# PULL FUNCTIONS
# ─────────────────────────────────────────────

def pull_departments(supabase, cursor, conn):
    print("\n📋 Pulling Departments...")
    _oled("PULLING", "Departments", "")
    rows = fetch_all_pages(supabase, "departments")
    if not rows:
        print("  ⚠️  No departments found in cloud")
        return
    cursor.executemany("""
        INSERT INTO Departments (dept_code, dept_name)
        VALUES (:dept_code, :dept_name)
        ON CONFLICT(dept_code) DO UPDATE SET dept_name = excluded.dept_name
    """, rows)
    conn.commit()
    print(f"✅ Departments: {len(rows)} pulled")


def pull_programs(supabase, cursor, conn):
    print("\n📋 Pulling Programs...")
    _oled("PULLING", "Programs", "")
    rows = fetch_all_pages(supabase, "programs")
    if not rows:
        print("  ⚠️  No programs found in cloud")
        return
    cursor.executemany("""
        INSERT INTO Programs (program_code, program_name)
        VALUES (:program_code, :program_name)
        ON CONFLICT(program_code) DO UPDATE SET program_name = excluded.program_name
    """, rows)
    conn.commit()
    print(f"✅ Programs: {len(rows)} pulled")


def pull_professors(supabase, cursor, conn):
    """Local fingerprint template always protected — never overwritten by cloud."""
    print("\n👨‍🏫 Pulling Professors...")
    _oled("PULLING", "Professors", "")
    rows = fetch_all_pages(supabase, "profs")
    if not rows:
        print("  ⚠️  No professors found in cloud")
        return
    upserted = 0
    for row in rows:
        try:
            cursor.execute(
                "SELECT template FROM profs WHERE prof_id = ?", (row["prof_id"],)
            )
            existing      = cursor.fetchone()
            local_template = existing[0] if existing else None

            if is_real_blob(local_template):
                final_template = to_blob(local_template)
                t_src = f"kept local ({len(bytes(local_template))} bytes)"
            else:
                cloud_raw = supabase_to_bytes(row.get("template"))
                if cloud_raw:
                    final_template = to_blob(cloud_raw)
                    t_src = f"cloud ({len(cloud_raw)} bytes)"
                else:
                    final_template = to_blob(b"")
                    t_src = "placeholder"

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
                row["prof_id"], row["name"], row["dept_code"],
                row.get("email"), final_template, row.get("created_at")
            ))
            upserted += 1
            print(f"  ✓ {row['prof_id']}: {row['name']} | {t_src}")
        except Exception as e:
            print(f"  ✗ Prof {row.get('prof_id')}: {e}")

    conn.commit()
    print(f"✅ Professors: {upserted}/{len(rows)} pulled")


def pull_students(supabase, cursor, conn):
    """
    Template → local wins.
    Password → cloud wins (cloud column: password_hash → local column: password).
    """
    print("\n👨‍🎓 Pulling Students...")
    _oled("PULLING", "Students", "Please wait...")
    rows = fetch_all_pages(supabase, "students")
    if not rows:
        print("  ⚠️  No students found in cloud")
        return

    upserted    = 0
    no_template = 0
    no_password = 0

    for row in rows:
        try:
            cursor.execute(
                "SELECT password, template FROM students WHERE student_id = ?",
                (row["student_id"],)
            )
            existing       = cursor.fetchone()
            local_password = existing[0] if existing else None
            local_template = existing[1] if existing else None

            # Template — local wins
            if is_real_blob(local_template):
                final_template = to_blob(local_template)
                t_src = f"local ({len(bytes(local_template))}B)"
            else:
                cloud_raw = supabase_to_bytes(row.get("template"))
                if cloud_raw:
                    final_template = to_blob(cloud_raw)
                    t_src = f"cloud ({len(cloud_raw)}B)"
                else:
                    final_template = to_blob(b"")
                    t_src = "placeholder"
                    no_template += 1

            # Password — cloud wins
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
                row["student_id"], row["first_name"], row["last_name"],
                row["dept"], row["year"], row["program"],
                row.get("email"), final_password, final_template,
                row.get("created_at")
            ))
            upserted += 1
            print(f"  ✓ {row['student_id']}: {row['first_name']} {row['last_name']} "
                  f"| pwd:{p_src} | tmpl:{t_src}")

        except Exception as e:
            print(f"  ✗ Student {row.get('student_id')}: {e}")

    conn.commit()
    print(f"✅ Students: {upserted}/{len(rows)} pulled "
          f"({no_template} no template, {no_password} no password)")


def pull_courses(supabase, cursor, conn):
    print("\n📚 Pulling Courses...")
    _oled("PULLING", "Courses", "")
    rows = fetch_all_pages(supabase, "courses")
    if not rows:
        print("  ⚠️  No courses found in cloud")
        return
    cursor.executemany("""
        INSERT INTO courses
            (course_code, course_name, prof_id, dept_code,
             semester, year, time_slot, created_at)
        VALUES
            (:course_code, :course_name, :prof_id, :dept_code,
             :semester, :year, :time_slot, :created_at)
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


def pull_enrollments(supabase, cursor, conn):
    print("\n📝 Pulling Enrollments...")
    _oled("PULLING", "Enrollments", "")
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

    try:
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        pending = cursor.fetchone()[0]
        print(f"\n  Attendance pending sync: {pending}")
        if pending > 0:
            print("  ⚠️  Run Cloud Sync to push pending attendance!")
    except Exception:
        pass


# ─────────────────────────────────────────────
# PUBLIC ENTRY POINTS — called from main menu
# ─────────────────────────────────────────────

def run_full_pull(silent=False):
    """
    Full pull: all tables.
    silent=True  → no OLED writes, no time.sleep() pauses (background use).
    silent=False → full OLED feedback (manual/menu use).
    """
    global _silent
    _silent = silent

    print("\n" + "=" * 70)
    print("  IITDH ATTENDANCE SYSTEM - CLOUD PULL (Full)" + (" [silent]" if silent else ""))
    print("=" * 70)

    _oled("CLOUD PULL", "Connecting...", "")

    supabase = _connect_supabase()
    if not supabase:
        if not silent:
            time.sleep(3)
        _silent = False
        return

    conn = _connect_local()
    if not conn:
        if not silent:
            time.sleep(3)
        _silent = False
        return

    cursor = conn.cursor()
    _oled("CLOUD PULL", "Connected", "Starting...")
    if not silent:
        time.sleep(0.5)

    try:
        migrate_templates(cursor, conn)
        pull_departments(supabase, cursor, conn)
        pull_programs(supabase, cursor, conn)
        pull_professors(supabase, cursor, conn)
        pull_students(supabase, cursor, conn)
        pull_courses(supabase, cursor, conn)
        pull_enrollments(supabase, cursor, conn)
        verify_local_db(cursor)

        print("\n" + "=" * 70)
        print("  PULL COMPLETE")
        print("=" * 70)
        print("\n✅ Local DB is up to date. Ready for attendance.")

        _oled("PULL COMPLETE", "DB up to date", "Ready!")
        if not silent:
            time.sleep(3)

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"\n❌ Database is locked. Stop main script first.")
            _oled("DB LOCKED", "Stop main app", "then retry")
        else:
            print(f"\n❌ Pull error: {e}")
            _oled("PULL ERROR", str(e)[:20], "")
        import traceback
        traceback.print_exc()
        if not silent:
            time.sleep(3)

    except Exception as e:
        print(f"\n❌ Pull error: {e}")
        import traceback
        traceback.print_exc()
        _oled("PULL ERROR", str(e)[:20], "Check terminal")
        if not silent:
            time.sleep(3)

    finally:
        _silent = False   # always restore
        if conn:
            flush_wal(conn, cursor)
            conn.close()
            print("💾 Local database connection closed")


def run_students_pull(silent=False):
    """
    Students + enrollments only quick pull.
    silent=True  → no OLED writes, no sleeps (background use).
    """
    global _silent
    _silent = silent

    print("\n" + "=" * 70)
    print("  QUICK PULL: Students & Enrollments" + (" [silent]" if silent else ""))
    print("=" * 70)

    _oled("QUICK PULL", "Connecting...", "")

    supabase = _connect_supabase()
    if not supabase:
        if not silent:
            time.sleep(3)
        _silent = False
        return

    conn = _connect_local()
    if not conn:
        if not silent:
            time.sleep(3)
        _silent = False
        return

    cursor = conn.cursor()
    try:
        pull_students(supabase, cursor, conn)
        pull_enrollments(supabase, cursor, conn)
        flush_wal(conn, cursor)
        print("\n✅ Students and enrollments refreshed")
        _oled("PULL DONE", "Students updated", "")
        if not silent:
            time.sleep(2)
    except Exception as e:
        print(f"❌ Error: {e}")
        _oled("PULL ERROR", str(e)[:20], "")
        if not silent:
            time.sleep(3)
    finally:
        _silent = False   # always restore
        if conn:
            conn.close()