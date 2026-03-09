#!/usr/bin/env python3
"""
IITDH Biometric Attendance System - Administrative Console
Manual data entry using system keyboard (no hardware required)
WITH OLED DISPLAY SUPPORT AND FINGERPRINT REGISTRATION
Merge v2: Re-anchor strategy + self-match confidence verification
"""

import sqlite3
import sys
import serial
import struct
import time
from datetime import datetime
from adafruit_fingerprint import Adafruit_Fingerprint
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

# --- Database Configuration ---
DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# --- Mapping Dictionaries ---
DEPT_MAP = {
    "CS": "Computer Science",
    "EE": "Electrical Engineering",
    "MC": "Math & Computing",
    "ME": "Mechanical Engineering",
    "CH": "Chemical Engineering",
    "CE": "Civil Engineering"
}

PROG_MAP = {
    "BT": "B.Tech",
    "IS": "BSMS",
    "MT": "M.Tech"
}

# --- Fingerprint Merge Configuration ---
FP_NUM_SCANS         = 5      # Total scans to merge
FP_MAX_RETRIES       = 6      # Max attempts per scan before giving up
FP_TEMP_SLOT         = 127    # Temporary sensor slot for self-match test
FP_MIN_CONFIDENCE    = 50     # Below this → reject template (re-enroll)
FP_WARN_CONFIDENCE   = 100    # Below this → warn but allow save

# R307 raw packet constants (for 1:1 match fallback)
R307_ADDR            = 0xFFFFFFFF
START_CODE           = 0xEF01

# --- OLED Setup ---
try:
    oled_interface = spi(device=0, port=0, bus_speed_hz=1000000, gpio_DC=25, gpio_RST=27, gpio_CS=8)
    device = ssd1306(oled_interface)
    device.contrast(255)
    OLED_AVAILABLE = True
    print("✅ OLED Display initialized")
except Exception as e:
    print(f"⚠️  OLED Display not available: {e}")
    OLED_AVAILABLE = False

# --- Fingerprint Sensor Setup ---
try:
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=2)
    finger = Adafruit_Fingerprint(uart)
    FINGERPRINT_AVAILABLE = True
    print("✅ Fingerprint sensor initialized")
except Exception as e:
    print(f"⚠️  Fingerprint sensor not available: {e}")
    FINGERPRINT_AVAILABLE = False

# ==================== OLED DISPLAY ====================

def display_oled(line1, line2="", line3="", invert_header=False):
    """Display message on OLED in compact form"""
    if not OLED_AVAILABLE:
        return
    try:
        with canvas(device) as draw:
            if invert_header:
                draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
                draw.text((5, 2), line1[:18], fill="black")
                draw.line([(0, 15), (127, 15)], fill="white", width=1)
                draw.text((5, 22), line2[:21], fill="white")
                draw.text((5, 40), line3[:21], fill="white")
            else:
                draw.rectangle(device.bounding_box, outline="white")
                draw.text((5, 10), line1[:21], fill="white")
                draw.text((5, 28), line2[:21], fill="white")
                draw.text((5, 46), line3[:21], fill="white")
    except Exception:
        pass

# ==================== FINGERPRINT HELPERS ====================

def _wait_for_finger(timeout_sec=12):
    """Wait until a finger is placed. Returns True/False."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if finger.get_image() == 0:
            return True
        time.sleep(0.1)
    return False

def _wait_for_removal(timeout_sec=6):
    """Wait until finger is lifted."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if finger.get_image() != 0:
            time.sleep(0.3)   # debounce
            return
        time.sleep(0.1)

def _raw_match_buffers():
    """
    Send R307 Match command (0x03) directly over UART.
    Compares CharBuffer1 vs CharBuffer2.
    Returns score (int 0-200) or None on error.
    Used as fallback when finger_search() fails.
    """
    try:
        pkt_id   = 0x01
        length   = 0x0003
        cmd      = 0x03
        checksum = pkt_id + (length >> 8) + (length & 0xFF) + cmd

        packet = (
            struct.pack('>H', START_CODE) +
            struct.pack('>I', R307_ADDR)  +
            struct.pack('>B', pkt_id)     +
            struct.pack('>H', length)     +
            struct.pack('>B', cmd)        +
            struct.pack('>H', checksum)
        )

        uart.reset_input_buffer()
        uart.write(packet)
        time.sleep(0.15)

        response = uart.read(14)
        if len(response) < 14:
            return None

        confirm_code = response[9]
        score        = struct.unpack('>H', response[10:12])[0]

        if confirm_code == 0x00:
            return score
        elif confirm_code == 0x08:
            return 0      # Buffers don't match
        return None

    except Exception:
        return None

def _confidence_label(score):
    """Return status string for a confidence score."""
    if score is None:
        return "❓ Unknown"
    if score <= FP_MIN_CONFIDENCE:
        return f"🔴 POOR ({score}/200)"
    if score <= FP_WARN_CONFIDENCE:
        return f"🟡 WEAK ({score}/200)"
    if score <= 150:
        return f"🟢 GOOD ({score}/200)"
    return f"✅ EXCELLENT ({score}/200)"

