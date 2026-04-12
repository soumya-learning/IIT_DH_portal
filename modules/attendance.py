import time
import sqlite3
import modules.hardware as hw
from modules.config import DB_PATH, BackToMainMenu


def classroom_session(prof_name):
    """
    Run an attendance session for a professor.

    D key behaviour:
      BEFORE session opens  — D works normally (prof can cancel course selection)
      AFTER session opens   — D is LOCKED via hw.back_locked()
                              Only professor's fingerprint closes the session.
                              D is automatically re-enabled when session ends.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE name=?", (prof_name,))
    prof_result = cursor.fetchone()

    if not prof_result:
        hw.display_msg("ERROR", "Prof not found")
        conn.close()
        time.sleep(2)
        return

    prof_id = prof_result[0]
    cursor.execute(
        "SELECT course_code, course_name FROM courses "
        "WHERE prof_id=? ORDER BY course_code",
        (prof_id,)
    )
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        hw.display_msg("NO COURSES", "No courses found", "for this prof")
        time.sleep(3)
        return

    # ── Course selection — D still works here ──────────────────────
    # Prof can press D to cancel before the session opens.
    course_options  = [f"{code}: {name[:12]}" for code, name in courses]
    selected_course = hw.select_from_menu("SELECT COURSE", course_options)
    course_code     = selected_course.split(':')[0]
    course_name     = next(name for code, name in courses if code == course_code)

    hw.display_msg("COURSE SELECTED", course_code, course_name[:16])
    time.sleep(1.5)

    # ── Load enrolled students ─────────────────────────────────────
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.student_id, s.first_name, s.template
        FROM students s
        JOIN course_enrollments ce ON s.student_id = ce.student_id
        WHERE ce.course_code = ? AND ce.status = 'active'
    """, (course_code,))
    enrolled_students = cursor.fetchall()
    conn.close()

    if not enrolled_students:
        hw.display_msg("NO STUDENTS", "No enrollments", "for this course")
        time.sleep(3)
        return

    hw.display_msg("CLASS OPEN", course_code, "Scan Finger")
    time.sleep(1.5)

    session_start    = time.time()
    attendance_count = 0
    attended_ids     = set()

    # ── Session loop — D key LOCKED ────────────────────────────────
    # hw.back_locked() disables D for the entire with-block.
    # It is automatically re-enabled on any exit (return, exception, crash).
    # The ONLY way to end the session is the professor scanning their finger.
    with hw.back_locked():
        while True:
            hw.display_msg(
                "CLASS SESSION",
                f"{course_code} ({attendance_count})",
                "Scan or Prof=Exit"
            )
            hw.uart.reset_input_buffer()

            if hw.finger.get_image() != 0:
                time.sleep(0.1)
                continue

            hw.finger.image_2_tz(1)

            conn   = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # ── Professor's fingerprint ends the session ───────────
            cursor.execute("SELECT template FROM profs WHERE prof_id=?",
                           (prof_id,))
            prof_tmpl = cursor.fetchone()
            if prof_tmpl:
                hw.finger.send_fpdata(list(prof_tmpl[0]), "char", 2)
                if hw.finger.compare_templates() == 0:
                    duration = int((time.time() - session_start) / 60)
                    hw.display_msg("SESSION CLOSED",
                                   f"Total: {attendance_count}",
                                   f"Time: {duration}min")
                    conn.close()
                    time.sleep(3)
                    return      # exits with-block → D auto-unlocked

            # ── Match against enrolled students ───────────────────
            found = False
            for s_id, s_name, s_template in enrolled_students:
                hw.finger.send_fpdata(list(s_template), "char", 2)
                if hw.finger.compare_templates() == 0:
                    if s_id in attended_ids:
                        hw.display_msg("ALREADY MARKED", s_name,
                                       "Present today")
                        time.sleep(2)
                    else:
                        hw.display_msg("VERIFIED!", s_name, s_id)
                        cursor.execute("""
                            INSERT INTO attendance
                            (course_code, student_id, student_name,
                             authorized_by, timestamp, session_date)
                            VALUES (?, ?, ?, ?,
                                    datetime('now','localtime'),
                                    date('now','localtime'))
                        """, (course_code, s_id, s_name, prof_id))
                        conn.commit()
                        attendance_count += 1
                        attended_ids.add(s_id)
                        time.sleep(2)
                    found = True
                    break

            if not found:
                hw.display_msg("NOT FOUND", "Not enrolled in", course_code)
                time.sleep(1.5)

            conn.close()
    # back_locked() exits here — D key automatically re-enabled