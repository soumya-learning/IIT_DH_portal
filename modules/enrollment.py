import time
import sqlite3
import modules.hardware as hw
from modules.config  import DB_PATH, DEPT_MAP, PROG_MAP, DEPT_REVERSE, PROG_REVERSE, BackToMainMenu
from modules.keypad  import read_keypad_input


def enroll_student():
    """
    Full interactive student registration:
      1. Select branch + program via joystick
      2. Enter batch year + roll suffix via keypad → auto-generate roll no
      3. Enter name + password via keypad
      4. Capture 4 fingerprint scans, merge on sensor
      5. Save to SQLite students table
    """
    print("\n--- Interactive Student Registration ---")
    try:
        # ── Step 1: Branch & Program ──────────────────────────────
        hw.display_msg("ENROLLMENT", "Select Branch", "Use Joystick")
        time.sleep(0.5)
        selected_branch = hw.select_from_menu("SELECT BRANCH", list(DEPT_MAP.values()))
        branch_code     = DEPT_REVERSE[selected_branch]

        hw.display_msg("ENROLLMENT", "Select Program", "Use Joystick")
        time.sleep(0.5)
        selected_program = hw.select_from_menu("SELECT PROGRAM", list(PROG_MAP.values()))
        program_code     = PROG_REVERSE[selected_program]

        # ── Step 2: Roll number ───────────────────────────────────
        batch_year = read_keypad_input("BATCH YEAR", mode="NUMBER",
                                       display_line2="4 digits,OK=Ctr")
        if not batch_year or len(batch_year) != 4 or not batch_year.isdigit():
            hw.display_msg("ERROR", "Invalid Year")
            time.sleep(2)
            return

        year_short = batch_year[2:4]

        roll_suffix = read_keypad_input("ROLL SUFFIX", mode="NUMBER",
                                        display_line2="3 digits,OK=Ctr")
        if not roll_suffix or len(roll_suffix) != 3 or not roll_suffix.isdigit():
            hw.display_msg("ERROR", "Need 3 digits")
            time.sleep(2)
            return

        roll_no = f"{branch_code}{year_short}{program_code}{roll_suffix}"
        hw.display_msg("ROLL NUMBER", roll_no, "Ctr=confirm")
        time.sleep(2)

        # Duplicate check
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
        if cursor.fetchone():
            hw.display_msg("ERROR", f"{roll_no} exists")
            conn.close()
            time.sleep(2)
            return
        conn.close()

        # ── Step 3: Name + Password ───────────────────────────────
        first_name = read_keypad_input("FIRST NAME", mode="ALPHA",
                                       display_line2="C=CAPS,OK=Ctr")
        if not first_name:
            return

        last_name = read_keypad_input("LAST NAME", mode="ALPHA",
                                      display_line2="C=CAPS,OK=Ctr")
        if not last_name:
            return

        password = read_keypad_input("PASSWORD", mode="NUMBER",
                                     display_line2="Numbers,OK=Ctr",
                                     show_as_password=True)
        if not password:
            return

        hw.display_msg("SUMMARY", f"{first_name} {last_name}", roll_no)
        time.sleep(1.5)

        # ── Step 4: Fingerprint — 4 scans ────────────────────────
        print("\n--- Starting 4-Scan Fingerprint Registration ---")

        # Scan 1
        scan1_ok  = False
        retries   = 0
        while not scan1_ok and retries < 5:
            hw.display_msg("SCAN 1 of 4", "Place finger")
            hw.uart.reset_input_buffer()
            placed  = False
            timeout = time.time() + 10
            while time.time() < timeout and not placed:
                if hw.scan_d_key():
                    raise BackToMainMenu()
                if hw.finger.get_image() == 0:
                    placed = True
                time.sleep(0.1)

            if not placed:
                retries += 1
                hw.display_msg("TIMEOUT", f"Try {retries}/5")
                time.sleep(1)
                continue

            if hw.finger.image_2_tz(1) != 0:
                retries += 1
                hw.display_msg("Bad Image", f"Try {retries}/5")
                time.sleep(1.5)
                continue

            hw.display_msg("SCAN 1 of 4", "Success!")
            time.sleep(0.5)
            scan1_ok = True

        if not scan1_ok:
            hw.display_msg("ENROLLMENT", "FAILED", "Try again later")
            time.sleep(3)
            return

        # Scans 2–4
        for scan_num in range(2, 5):
            retry_count = 0
            scan_ok     = False

            while not scan_ok and retry_count < 5:
                hw.display_msg(f"SCAN {scan_num} of 4", "Remove finger")
                time.sleep(1.5)

                removal_t = time.time() + 5
                while time.time() < removal_t:
                    if hw.scan_d_key():
                        raise BackToMainMenu()
                    if hw.finger.get_image() != 0:
                        break
                    time.sleep(0.1)

                hw.display_msg(f"SCAN {scan_num} of 4", "Place finger")
                placed    = False
                place_t   = time.time() + 10
                while time.time() < place_t and not placed:
                    if hw.scan_d_key():
                        raise BackToMainMenu()
                    if hw.finger.get_image() == 0:
                        placed = True
                    time.sleep(0.1)

                if not placed:
                    retry_count += 1
                    hw.display_msg("TIMEOUT", f"Retry {retry_count}/5")
                    time.sleep(1.5)
                    continue

                if hw.finger.image_2_tz(2) != 0:
                    retry_count += 1
                    hw.display_msg("Bad Image", f"Retry {retry_count}/5")
                    time.sleep(1.5)
                    continue

                hw.display_msg(f"SCAN {scan_num} of 4", "Merging...")
                if hw.finger.create_model() == 0:
                    hw.display_msg(f"SCAN {scan_num} of 4", "Success!")
                    time.sleep(0.5)
                    scan_ok = True
                else:
                    retry_count += 1
                    hw.display_msg("No Match", f"Retry {retry_count}/5")
                    time.sleep(1.5)

            if not scan_ok:
                hw.display_msg("ENROLLMENT", "FAILED", "Try again later")
                time.sleep(3)
                return

        # ── Step 5: Save ──────────────────────────────────────────
        hw.display_msg("Saving...", "Please wait")
        template = hw.finger.get_fpdata("char", 1)
        if not template:
            hw.display_msg("ERROR", "Save Failed")
            time.sleep(2)
            return

        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO students
               (student_id, first_name, last_name, password,
                dept, year, program, template)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (roll_no, first_name, last_name, password,
             selected_branch, int(batch_year),
             selected_program, sqlite3.Binary(bytearray(template)))
        )
        conn.commit()
        conn.close()

        hw.display_msg("SUCCESS!", f"{first_name} {last_name}", roll_no)
        time.sleep(3)

    except BackToMainMenu:
        raise                   # let it propagate to the main loop
    except Exception as e:
        print(f"❌ Enrollment error: {e}")
        hw.display_msg("ERROR", str(e)[:20])
        time.sleep(2)