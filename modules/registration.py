"""
modules/registration.py
IITDH Attendance System — Headless Admin Registration Console

Fully headless — no desktop, monitor, or PC keyboard required.
All interaction uses:
  • Matrix keypad (I2C 0x20) — text/number entry
  • Joystick                 — menu navigation + confirm/cancel
  • OLED display             — all feedback

Available functions (all callable from the joystick menu):
  1. Register Professor    — ID, name, dept, email(opt), fingerprint
  2. Register Student      — dept, program, year, roll, name, password, email(opt), fingerprint
  3. Add Course            — code, name, prof (joystick), dept, semester(opt)
  4. Enroll Student        — student ID (keypad), course (joystick)
  5. Delete Student        — ID, two-step joystick confirmation
  6. View System Data      — scrollable OLED pages for all tables

Entry point: main_menu()  — called from 01marchrunningcode.py
D key always = back to main menu (raises BackToMainMenu)
"""

import time
import sqlite3

import modules.hardware as hw
from modules.config      import (DB_PATH, DEPT_MAP, PROG_MAP,
                                 DEPT_REVERSE, PROG_REVERSE, BackToMainMenu)
from modules.keypad      import read_keypad_input
from modules.reg_fingerprint import scan_fingerprint


# ─────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────

def _confirm(title, line2="CENTER=Yes", line3="LEFT=Cancel"):
    """
    Show a confirm prompt on OLED.
    CENTER → True (confirmed)
    Any other button (LEFT, D, etc.) → False (cancelled)
    D key propagates as BackToMainMenu automatically via wait_for_button.
    """
    hw.display_msg(title, line2, line3)
    btn = hw.wait_for_button()
    return btn == "CENTER"


def _double_confirm(title):
    """
    Two-step confirmation to prevent accidental destructive actions.
    Both steps must be CENTER to return True.
    """
    hw.display_msg(title, "CENTER=Confirm", "LEFT=Cancel")
    if hw.wait_for_button() != "CENTER":
        hw.display_msg("CANCELLED", "Action aborted", "")
        time.sleep(1.5)
        return False
    hw.display_msg("ARE YOU SURE?", "CENTER=YES", "Any other=No")
    if hw.wait_for_button() != "CENTER":
        hw.display_msg("CANCELLED", "Action aborted", "")
        time.sleep(1.5)
        return False
    return True


def _optional_field(prompt, mode="ALPHA", hint=""):
    """
    Ask if the user wants to enter an optional field.
    Shows: "ADD <prompt>?" / "CENTER=Enter" / "LEFT=Skip"
    Returns the entered string or None (skipped).
    D key still propagates as BackToMainMenu.
    """
    hw.display_msg(f"{prompt[:12]}?", "CENTER=Enter", "LEFT=Skip")
    btn = hw.wait_for_button()
    if btn == "CENTER":
        return read_keypad_input(prompt, mode=mode, display_line2=hint)
    return None     # skipped


def _show_pages(pages, title="INFO"):
    """
    Display a list of (line1, line2, line3) tuples as OLED pages.
    Navigate: DOWN / CENTER = next page, LEFT = go back/exit.
    Last page auto-exits after 2 s or on any button.

    pages: list of tuples (l1, l2, l3)
    """
    for i, (l1, l2, l3) in enumerate(pages):
        is_last = (i == len(pages) - 1)
        nav = "DOWN/Ctr=Next" if not is_last else "Any=Done"
        hw.display_msg(l1, l2, f"{l3}  [{i+1}/{len(pages)}]")
        if is_last:
            time.sleep(2.5)
            return
        btn = hw.wait_for_button()
        if btn == "LEFT":
            return


def _success(line2, line3=""):
    hw.display_msg("SUCCESS!", line2[:20], line3[:20])
    time.sleep(2.5)


def _error(line2, line3=""):
    hw.display_msg("ERROR", line2[:20], line3[:20])
    time.sleep(2.5)


def _not_found(what):
    hw.display_msg("NOT FOUND", what[:20], "Check ID")
    time.sleep(2)


# ─────────────────────────────────────────────
# 1. REGISTER PROFESSOR
# ─────────────────────────────────────────────

