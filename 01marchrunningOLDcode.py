## 01marchrunningcode
import time
import serial
import sqlite3
import os
import smbus
from adafruit_fingerprint import Adafruit_Fingerprint
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas
from PIL import ImageFont
import RPi.GPIO as GPIO

from exit_handler import ExitHandler
exit_handler = ExitHandler()
exit_handler.start()

# --- GPIO Pin Configuration for 5D Joystick ---
JOYSTICK_UP = 17      # Pin 11
JOYSTICK_DOWN = 6     # Pin 31
JOYSTICK_LEFT = 22    # Pin 15
JOYSTICK_RIGHT = 23   # Pin 16
JOYSTICK_CENTER = 26  # Pin 37

# --- 4x4 Matrix Keyboard via I2C ---
I2C_ADDR = 0x20
bus = smbus.SMBus(1)
ROWS = [4, 5, 6, 7]
COLS = [0, 1, 2, 3]
KEYPAD = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

LETTERS = {
    '1': ['a', 'b', 'c'],
    '2': ['d', 'e', 'f'],
    '3': ['g', 'h', 'i'],
    '4': ['j', 'k', 'l'],
    '5': ['m', 'n', 'o'],
    '6': ['p', 'q', 'r'],
    '7': ['s', 't', 'u'],
    '8': ['v', 'w', 'x'],
    '9': ['y', 'z']
}

DEPT_MAP = {"CS": "Computer Science", "EE": "Electrical Engineering", "MC": "Math & Computing",
            "ME": "Mechanical Engineering", "CH": "Chemical Engineering", "CE": "Civil Engineering"}
PROG_MAP = {"BT": "B.Tech", "IS": "BSMS", "MT": "M.Tech"}

DEPT_REVERSE = {v: k for k, v in DEPT_MAP.items()}
PROG_REVERSE = {v: k for k, v in PROG_MAP.items()}

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# ─────────────────────────────────────────────
# HARDWARE SETUP — with retry loop for cold boot
# Retries up to 5 times with 2s gap instead of
# one big upfront sleep. Shows status on OLED
# as soon as it's available.
# ─────────────────────────────────────────────