# ==================== CORE MERGE LOGIC ====================

def _run_merge():
    """
    Phase 1: Perform 4-scan iterative merge.
    After success, CharBuffer1 holds the final merged template.

    Returns (success: bool, merge_log: list of (scan, attempt, code))

    Re-anchor strategy: if a scan is rejected 3+ times in a row,
    re-capture CharBuffer1 from a fresh scan to reset the base.
    This addresses the R307's ~70-80% similarity gate issue.
    """
    merge_log = []

    # ── Scan 1: capture base into CharBuffer1 ──
    print(f"\n📌 SCAN 1/{FP_NUM_SCANS}: Place finger on sensor...")
    display_oled("SCAN 1 of 4", "Place finger")

    ok = False
    for attempt in range(1, FP_MAX_RETRIES + 1):
        if not _wait_for_finger():
            print(f"   ⏱️  Timeout (attempt {attempt}/{FP_MAX_RETRIES})")
            display_oled("TIMEOUT", f"Try {attempt}/{FP_MAX_RETRIES}")
            continue

        code = finger.image_2_tz(1)
        if code == 0:
            print("   ✅ Scan 1 captured → CharBuffer1")
            display_oled("SCAN 1 of 4", "Captured!")
            _wait_for_removal()
            ok = True
            break

        print(f"   ❌ Bad image (code {hex(code)}), retry...")
        display_oled("Bad Image", f"Try {attempt}/{FP_MAX_RETRIES}")
        _wait_for_removal()
        time.sleep(0.5)

    if not ok:
        print("❌ Failed to capture scan 1")
        display_oled("FAILED", "Scan 1 failed")
        return False, merge_log

    # ── Scans 2-4: capture into CharBuffer2, merge into CharBuffer1 ──
    for scan_num in range(2, FP_NUM_SCANS + 1):
        scan_ok       = False
        consec_reject = 0     # consecutive rejection counter for re-anchor trigger

        for attempt in range(1, FP_MAX_RETRIES + 1):
            print(f"\n📌 SCAN {scan_num}/{FP_NUM_SCANS}: Remove finger, then place again...")
            display_oled(f"SCAN {scan_num} of 4", "Remove finger")
            _wait_for_removal()
            time.sleep(0.5)

            display_oled(f"SCAN {scan_num} of 4", "Place finger")
            if not _wait_for_finger():
                print(f"   ⏱️  Timeout (attempt {attempt}/{FP_MAX_RETRIES})")
                display_oled("TIMEOUT", f"Retry {attempt}/{FP_MAX_RETRIES}")
                continue

            # Capture into CharBuffer2
            img_code = finger.image_2_tz(2)
            if img_code != 0:
                print(f"   ❌ Bad image (code {hex(img_code)}), retry...")
                display_oled("Bad Image", f"Retry {attempt}/{FP_MAX_RETRIES}")
                _wait_for_removal()
                time.sleep(0.5)
                continue

            # Merge CharBuffer1 + CharBuffer2 → updated CharBuffer1
            display_oled(f"SCAN {scan_num} of 4", "Merging...")
            merge_code = finger.create_model()
            merge_log.append((scan_num, attempt, merge_code))

            if merge_code == 0:
                print(f"   ✅ Scan {scan_num} merged successfully")
                display_oled(f"SCAN {scan_num} of 4", "Success!")
                _wait_for_removal()
                consec_reject = 0
                scan_ok = True
                break

            elif merge_code == 0x0A:
                # Sensor's internal similarity gate rejected the merge
                consec_reject += 1
                print(f"   ⚠️  Merge rejected — similarity too low (attempt {attempt}/{FP_MAX_RETRIES})")
                print(f"      Tip: Press more firmly, centre finger on sensor")
                display_oled("No Match", f"Retry {attempt}/{FP_MAX_RETRIES}")
                _wait_for_removal()

                # ── Re-anchor: refresh CharBuffer1 after 3 consecutive rejects ──
                # Repeated rejections can mean CharBuffer1 drifted from partial
                # merges. Re-capturing a fresh scan resets the base template.
                if consec_reject >= 3:
                    print(f"\n   🔄 Re-anchoring base (3 rejects in a row)...")
                    print(f"   📌 Place finger for re-anchor scan...")
                    display_oled("RE-ANCHOR", "Place finger")
                    if _wait_for_finger(timeout_sec=10):
                        reanchor_code = finger.image_2_tz(1)
                        if reanchor_code == 0:
                            print("      ✅ CharBuffer1 re-anchored with fresh scan")
                            display_oled("Re-anchored", "Try again")
                        else:
                            print(f"      ⚠️  Re-anchor image bad (code {hex(reanchor_code)})")
                        _wait_for_removal()
                    consec_reject = 0   # Reset counter after re-anchor attempt
                time.sleep(0.8)

            else:
                print(f"   ❌ Merge error (code {hex(merge_code)}), retry...")
                display_oled("Merge Error", f"Code {hex(merge_code)}")
                _wait_for_removal()
                time.sleep(0.5)

        if not scan_ok:
            print(f"❌ Failed scan {scan_num} after {FP_MAX_RETRIES} attempts")
            display_oled("FAILED", f"Scan {scan_num} failed")
            time.sleep(2)
            return False, merge_log

    print("\n✅ All 4 scans merged — CharBuffer1 has final template")
    return True, merge_log

