import time
import sqlite3
import modules.hardware as hw
from modules.config import DB_PATH


def view_stats():
    """
    Show 3 pages of system statistics on OLED, 3 seconds each:
      Page 1: total students + courses
      Page 2: total profs + today's unique attendance
      Page 3: today's unique vs total scan count
    """
    hw.display_msg("Loading Stats", "Please wait...")
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM courses")
        total_courses = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM profs")
        total_profs = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) FROM attendance
            WHERE date(session_date) = date('now', 'localtime')
        """)
        today_unique = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM attendance
            WHERE date(session_date) = date('now', 'localtime')
        """)
        today_total = cursor.fetchone()[0]

        conn.close()

        hw.display_msg("STATISTICS",
                       f"Students: {total_students}",
                       f"Courses:  {total_courses}")
        time.sleep(3)

        hw.display_msg("STATISTICS",
                       f"Professors: {total_profs}",
                       f"Today: {today_unique}/{total_students}")
        time.sleep(3)

        hw.display_msg("TODAY'S DATA",
                       f"Unique: {today_unique}",
                       f"Scans:  {today_total}")
        time.sleep(3)

    except Exception as e:
        hw.display_msg("ERROR", "Stats Failed", str(e)[:16])
        time.sleep(2)