def register_professor():
    """
    Prof registration — fully headless.
    Fields: prof_id (keypad ALPHA), name (keypad ALPHA),
            dept (joystick), email (optional keypad), fingerprint.
    """
    hw.display_msg("PROF REGISTER", "Enter Prof ID", "A=alpha OK=Ctr")
    time.sleep(0.8)

    # ── Prof ID ───────────────────────────────────────────────────
    prof_id = read_keypad_input("PROF ID", mode="ALPHA",
                                display_line2="e.g. PROF001")
    if not prof_id:
        return
    prof_id = prof_id.upper()

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE prof_id=?", (prof_id,))
    if cursor.fetchone():
        conn.close()
        _error(f"{prof_id} exists", "Use diff ID")
        return
    conn.close()

    # ── Name ──────────────────────────────────────────────────────
    prof_name = read_keypad_input("PROF NAME", mode="ALPHA",
                                  display_line2="C=CAPS OK=Ctr")
    if not prof_name:
        return
    prof_name = prof_name.title()

    # ── Department (joystick) ─────────────────────────────────────
    dept_code = hw.select_from_menu("SELECT DEPT", list(DEPT_MAP.keys()))

    # ── Email (auto-generated from prof_id) ───────────────────────
    email = f"{prof_id.lower()}@iitdh.ac.in"

    # ── Summary ───────────────────────────────────────────────────
    _show_pages([
        ("PROF SUMMARY", prof_id, prof_name[:18]),
        ("DEPT", DEPT_MAP[dept_code][:18], email[:18]),
    ])

    if not _confirm("SAVE PROF?"):
        hw.display_msg("CANCELLED", "Not saved", "")
        time.sleep(1.5)
        return

    # ── Fingerprint ───────────────────────────────────────────────
    hw.display_msg("FINGERPRINT", "4 scans needed", "Place finger")
    time.sleep(0.5)
    template = scan_fingerprint()

    if not template:
        if _confirm("SAVE W/O FP?", "No fingerprint", "CENTER=Yes LEFT=No"):
            template = b'\x00' * 512
            print("  Using placeholder fingerprint")
        else:
            hw.display_msg("CANCELLED", "Not saved", "")
            time.sleep(1.5)
            return

    # ── Save to DB ────────────────────────────────────────────────
    hw.display_msg("SAVING...", prof_id, "Please wait")
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO profs (prof_id, name, template, dept_code, email) "
            "VALUES (?,?,?,?,?)",
            (prof_id, prof_name,
             sqlite3.Binary(bytearray(template)), dept_code, email)
        )
        conn.commit()
        conn.close()
        _success(prof_name[:18], prof_id)
        print(f"✅ Prof registered: {prof_id} — {prof_name}")
    except Exception as e:
        _error("DB save failed", str(e)[:18])
        print(f"❌ Prof save error: {e}")


# ─────────────────────────────────────────────
# 2. REGISTER STUDENT
# ─────────────────────────────────────────────

