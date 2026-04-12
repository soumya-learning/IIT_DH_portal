#!/usr/bin/env python3
"""
IITDH Attendance System — R307s On-Pi Fingerprint Tool
=======================================================
Standalone diagnostic and enrollment tool using on-Pi numpy matching.

HOW IT WORKS:
  Sensor  → captures image → converts to 512-byte char buffer (hardware)
  Pi      → downloads buffer → numpy cosine similarity matching (software)

This gives better accuracy than on-sensor matching because:
  - Weighted multi-sample merge during enrollment
  - Cosine similarity ignores finger pressure variation
  - Threshold tunable without re-enrolling

IMPORTANT — Run ONLY when main attendance code is NOT running.
Both scripts use /dev/ttyAMA0 and cannot share the port.

WIRING (same as main code):
  R307s VCC → Pi Pin 1  (3.3 V)
  R307s GND → Pi Pin 6  (GND)
  R307s TX  → Pi Pin 10 (RXD / GPIO15)  ← /dev/ttyAMA0
  R307s RX  → Pi Pin 8  (TXD / GPIO14)

INSTALL:
  pip install pyserial numpy
"""

import serial
import struct
import time
import sqlite3
import os
import numpy as np

# ─────────────────────────────────────────────
# HARDWARE — import same stack as main code
# ─────────────────────────────────────────────
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas
import RPi.GPIO as GPIO
import smbus

# ─────────────────────────────────────────────
# CONFIG — must match 01marchrunningcode.py
# ─────────────────────────────────────────────

SERIAL_PORT     = "/dev/ttyAMA0"   # ← FIXED: was /dev/serial0 (wrong UART)
BAUD_RATE       = 57600
DB_PATH         = '/home/bio_user_iitdh/new_env/DB/college.db'

# Enrollment: how many scans to merge per finger
ENROLL_SAMPLES  = 3

# Match threshold: 0.0 = strictest, 1.0 = most lenient
MATCH_THRESHOLD = 0.72

# Joystick pins — same as main code
JOYSTICK_UP     = 17
JOYSTICK_DOWN   = 6
JOYSTICK_LEFT   = 22
JOYSTICK_RIGHT  = 23
JOYSTICK_CENTER = 26

# ─────────────────────────────────────────────
# R307 PROTOCOL CONSTANTS
# ─────────────────────────────────────────────

HEADER        = b'\xEF\x01'
ADDR          = b'\xFF\xFF\xFF\xFF'
PID_CMD       = 0x01
PID_DATA      = 0x02
PID_END       = 0x08

CMD_VERIFYPSW = 0x13
CMD_GENIMG    = 0x01
CMD_IMG2TZ    = 0x02
CMD_UPCHAR    = 0x08

ACK_OK        = 0x00
ACK_NO_FINGER = 0x02
ACK_BAD_IMAGE = 0x03

CHAR_BUF_1    = 0x01
CHAR_BUF_2    = 0x02
FEATURE_LEN   = 512


# ─────────────────────────────────────────────
# HARDWARE INIT
# ─────────────────────────────────────────────

def init_display():
    """Initialize SSD1306 OLED — same SPI config as main code."""
    try:
        oled_serial = spi(device=0, port=0, bus_speed_hz=1000000,
                          gpio_DC=25, gpio_RST=27, gpio_CS=8)
        device = ssd1306(oled_serial)
        device.contrast(255)
        return device
    except Exception as e:
        print(f"⚠️  OLED init failed: {e} — running without display")
        return None


def init_gpio():
    GPIO.setmode(GPIO.BCM)
    for pin in [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT,
                JOYSTICK_RIGHT, JOYSTICK_CENTER]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def display_msg(device, line1, line2="", line3=""):
    if device is None:
        print(f"[OLED] {line1} | {line2} | {line3}")
        return
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 10), line1[:20], fill="white")
        draw.text((5, 28), line2[:20], fill="white")
        draw.text((5, 46), line3[:20], fill="white")


def wait_for_button(device=None, debounce=0.3):
    while True:
        if GPIO.input(JOYSTICK_UP) == GPIO.LOW:
            time.sleep(debounce); return "UP"
        if GPIO.input(JOYSTICK_DOWN) == GPIO.LOW:
            time.sleep(debounce); return "DOWN"
        if GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
            time.sleep(debounce); return "CENTER"
        if GPIO.input(JOYSTICK_LEFT) == GPIO.LOW:
            time.sleep(debounce); return "LEFT"
        if GPIO.input(JOYSTICK_RIGHT) == GPIO.LOW:
            time.sleep(debounce); return "RIGHT"
        time.sleep(0.05)