def _run_self_match_verify():
    """
    Phase 2: Self-match verification.
    CharBuffer1 already has the merged template — store it to TEMP_SLOT,
    then scan the same finger and check confidence via finger_search().
    Falls back to raw 1:1 UART match if search fails.

    Returns confidence score (int) or None on total failure.
    """
    print("\n💾 Storing merged template to temp slot for verification...")
    display_oled("VERIFYING...", "Storing temp")

    store_code = finger.store_model(FP_TEMP_SLOT, 1)
    if store_code != 0:
        print(f"   ⚠️  store_model failed (code {hex(store_code)}) — trying 1:1 compare fallback")
        return _run_11_compare_fallback()

    print(f"   ✅ Template stored in slot {FP_TEMP_SLOT}")
    time.sleep(0.5)

    print("\n🔍 Scan SAME finger again to verify merge quality...")
    display_oled("VERIFY SCAN", "Same finger")

    for attempt in range(1, 4):
        if not _wait_for_finger():
            print(f"   ⏱️  Timeout on verify (attempt {attempt}/3)")
            continue

        img_code = finger.image_2_tz(1)
        if img_code != 0:
            print(f"   ❌ Bad image (code {hex(img_code)})")
            _wait_for_removal()
            continue

        search_code = finger.finger_search()
        _wait_for_removal()

        if search_code == 0:
            score = finger.confidence
            slot  = finger.finger_id
            print(f"   ✅ Self-match: slot {slot}, confidence {score}/200")
            return score
        else:
            print(f"   ⚠️  finger_search failed (code {hex(search_code)}) — trying 1:1 fallback")
            return _run_11_compare_fallback()

    return None

def _run_11_compare_fallback():
    """
    Fallback: Load template from TEMP_SLOT into CharBuffer1,
    scan new finger into CharBuffer2, run raw 0x03 Match command.
    Returns score or None.
    """
    print("\n   🔁 Fallback: 1:1 buffer compare (raw UART Match 0x03)...")
    display_oled("FALLBACK", "1:1 Compare")

    load_code = finger.load_model(FP_TEMP_SLOT, 1)
    if load_code != 0:
        print(f"   ❌ load_model failed (code {hex(load_code)})")
        return None

    print("   📌 Place same finger for 1:1 compare...")
    display_oled("1:1 COMPARE", "Place finger")

    for attempt in range(1, 4):
        if not _wait_for_finger():
            continue

        img_code = finger.image_2_tz(2)
        if img_code != 0:
            print(f"   ❌ Bad image (code {hex(img_code)})")
            _wait_for_removal()
            continue

        score = _raw_match_buffers()
        _wait_for_removal()

        if score is not None:
            print(f"   ✅ 1:1 match score: {score}/200")
            return score

    print("   ❌ 1:1 compare also failed")
    return None

def _cleanup_temp_slot():
    """Remove the temporary sensor flash slot."""
    try:
        code = finger.delete_model(FP_TEMP_SLOT)
        if code == 0:
            print(f"   🗑️  Temp slot {FP_TEMP_SLOT} cleaned up")
        else:
            print(f"   ⚠️  Could not delete slot {FP_TEMP_SLOT} (code {hex(code)})")
    except Exception as e:
        print(f"   ⚠️  Cleanup error: {e}")

def _print_merge_report(merge_log, confidence):
    """Print a concise merge quality summary."""
    print("\n" + "─"*50)
    print("  MERGE QUALITY REPORT")
    print("─"*50)

    # Rejection stats
    total   = len(merge_log)
    rejects = sum(1 for _, _, c in merge_log if c == 0x0A)
    if total > 0:
        pct = rejects / total * 100
        print(f"  Merge rejections : {rejects}/{total} ({pct:.0f}%)")
        if pct > 60:
            print("  ⚠️  High rejection rate — sensor may be dirty or dry finger")

    # Confidence
    print(f"  Self-match score : {_confidence_label(confidence)}")

    # Verdict
    print()
    if confidence is None:
        verdict = "❓ INCONCLUSIVE — could not verify template"
    elif confidence <= FP_MIN_CONFIDENCE:
        verdict = "🔴 POOR — template rejected, re-enroll recommended"
    elif confidence <= FP_WARN_CONFIDENCE:
        verdict = "🟡 WEAK — saved with warning, monitor for false rejects"
    elif confidence <= 150:
        verdict = "🟢 GOOD — template healthy, safe to store"
    else:
        verdict = "✅ EXCELLENT — perfect merge"

    print(f"  Verdict          : {verdict}")
    print("─"*50)

