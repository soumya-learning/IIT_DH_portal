import time
import sqlite3
import modules.hardware as hw
from modules.config  import DB_PATH, DEPT_MAP
from modules.keypad  import read_keypad_input
from modules.auth    import authenticate_prof


# ─────────────────────────────────────────────
# ADD COURSE
# ─────────────────────────────────────────────

def add_course():
    hw.display_msg("ADD COURSE", "Prof Auth Needed")
    time.sleep(0.5)

    prof = authenticate_prof()
    if not prof:
        hw.display_msg("AUTH FAILED", "Cannot add course")
        time.sleep(2)
        return

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE name=?", (prof,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        hw.display_msg("ERROR", "Prof not found")
        time.sleep(2)
        return
    prof_id = result[0]

    course_code = read_keypad_input("COURSE CODE", mode="ALPHA",
                                    display_line2="OK=Center")
    if not course_code:
        return
    course_code = course_code.upper()

    course_name = read_keypad_input("COURSE NAME", mode="ALPHA",
                                    display_line2="OK=Center")
    if not course_name:
        return

    selected_dept = hw.select_from_menu("SELECT DEPT", list(DEPT_MAP.keys()))

    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT course_code FROM courses WHERE course_code=?",
                       (course_code,))
        if cursor.fetchone():
            hw.display_msg("ERROR", "Course exists")
            conn.close()
            time.sleep(2)
            return
        cursor.execute(
            "INSERT INTO courses (course_code, course_name, prof_id, dept_code) "
            "VALUES (?, ?, ?, ?)",
            (course_code, course_name, prof_id, selected_dept)
        )
        conn.commit()
        conn.close()
        hw.display_msg("SUCCESS!", course_code, "Course added")
        time.sleep(2)
    except Exception as e:
        hw.display_msg("ERROR", str(e)[:16])
        time.sleep(2)


# ─────────────────────────────────────────────
# VIEW COURSES
# ─────────────────────────────────────────────

def view_courses():
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name
            FROM courses c
            JOIN profs p ON c.prof_id = p.prof_id
            ORDER BY c.course_code
        """)
        courses = cursor.fetchall()
        conn.close()

        if not courses:
            hw.display_msg("NO COURSES", "No courses found")
            time.sleep(2)
            return

        for code, name, prof in courses:
            hw.display_msg(code, name[:16], f"Prof: {prof[:12]}")
            time.sleep(2)
    except Exception as e:
        hw.display_msg("ERROR", str(e)[:16])
        time.sleep(2)


# ─────────────────────────────────────────────
# ENROLL STUDENT IN COURSE
# ─────────────────────────────────────────────

def enroll_student_in_course():
    student_id = read_keypad_input("STUDENT ID", mode="ALPHA",
                                   display_line2="OK=Center")
    if not student_id:
        return
    student_id = student_id.upper()

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name FROM students WHERE student_id=?",
                   (student_id,))
    student = cursor.fetchone()

    if not student:
        hw.display_msg("ERROR", "Student not found")
        conn.close()
        time.sleep(2)
        return

    student_name = f"{student[0]} {student[1]}"
    cursor.execute("SELECT course_code, course_name FROM courses ORDER BY course_code")
    courses = cursor.fetchall()

    if not courses:
        hw.display_msg("NO COURSES", "No courses found")
        conn.close()
        time.sleep(2)
        return

    selected = hw.select_from_menu(
        "SELECT COURSE",
        [f"{code}: {name[:10]}" for code, name in courses]
    )
    course_code = selected.split(':')[0]

    try:
        cursor.execute(
            "SELECT enrollment_id FROM course_enrollments "
            "WHERE student_id=? AND course_code=?",
            (student_id, course_code)
        )
        if cursor.fetchone():
            hw.display_msg("ALREADY", "Enrolled", course_code)
            time.sleep(2)
        else:
            cursor.execute(
                "INSERT INTO course_enrollments (student_id, course_code, status) "
                "VALUES (?, ?, 'active')",
                (student_id, course_code)
            )
            conn.commit()
            hw.display_msg("SUCCESS!", student_name[:16], f"Enrolled {course_code}")
            time.sleep(2)
        conn.close()
    except Exception as e:
        hw.display_msg("ERROR", str(e)[:16])
        time.sleep(2)


# ─────────────────────────────────────────────
# VIEW ENROLLMENTS
# ─────────────────────────────────────────────

def view_course_enrollments():
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA",
                                    display_line2="OK=Center")
    if not course_code:
        return
    course_code = course_code.upper()

    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.first_name, s.last_name, s.dept
            FROM students s
            JOIN course_enrollments ce ON s.student_id = ce.student_id
            WHERE ce.course_code = ? AND ce.status = 'active'
            ORDER BY s.student_id
        """, (course_code,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            hw.display_msg("NO STUDENTS", "No enrollments", course_code)
            time.sleep(2)
            return

        for sid, fname, lname, dept in rows:
            hw.display_msg(sid, f"{fname} {lname}"[:16], dept[:16])
            time.sleep(2)
    except Exception as e:
        hw.display_msg("ERROR", str(e)[:16])
        time.sleep(2)


# ─────────────────────────────────────────────
# MANAGE COURSES MENU
# ─────────────────────────────────────────────

def manage_courses():
    menu = ["Add Course", "View Courses", "Enroll Students",
            "View Enrollments", "Back"]

    while True:
        selected      = 0
        scroll_offset = 0

        while True:
            if selected < scroll_offset:
                scroll_offset = selected
            elif selected >= scroll_offset + 3:
                scroll_offset = selected - 2
            hw.display_scrolling_menu(menu, selected, scroll_offset)
            btn = hw.wait_for_button()
            if btn == "UP":     selected = (selected - 1) % len(menu)
            elif btn == "DOWN": selected = (selected + 1) % len(menu)
            elif btn == "CENTER": break

        if   selected == 0: add_course()
        elif selected == 1: view_courses()
        elif selected == 2: enroll_student_in_course()
        elif selected == 3: view_course_enrollments()
        elif selected == 4: return