def select_from_list(device, title, options):
    """Joystick-driven list selector — same UX as main code."""
    selected = 0
    scroll_offset = 0
    visible = 3

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible:
            scroll_offset = selected - visible + 1

        if device:
            with canvas(device) as draw:
                draw.rectangle([(0,0),(127,14)], fill="white")
                draw.text((5, 2), title[:18], fill="black")
                draw.line([(0,15),(127,15)], fill="white")
                for i in range(visible):
                    idx = scroll_offset + i
                    if idx >= len(options):
                        break
                    y = 20 + i * 14
                    if idx == selected:
                        draw.rectangle([(2,y),(125,y+12)], fill="white")
                        draw.text((8, y+2), options[idx][:18], fill="black")
                    else:
                        draw.text((8, y+2), options[idx][:18], fill="white")
        else:
            print(f"\n--- {title} ---")
            for i, opt in enumerate(options):
                marker = ">" if i == selected else " "
                print(f"  {marker} {opt}")

        btn = wait_for_button(device)
        if btn == "UP":
            selected = (selected - 1) % len(options)
        elif btn == "DOWN":
            selected = (selected + 1) % len(options)
        elif btn == "CENTER":
            return selected


# ─────────────────────────────────────────────
# R307 PACKET HELPERS
# ─────────────────────────────────────────────

def _checksum(data):
    return sum(data) & 0xFFFF


def send_cmd(ser, cmd, params=b''):
    payload = bytes([cmd]) + params
    length  = len(payload) + 2
    packet  = (HEADER + ADDR +
               bytes([PID_CMD]) +
               struct.pack('>H', length) +
               payload)
    chk     = _checksum(bytes([PID_CMD]) + struct.pack('>H', length) + payload)
    packet += struct.pack('>H', chk)
    ser.write(packet)


def read_ack(ser, timeout=3.0):
    """Read one ACK packet. Returns (confirm_code, extra_bytes)."""
    ser.timeout = timeout
    buf      = b''
    deadline = time.time() + timeout

    # Hunt for EF 01 header
    while time.time() < deadline:
        b = ser.read(1)
        if not b:
            continue
        buf += b
        if buf[-2:] == b'\xef\x01':
            break
    else:
        raise TimeoutError(
            "Sensor silent — check /dev/ttyAMA0 wiring and baud rate"
        )

    header = ser.read(7)
    if len(header) < 7:
        raise IOError("Short header from sensor")

    length       = struct.unpack('>H', header[5:7])[0]
    body         = ser.read(length)
    confirm_code = body[0]
    extra        = body[1:-2]
    return confirm_code, extra


def read_datastream(ser, timeout=5.0):
    """Collect DATA + END packets after CMD_UPCHAR ACK."""
    ser.timeout = timeout
    collected   = b''

    while True:
        buf      = b''
        deadline = time.time() + timeout
        while time.time() < deadline:
            b = ser.read(1)
            if not b:
                continue
            buf += b
            if buf[-2:] == b'\xef\x01':
                break
        else:
            break

        meta = ser.read(7)
        if len(meta) < 7:
            break
        pid    = meta[4]
        length = struct.unpack('>H', meta[5:7])[0]
        chunk  = ser.read(length - 2)
        ser.read(2)        # checksum
        collected += chunk
        if pid == PID_END:
            break

    return collected


# ─────────────────────────────────────────────
# SENSOR CLASS
# ─────────────────────────────────────────────

class R307:
    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        # Flush any stale bytes before opening
        self.ser = serial.Serial(port, baud, timeout=3)
        self.ser.reset_input_buffer()
        time.sleep(0.5)          # give sensor time after port open
        print(f"[SENSOR] Opened {port} at {baud} baud")

    def verify_password(self, password=b'\x00\x00\x00\x00'):
        """Handshake. Default sensor password is 0x00000000."""
        self.ser.reset_input_buffer()
        send_cmd(self.ser, CMD_VERIFYPSW, password)
        code, _ = read_ack(self.ser)
        return code == ACK_OK

    def capture_image(self):
        send_cmd(self.ser, CMD_GENIMG)
        code, _ = read_ack(self.ser)
        return code

    def image_to_char_buffer(self, buf_id=CHAR_BUF_1):
        send_cmd(self.ser, CMD_IMG2TZ, bytes([buf_id]))
        code, _ = read_ack(self.ser)
        return code

    def upload_char_buffer(self, buf_id=CHAR_BUF_1):
        """Download 512-byte char buffer from sensor to Pi."""
        send_cmd(self.ser, CMD_UPCHAR, bytes([buf_id]))
        code, _ = read_ack(self.ser)
        if code != ACK_OK:
            print(f"  [!] UPCHAR failed: 0x{code:02X}")
            return None
        data = read_datastream(self.ser)
        return data if len(data) >= 256 else None

    def wait_for_finger(self, retries=40, delay=0.25):
        for _ in range(retries):
            code = self.capture_image()
            if code == ACK_OK:
                return True
            if code == ACK_NO_FINGER:
                time.sleep(delay)
                continue
            print(f"  [!] Sensor error: 0x{code:02X}")
            return False
        print("  [!] No finger detected (timeout)")
        return False

    def wait_finger_removed(self, retries=20):
        for _ in range(retries):
            if self.capture_image() == ACK_NO_FINGER:
                return
            time.sleep(0.2)

    def close(self):
        self.ser.close()