# ==================== MAIN SCAN FUNCTION ====================

def scan_fingerprint():
    """
    Full 4-scan merge with self-match quality verification.
    Returns:
      - template bytes on success (confidence ≥ FP_MIN_CONFIDENCE)
      - None on failure or poor quality rejection
    """
    if not FINGERPRINT_AVAILABLE:
        print("❌ Fingerprint sensor not available")
        display_oled("ERROR", "No sensor")
        return None

    try:
        print("\n--- Starting 4-Scan Fingerprint Registration (v2) ---")
        display_oled("FINGERPRINT", "4 scans needed")
        time.sleep(1.5)

        # ── Phase 1: Merge ──
        success, merge_log = _run_merge()

        if not success:
            display_oled("FAILED", "Merge failed")
            time.sleep(2)
            return None

        # ── Phase 2: Self-match verification ──
        display_oled("VERIFYING", "Self-match...")
        confidence = _run_self_match_verify()

        # ── Phase 3: Cleanup temp slot ──
        _cleanup_temp_slot()

        # ── Phase 4: Report ──
        _print_merge_report(merge_log, confidence)

        # ── Phase 5: Decision based on confidence ──
        if confidence is not None and confidence <= FP_MIN_CONFIDENCE:
            print(f"\n❌ Template quality too poor (score={confidence}) — NOT saving")
            print("   Please re-enroll: press finger flat and firmly each scan")
            display_oled("REJECTED", f"Score:{confidence}", "Re-enroll")
            time.sleep(3)
            return None

        if confidence is not None and confidence <= FP_WARN_CONFIDENCE:
            print(f"\n⚠️  Weak template (score={confidence}) — saving with warning")
            display_oled("WEAK TEMPLATE", f"Score:{confidence}", "Saved anyway")
            time.sleep(2)

        # ── Phase 6: Download template from CharBuffer1 ──
        # Re-load from TEMP_SLOT back into CharBuffer1 since verify scan
        # may have overwritten it — store_model saved it safely
        print("\n💾 Downloading final template...")
        display_oled("SAVING...", "Downloading")

        load_back = finger.load_model(FP_TEMP_SLOT, 1)
        if load_back == 0:
            template = finger.get_fpdata("char", 1)
        else:
            # store_model already saved it; get_fpdata still reads CharBuffer1
            template = finger.get_fpdata("char", 1)

        if not template:
            print("❌ Failed to download template")
            display_oled("ERROR", "Download failed")
            time.sleep(2)
            return None

        print(f"✅ Template downloaded — {len(template)} bytes")
        print(f"✅ Fingerprint registered! (confidence: {confidence}/200)")
        display_oled("SUCCESS!", f"Score:{confidence}", "FP captured")
        time.sleep(1)
        return template

    except Exception as e:
        print(f"❌ Fingerprint error: {e}")
        display_oled("ERROR", str(e)[:21])
        return None

# ==================== UTILITY FUNCTIONS ====================