def init_hardware(max_attempts=5, retry_delay=2):
    global device, uart, finger, KEYBOARD_AVAILABLE

    for attempt in range(1, max_attempts + 1):
        try:
            # OLED via SPI
            oled_interface = spi(device=0, port=0, bus_speed_hz=1000000,
                                 gpio_DC=25, gpio_RST=27, gpio_CS=8)
            device = ssd1306(oled_interface)
            device.contrast(255)

            # Fingerprint sensor via UART
            uart = serial.Serial("/dev/ttyAMA0", baudrate=57600, timeout=1)
            finger = Adafruit_Fingerprint(uart)

            # GPIO for Joystick
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(JOYSTICK_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(JOYSTICK_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(JOYSTICK_LEFT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(JOYSTICK_RIGHT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(JOYSTICK_CENTER, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            # I2C Keyboard — non-fatal
            try:
                bus.write_byte(I2C_ADDR, 0xFF)
                print("✅ I2C Keyboard detected at 0x20")
                KEYBOARD_AVAILABLE = True
            except Exception as e:
                print(f"⚠️  I2C Keyboard not found: {e} — continuing without keypad")
                KEYBOARD_AVAILABLE = False

            print(f"✅ Hardware initialized (attempt {attempt})")
            return True

        except Exception as e:
            print(f"⚠️  Hardware init attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
                time.sleep(retry_delay)

    print("❌ Hardware initialization failed after all attempts")
    return False


KEYBOARD_AVAILABLE = False
device = None
uart = None
finger = None

if not init_hardware():
    exit(1)

# ─────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────

def display_msg(line1, line2="", line3=""):
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 10), line1, fill="white")
        draw.text((5, 28), line2, fill="white")
        draw.text((5, 46), line3, fill="white")

def display_scrolling_menu(options, selected_index, scroll_offset):
    with canvas(device) as draw:
        draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
        draw.text((5, 2), "IITDH BIOMETRIC", fill="black")
        draw.line([(0, 15), (127, 15)], fill="white", width=1)

        visible_items = 3
        max_scroll = max(0, len(options) - visible_items)
        y_start = 20
        item_height = 14

        for i in range(visible_items):
            item_index = scroll_offset + i
            if item_index >= len(options):
                break
            y_pos = y_start + (i * item_height)
            if item_index == selected_index:
                draw.rectangle([(2, y_pos), (125, y_pos + item_height - 2)],
                               fill="white", outline="white")
                text_color = "black"
            else:
                text_color = "white"
            draw.text((8, y_pos + 2), options[item_index][:18], fill=text_color)

        if scroll_offset > 0:
            draw.polygon([(124, 18), (120, 22), (128, 22)], fill="white")
        if scroll_offset < max_scroll:
            draw.polygon([(124, 60), (120, 56), (128, 56)], fill="white")

def display_msg_with_flicker(line1, line2="", line3="", flicker_text=""):
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 10), line1, fill="white")
        draw.text((5, 28), line2, fill="white")
        draw.text((5, 46), line3, fill="white")
        if flicker_text:
            x_pos = 5 + len(line3) * 6
            draw.rectangle([(x_pos, 46), (x_pos + 8, 58)], fill="white", outline="white")
            draw.text((x_pos + 1, 46), flicker_text, fill="black")

# ─────────────────────────────────────────────
# JOYSTICK
# ─────────────────────────────────────────────

def wait_for_button(debounce_time=0.3):
    while True:
        if GPIO.input(JOYSTICK_UP) == GPIO.LOW:
            time.sleep(debounce_time)
            return "UP"
        elif GPIO.input(JOYSTICK_DOWN) == GPIO.LOW:
            time.sleep(debounce_time)
            return "DOWN"
        elif GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
            time.sleep(debounce_time)
            return "CENTER"
        elif GPIO.input(JOYSTICK_LEFT) == GPIO.LOW:
            time.sleep(debounce_time)
            return "LEFT"
        elif GPIO.input(JOYSTICK_RIGHT) == GPIO.LOW:
            time.sleep(debounce_time)
            return "RIGHT"
        time.sleep(0.05)

# ─────────────────────────────────────────────
# UPS / BATTERY
# ─────────────────────────────────────────────

UPS_ADDR = 0x2d

def get_battery_percent():
    try:
        percent = bus.read_byte_data(UPS_ADDR, 0x24)
        return min(percent, 100)
    except:
        return -1

def draw_battery_icon(draw, x, y, percent):
    draw.rectangle([(x, y), (x + 18, y + 9)], outline="white")
    draw.rectangle([(x + 19, y + 3), (x + 21, y + 6)], fill="white")
    fill_width = int((percent / 100) * 16)
    if fill_width > 0:
        draw.rectangle([(x + 1, y + 1), (x + 1 + fill_width, y + 8)], fill="white")

# ─────────────────────────────────────────────
# SCREENSAVER
# ─────────────────────────────────────────────

def screensaver():
    print("[Screensaver] Activated")
    last_draw = 0

    while True:
        now = time.time()

        # ── Only redraw once per minute — saves ~60x SPI writes ──────
        if now - last_draw >= 60.0:
            percent      = get_battery_percent()
            current_time = time.strftime("%H:%M")        # no seconds
            current_date = time.strftime("%d %b %Y")

            if percent == -1:
                batt_label = "Batt: N/A"
            elif percent > 80:
                batt_label = f"{percent}%  Good"
            elif percent > 30:
                batt_label = f"{percent}%  OK"
            else:
                batt_label = f"{percent}%  LOW!"

            with canvas(device) as draw:
                draw.rectangle([(0, 0), (127, 63)], outline="white")
                draw.text((38, 4),  "-- IITDH --",  fill="white")
                draw.line([(1, 15), (126, 15)],      fill="white", width=1)
                draw.text((28, 22), current_time,    fill="white")  # bigger gap, no seconds
                draw.text((22, 36), current_date,    fill="white")
                draw.line([(1, 48), (126, 48)],      fill="white", width=1)
                if percent != -1:
                    draw_battery_icon(draw, 4, 53, percent)
                    draw.text((30, 53), batt_label,  fill="white")
                else:
                    draw.text((5, 53), "Battery: N/A", fill="white")

            last_draw = now

        # ── Joystick wake check — still fast so response feels instant ─
        if (GPIO.input(JOYSTICK_UP)     == GPIO.LOW or
            GPIO.input(JOYSTICK_DOWN)   == GPIO.LOW or
            GPIO.input(JOYSTICK_LEFT)   == GPIO.LOW or
            GPIO.input(JOYSTICK_RIGHT)  == GPIO.LOW or
            GPIO.input(JOYSTICK_CENTER) == GPIO.LOW):

            print("[Screensaver] Deactivated")
            while (GPIO.input(JOYSTICK_UP)     == GPIO.LOW or
                   GPIO.input(JOYSTICK_DOWN)    == GPIO.LOW or
                   GPIO.input(JOYSTICK_LEFT)    == GPIO.LOW or
                   GPIO.input(JOYSTICK_RIGHT)   == GPIO.LOW or
                   GPIO.input(JOYSTICK_CENTER)  == GPIO.LOW):
                time.sleep(0.05)
            time.sleep(0.1)

            # Force immediate redraw when waking so time is current
            last_draw = 0
            return

        time.sleep(0.1)   # 10 checks/sec is plenty for button response

# ─────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────

def show_menu():
    menu_options = [
        "Enroll Student",
        "Take Attendance",
        "View Stats",
        "Admin Settings",
        "System Info",
        "Shutdown"
    ]

    selected = 0
    scroll_offset = 0
    visible_items = 3
    SCREENSAVER_TIMEOUT = 45

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible_items:
            scroll_offset = selected - visible_items + 1

        display_scrolling_menu(menu_options, selected, scroll_offset)

        deadline = time.time() + SCREENSAVER_TIMEOUT
        button = None

        while time.time() < deadline:
            if GPIO.input(JOYSTICK_UP) == GPIO.LOW:
                time.sleep(0.3)
                button = "UP"
                break
            elif GPIO.input(JOYSTICK_DOWN) == GPIO.LOW:
                time.sleep(0.3)
                button = "DOWN"
                break
            elif GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
                time.sleep(0.3)
                button = "CENTER"
                break
            elif GPIO.input(JOYSTICK_LEFT) == GPIO.LOW:
                time.sleep(0.3)
                button = "LEFT"
                break
            elif GPIO.input(JOYSTICK_RIGHT) == GPIO.LOW:
                time.sleep(0.3)
                button = "RIGHT"
                break
            time.sleep(0.05)

        if button is None:
            screensaver()
            continue

        if button == "UP":
            selected = (selected - 1) % len(menu_options)
        elif button == "DOWN":
            selected = (selected + 1) % len(menu_options)
        elif button == "CENTER":
            return selected
        elif button == "LEFT":
            selected = max(0, selected - visible_items)
        elif button == "RIGHT":
            selected = min(len(menu_options) - 1, selected + visible_items)

# ─────────────────────────────────────────────
# GENERIC MENU SELECTOR
# ─────────────────────────────────────────────

def select_from_menu(title, options):
    selected = 0
    scroll_offset = 0
    visible_items = 3

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible_items:
            scroll_offset = selected - visible_items + 1

        with canvas(device) as draw:
            draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
            draw.text((5, 2), title[:18], fill="black")
            draw.line([(0, 15), (127, 15)], fill="white", width=1)

            y_start = 20
            item_height = 14
            max_scroll = max(0, len(options) - visible_items)

            for i in range(visible_items):
                item_index = scroll_offset + i
                if item_index >= len(options):
                    break
                y_pos = y_start + (i * item_height)
                if item_index == selected:
                    draw.rectangle([(2, y_pos), (125, y_pos + item_height - 2)],
                                   fill="white", outline="white")
                    text_color = "black"
                else:
                    text_color = "white"
                draw.text((8, y_pos + 2), options[item_index][:18], fill=text_color)

            if scroll_offset > 0:
                draw.polygon([(124, 18), (120, 22), (128, 22)], fill="white")
            if scroll_offset < max_scroll:
                draw.polygon([(124, 60), (120, 56), (128, 56)], fill="white")

        button = wait_for_button()
        if button == "UP":
            selected = (selected - 1) % len(options)
        elif button == "DOWN":
            selected = (selected + 1) % len(options)
        elif button == "CENTER":
            return options[selected]

# ─────────────────────────────────────────────
# KEYPAD INPUT
# ─────────────────────────────────────────────

def read_keypad_input(prompt, mode="NUMBER", display_line2="", show_as_password=False):
    if not KEYBOARD_AVAILABLE:
        display_msg("NO KEYBOARD", "Keypad missing", "Check I2C 0x20")
        time.sleep(3)
        return None

    output = ""
    last_key = None
    tap_count = 0
    last_time = 0
    current_mode = mode
    current_preview = ""
    flicker_state = True
    last_flicker_time = 0

    bus.write_byte(I2C_ADDR, 0xFF)

    while True:
        current_time = time.time()
        if current_time - last_flicker_time > 0.3:
            flicker_state = not flicker_state
            last_flicker_time = current_time

        if show_as_password:
            display_msg(prompt, display_line2, "*" * len(output))
        else:
            if current_preview and flicker_state:
                display_msg_with_flicker(prompt, display_line2, output, current_preview)
            else:
                display_msg(prompt, display_line2, output + current_preview)

        if GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
            if last_key and last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS":
                    ch = ch.upper()
                output += ch
                last_key = None
                tap_count = 0
                current_preview = ""
            if output:
                time.sleep(0.3)
                return output
            time.sleep(0.3)

        for r, row in enumerate(ROWS):
            bus.write_byte(I2C_ADDR, 0xFF & ~(1 << row))
            time.sleep(0.01)
            data = bus.read_byte(I2C_ADDR)

            for c, col in enumerate(COLS):
                if not (data & (1 << col)):
                    key = KEYPAD[r][c]
                    now = time.time()

                    if key == 'A':
                        if current_mode != "ALPHA" and current_mode != "CAPS" and not show_as_password:
                            current_mode = "ALPHA"
                            display_msg(prompt, "ALPHA MODE", output)
                            time.sleep(0.5)
                    elif key == '#':
                        if current_mode != "NUMBER" and not show_as_password:
                            current_mode = "NUMBER"
                            display_msg(prompt, "NUMBER MODE", output)
                            time.sleep(0.5)
                    elif key == 'C':
                        if current_mode == "ALPHA":
                            current_mode = "CAPS"
                            display_msg(prompt, "CAPS MODE", output)
                            time.sleep(0.5)
                        elif current_mode == "CAPS":
                            current_mode = "ALPHA"
                            display_msg(prompt, "ALPHA MODE", output)
                            time.sleep(0.5)
                    elif key == 'B':
                        if current_preview:
                            current_preview = ""
                            last_key = None
                            tap_count = 0
                        else:
                            output = output[:-1]
                    elif key == '*':
                        output = ""
                        last_key = None
                        tap_count = 0
                        current_preview = ""
                        display_msg(prompt, "CLEARED", "")
                        time.sleep(0.5)
                    elif key.isdigit():
                        if current_mode == "NUMBER" or show_as_password:
                            output += key
                        elif current_mode in ["ALPHA", "CAPS"] and key in LETTERS:
                            if key != last_key:
                                if last_key and last_key in LETTERS:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS":
                                        ch = ch.upper()
                                    output += ch
                                last_key = key
                                tap_count = 0
                            else:
                                if (now - last_time) < 1.0:
                                    tap_count += 1
                                else:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS":
                                        ch = ch.upper()
                                    output += ch
                                    tap_count = 0
                            ch = LETTERS[key][tap_count % len(LETTERS[key])]
                            if current_mode == "CAPS":
                                ch = ch.upper()
                            current_preview = ch
                            last_time = now

                    time.sleep(0.3)

        if last_key and (time.time() - last_time) > 1.0:
            if last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS":
                    ch = ch.upper()
                output += ch
            last_key = None
            tap_count = 0
            current_preview = ""

# ─────────────────────────────────────────────
# PROFESSOR AUTH
# ─────────────────────────────────────────────

def authenticate_prof():
    print("\n--- Professor Authorization Required ---")
    display_msg("ADMIN REQUIRED", "Scan Prof Finger")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, template FROM profs")
    profs = cursor.fetchall()
    conn.close()

    if not profs:
        display_msg("ERROR", "No Profs Found")
        time.sleep(2)
        return None

    uart.reset_input_buffer()
    timeout = time.time() + 15
    while time.time() < timeout:
        if finger.get_image() == 0:
            finger.image_2_tz(1)
            for name, template in profs:
                finger.send_fpdata(list(template), "char", 2)
                if finger.compare_templates() == 0:
                    display_msg("AUTHORIZED", f"Prof. {name}")
                    time.sleep(1.5)
                    return name
        time.sleep(0.1)

    display_msg("TIMEOUT", "Auth Failed")
    time.sleep(2)
    return None

# ─────────────────────────────────────────────
# STUDENT ENROLLMENT
# ─────────────────────────────────────────────

def enroll_student():
    print("\n--- Interactive Student Registration ---")
    try:
        display_msg("ENROLLMENT", "Select Branch", "Use Joystick")
        time.sleep(0.5)
        selected_branch = select_from_menu("SELECT BRANCH", list(DEPT_MAP.values()))
        branch_code = DEPT_REVERSE[selected_branch]

        display_msg("ENROLLMENT", "Select Program", "Use Joystick")
        time.sleep(0.5)
        selected_program = select_from_menu("SELECT PROGRAM", list(PROG_MAP.values()))
        program_code = PROG_REVERSE[selected_program]

        batch_year = read_keypad_input("BATCH YEAR", mode="NUMBER", display_line2="4 digits,OK=Ctr")
        if not batch_year or len(batch_year) != 4 or not batch_year.isdigit():
            display_msg("ERROR", "Invalid Year")
            time.sleep(2)
            return

        year_short = batch_year[2:4]

        roll_suffix = read_keypad_input("ROLL SUFFIX", mode="NUMBER", display_line2="3 digits,OK=Ctr")
        if not roll_suffix or len(roll_suffix) != 3 or not roll_suffix.isdigit():
            display_msg("ERROR", "Need 3 digits")
            time.sleep(2)
            return

        roll_no = f"{branch_code}{year_short}{program_code}{roll_suffix}"
        display_msg("ROLL NUMBER", roll_no, "Ctr=confirm")
        time.sleep(2)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
        if cursor.fetchone():
            display_msg("ERROR", f"{roll_no} exists")
            conn.close()
            time.sleep(2)
            return
        conn.close()

        first_name = read_keypad_input("FIRST NAME", mode="ALPHA", display_line2="C=CAPS,OK=Ctr")
        if not first_name:
            return

        last_name = read_keypad_input("LAST NAME", mode="ALPHA", display_line2="C=CAPS,OK=Ctr")
        if not last_name:
            return

        password = read_keypad_input("PASSWORD", mode="NUMBER", display_line2="Numbers,OK=Ctr", show_as_password=True)
        if not password:
            return

        display_msg("SUMMARY", f"{first_name} {last_name}", roll_no)
        time.sleep(1.5)

        # Fingerprint — 4 scans
        print("\n--- Starting 4-Scan Fingerprint Registration ---")
        scan1_successful = False
        retry_attempts = 0

        while not scan1_successful and retry_attempts < 5:
            display_msg("SCAN 1 of 4", "Place finger")
            uart.reset_input_buffer()
            finger_placed = False
            timeout = time.time() + 10
            while time.time() < timeout and not finger_placed:
                if finger.get_image() == 0:
                    finger_placed = True
                time.sleep(0.1)

            if not finger_placed:
                retry_attempts += 1
                display_msg("TIMEOUT", f"Try {retry_attempts}/5")
                time.sleep(1)
                continue

            if finger.image_2_tz(1) != 0:
                retry_attempts += 1
                display_msg("Bad Image", f"Try {retry_attempts}/5")
                time.sleep(1.5)
                continue

            display_msg("SCAN 1 of 4", "Success!")
            time.sleep(0.5)
            scan1_successful = True

        if not scan1_successful:
            display_msg("ENROLLMENT", "FAILED", "Try again later")
            time.sleep(3)
            return

        for scan_num in range(2, 5):
            retry_count = 0
            scan_successful = False

            while not scan_successful and retry_count < 5:
                display_msg(f"SCAN {scan_num} of 4", "Remove finger")
                time.sleep(1.5)

                removal_timeout = time.time() + 5
                while time.time() < removal_timeout:
                    if finger.get_image() != 0:
                        break
                    time.sleep(0.1)

                display_msg(f"SCAN {scan_num} of 4", "Place finger")
                finger_placed = False
                placement_timeout = time.time() + 10
                while time.time() < placement_timeout and not finger_placed:
                    if finger.get_image() == 0:
                        finger_placed = True
                    time.sleep(0.1)

                if not finger_placed:
                    retry_count += 1
                    display_msg("TIMEOUT", f"Retry {retry_count}/5")
                    time.sleep(1.5)
                    continue

                if finger.image_2_tz(2) != 0:
                    retry_count += 1
                    display_msg("Bad Image", f"Retry {retry_count}/5")
                    time.sleep(1.5)
                    continue

                display_msg(f"SCAN {scan_num} of 4", "Merging...")
                if finger.create_model() == 0:
                    display_msg(f"SCAN {scan_num} of 4", "Success!")
                    time.sleep(0.5)
                    scan_successful = True
                else:
                    retry_count += 1
                    display_msg("No Match", f"Retry {retry_count}/5")
                    time.sleep(1.5)

            if not scan_successful:
                display_msg("ENROLLMENT", "FAILED", "Try again later")
                time.sleep(3)
                return

        display_msg("Saving...", "Please wait")
        template = finger.get_fpdata("char", 1)
        if not template:
            display_msg("ERROR", "Save Failed")
            time.sleep(2)
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (roll_no, first_name, last_name, password, selected_branch,
             int(batch_year), selected_program, sqlite3.Binary(bytearray(template))))
        conn.commit()
        conn.close()

        display_msg("SUCCESS!", f"{first_name} {last_name}", roll_no)
        time.sleep(3)

    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:20])
        time.sleep(2)