def register_student():
    """
    Student registration — fully headless.
    Fields: dept (joystick), program (joystick), batch year (keypad NUMBER 4-digit),
            roll suffix (keypad NUMBER 3-digit), first name, last name,
            password (keypad NUMBER), email (optional), fingerprint.
    Roll number auto-generated: DEPT+YY+PROG+SUFFIX e.g. EE23BT037
    """
    hw.display_msg("STUD REGISTER", "Select Dept", "Use Joystick")
    time.sleep(0.5)

    # ── Dept + Program (joystick) ─────────────────────────────────
    dept_code = hw.select_from_menu("SELECT DEPT", list(DEPT_MAP.keys()))
    dept_name = DEPT_MAP[dept_code]

    prog_code = hw.select_from_menu("SELECT PROG", list(PROG_MAP.keys()))
    prog_name = PROG_MAP[prog_code]

    # ── Batch year ────────────────────────────────────────────────
    batch_year = read_keypad_input("BATCH YEAR", mode="NUMBER",
                                   display_line2="4 digits OK=Ctr")
    if not batch_year or len(batch_year) != 4 or not batch_year.isdigit():
        _error("Invalid year", "Need 4 digits")
        return
    year_short = batch_year[2:4]

    # ── Roll suffix ───────────────────────────────────────────────
    roll_suffix = read_keypad_input("ROLL SUFFIX", mode="NUMBER",
                                    display_line2="3 digits OK=Ctr")
    if not roll_suffix or len(roll_suffix) != 3 or not roll_suffix.isdigit():
        _error("Need 3 digits", "e.g. 037")
        return

    roll_no = f"{dept_code}{year_short}{prog_code}{roll_suffix}"
    hw.display_msg("ROLL NUMBER", roll_no, "Ctr=continue")
    time.sleep(1.5)

    # Duplicate check
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
    if cursor.fetchone():
        conn.close()
        _error(f"{roll_no} exists", "Already registered")
        return
    conn.close()

    # ── Name ──────────────────────────────────────────────────────
    first_name = read_keypad_input("FIRST NAME", mode="ALPHA",
                                   display_line2="C=CAPS OK=Ctr")
    if not first_name:
        return
    first_name = first_name.title()

    last_name = read_keypad_input("LAST NAME", mode="ALPHA",
                                  display_line2="C=CAPS OK=Ctr")
    if not last_name:
        return
    last_name = last_name.title()

    # ── Password ──────────────────────────────────────────────────
    password = read_keypad_input("PASSWORD", mode="NUMBER",
                                 display_line2="Numbers OK=Ctr",
                                 show_as_password=True)
    if not password:
        return

    # ── Email (auto-generated from roll number) ──────────────────
    email = f"{roll_no.lower()}@iitdh.ac.in"

    # ── Summary pages ─────────────────────────────────────────────
    _show_pages([
        ("STUD SUMMARY", roll_no, f"{first_name} {last_name}"[:18]),
        ("DEPT/PROG", f"{dept_code}/{prog_code}", f"Year {batch_year}"),
        ("EMAIL", email[:18], "DOWN=continue"),
    ])

    if not _confirm("SAVE STUDENT?"):
        hw.display_msg("CANCELLED", "Not saved", "")
        time.sleep(1.5)
        return

    # ── Fingerprint ───────────────────────────────────────────────
    hw.display_msg("FINGERPRINT", "4 scans needed", "Place finger")
    time.sleep(0.5)
    template = scan_fingerprint()

    if not template:
        if _confirm("SAVE W/O FP?", "No fingerprint", "CENTER=Yes LEFT=No"):
            template = b'\x00' * 512
        else:
            hw.display_msg("CANCELLED", "Not saved", "")
            time.sleep(1.5)
            return

    # ── Save to DB ────────────────────────────────────────────────
    hw.display_msg("SAVING...", roll_no, "Please wait")
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO students
               (student_id, first_name, last_name, password,
                dept, year, program, template, email)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (roll_no, first_name, last_name, password,
             dept_name, int(batch_year), prog_name,
             sqlite3.Binary(bytearray(template)), email)
        )
        conn.commit()
        conn.close()
        _success(f"{first_name} {last_name}"[:18], roll_no)
        print(f"✅ Student registered: {roll_no} — {first_name} {last_name}")
    except Exception as e:
        _error("DB save failed", str(e)[:18])
        print(f"❌ Student save error: {e}")


# ─────────────────────────────────────────────
# 3. ADD COURSE
# ─────────────────────────────────────────────

