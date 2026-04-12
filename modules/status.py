"""
modules/status.py
IITDH Attendance System — Professor Status Viewer

Identifies a professor by fingerprint scan, then shows:
  Page 1 — Last class: course code + date
  Page 2 — Attendance count for that class vs enrolled
  Page 3 — Today's classes (if any were held today)
"""

import time
import sqlite3
import modules.hardware as hw
from modules.config import DB_PATH


def view_prof_status():
    """
    Fingerprint-identify a professor then display their recent class stats.
    Waits up to 15 seconds for a scan; 3 display pages, each shown 2.5 s.
    """
    hw.display_msg("PROF STATUS", "Scan Finger", "15s timeout")

    # ── Load all prof templates ───────────────────────────────────
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, prof_id, template FROM profs")
    profs  = cursor.fetchall()
    conn.close()

    if not profs:
        hw.display_msg("ERROR", "No Profs Found", "")
        time.sleep(2)
        return

    # ── Fingerprint scan + match ──────────────────────────────────
    hw.uart.reset_input_buffer()
    deadline  = time.time() + 15
    prof_name = None
    prof_id   = None

    while time.time() < deadline:
        if hw.finger.get_image() == 0:
            hw.finger.image_2_tz(1)
            for name, p_id, template in profs:
                hw.finger.send_fpdata(list(template), "char", 2)
                if hw.finger.compare_templates() == 0:
                    prof_name = name
                    prof_id   = p_id
                    break
            if prof_name:
                break
        time.sleep(0.1)

    if not prof_name:
        hw.display_msg("TIMEOUT", "No match found", "")
        time.sleep(2)
        return

    hw.display_msg("IDENTIFIED", f"Prof {prof_name[:14]}", "Loading...")
    time.sleep(1)

    # ── Query stats ───────────────────────────────────────────────
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Most recent class session for this professor
    cursor.execute("""
        SELECT course_code, session_date,
               COUNT(DISTINCT student_id) AS attended
        FROM attendance
        WHERE authorized_by = ?
        GROUP BY course_code, session_date
        ORDER BY session_date DESC, course_code
        LIMIT 1
    """, (prof_id,))
    last = cursor.fetchone()

    if not last:
        hw.display_msg(f"Prof {prof_name[:10]}", "No classes", "recorded yet")
        conn.close()
        time.sleep(3)
        return

    course_code, session_date, attended = last

    # Total enrolled in that course
    cursor.execute("""
        SELECT COUNT(*) FROM course_enrollments
        WHERE course_code = ? AND status = 'active'
    """, (course_code,))
    enrolled = cursor.fetchone()[0]

    # All classes held by this prof today
    cursor.execute("""
        SELECT course_code, COUNT(DISTINCT student_id)
        FROM attendance
        WHERE authorized_by = ?
          AND date(session_date) = date('now', 'localtime')
        GROUP BY course_code
    """, (prof_id,))
    today_rows = cursor.fetchall()
    conn.close()

    # ── Display pages ─────────────────────────────────────────────

    # Page 1: Last class identity
    hw.display_msg("LAST CLASS", course_code, session_date)
    time.sleep(2.5)

    # Page 2: Attendance count
    hw.display_msg(
        course_code,
        f"Present: {attended}/{enrolled}",
        session_date
    )
    time.sleep(2.5)

    # Page 3: Today's activity
    if today_rows:
        for code, cnt in today_rows:
            hw.display_msg("TODAY", code, f"Attended: {cnt}")
            time.sleep(2.5)
    else:
        hw.display_msg("TODAY", "No class", "recorded today")
        time.sleep(2)