def print_header(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def print_section(title):
    print("\n" + "-"*70)
    print(f"  {title}")
    print("-"*70)

def get_input(prompt, required=True, validation=None):
    while True:
        value = input(f"{prompt}: ").strip()
        if not value and not required:
            return None
        if not value and required:
            print("❌ This field is required. Please try again.")
            continue
        if validation:
            valid, message = validation(value)
            if not valid:
                print(f"❌ {message}")
                continue
        return value

def validate_dept_code(code):
    code = code.upper()
    if code in DEPT_MAP:
        return True, None
    return False, f"Invalid department code. Valid codes: {', '.join(DEPT_MAP.keys())}"

def validate_prog_code(code):
    code = code.upper()
    if code in PROG_MAP:
        return True, None
    return False, f"Invalid program code. Valid codes: {', '.join(PROG_MAP.keys())}"

def validate_year(year):
    try:
        y = int(year)
        if 2000 <= y <= 2100:
            return True, None
        return False, "Year must be between 2000 and 2100"
    except:
        return False, "Year must be a valid number"

def validate_email(email):
    if '@' in email and '.' in email:
        return True, None
    return False, "Invalid email format"

# ==================== PROFESSOR REGISTRATION ====================

def register_professor():
    print_header("PROFESSOR REGISTRATION")
    display_oled("ADMIN CONSOLE", "Prof Registration", invert_header=True)

    print("\n📝 Enter professor details manually")

    try:
        display_oled("INPUT", "Enter Prof ID")
        prof_id = get_input("Professor ID (e.g., PROF001)").upper()
        display_oled("PROF ID", prof_id)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT prof_id FROM profs WHERE prof_id=?", (prof_id,))
        if cursor.fetchone():
            print(f"\n❌ Error: Professor ID '{prof_id}' already exists")
            display_oled("ERROR", f"{prof_id} exists")
            conn.close()
            return
        conn.close()

        display_oled("INPUT", "Enter Name")
        prof_name = get_input("Full Name (e.g., John Smith)").title()
        display_oled("NAME", prof_name[:21])

        print("\nAvailable Departments:")
        for code, name in DEPT_MAP.items():
            print(f"  {code} - {name}")

        display_oled("INPUT", "Enter Dept Code")
        dept_code = get_input("Department Code", validation=validate_dept_code).upper()
        display_oled("DEPT", DEPT_MAP[dept_code][:21])

        display_oled("INPUT", "Email (optional)")
        email = get_input("Email (optional)", required=False,
                          validation=lambda x: validate_email(x) if x else (True, None))
        if email:
            display_oled("EMAIL", email[:21])

        print_section("SUMMARY")
        print(f"Professor ID:  {prof_id}")
        print(f"Name:          {prof_name}")
        print(f"Department:    {DEPT_MAP[dept_code]} ({dept_code})")
        if email:
            print(f"Email:         {email}")

        display_oled("SUMMARY", prof_id, prof_name[:21])
        confirm = input("\n✅ Save this professor? (yes/no): ").lower()

        if confirm in ['yes', 'y']:
            print("\n🔐 Now registering fingerprint...")
            display_oled("FINGERPRINT", "Starting scan")
            time.sleep(1)

            template = scan_fingerprint()

            if not template:
                print("\n⚠️  Fingerprint registration failed or rejected")
                retry = input("Would you like to save without fingerprint? (yes/no): ").lower()
                if retry not in ['yes', 'y']:
                    print("❌ Registration cancelled")
                    display_oled("CANCELLED", "Not saved")
                    return
                template = b'\x00' * 512
                print("⚠️  Using placeholder fingerprint")

            display_oled("SAVING...", "To database")

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO profs (prof_id, name, template, dept_code, email) 
                VALUES (?, ?, ?, ?, ?)
            """, (prof_id, prof_name, sqlite3.Binary(bytearray(template)), dept_code, email))
            conn.commit()
            conn.close()

            print("\n✅ Professor registered successfully!")
            if len(template) > 512:
                print("✅ Fingerprint registered successfully!")
            else:
                print("⚠️  Fingerprint NOT registered - using placeholder")
            display_oled("SUCCESS!", prof_id, "Prof registered")
        else:
            print("\n❌ Registration cancelled")
            display_oled("CANCELLED", "Not saved")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

# ==================== STUDENT REGISTRATION ====================

def register_student():
    print_header("STUDENT REGISTRATION")
    display_oled("ADMIN CONSOLE", "Student Register", invert_header=True)

    print("\n📝 Enter student details manually")

    try:
        print("\nAvailable Departments:")
        for code, name in DEPT_MAP.items():
            print(f"  {code} - {name}")

        display_oled("INPUT", "Enter Dept Code")
        dept_code = get_input("Department Code", validation=validate_dept_code).upper()
        dept_name = DEPT_MAP[dept_code]
        display_oled("DEPT", dept_name[:21])

        print("\nAvailable Programs:")
        for code, name in PROG_MAP.items():
            print(f"  {code} - {name}")

        display_oled("INPUT", "Enter Prog Code")
        prog_code = get_input("Program Code", validation=validate_prog_code).upper()
        prog_name = PROG_MAP[prog_code]
        display_oled("PROGRAM", prog_name[:21])

        display_oled("INPUT", "Enter Year")
        batch_year = get_input("Batch Year (e.g., 2023)", validation=validate_year)
        year_short = batch_year[2:4]
        display_oled("YEAR", batch_year)

        display_oled("INPUT", "Last 3 digits")
        roll_suffix = get_input("Last 3 digits of Roll No (e.g., 037)")

        if len(roll_suffix) != 3 or not roll_suffix.isdigit():
            print("❌ Error: Roll suffix must be exactly 3 digits")
            display_oled("ERROR", "Need 3 digits")
            return

        roll_no = f"{dept_code}{year_short}{prog_code}{roll_suffix}"
        print(f"\n✅ Generated Roll Number: {roll_no}")
        display_oled("ROLL NUMBER", roll_no)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
        if cursor.fetchone():
            print(f"❌ Error: Student ID '{roll_no}' already exists")
            display_oled("ERROR", f"{roll_no} exists")
            conn.close()
            return
        conn.close()

        display_oled("INPUT", "First Name")
        first_name = get_input("First Name").title()
        display_oled("INPUT", "Last Name")
        last_name = get_input("Last Name").title()
        display_oled("NAME", f"{first_name} {last_name}"[:21])

        display_oled("INPUT", "Password")
        password = get_input("Password (numeric)")

        display_oled("INPUT", "Email (optional)")
        email = get_input("Email (optional)", required=False,
                          validation=lambda x: validate_email(x) if x else (True, None))

        print_section("SUMMARY")
        print(f"Student ID:    {roll_no}")
        print(f"Name:          {first_name} {last_name}")
        print(f"Department:    {dept_name}")
        print(f"Program:       {prog_name}")
        print(f"Batch Year:    {batch_year}")
        print(f"Password:      {'*' * len(password)}")
        if email:
            print(f"Email:         {email}")

        display_oled("SUMMARY", roll_no, f"{first_name} {last_name}"[:21])
        confirm = input("\n✅ Save this student? (yes/no): ").lower()

        if confirm in ['yes', 'y']:
            print("\n🔐 Now registering fingerprint...")
            display_oled("FINGERPRINT", "Starting scan")
            time.sleep(1)

            template = scan_fingerprint()

            if not template:
                print("\n⚠️  Fingerprint registration failed or rejected")
                retry = input("Would you like to save without fingerprint? (yes/no): ").lower()
                if retry not in ['yes', 'y']:
                    print("❌ Registration cancelled")
                    display_oled("CANCELLED", "Not saved")
                    return
                template = b'\x00' * 512
                print("⚠️  Using placeholder fingerprint")

            display_oled("SAVING...", "To database")

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template, email) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (roll_no, first_name, last_name, password, dept_name, int(batch_year),
                  prog_name, sqlite3.Binary(bytearray(template)), email))
            conn.commit()
            conn.close()

            print("\n✅ Student registered successfully!")
            if len(template) > 512:
                print("✅ Fingerprint registered successfully!")
            else:
                print("⚠️  Fingerprint NOT registered - using placeholder")
            display_oled("SUCCESS!", roll_no, "Student saved")
        else:
            print("\n❌ Registration cancelled")
            display_oled("CANCELLED", "Not saved")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

# ==================== COURSE MANAGEMENT ====================

def add_course():
    print_header("COURSE ADDITION")
    display_oled("ADMIN CONSOLE", "Add Course", invert_header=True)
    print("\n📚 Enter course details")

    try:
        display_oled("INPUT", "Course Code")
        course_code = get_input("Course Code (e.g., CS101)").upper()
        display_oled("COURSE", course_code)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT course_code FROM courses WHERE course_code=?", (course_code,))
        if cursor.fetchone():
            print(f"\n❌ Error: Course '{course_code}' already exists")
            display_oled("ERROR", f"{course_code} exists")
            conn.close()
            return

        display_oled("INPUT", "Course Name")
        course_name = get_input("Course Name (e.g., Introduction to Programming)").title()
        display_oled("NAME", course_name[:21])

        cursor.execute("SELECT prof_id, name, dept_code FROM profs ORDER BY prof_id")
        profs = cursor.fetchall()

        if not profs:
            print("\n❌ Error: No professors registered in the system")
            display_oled("ERROR", "No professors")
            conn.close()
            return

        print("\nAvailable Professors:")
        for prof_id, name, dept in profs:
            print(f"  {prof_id} - {name} ({DEPT_MAP.get(dept, dept)})")

        display_oled("INPUT", "Professor ID")
        prof_id = get_input("Professor ID")

        cursor.execute("SELECT name FROM profs WHERE prof_id=?", (prof_id,))
        prof = cursor.fetchone()
        if not prof:
            print(f"❌ Error: Professor '{prof_id}' not found")
            display_oled("ERROR", "Prof not found")
            conn.close()
            return

        display_oled("PROF", prof[0][:21])

        print("\nCourse Department:")
        for code, name in DEPT_MAP.items():
            print(f"  {code} - {name}")

        display_oled("INPUT", "Dept Code")
        dept_code = get_input("Department Code", validation=validate_dept_code).upper()
        display_oled("DEPT", DEPT_MAP[dept_code][:21])

        semester  = get_input("Semester (e.g., Fall 2024)", required=False)
        year      = get_input("Academic Year (e.g., 2024)", required=False)
        time_slot = get_input("Time Slot (e.g., Mon/Wed 10:00-11:30)", required=False)

        print_section("SUMMARY")
        print(f"Course Code:   {course_code}")
        print(f"Course Name:   {course_name}")
        print(f"Professor:     {prof[0]} ({prof_id})")
        print(f"Department:    {DEPT_MAP[dept_code]}")
        if semester:  print(f"Semester:      {semester}")
        if year:      print(f"Year:          {year}")
        if time_slot: print(f"Time Slot:     {time_slot}")

        display_oled("SUMMARY", course_code, course_name[:21])
        confirm = input("\n✅ Save this course? (yes/no): ").lower()

        if confirm in ['yes', 'y']:
            display_oled("SAVING...", "Please wait")
            cursor.execute("""
                INSERT INTO courses (course_code, course_name, prof_id, dept_code, semester, year, time_slot) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (course_code, course_name, prof_id, dept_code, semester, year, time_slot))
            conn.commit()
            conn.close()
            print("\n✅ Course added successfully!")
            display_oled("SUCCESS!", course_code, "Course added")
        else:
            print("\n❌ Course addition cancelled")
            display_oled("CANCELLED", "Not saved")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