def add_course():
    """
    Course addition — fully headless.
    Fields: course code (keypad ALPHA), course name (keypad ALPHA),
            professor (joystick — loaded from DB), dept (joystick),
            semester (optional keypad), year (optional keypad).
    """
    hw.display_msg("ADD COURSE", "Enter Course Code", "A=alpha OK=Ctr")
    time.sleep(0.5)

    # ── Course code ───────────────────────────────────────────────
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA",
                                    display_line2="e.g. EE101")
    if not course_code:
        return
    course_code = course_code.upper()

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT course_code FROM courses WHERE course_code=?",
                   (course_code,))
    if cursor.fetchone():
        conn.close()
        _error(f"{course_code} exists", "Use diff code")
        return

    # ── Course name ───────────────────────────────────────────────
    course_name = read_keypad_input("COURSE NAME", mode="ALPHA",
                                    display_line2="C=CAPS OK=Ctr")
    if not course_name:
        conn.close()
        return
    course_name = course_name.title()

    # ── Professor (joystick — from DB) ────────────────────────────
    cursor.execute("SELECT prof_id, name FROM profs ORDER BY prof_id")
    profs = cursor.fetchall()
    conn.close()

    if not profs:
        _error("No professors", "Register prof 1st")
        return

    prof_options = [f"{p_id}: {name[:12]}" for p_id, name in profs]
    selected_prof = hw.select_from_menu("SELECT PROF", prof_options)
    prof_id = selected_prof.split(':')[0]
    prof_name = next(name for p_id, name in profs if p_id == prof_id)

    # ── Department (joystick) ─────────────────────────────────────
    dept_code = hw.select_from_menu("SELECT DEPT", list(DEPT_MAP.keys()))

    # ── Optional fields ───────────────────────────────────────────
    semester  = _optional_field("SEMESTER", mode="ALPHA", hint="e.g. Fall 2024")
    year_val  = _optional_field("ACAD YEAR", mode="NUMBER", hint="e.g. 2024")

    # ── Summary ───────────────────────────────────────────────────
    _show_pages([
        ("COURSE SUMMARY", course_code, course_name[:18]),
        ("PROFESSOR", prof_name[:18], prof_id),
        ("DEPT", DEPT_MAP[dept_code][:18],
         semester[:16] if semester else "No semester"),
    ])

    if not _confirm("SAVE COURSE?"):
        hw.display_msg("CANCELLED", "Not saved", "")
        time.sleep(1.5)
        return

    # ── Save ──────────────────────────────────────────────────────
    hw.display_msg("SAVING...", course_code, "Please wait")
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO courses
               (course_code, course_name, prof_id, dept_code, semester, year)
               VALUES (?,?,?,?,?,?)""",
            (course_code, course_name, prof_id, dept_code, semester, year_val)
        )
        conn.commit()
        conn.close()
        _success(course_code, course_name[:18])
        print(f"✅ Course added: {course_code} — {course_name}")
    except Exception as e:
        _error("DB save failed", str(e)[:18])
        print(f"❌ Course save error: {e}")


# ─────────────────────────────────────────────
# 4. ENROLL STUDENT IN COURSE
# ─────────────────────────────────────────────

def enroll_student_in_course():
    """
    Enroll a student in a course — fully headless.
    Student ID entered via keypad, course selected via joystick from DB list.
    """
    hw.display_msg("ENROLL STUDENT", "Enter Student ID", "A=alpha OK=Ctr")
    time.sleep(0.5)

    student_id = read_keypad_input("STUDENT ID", mode="ALPHA",
                                   display_line2="e.g. EE23BT037")
    if not student_id:
        return
    student_id = student_id.upper()

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT first_name, last_name, dept FROM students WHERE student_id=?",
        (student_id,)
    )
    student = cursor.fetchone()
    if not student:
        conn.close()
        _not_found(student_id)
        return

    student_name = f"{student[0]} {student[1]}"
    hw.display_msg("FOUND", student_name[:18], student[2][:18])
    time.sleep(1.5)

    # ── Course selection (joystick) ───────────────────────────────
    cursor.execute("""
        SELECT c.course_code, c.course_name, p.name
        FROM courses c JOIN profs p ON c.prof_id = p.prof_id
        ORDER BY c.course_code
    """)
    courses = cursor.fetchall()

    if not courses:
        conn.close()
        _error("No courses", "Add a course first")
        return

    course_options = [f"{code}: {name[:10]}" for code, name, _ in courses]
    selected = hw.select_from_menu("SELECT COURSE", course_options)
    course_code = selected.split(':')[0]
    course_name = next(name for code, name, _ in courses if code == course_code)

    # ── Duplicate check ───────────────────────────────────────────
    cursor.execute(
        "SELECT enrollment_id FROM course_enrollments "
        "WHERE student_id=? AND course_code=?",
        (student_id, course_code)
    )
    if cursor.fetchone():
        conn.close()
        hw.display_msg("ALREADY", "Already enrolled", course_code)
        time.sleep(2)
        return

    # ── Confirm ───────────────────────────────────────────────────
    hw.display_msg("ENROLL?", student_name[:18], course_code)
    if not _confirm("CONFIRM?"):
        hw.display_msg("CANCELLED", "Not enrolled", "")
        conn.close()
        time.sleep(1.5)
        return

    # ── Save ──────────────────────────────────────────────────────
    try:
        cursor.execute(
            "INSERT INTO course_enrollments (student_id, course_code, status) "
            "VALUES (?,?,'active')",
            (student_id, course_code)
        )
        conn.commit()
        conn.close()
        _success(student_name[:18], f"-> {course_code}")
        print(f"✅ Enrolled: {student_id} in {course_code}")
    except Exception as e:
        conn.close()
        _error("DB save failed", str(e)[:18])
        print(f"❌ Enroll error: {e}")


# ─────────────────────────────────────────────
# 5. DELETE STUDENT
# ─────────────────────────────────────────────

def delete_student():
    """
    Delete a student — fully headless with two-step joystick confirmation.
    Shows full student info before confirming.
    Both confirm steps must be CENTER to proceed.
    """
    hw.display_msg("DELETE STUDENT", "Enter Roll No", "A=alpha OK=Ctr")
    time.sleep(0.5)

    student_id = read_keypad_input("ROLL NUMBER", mode="ALPHA",
                                   display_line2="e.g. EE23BT037")
    if not student_id:
        return
    student_id = student_id.upper()

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT first_name, last_name, dept, year, program "
        "FROM students WHERE student_id=?",
        (student_id,)
    )
    student = cursor.fetchone()
    if not student:
        conn.close()
        _not_found(student_id)
        return

    fname, lname, dept, year, program = student
    student_name = f"{fname} {lname}"

    cursor.execute(
        "SELECT COUNT(*) FROM course_enrollments WHERE student_id=?",
        (student_id,)
    )
    enroll_count = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM attendance WHERE student_id=?",
        (student_id,)
    )
    att_count = cursor.fetchone()[0]

    # ── Show info ─────────────────────────────────────────────────
    _show_pages([
        ("STUDENT FOUND", student_name[:18], student_id),
        (dept[:18], f"{program} {year}", "DOWN=continue"),
        (f"Enrollments:{enroll_count}", f"Att.records:{att_count}",
         "DOWN=Confirm/Del"),
    ])

    # ── Double confirm ────────────────────────────────────────────
    if not _double_confirm(f"DELETE {student_id[:12]}?"):
        return

    # ── Delete ────────────────────────────────────────────────────
    hw.display_msg("DELETING...", student_id, "Please wait")
    try:
        cursor.execute("DELETE FROM students WHERE student_id=?", (student_id,))
        conn.commit()
        conn.close()
        hw.display_msg("DELETED!", student_name[:18], student_id)
        time.sleep(3)
        print(f"✅ Deleted: {student_id} — {student_name}")
    except Exception as e:
        conn.close()
        _error("Delete failed", str(e)[:18])
        print(f"❌ Delete error: {e}")


# ─────────────────────────────────────────────
# 6. VIEW SYSTEM DATA
# ─────────────────────────────────────────────

def view_system_data():
    """
    Browse system data on OLED — fully headless.
    Sub-menu: Professors / Students / Courses / Attendance / Back
    Each section shows scrollable pages.
    """
    sections = ["Professors", "Students", "Courses", "Attendance", "Back"]
    selected      = 0
    scroll_offset = 0
    visible       = 3

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible:
            scroll_offset = selected - visible + 1

        hw.display_scrolling_menu(sections, selected, scroll_offset)
        btn = hw.wait_for_button()

        if btn == "UP":
            selected = (selected - 1) % len(sections)
        elif btn == "DOWN":
            selected = (selected + 1) % len(sections)
        elif btn == "CENTER":
            if selected == 0: _view_professors()
            elif selected == 1: _view_students()
            elif selected == 2: _view_courses()
            elif selected == 3: _view_attendance()
            elif selected == 4: return
        elif btn == "LEFT":
            return


def _view_professors():
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM profs")
        total = cursor.fetchone()[0]
        cursor.execute(
            "SELECT prof_id, name, dept_code FROM profs ORDER BY prof_id"
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        _error("DB error", str(e)[:18])
        return

    if not rows:
        hw.display_msg("PROFESSORS", "None registered", "")
        time.sleep(2)
        return

    pages = [("PROFESSORS", f"Total: {total}", "DOWN=scroll")]
    for p_id, name, dept in rows:
        pages.append((p_id, name[:18], DEPT_MAP.get(dept, dept)[:18]))
    _show_pages(pages)


def _view_students():
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students")
        total = cursor.fetchone()[0]
        cursor.execute(
            "SELECT student_id, first_name, last_name, dept "
            "FROM students ORDER BY student_id LIMIT 20"
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        _error("DB error", str(e)[:18])
        return

    if not rows:
        hw.display_msg("STUDENTS", "None registered", "")
        time.sleep(2)
        return

    pages = [("STUDENTS", f"Total: {total}", "DOWN=scroll")]
    for sid, fname, lname, dept in rows:
        pages.append((sid, f"{fname} {lname}"[:18], dept[:18]))
    if total > 20:
        pages.append(("STUDENTS", f"...+{total-20} more", "Showing top 20"))
    _show_pages(pages)


def _view_courses():
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM courses")
        total = cursor.fetchone()[0]
        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name
            FROM courses c JOIN profs p ON c.prof_id = p.prof_id
            ORDER BY c.course_code
        """)
        rows = cursor.fetchall()
        # enrollment count per course
        counts = {}
        for code, _, _ in rows:
            cursor.execute(
                "SELECT COUNT(*) FROM course_enrollments "
                "WHERE course_code=? AND status='active'",
                (code,)
            )
            counts[code] = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        _error("DB error", str(e)[:18])
        return

    if not rows:
        hw.display_msg("COURSES", "None added", "")
        time.sleep(2)
        return

    pages = [("COURSES", f"Total: {total}", "DOWN=scroll")]
    for code, name, prof in rows:
        enrolled = counts.get(code, 0)
        pages.append((code, name[:18], f"{prof[:10]} ({enrolled}stu)"))
    _show_pages(pages)