# ─────────────────────────────────────────────
# ON-PI FEATURE PROCESSING
# ─────────────────────────────────────────────

def buffer_to_vector(raw):
    """512-byte char buffer → normalised float32 numpy vector."""
    arr = np.frombuffer(raw[:FEATURE_LEN], dtype=np.uint8).astype(np.float32)
    if len(arr) < FEATURE_LEN:
        arr = np.pad(arr, (0, FEATURE_LEN - len(arr)))
    return arr / 255.0


def quality_score(vec):
    """Higher std dev = better quality scan (clearer ridge pattern)."""
    return float(np.std(vec))


def merge_vectors(vectors):
    """Weighted average of N enrollment scans → master template."""
    scores  = np.array([quality_score(v) for v in vectors], dtype=np.float32)
    weights = scores / (scores.sum() + 1e-9)
    print(f"\n  [PI] Merging {len(vectors)} samples:")
    for i, (w, s) in enumerate(zip(weights, scores)):
        print(f"       Sample {i+1}: quality={s:.4f}  weight={w:.3f}")
    master = np.zeros(FEATURE_LEN, dtype=np.float32)
    for w, v in zip(weights, vectors):
        master += w * v
    return master


def cosine_similarity(a, b):
    dot  = float(np.dot(a, b))
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return (dot / norm) if norm > 1e-9 else 0.0


def match_probe(probe, template_blob):
    """
    Match probe vector against a raw BLOB from SQLite.
    template_blob: bytes from DB (768 bytes = two 384-byte buffers)
    Uses first 512 bytes for matching (char buffer 1).
    Returns (is_match, score).
    """
    raw = bytes(template_blob)
    if len(raw) < 256:
        return False, 0.0
    # Use first 512 bytes (or however many available up to FEATURE_LEN)
    template_vec = buffer_to_vector(raw[:FEATURE_LEN])
    score        = cosine_similarity(probe, template_vec)
    return score >= MATCH_THRESHOLD, score


# ─────────────────────────────────────────────
# DATABASE — reads/writes college.db (same as main code)
# ─────────────────────────────────────────────