def enroll_student_in_course():
    print_header("STUDENT COURSE ENROLLMENT")
    display_oled("ADMIN CONSOLE", "Enroll Student", invert_header=True)

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        display_oled("INPUT", "Student ID")
        student_id = get_input("Student ID (e.g., EE23BT037)").upper()
        display_oled("STUDENT", student_id)

        cursor.execute("SELECT first_name, last_name, dept FROM students WHERE student_id=?", (student_id,))
        student = cursor.fetchone()
        if not student:
            print(f"❌ Error: Student '{student_id}' not found")
            display_oled("ERROR", "Not found")
            conn.close()
            return

        student_name = f"{student[0]} {student[1]}"
        print(f"\n✅ Student Found: {student_name} ({student[2]})")
        display_oled("FOUND", student_name[:21])

        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name 
            FROM courses c JOIN profs p ON c.prof_id = p.prof_id
            ORDER BY c.course_code
        """)
        courses = cursor.fetchall()

        if not courses:
            print("\n❌ Error: No courses available")
            display_oled("ERROR", "No courses")
            conn.close()
            return

        print("\nAvailable Courses:")
        for code, name, prof in courses:
            print(f"  {code} - {name} (Prof. {prof})")

        display_oled("INPUT", "Course Code")
        course_code = get_input("Course Code to enroll in").upper()

        cursor.execute("SELECT course_name FROM courses WHERE course_code=?", (course_code,))
        course = cursor.fetchone()
        if not course:
            print(f"❌ Error: Course '{course_code}' not found")
            display_oled("ERROR", "Course not found")
            conn.close()
            return

        cursor.execute("""
            SELECT enrollment_id FROM course_enrollments 
            WHERE student_id=? AND course_code=?
        """, (student_id, course_code))
        if cursor.fetchone():
            print(f"\n❌ Error: {student_name} is already enrolled in {course_code}")
            display_oled("ERROR", "Already enrolled")
            conn.close()
            return

        print_section("ENROLLMENT SUMMARY")
        print(f"Student:       {student_name} ({student_id})")
        print(f"Course:        {course[0]} ({course_code})")
        display_oled("ENROLLING", student_id, course_code)
        confirm = input("\n✅ Confirm enrollment? (yes/no): ").lower()

        if confirm in ['yes', 'y']:
            display_oled("SAVING...", "Please wait")
            cursor.execute("""
                INSERT INTO course_enrollments (student_id, course_code, status)
                VALUES (?, ?, 'active')
            """, (student_id, course_code))
            conn.commit()
            conn.close()
            print("\n✅ Student enrolled successfully!")
            display_oled("SUCCESS!", student_id, f"→ {course_code}")
        else:
            print("\n❌ Enrollment cancelled")
            display_oled("CANCELLED", "Not saved")
            conn.close()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

def delete_student():
    print_header("DELETE STUDENT")
    display_oled("ADMIN CONSOLE", "Delete Student", invert_header=True)

    print("\n⚠️  WARNING: This will permanently delete the student and all related data!")

    try:
        display_oled("INPUT", "Enter Roll No")
        student_id = get_input("Student Roll Number (e.g., EE23BT037)").upper()
        display_oled("SEARCHING", student_id)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_name, last_name, dept, year, program 
            FROM students WHERE student_id=?
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            print(f"\n❌ Error: Student '{student_id}' not found")
            display_oled("ERROR", "Not found", student_id)
            conn.close()
            time.sleep(2)
            return

        first_name, last_name, dept, year, program = student
        student_name = f"{first_name} {last_name}"

        cursor.execute("SELECT COUNT(*) FROM course_enrollments WHERE student_id=?", (student_id,))
        enrollment_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (student_id,))
        attendance_count = cursor.fetchone()[0]

        print_section("STUDENT DETAILS")
        print(f"Roll Number:   {student_id}")
        print(f"Name:          {student_name}")
        print(f"Department:    {dept}")
        print(f"Program:       {program}")
        print(f"Batch Year:    {year}")
        print(f"Enrollments:   {enrollment_count} courses")
        print(f"Attendance:    {attendance_count} records")

        display_oled("FOUND", student_name[:21], student_id)
        time.sleep(2)

        print("\n⚠️  ARE YOU SURE?")
        display_oled("CONFIRM?", "Delete student?", "yes/no")
        confirm = input("Type 'DELETE' to confirm deletion: ").strip()

        if confirm == "DELETE":
            display_oled("DELETING...", "Please wait")
            cursor.execute("DELETE FROM students WHERE student_id=?", (student_id,))
            conn.commit()
            conn.close()
            print(f"\n✅ Student '{student_name}' ({student_id}) deleted successfully")
            print(f"   • {enrollment_count} course enrollments removed")
            print(f"   • {attendance_count} attendance records removed")
            display_oled("DELETED!", student_id, "All data removed")
            time.sleep(3)
        else:
            print("\n❌ Deletion cancelled - student data preserved")
            display_oled("CANCELLED", "Not deleted")
            conn.close()
            time.sleep(2)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])
        time.sleep(2)

def view_all_data():
    print_header("SYSTEM DATA OVERVIEW")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM profs")
        prof_count = cursor.fetchone()[0]
        cursor.execute("SELECT prof_id, name, dept_code FROM profs ORDER BY prof_id")
        profs = cursor.fetchall()

        print_section(f"PROFESSORS ({prof_count})")
        if profs:
            for prof_id, name, dept in profs:
                print(f"  {prof_id}: {name} - {DEPT_MAP.get(dept, dept)}")
        else:
            print("  No professors registered")

        cursor.execute("SELECT COUNT(*) FROM students")
        student_count = cursor.fetchone()[0]
        cursor.execute("SELECT student_id, first_name, last_name, dept FROM students ORDER BY student_id LIMIT 10")
        students = cursor.fetchall()

        print_section(f"STUDENTS ({student_count})")
        if students:
            for sid, fname, lname, dept in students:
                print(f"  {sid}: {fname} {lname} - {dept}")
            if student_count > 10:
                print(f"  ... and {student_count - 10} more students")
        else:
            print("  No students registered")

        cursor.execute("SELECT COUNT(*) FROM courses")
        course_count = cursor.fetchone()[0]
        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name 
            FROM courses c JOIN profs p ON c.prof_id = p.prof_id
            ORDER BY c.course_code
        """)
        courses = cursor.fetchall()

        print_section(f"COURSES ({course_count})")
        if courses:
            for code, name, prof in courses:
                cursor.execute("""
                    SELECT COUNT(*) FROM course_enrollments 
                    WHERE course_code=? AND status='active'
                """, (code,))
                enrollment = cursor.fetchone()[0]
                print(f"  {code}: {name} - Prof. {prof} ({enrollment} students)")
        else:
            print("  No courses added")

        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) FROM attendance 
            WHERE date(session_date) = date('now', 'localtime')
        """)
        today_attendance = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM attendance")
        total_attendance = cursor.fetchone()[0]

        print_section("ATTENDANCE RECORDS")
        print(f"  Today's Attendance: {today_attendance} students")
        print(f"  Total Records:      {total_attendance}")

        conn.close()

    except Exception as e:
        print(f"\n❌ Error: {e}")

# ==================== MAIN MENU ====================

def main_menu():
    while True:
        print_header("IITDH BIOMETRIC ATTENDANCE - ADMIN CONSOLE")
        display_oled("ADMIN CONSOLE", "Ready", "Select option", invert_header=True)

        print("\n📋 Administrative Options:")
        print("  1. Register Professor (with Fingerprint)")
        print("  2. Register Student (with Fingerprint)")
        print("  3. Add Course")
        print("  4. Enroll Student in Course")
        print("  5. Delete Student")
        print("  6. View All System Data")
        print("  7. Exit")

        choice = input("\n👉 Select option (1-7): ").strip()

        if choice == '1':   register_professor()
        elif choice == '2': register_student()
        elif choice == '3': add_course()
        elif choice == '4': enroll_student_in_course()
        elif choice == '5': delete_student()
        elif choice == '6': view_all_data()
        elif choice == '7':
            print("\n" + "="*70)
            print("  👋 Goodbye! Have a great day!")
            print("="*70 + "\n")
            display_oled("GOODBYE", "System exit")
            break
        else:
            print("\n❌ Invalid choice. Please select 1-7")
            display_oled("ERROR", "Invalid choice")

        input("\n⏎ Press Enter to continue...")

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  IITDH BIOMETRIC ATTENDANCE SYSTEM")
    print("  Administrative Console - v2 Merge Quality Check")
    print("="*70)
    print("\n📝 FEATURES:")
    print("  • 4-scan merge with re-anchor on repeated rejections")
    print("  • Self-match confidence verification after every enrollment")
    print(f"  • Auto-reject if confidence < {FP_MIN_CONFIDENCE}/200")
    print(f"  • Warn if confidence < {FP_WARN_CONFIDENCE}/200")
    print("  • Raw UART 1:1 compare fallback")
    print("  • OLED display feedback")
    print("\n💾 Database: " + DB_PATH)

    if FINGERPRINT_AVAILABLE:
        print("✅ Fingerprint sensor: Available")
    else:
        print("⚠️  Fingerprint sensor: Not available (will use placeholders)")

    if OLED_AVAILABLE:
        print("✅ OLED display: Available")
        display_oled("IITDH ADMIN", "Initializing...", invert_header=True)
    else:
        print("⚠️  OLED display: Not available")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.close()
        print("✅ Database connection: Successful\n")

        if OLED_AVAILABLE:
            display_oled("ADMIN CONSOLE", "DB Connected", "Ready", invert_header=True)

        input("⏎ Press Enter to start...")
        main_menu()

    except Exception as e:
        print(f"\n❌ Error connecting to database: {e}")
        print("\n💡 TIP: Run 'python3 setup_database.py' first to create the database")
        if OLED_AVAILABLE:
            display_oled("ERROR", "DB not found")
        sys.exit(1)