def _view_attendance():
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM attendance")
        total = cursor.fetchone()[0]
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
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE synced = 0")
        pending = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        _error("DB error", str(e)[:18])
        return

    _show_pages([
        ("ATTENDANCE", f"Total: {total}", f"Today uniq:{today_unique}"),
        ("TODAY", f"Scans: {today_total}", f"Pending sync:{pending}"),
    ])


# ─────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────

MENU = [
    "1.Reg Professor",
    "2.Reg Student",
    "3.Add Course",
    "4.Enroll Student",
    "5.Delete Student",
    "6.View Data",
    "7.Back",
]


def main_menu():
    """
    Entry point — called from launch_registration() in 01marchrunningcode.py.
    Fully headless: OLED + joystick + matrix keypad, no keyboard or desktop.
    D key on keypad always exits to main menu via BackToMainMenu.
    """
    selected      = 0
    scroll_offset = 0
    visible       = 3

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible:
            scroll_offset = selected - visible + 1

        hw.display_scrolling_menu(MENU, selected, scroll_offset)
        btn = hw.wait_for_button()

        if btn == "UP":
            selected = (selected - 1) % len(MENU)
        elif btn == "DOWN":
            selected = (selected + 1) % len(MENU)
        elif btn == "CENTER":
            hw.display_msg("LOADING...", MENU[selected][:18], "")
            time.sleep(0.3)

            if   selected == 0: register_professor()
            elif selected == 1: register_student()
            elif selected == 2: add_course()
            elif selected == 3: enroll_student_in_course()
            elif selected == 4: delete_student()
            elif selected == 5: view_system_data()
            elif selected == 6:
                hw.display_msg("REG MENU", "Returning...", "")
                time.sleep(0.8)
                return

        elif btn == "LEFT":
            hw.display_msg("REG MENU", "Returning...", "")
            time.sleep(0.8)
            return