# ─────────────────────────────────────────────
# ATTENDANCE SESSION
# ─────────────────────────────────────────────

def classroom_session(prof_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE name=?", (prof_name,))
    prof_result = cursor.fetchone()

    if not prof_result:
        display_msg("ERROR", "Prof not found")
        conn.close()
        time.sleep(2)
        return

    prof_id = prof_result[0]
    cursor.execute("SELECT course_code, course_name FROM courses WHERE prof_id=? ORDER BY course_code", (prof_id,))
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        display_msg("NO COURSES", "No courses found", "for this prof")
        time.sleep(3)
        return

    course_options = [f"{code}: {name[:12]}" for code, name in courses]
    selected_course = select_from_menu("SELECT COURSE", course_options)
    course_code = selected_course.split(':')[0]
    course_name = [name for code, name in courses if code == course_code][0]

    display_msg("COURSE SELECTED", course_code, course_name[:16])
    time.sleep(1.5)

    conn = sqlite3.connect(DB_PATH)
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
        display_msg("NO STUDENTS", "No enrollments", "for this course")
        time.sleep(3)
        return

    display_msg("CLASS OPEN", course_code, "Scan Finger")
    time.sleep(1.5)

    session_start = time.time()
    attendance_count = 0
    attended_students = set()

    while True:
        display_msg("CLASS SESSION", f"{course_code} ({attendance_count})", "Scan or Prof=Exit")
        uart.reset_input_buffer()

        if finger.get_image() == 0:
            finger.image_2_tz(1)
            is_prof = False
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT template FROM profs WHERE prof_id=?", (prof_id,))
            prof_template = cursor.fetchone()

            if prof_template:
                finger.send_fpdata(list(prof_template[0]), "char", 2)
                if finger.compare_templates() == 0:
                    is_prof = True

            if is_prof:
                session_duration = int((time.time() - session_start) / 60)
                display_msg("SESSION CLOSED", f"Total: {attendance_count}", f"Time: {session_duration}min")
                conn.close()
                time.sleep(3)
                break

            found = False
            for s_id, s_name, s_template in enrolled_students:
                finger.send_fpdata(list(s_template), "char", 2)
                if finger.compare_templates() == 0:
                    if s_id in attended_students:
                        display_msg("ALREADY MARKED", s_name, "Present today")
                        time.sleep(2)
                    else:
                        display_msg("VERIFIED!", s_name, s_id)
                        cursor.execute("""
                            INSERT INTO attendance 
                            (course_code, student_id, student_name, authorized_by, timestamp, session_date)
                            VALUES (?, ?, ?, ?, datetime('now', 'localtime'), date('now', 'localtime'))
                        """, (course_code, s_id, s_name, prof_id))
                        conn.commit()
                        attendance_count += 1
                        attended_students.add(s_id)
                        time.sleep(2)
                    found = True
                    break

            if not found:
                display_msg("FAILED", "Not enrolled in", course_code)
                time.sleep(1.5)

            conn.close()
        time.sleep(0.1)

# ─────────────────────────────────────────────
# VIEW STATS
# ─────────────────────────────────────────────

def view_stats():
    display_msg("Loading Stats", "Please wait...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM courses")
        total_courses = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM profs")
        total_profs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE date(session_date) = date('now', 'localtime')")
        today_attendance = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE date(session_date) = date('now', 'localtime')")
        today_total = cursor.fetchone()[0]
        conn.close()

        display_msg("STATISTICS", f"Students: {total_students}", f"Courses: {total_courses}")
        time.sleep(3)
        display_msg("STATISTICS", f"Professors: {total_profs}", f"Today: {today_attendance}/{total_students}")
        time.sleep(3)
        display_msg("TODAY'S DATA", f"Unique: {today_attendance}", f"Scans: {today_total}")
        time.sleep(3)

    except Exception as e:
        display_msg("ERROR", "Stats Failed", str(e)[:16])
        time.sleep(2)

# ─────────────────────────────────────────────
# COURSE MANAGEMENT
# ─────────────────────────────────────────────

def manage_courses():
    course_menu = ["Add Course", "View Courses", "Enroll Students", "View Enrollments", "Back"]

    while True:
        selected = 0
        scroll_offset = 0

        while True:
            if selected < scroll_offset:
                scroll_offset = selected
            elif selected >= scroll_offset + 3:
                scroll_offset = selected - 2
            display_scrolling_menu(course_menu, selected, scroll_offset)
            button = wait_for_button()
            if button == "UP":
                selected = (selected - 1) % len(course_menu)
            elif button == "DOWN":
                selected = (selected + 1) % len(course_menu)
            elif button == "CENTER":
                break

        if selected == 0:
            add_course()
        elif selected == 1:
            view_courses()
        elif selected == 2:
            enroll_student_in_course()
        elif selected == 3:
            view_course_enrollments()
        elif selected == 4:
            return

def add_course():
    display_msg("ADD COURSE", "Prof Auth Needed")
    time.sleep(0.5)
    prof = authenticate_prof()
    if not prof:
        display_msg("AUTH FAILED", "Cannot add course")
        time.sleep(2)
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE name=?", (prof,))
    prof_result = cursor.fetchone()
    if not prof_result:
        display_msg("ERROR", "Prof not found")
        conn.close()
        time.sleep(2)
        return
    prof_id = prof_result[0]
    conn.close()

    course_code = read_keypad_input("COURSE CODE", mode="ALPHA", display_line2="OK=Center")
    if not course_code:
        return
    course_code = course_code.upper()

    course_name = read_keypad_input("COURSE NAME", mode="ALPHA", display_line2="OK=Center")
    if not course_name:
        return

    selected_dept = select_from_menu("SELECT DEPT", list(DEPT_MAP.keys()))

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT course_code FROM courses WHERE course_code=?", (course_code,))
        if cursor.fetchone():
            display_msg("ERROR", "Course exists")
            conn.close()
            time.sleep(2)
            return
        cursor.execute("INSERT INTO courses (course_code, course_name, prof_id, dept_code) VALUES (?, ?, ?, ?)",
                       (course_code, course_name, prof_id, selected_dept))
        conn.commit()
        conn.close()
        display_msg("SUCCESS!", course_code, "Course added")
        time.sleep(2)
    except Exception as e:
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def view_courses():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT c.course_code, c.course_name, p.name FROM courses c JOIN profs p ON c.prof_id = p.prof_id ORDER BY c.course_code")
        courses = cursor.fetchall()
        conn.close()
        if not courses:
            display_msg("NO COURSES", "No courses found")
            time.sleep(2)
            return
        for code, name, prof in courses:
            display_msg(code, name[:16], f"Prof: {prof[:12]}")
            time.sleep(2)
    except Exception as e:
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def enroll_student_in_course():
    student_id = read_keypad_input("STUDENT ID", mode="ALPHA", display_line2="OK=Center")
    if not student_id:
        return
    student_id = student_id.upper()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name FROM students WHERE student_id=?", (student_id,))
    student = cursor.fetchone()
    if not student:
        display_msg("ERROR", "Student not found")
        conn.close()
        time.sleep(2)
        return

    student_name = f"{student[0]} {student[1]}"
    cursor.execute("SELECT course_code, course_name FROM courses ORDER BY course_code")
    courses = cursor.fetchall()
    if not courses:
        display_msg("NO COURSES", "No courses found")
        conn.close()
        time.sleep(2)
        return

    selected_course = select_from_menu("SELECT COURSE", [f"{code}: {name[:10]}" for code, name in courses])
    course_code = selected_course.split(':')[0]

    try:
        cursor.execute("SELECT enrollment_id FROM course_enrollments WHERE student_id=? AND course_code=?", (student_id, course_code))
        if cursor.fetchone():
            display_msg("ALREADY", "Enrolled", course_code)
            time.sleep(2)
        else:
            cursor.execute("INSERT INTO course_enrollments (student_id, course_code, status) VALUES (?, ?, 'active')", (student_id, course_code))
            conn.commit()
            display_msg("SUCCESS!", student_name[:16], f"Enrolled {course_code}")
            time.sleep(2)
        conn.close()
    except Exception as e:
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def view_course_enrollments():
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA", display_line2="OK=Center")
    if not course_code:
        return
    course_code = course_code.upper()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.first_name, s.last_name, s.dept
            FROM students s JOIN course_enrollments ce ON s.student_id = ce.student_id
            WHERE ce.course_code = ? AND ce.status = 'active' ORDER BY s.student_id
        """, (course_code,))
        enrollments = cursor.fetchall()
        conn.close()
        if not enrollments:
            display_msg("NO STUDENTS", "No enrollments", course_code)
            time.sleep(2)
            return
        for sid, fname, lname, dept in enrollments:
            display_msg(sid, f"{fname} {lname}"[:16], dept[:16])
            time.sleep(2)
    except Exception as e:
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def admin_settings():
    display_msg("ADMIN SETTINGS", "Course Management")
    time.sleep(0.5)
    manage_courses()

# ─────────────────────────────────────────────
# SYSTEM ACCESS
# ─────────────────────────────────────────────

def load_sysaccess_creds():
    creds = {}
    try:
        with open('/home/bio_user_iitdh/new_env/.sysaccess_creds', 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, val = line.split('=', 1)
                    creds[key.strip()] = val.strip()
    except Exception as e:
        print(f"❌ Could not load creds: {e}")
    return creds

def system_access():
    creds = load_sysaccess_creds()
    secret_keyword = creds.get('KEYWORD', '')
    secret_password = creds.get('PASSWORD', '')

    if not secret_keyword or not secret_password:
        display_msg("SYS ACCESS", "Creds missing!", "Contact Admin")
        time.sleep(3)
        return

    entered_keyword = read_keypad_input("KEYWORD", mode="ALPHA", display_line2="CENTER=OK", show_as_password=True)
    if not entered_keyword or entered_keyword != secret_keyword:
        display_msg("ACCESS DENIED", "Wrong keyword", "")
        time.sleep(3)
        return

    entered_password = read_keypad_input("PASSWORD", mode="NUMBER", display_line2="CENTER=OK", show_as_password=True)
    if not entered_password or entered_password != secret_password:
        display_msg("ACCESS DENIED", "Wrong password", "")
        time.sleep(3)
        return

    display_msg("ACCESS GRANTED", "Loading Desktop", "Please wait...")
    time.sleep(2)
    GPIO.cleanup()
    os._exit(42)

# ─────────────────────────────────────────────
# SYSTEM INFO
# ─────────────────────────────────────────────

def system_info():
    sub_options = ["Device Info", "System Access", "Back"]
    selected = 0
    scroll_offset = 0

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + 3:
            scroll_offset = selected - 2
        display_scrolling_menu(sub_options, selected, scroll_offset)
        button = wait_for_button()

        if button == "UP":
            selected = (selected - 1) % len(sub_options)
        elif button == "DOWN":
            selected = (selected + 1) % len(sub_options)
        elif button == "CENTER":
            if selected == 0:
                display_msg("SYSTEM INFO", "IITDH v2.0", "Raspberry Pi")
                time.sleep(5)
            elif selected == 1:
                system_access()
                return
            elif selected == 2:
                return
        elif button == "LEFT":
            return

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

try:
    # Minimal init message — removed long sleep
    display_msg("IITDH System", "Ready", "")
    time.sleep(0.5)

    while True:
        selection = show_menu()

        if selection == 0:
            prof = authenticate_prof()
            if prof:
                enroll_student()
            else:
                display_msg("AUTH FAILED", "Access Denied")
                time.sleep(2)

        elif selection == 1:
            prof = authenticate_prof()
            if prof:
                classroom_session(prof)
            else:
                display_msg("AUTH FAILED", "Access Denied")
                time.sleep(2)

        elif selection == 2:
            view_stats()

        elif selection == 3:
            prof = authenticate_prof()
            if prof:
                admin_settings()
            else:
                display_msg("AUTH FAILED", "Access Denied")
                time.sleep(2)

        elif selection == 4:
            system_info()

        elif selection == 5:
            display_msg("CONFIRM?", "Press CENTER", "to Shutdown")
            button = wait_for_button()
            if button == "CENTER":
                display_msg("SHUTTING DOWN", "Goodbye!", "")
                time.sleep(2)
                GPIO.cleanup()
                os.system("sudo shutdown -h now")
                break
            else:
                continue

except KeyboardInterrupt:
    display_msg("SHUTDOWN", "Goodbye!")
    time.sleep(1)
    GPIO.cleanup()

except Exception as e:
    print(f"\n❌ Critical Error: {e}")
    display_msg("SYSTEM ERROR", str(e)[:20])
    time.sleep(3)
    GPIO.cleanup()