def get_all_students():
    """Return list of (student_id, first_name, last_name, template_blob)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT student_id, first_name, last_name, template FROM students "
        "WHERE template IS NOT NULL AND length(template) > 0"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_profs():
    """Return list of (prof_id, name, template_blob)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT prof_id, name, template FROM profs "
        "WHERE template IS NOT NULL AND length(template) > 0"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_template_to_db(table, id_col, row_id, template_bytes):
    """Write merged numpy template back as BLOB."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE {table} SET template = ? WHERE {id_col} = ?",
        (sqlite3.Binary(template_bytes), row_id)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ENROLLMENT — on-Pi multi-sample merge
# ─────────────────────────────────────────────

def enroll_fingerprint(sensor, device, subject_label="user"):
    """
    Capture ENROLL_SAMPLES scans, merge on Pi, return raw bytes.
    subject_label: shown on OLED during prompts.
    """
    vectors = []

    for i in range(ENROLL_SAMPLES):
        display_msg(device,
                    f"SCAN {i+1}/{ENROLL_SAMPLES}",
                    subject_label[:16],
                    "Place finger")
        print(f"\n  [Sample {i+1}/{ENROLL_SAMPLES}] Place finger...")

        if not sensor.wait_for_finger():
            display_msg(device, "TIMEOUT", "No finger", "Try again")
            return None

        code = sensor.image_to_char_buffer(CHAR_BUF_1)
        if code != ACK_OK:
            display_msg(device, "BAD IMAGE", f"Code 0x{code:02X}", "Retry")
            print(f"  [!] img2tz failed: 0x{code:02X}")
            return None

        raw = sensor.upload_char_buffer(CHAR_BUF_1)
        if raw is None:
            display_msg(device, "UPLOAD FAILED", "Check sensor", "Retry")
            return None

        vec = buffer_to_vector(raw)
        vectors.append(vec)
        q   = quality_score(vec)
        display_msg(device, f"SCAN {i+1} OK", f"Quality:{q:.3f}", "Lift finger")
        print(f"  ✓ Captured  (quality: {q:.4f})")

        if i < ENROLL_SAMPLES - 1:
            sensor.wait_finger_removed()
            time.sleep(0.5)

    # Merge on Pi
    display_msg(device, "MERGING...", "Please wait", "")
    master = merge_vectors(vectors)

    # Convert float32 numpy array → raw bytes for SQLite BLOB
    # Store as float32 bytes (FEATURE_LEN * 4 bytes = 2048 bytes)
    merged_bytes = master.astype(np.float32).tobytes()
    return merged_bytes


# ─────────────────────────────────────────────
# IDENTIFICATION — on-Pi cosine match
# ─────────────────────────────────────────────

def identify_fingerprint(sensor, device):
    """
    Capture one scan, match against all students in DB.
    Returns (student_id, name, score) or (None, None, 0).
    """
    display_msg(device, "SCAN FINGER", "Place finger", "on sensor")
    print("\n  Place finger on sensor...")

    if not sensor.wait_for_finger():
        display_msg(device, "NO FINGER", "Timed out", "")
        return None, None, 0.0

    code = sensor.image_to_char_buffer(CHAR_BUF_1)
    if code != ACK_OK:
        display_msg(device, "BAD IMAGE", f"0x{code:02X}", "Try again")
        return None, None, 0.0

    raw = sensor.upload_char_buffer(CHAR_BUF_1)
    if raw is None:
        display_msg(device, "UPLOAD FAIL", "", "")
        return None, None, 0.0

    probe    = buffer_to_vector(raw)
    students = get_all_students()

    if not students:
        display_msg(device, "NO STUDENTS", "DB is empty", "Enroll first")
        return None, None, 0.0

    display_msg(device, "MATCHING...", f"{len(students)} students", "")
    print(f"\n  [PI] Matching against {len(students)} student(s)...")
    print(f"  {'ID':<20}  {'Score':>6}  Result")
    print(f"  {'-'*20}  {'-'*6}  {'-'*6}")

    best_id    = None
    best_name  = None
    best_score = 0.0

    for s_id, fname, lname, template_blob in students:
        # Handle both old 768-byte raw BLOB and new float32 merged BLOB
        raw_tmpl = bytes(template_blob)
        if len(raw_tmpl) == FEATURE_LEN * 4:
            # New format: float32 merged template (2048 bytes)
            tmpl_vec = np.frombuffer(raw_tmpl, dtype=np.float32)
        else:
            # Old format: raw sensor bytes (768 or 512 bytes)
            tmpl_vec = buffer_to_vector(raw_tmpl[:FEATURE_LEN])

        score    = cosine_similarity(probe, tmpl_vec)
        accepted = score >= MATCH_THRESHOLD
        result   = "MATCH" if accepted else "-"
        print(f"  {s_id:<20}  {score:.4f}  {result}")

        if accepted and score > best_score:
            best_id    = s_id
            best_name  = f"{fname} {lname}"
            best_score = score

    if best_id:
        print(f"\n  ✅ IDENTIFIED: {best_id}  ({best_score:.4f})")
        display_msg(device, "IDENTIFIED!", best_name[:16], f"Score:{best_score:.3f}")
    else:
        print(f"\n  ❌ No match (threshold: {MATCH_THRESHOLD})")
        display_msg(device, "NO MATCH", f"Threshold:{MATCH_THRESHOLD}", "Try again")

    time.sleep(2)
    return best_id, best_name, best_score


# ─────────────────────────────────────────────
# RE-ENROLL EXISTING STUDENT (update template)
# ─────────────────────────────────────────────

def reenroll_student(sensor, device):
    """
    Re-capture fingerprint for a student already in DB.
    Overwrites their template with a fresh merged vector.
    """
    students = get_all_students()
    if not students:
        display_msg(device, "NO STUDENTS", "DB empty", "")
        time.sleep(2)
        return

    options = [f"{s[0]}: {s[1]} {s[2]}" for s in students]
    idx     = select_from_list(device, "SELECT STUDENT", options)
    s_id, fname, lname, _ = students[idx]
    label   = f"{fname} {lname}"

    display_msg(device, "RE-ENROLL", label[:16], s_id)
    time.sleep(1)

    merged_bytes = enroll_fingerprint(sensor, device, label)
    if merged_bytes is None:
        display_msg(device, "ENROLL FAIL", "Template not", "updated")
        time.sleep(2)
        return

    save_template_to_db("students", "student_id", s_id, merged_bytes)
    display_msg(device, "UPDATED!", label[:16], s_id)
    print(f"\n  ✅ Template updated for {s_id}")
    time.sleep(3)


# ─────────────────────────────────────────────
# DIAGNOSTICS
# ─────────────────────────────────────────────

def run_diagnostics(sensor, device):
    """Quick sensor + DB health check."""
    display_msg(device, "DIAGNOSTICS", "Running...", "")

    # Sensor check
    try:
        ok = sensor.verify_password()
        sensor_status = "✓ OK" if ok else "✗ PW FAIL"
    except Exception as e:
        sensor_status = f"✗ {str(e)[:12]}"

    # DB check
    try:
        students = get_all_students()
        profs    = get_all_profs()
        db_status = f"S:{len(students)} P:{len(profs)}"
    except Exception as e:
        db_status = f"DB ERR: {str(e)[:12]}"

    print(f"\n  Sensor  : {sensor_status}")
    print(f"  DB      : {db_status}")
    print(f"  Port    : {SERIAL_PORT} @ {BAUD_RATE}")
    print(f"  Thresh  : {MATCH_THRESHOLD}")

    display_msg(device, f"Sensor:{sensor_status}", f"DB {db_status}", f"Thr:{MATCH_THRESHOLD}")
    time.sleep(4)


# ─────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────

MENU_OPTIONS = [
    "1. Identify Finger",
    "2. Re-Enroll Student",
    "3. Diagnostics",
    "4. Exit",
]

def main():
    print("\n" + "="*50)
    print("  IITDH R307s On-Pi Fingerprint Tool")
    print(f"  Port: {SERIAL_PORT} @ {BAUD_RATE} baud")
    print(f"  DB  : {DB_PATH}")
    print("="*50)

    # Init hardware
    device = init_display()
    init_gpio()

    display_msg(device, "IITDH FP TOOL", "Initializing...", "")

    # Init sensor — with clear error message
    try:
        sensor = R307(SERIAL_PORT, BAUD_RATE)
    except serial.SerialException as e:
        msg = str(e)
        if "Permission denied" in msg:
            print(f"\n❌ Permission denied on {SERIAL_PORT}")
            print(f"   Run: sudo usermod -a -G dialout $USER && reboot")
        elif "in use" in msg.lower() or "busy" in msg.lower():
            print(f"\n❌ Port {SERIAL_PORT} is already in use")
            print(f"   Stop the main attendance script first")
        else:
            print(f"\n❌ Serial error: {e}")
        display_msg(device, "SERIAL ERROR", "Check wiring", "or port busy")
        time.sleep(5)
        GPIO.cleanup()
        return

    # Verify sensor communication
    display_msg(device, "CHECKING", "Sensor...", "")
    try:
        if not sensor.verify_password():
            print("\n❌ Sensor password check failed — sensor responded but rejected password")
            print("   This usually means sensor is connected but configured with non-default password")
            display_msg(device, "SENSOR FAIL", "Bad password", "")
            time.sleep(3)
            sensor.close()
            GPIO.cleanup()
            return
    except TimeoutError:
        print(f"\n❌ Sensor did not respond on {SERIAL_PORT}")
        print("   Common causes:")
        print("   1. TX/RX swapped — try swapping Pi Pin 8 and Pin 10")
        print("   2. Sensor unpowered — check 3.3V on Pin 1")
        print("   3. Wrong port — check ls /dev/serial* and /dev/ttyAMA*")
        print("   4. Main code still running — stop it first")
        print("   5. Serial console enabled — run: sudo raspi-config → Interface → Serial")
        print("      Disable 'Login shell over serial', Enable 'Serial port hardware'")
        display_msg(device, "TIMEOUT", "No response", "Check wiring")
        time.sleep(5)
        sensor.close()
        GPIO.cleanup()
        return

    print("[OK] Sensor ready.\n")
    display_msg(device, "SENSOR READY", "Use joystick", "to navigate")
    time.sleep(1)

    # Main loop
    try:
        while True:
            idx = select_from_list(device, "FP TOOL", MENU_OPTIONS)

            if idx == 0:
                identify_fingerprint(sensor, device)

            elif idx == 1:
                reenroll_student(sensor, device)

            elif idx == 2:
                run_diagnostics(sensor, device)

            elif idx == 3:
                display_msg(device, "GOODBYE", "Tool closed", "")
                time.sleep(1)
                break

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        sensor.close()
        GPIO.cleanup()
        print("Done.")


if __name__ == "__main__":
    main()