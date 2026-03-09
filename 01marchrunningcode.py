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

# Letter mapping for keyboard (like T9)
LETTERS = {
    '1': ['a', 'b', 'c'],
    '2': ['d', 'e', 'f'],
    '3': ['g', 'h', 'i'],
    '4': ['j', 'k', 'l'],
    '5': ['m', 'n', 'o'],
    '6': ['p', 'q', 'r'],
    '7': ['s','t', 'u'],
    '8': ['v','w', 'x'],
    '9': ['y', 'z']
}

# --- Mapping Dictionaries ---
DEPT_MAP = {"CS": "Computer Science", "EE": "Electrical Engineering", "MC": "Math & Computing", 
            "ME": "Mechanical Engineering", "CH": "Chemical Engineering", "CE": "Civil Engineering"}
PROG_MAP = {"BT": "B.Tech", "IS": "BSMS", "MT": "M.Tech"}

# Reverse mapping for display to code
DEPT_REVERSE = {v: k for k, v in DEPT_MAP.items()}
PROG_REVERSE = {v: k for k, v in PROG_MAP.items()}

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# --- Hardware Setup ---
try:
    # OLED via SPI
    oled_interface = spi(device=0, port=0, bus_speed_hz=1000000, gpio_DC=25, gpio_RST=27, gpio_CS=8)
    device = ssd1306(oled_interface)
    device.contrast(255)

    # R307S via USB-UART or GPIO-UART
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
    
    # Setup GPIO for Joystick
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(JOYSTICK_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(JOYSTICK_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(JOYSTICK_LEFT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(JOYSTICK_RIGHT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(JOYSTICK_CENTER, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # Initialize I2C Keyboard
    bus.write_byte(I2C_ADDR, 0xFF)
    
    print("✅ Hardware initialized successfully")
except Exception as e:
    print(f"Hardware Setup Error: {e}")
    exit(1)

def display_msg(line1, line2="", line3=""):
    """Display message on OLED (up to 3 lines)"""
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 10), line1, fill="white")
        draw.text((5, 28), line2, fill="white")
        draw.text((5, 46), line3, fill="white")

def display_scrolling_menu(options, selected_index, scroll_offset):
    """
    Professional scrolling menu with window view.
    Shows 3 items at a time with scroll indicators.
    """
    with canvas(device) as draw:
        # Header bar with filled background
        draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
        draw.text((5, 2), "IITDH BIOMETRIC", fill="black")
        
        # Bottom border line under header
        draw.line([(0, 15), (127, 15)], fill="white", width=1)
        
        # Calculate visible items (3 items in viewport)
        visible_items = 3
        max_scroll = max(0, len(options) - visible_items)
        
        # Draw visible menu items
        y_start = 20
        item_height = 14
        
        for i in range(visible_items):
            item_index = scroll_offset + i
            
            if item_index >= len(options):
                break
            
            y_pos = y_start + (i * item_height)
            
            # Draw selection box (inverted colors for selected item)
            if item_index == selected_index:
                draw.rectangle([(2, y_pos), (125, y_pos + item_height - 2)], 
                             fill="white", outline="white")
                text_color = "black"
            else:
                text_color = "white"
            
            # Draw menu text (truncate if too long)
            menu_text = options[item_index][:18]  # Limit to 18 chars
            draw.text((8, y_pos + 2), menu_text, fill=text_color)
        
        # Scroll indicators
        if scroll_offset > 0:
            # Up arrow indicator
            draw.polygon([(124, 18), (120, 22), (128, 22)], fill="white")
        
        if scroll_offset < max_scroll:
            # Down arrow indicator  
            draw.polygon([(124, 60), (120, 56), (128, 56)], fill="white")

def wait_for_button(debounce_time=0.3):
    """Wait for any joystick button press and return which one"""
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

def show_menu():
    """
    Professional scrolling menu navigation using 5D joystick.
    Can handle unlimited menu options with 3-item viewport.
    """
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
    
    while True:
        # Auto-scroll logic: keep selected item in view
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible_items:
            scroll_offset = selected - visible_items + 1
        
        display_scrolling_menu(menu_options, selected, scroll_offset)
        
        button = wait_for_button()
        
        if button == "UP":
            selected = (selected - 1) % len(menu_options)
        elif button == "DOWN":
            selected = (selected + 1) % len(menu_options)
        elif button == "CENTER":
            return selected  # Return the selected menu index
        elif button == "LEFT":
            # Quick scroll up by visible_items
            selected = max(0, selected - visible_items)
        elif button == "RIGHT":
            # Quick scroll down by visible_items
            selected = min(len(menu_options) - 1, selected + visible_items)

def select_from_menu(title, options):
    """
    Generic menu selector using joystick.
    Returns selected option string.
    """
    selected = 0
    scroll_offset = 0
    visible_items = 3
    
    while True:
        # Auto-scroll logic
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible_items:
            scroll_offset = selected - visible_items + 1
        
        # Display menu with custom title
        with canvas(device) as draw:
            # Header
            draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
            draw.text((5, 2), title[:18], fill="black")
            draw.line([(0, 15), (127, 15)], fill="white", width=1)
            
            # Menu items
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
                
                menu_text = options[item_index][:18]
                draw.text((8, y_pos + 2), menu_text, fill=text_color)
            
            # Scroll indicators
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

def display_msg_with_flicker(line1, line2="", line3="", flicker_text=""):
    """Display message on OLED with flickering text at the end of line3"""
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 10), line1, fill="white")
        draw.text((5, 28), line2, fill="white")
        
        # Draw main text
        draw.text((5, 46), line3, fill="white")
        
        # Draw flickering preview at the end with inverted colors
        if flicker_text:
            # Calculate position after main text
            text_width = len(line3) * 6  # Approximate character width
            x_pos = 5 + text_width
            # Draw inverted box for flicker effect
            draw.rectangle([(x_pos, 46), (x_pos + 8, 58)], fill="white", outline="white")
            draw.text((x_pos + 1, 46), flicker_text, fill="black")

def read_keypad_input(prompt, mode="NUMBER", display_line2="", show_as_password=False):
    """
    Read input from 4x4 matrix keyboard with OLED display.
    
    Keyboard Layout:
    - A = Switch to Alphabet mode
    - # = Switch to Number mode
    - C = CAPS toggle (when in ALPHA mode)
    - B = Backspace
    - * = Clear all
    
    Press CENTER button on joystick to confirm
    """
    output = ""
    last_key = None
    tap_count = 0
    last_time = 0
    current_mode = mode
    current_preview = ""  # Preview of current letter being typed
    flicker_state = True  # For flickering effect
    last_flicker_time = 0
    
    bus.write_byte(I2C_ADDR, 0xFF)
    
    while True:
        # Flicker effect - toggle every 0.3 seconds
        current_time = time.time()
        if current_time - last_flicker_time > 0.3:
            flicker_state = not flicker_state
            last_flicker_time = current_time
        
        # Update display - show asterisks for password
        if show_as_password:
            display_output = "*" * len(output)
            display_msg(prompt, display_line2, display_output)
        else:
            # Show confirmed output + flickering current letter preview
            if current_preview and flicker_state:
                display_msg_with_flicker(prompt, display_line2, output, current_preview)
            else:
                display_msg(prompt, display_line2, output + current_preview)
        
        # Check for CENTER button (confirmation)
        if GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
            # Confirm last letter if in alpha mode
            if last_key and last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS":
                    ch = ch.upper()
                output += ch
                print(f"Auto-confirmed: {ch}")
                last_key = None
                tap_count = 0
                current_preview = ""
            
            # Return if we have input
            if output:
                print(f"Input confirmed: {output if not show_as_password else '****'}")
                time.sleep(0.3)  # Debounce
                return output
            time.sleep(0.3)
        
        # Scan keypad
        for r, row in enumerate(ROWS):
            bus.write_byte(I2C_ADDR, 0xFF & ~(1 << row))
            time.sleep(0.01)
            data = bus.read_byte(I2C_ADDR)
            
            for c, col in enumerate(COLS):
                if not (data & (1 << col)):
                    key = KEYPAD[r][c]
                    now = time.time()
                    
                    # A = Switch to Alphabet mode
                    if key == 'A':
                        if current_mode != "ALPHA" and current_mode != "CAPS" and not show_as_password:
                            current_mode = "ALPHA"
                            display_msg(prompt, "ALPHA MODE", output)
                            time.sleep(0.5)
                    
                    # # = Switch to Number mode
                    elif key == '#':
                        if current_mode != "NUMBER" and not show_as_password:
                            current_mode = "NUMBER"
                            display_msg(prompt, "NUMBER MODE", output)
                            time.sleep(0.5)
                    
                    # C = CAPS toggle (from ALPHA)
                    elif key == 'C':
                        if current_mode == "ALPHA":
                            current_mode = "CAPS"
                            display_msg(prompt, "CAPS MODE", output)
                            time.sleep(0.5)
                        elif current_mode == "CAPS":
                            current_mode = "ALPHA"
                            display_msg(prompt, "ALPHA MODE", output)
                            time.sleep(0.5)
                    
                    # B = Backspace
                    elif key == 'B':
                        if current_preview:
                            # Cancel current letter
                            current_preview = ""
                            last_key = None
                            tap_count = 0
                        else:
                            # Delete last confirmed character
                            output = output[:-1]
                    
                    # * = Clear all
                    elif key == '*':
                        output = ""
                        last_key = None
                        tap_count = 0
                        current_preview = ""
                        display_msg(prompt, "CLEARED", "")
                        time.sleep(0.5)
                    
                    # Number mode input (or password mode which is also numbers)
                    elif key.isdigit():
                        if current_mode == "NUMBER" or show_as_password:
                            output += key
                            print(f"Number input: {'*' * len(output) if show_as_password else output}")
                        # In ALPHA/CAPS mode, numbers trigger letter selection
                        elif current_mode in ["ALPHA", "CAPS"] and key in LETTERS:
                            # Confirm previous letter if different key pressed
                            if key != last_key:
                                if last_key and last_key in LETTERS:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS":
                                        ch = ch.upper()
                                    output += ch
                                    print(f"Auto-confirmed: {ch}")
                                last_key = key
                                tap_count = 0
                            else:
                                # Same key pressed again within timeout
                                if (now - last_time) < 1.0:
                                    tap_count += 1
                                else:
                                    # Timeout - confirm and start new
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS":
                                        ch = ch.upper()
                                    output += ch
                                    print(f"Auto-confirmed: {ch}")
                                    tap_count = 0
                            
                            # Update preview
                            ch = LETTERS[key][tap_count % len(LETTERS[key])]
                            if current_mode == "CAPS":
                                ch = ch.upper()
                            current_preview = ch
                            
                            last_time = now
                            print(f"Alpha input key {key}, tap {tap_count}: preview '{ch}'")
                    
                    time.sleep(0.3)
        
        # Auto-confirm letter after timeout
        if last_key and (time.time() - last_time) > 1.0:
            if last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS":
                    ch = ch.upper()
                output += ch
                print(f"Auto-confirmed: {ch}")
            last_key = None
            tap_count = 0
            current_preview = ""

def authenticate_prof():
    """Returns the Prof name if verified, else None."""
    print("\n--- Professor Authorization Required ---")
    display_msg("ADMIN REQUIRED", "Scan Prof Finger")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, template FROM profs")
    profs = cursor.fetchall()
    conn.close()

    if not profs:
        print("❌ No professors enrolled in system.")
        display_msg("ERROR", "No Profs Found")
        time.sleep(2)
        return None

    uart.reset_input_buffer()
    # 15-second timeout for Admin scan
    timeout = time.time() + 15
    while time.time() < timeout:
        if finger.get_image() == 0:
            finger.image_2_tz(1)
            for name, template in profs:
                finger.send_fpdata(list(template), "char", 2)
                if finger.compare_templates() == 0:
                    print(f"✅ Session authorized by Prof. {name}")
                    display_msg("AUTHORIZED", f"Prof. {name}")
                    time.sleep(1.5)
                    return name
        time.sleep(0.1)
    
    display_msg("TIMEOUT", "Auth Failed")
    time.sleep(2)
    return None

def enroll_student():
    """
    Complete interactive student enrollment with:
    1. Branch selection (from menu)
    2. Program selection (from menu)
    3. Batch year (keyboard input)
    4. Last 3 digits (keyboard input)
    5. First name (keyboard input)
    6. Last name (keyboard input)
    7. Password (keyboard input)
    8. 4-scan fingerprint
    """
    print("\n--- Interactive Student Registration ---")
    
    try:
        # STEP 1: Select Branch
        display_msg("ENROLLMENT", "Select Branch", "Use Joystick")
        time.sleep(1)
        branch_options = list(DEPT_MAP.values())
        selected_branch = select_from_menu("SELECT BRANCH", branch_options)
        branch_code = DEPT_REVERSE[selected_branch]
        print(f"✅ Branch: {selected_branch} ({branch_code})")
        
        # STEP 2: Select Program
        display_msg("ENROLLMENT", "Select Program", "Use Joystick")
        time.sleep(1)
        program_options = list(PROG_MAP.values())
        selected_program = select_from_menu("SELECT PROGRAM", program_options)
        program_code = PROG_REVERSE[selected_program]
        print(f"✅ Program: {selected_program} ({program_code})")
        
        # STEP 3: Enter Batch Year (e.g., 2023)
        display_msg("ENROLLMENT", "Enter Batch Year", "#=Num OK=Ctr")
        time.sleep(1)
        batch_year = read_keypad_input("BATCH YEAR", mode="NUMBER", display_line2="4 digits,OK=Ctr")
        
        if len(batch_year) != 4 or not batch_year.isdigit():
            display_msg("ERROR", "Invalid Year")
            time.sleep(2)
            return
        
        year_short = batch_year[2:4]  # Get last 2 digits (e.g., "23")
        print(f"✅ Batch Year: {batch_year}")
        
        # STEP 4: Enter Last 3 Digits of Roll No
        display_msg("ENROLLMENT", "Last 3 Digits", "#=Num OK=Ctr")
        time.sleep(1)
        roll_suffix = read_keypad_input("ROLL SUFFIX", mode="NUMBER", display_line2="3 digits,OK=Ctr")
        
        if len(roll_suffix) != 3 or not roll_suffix.isdigit():
            display_msg("ERROR", "Need 3 digits")
            time.sleep(2)
            return
        
        print(f"✅ Roll Suffix: {roll_suffix}")
        
        # Generate Roll Number: EE23BT037
        roll_no = f"{branch_code}{year_short}{program_code}{roll_suffix}"
        
        # Display generated Roll Number
        display_msg("ROLL NUMBER", roll_no, "Press Ctr confirm")
        print(f"✅ Generated Roll No: {roll_no}")
        time.sleep(3)
        
        # Check for duplicate
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
        if cursor.fetchone():
            print(f"❌ Error: ID {roll_no} already exists.")
            display_msg("ERROR", f"{roll_no} exists")
            conn.close()
            time.sleep(2)
            return
        conn.close()
        
        # STEP 5: Enter First Name
        display_msg("ENROLLMENT", "Enter First Name", "OK=Center")
        time.sleep(1)
        first_name = read_keypad_input("FIRST NAME", mode="ALPHA", display_line2="C=CAPS,OK=Ctr")
        print(f"✅ First Name: {first_name}")
        
        # STEP 6: Enter Last Name
        display_msg("ENROLLMENT", "Enter Last Name", "OK=Center")
        time.sleep(1)
        last_name = read_keypad_input("LAST NAME", mode="ALPHA", display_line2="C=CAPS,OK=Ctr")
        print(f"✅ Last Name: {last_name}")
        
        # STEP 7: Enter Password (shown as ***)
        display_msg("ENROLLMENT", "Enter Password", "Numbers,OK=Ctr")
        time.sleep(1)
        password = read_keypad_input("PASSWORD", mode="NUMBER", display_line2="Numbers,OK=Ctr", show_as_password=True)
        print(f"✅ Password set (hidden)")
        
        # Display Summary
        display_msg("SUMMARY", f"{first_name} {last_name}", roll_no)
        time.sleep(2)
        
        # STEP 8: Fingerprint Scanning (4 scans)
        print("\n--- Starting 4-Scan Fingerprint Registration ---")
        
        # Scan 1: Base Template
        scan1_successful = False
        retry_attempts = 0
        max_initial_retries = 5
        
        while not scan1_successful and retry_attempts < max_initial_retries:
            display_msg("SCAN 1 of 4", "Place finger")
            uart.reset_input_buffer()
            
            # Wait for finger placement
            finger_placed = False
            timeout = time.time() + 10  # 10 second timeout
            while time.time() < timeout and not finger_placed:
                if finger.get_image() == 0:
                    finger_placed = True
                time.sleep(0.1)
            
            if not finger_placed:
                retry_attempts += 1
                display_msg("TIMEOUT", f"Try {retry_attempts}/{max_initial_retries}")
                time.sleep(1)
                continue
            
            if finger.image_2_tz(1) != 0:
                retry_attempts += 1
                print(f"❌ Bad image quality (attempt {retry_attempts}/{max_initial_retries})")
                display_msg("Bad Image", f"Try {retry_attempts}/{max_initial_retries}")
                time.sleep(1.5)
                continue
            
            print("✅ Scan 1 captured")
            display_msg("SCAN 1 of 4", "Success!")
            time.sleep(1)
            scan1_successful = True
        
        if not scan1_successful:
            print("❌ Failed to get initial scan after multiple attempts")
            display_msg("ENROLLMENT", "FAILED", "Try again later")
            time.sleep(3)
            return
        
        # Scans 2-4: Iterative Merging
        for scan_num in range(2, 5):
            retry_count = 0
            max_retries = 5
            scan_successful = False
            
            while not scan_successful and retry_count < max_retries:
                # Remove finger
                display_msg(f"SCAN {scan_num} of 4", "Remove finger")
                time.sleep(1.5)
                
                # Wait for finger removal
                removal_timeout = time.time() + 5
                while time.time() < removal_timeout:
                    if finger.get_image() != 0:
                        break
                    time.sleep(0.1)
                
                # Place finger again
                display_msg(f"SCAN {scan_num} of 4", "Place finger")
                
                # Wait for finger placement
                finger_placed = False
                placement_timeout = time.time() + 10
                while time.time() < placement_timeout and not finger_placed:
                    if finger.get_image() == 0:
                        finger_placed = True
                    time.sleep(0.1)
                
                if not finger_placed:
                    retry_count += 1
                    display_msg("TIMEOUT", f"Retry {retry_count}/{max_retries}")
                    time.sleep(1.5)
                    continue
                
                if finger.image_2_tz(2) != 0:
                    retry_count += 1
                    print(f"❌ Bad image quality (attempt {retry_count}/{max_retries})")
                    display_msg("Bad Image", f"Retry {retry_count}/{max_retries}")
                    time.sleep(1.5)
                    continue
                
                # Merge with base template
                display_msg(f"SCAN {scan_num} of 4", "Merging...")
                
                if finger.create_model() == 0:
                    print(f"✅ Scan {scan_num} merged")
                    display_msg(f"SCAN {scan_num} of 4", "Success!")
                    time.sleep(1)
                    scan_successful = True
                else:
                    retry_count += 1
                    print(f"⚠️  Scan {scan_num} didn't match (Attempt {retry_count}/{max_retries})")
                    display_msg("No Match", f"Retry {retry_count}/{max_retries}")
                    time.sleep(1.5)
            
            if not scan_successful:
                print(f"❌ Failed to get matching scan {scan_num} after {max_retries} attempts")
                display_msg("ENROLLMENT", "FAILED", "Try again later")
                time.sleep(3)
                return
        
        # Download template
        display_msg("Saving...", "Please wait")
        template = finger.get_fpdata("char", 1)
        
        if not template:
            display_msg("ERROR", "Save Failed")
            time.sleep(2)
            return
        
        # Save to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        sql = "INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        cursor.execute(sql, (roll_no, first_name, last_name, password, selected_branch, 
                            int(batch_year), selected_program, sqlite3.Binary(bytearray(template))))
        conn.commit()
        conn.close()
        
        # Success!
        display_msg("SUCCESS!", f"{first_name} {last_name}", roll_no)
        print(f"✅ Successfully enrolled: {first_name} {last_name} ({roll_no})")
        time.sleep(4)

    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:20])
        time.sleep(2)

def classroom_session(prof_name):
    """
    Continuous loop for student verification and attendance logging.
    Now with course selection using the new database schema.
    """
    print(f"\n🎓 Attendance Session Open (Authorized by {prof_name})")
    
    # Get professor ID from name
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
    
    # Get courses taught by this professor
    cursor.execute("""
        SELECT course_code, course_name 
        FROM courses 
        WHERE prof_id=? 
        ORDER BY course_code
    """, (prof_id,))
    
    courses = cursor.fetchall()
    conn.close()
    
    if not courses:
        display_msg("NO COURSES", "No courses found", "for this prof")
        print("❌ No courses assigned to this professor")
        time.sleep(3)
        return
    
    # Let professor select which course
    display_msg("SELECT COURSE", "Use Joystick", "to choose")
    time.sleep(1)
    
    course_options = [f"{code}: {name[:12]}" for code, name in courses]
    selected_course = select_from_menu("SELECT COURSE", course_options)
    
    # Extract course code from selection
    course_code = selected_course.split(':')[0]
    course_name = [name for code, name in courses if code == course_code][0]
    
    print(f"✅ Selected Course: {course_code} - {course_name}")
    display_msg("COURSE SELECTED", course_code, course_name[:16])
    time.sleep(2)
    
    # Get enrolled students for this course
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
        print(f"❌ No students enrolled in {course_code}")
        time.sleep(3)
        return
    
    print(f"📚 Course: {course_name}")
    print(f"👥 Enrolled Students: {len(enrolled_students)}")
    
    # Start attendance session
    display_msg("CLASS OPEN", course_code, "Scan Finger")
    time.sleep(2)
    
    session_start = time.time()
    attendance_count = 0
    attended_students = set()  # Track who already scanned
    
    while True:
        display_msg("CLASS SESSION", f"{course_code} ({attendance_count})", "Scan or Prof=Exit")
        uart.reset_input_buffer()
        
        if finger.get_image() == 0:
            finger.image_2_tz(1)
            
            # Check if it's the Professor stopping the session
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
                print("🛑 Professor detected. Closing session.")
                session_duration = int((time.time() - session_start) / 60)
                display_msg("SESSION CLOSED", f"Total: {attendance_count}", f"Time: {session_duration}min")
                conn.close()
                time.sleep(3)
                break
            
            # Search enrolled students only
            found = False
            for s_id, s_name, s_template in enrolled_students:
                finger.send_fpdata(list(s_template), "char", 2)
                if finger.compare_templates() == 0:
                    # Check if already scanned in this session
                    if s_id in attended_students:
                        print(f"⚠️  {s_name} ({s_id}) already marked present")
                        display_msg("ALREADY MARKED", s_name, "Present today")
                        time.sleep(2)
                    else:
                        print(f"✅ {s_name} ({s_id}) Verified")
                        display_msg("VERIFIED!", s_name, s_id)
                        
                        # Log to attendance table with course info
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
                print("❌ Unknown or Not Enrolled")
                display_msg("FAILED", "Not enrolled in", course_code)
                time.sleep(1.5)
            
            conn.close()
        time.sleep(0.1)

def view_stats():
    """Display attendance statistics using new database schema"""
    display_msg("Loading Stats", "Please wait...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get total students
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0]
        
        # Get total courses
        cursor.execute("SELECT COUNT(*) FROM courses")
        total_courses = cursor.fetchone()[0]
        
        # Get total professors
        cursor.execute("SELECT COUNT(*) FROM profs")
        total_profs = cursor.fetchone()[0]
        
        # Get today's unique attendance across all courses
        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) 
            FROM attendance 
            WHERE date(session_date) = date('now', 'localtime')
        """)
        today_attendance = cursor.fetchone()[0]
        
        # Get total attendance records today
        cursor.execute("""
            SELECT COUNT(*) 
            FROM attendance 
            WHERE date(session_date) = date('now', 'localtime')
        """)
        today_total = cursor.fetchone()[0]
        
        conn.close()
        
        # Display on OLED (cycle through stats)
        display_msg("STATISTICS", f"Students: {total_students}", f"Courses: {total_courses}")
        time.sleep(3)
        
        display_msg("STATISTICS", f"Professors: {total_profs}", f"Today: {today_attendance}/{total_students}")
        time.sleep(3)
        
        display_msg("TODAY'S DATA", f"Unique: {today_attendance}", f"Total Scans: {today_total}")
        
        print(f"\n📊 System Statistics:")
        print(f"   Total Students: {total_students}")
        print(f"   Total Courses: {total_courses}")
        print(f"   Total Professors: {total_profs}")
        print(f"   Today's Attendance: {today_attendance} unique students")
        print(f"   Today's Total Scans: {today_total}")
        
        time.sleep(3)
        
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")
        display_msg("ERROR", "Stats Failed", str(e)[:16])
        time.sleep(2)

def manage_courses():
    """Course management menu"""
    display_msg("COURSE MGMT", "Loading...")
    time.sleep(1)
    
    course_menu = [
        "Add Course",
        "View Courses",
        "Enroll Students",
        "View Enrollments",
        "Back"
    ]
    
    while True:
        selected = 0
        scroll_offset = 0
        visible_items = 3
        
        while True:
            if selected < scroll_offset:
                scroll_offset = selected
            elif selected >= scroll_offset + visible_items:
                scroll_offset = selected - visible_items + 1
            
            display_scrolling_menu(course_menu, selected, scroll_offset)
            
            button = wait_for_button()
            
            if button == "UP":
                selected = (selected - 1) % len(course_menu)
            elif button == "DOWN":
                selected = (selected + 1) % len(course_menu)
            elif button == "CENTER":
                break
        
        if selected == 0:  # Add Course
            add_course()
        elif selected == 1:  # View Courses
            view_courses()
        elif selected == 2:  # Enroll Students
            enroll_student_in_course()
        elif selected == 3:  # View Enrollments
            view_course_enrollments()
        elif selected == 4:  # Back
            return

def add_course():
    """Add a new course"""
    print("\n--- Add New Course ---")
    
    # Get professor
    display_msg("ADD COURSE", "Prof Auth Needed")
    time.sleep(1)
    
    prof = authenticate_prof()
    if not prof:
        display_msg("AUTH FAILED", "Cannot add course")
        time.sleep(2)
        return
    
    # Get prof_id
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
    
    # Enter course code
    display_msg("ADD COURSE", "Enter Code", "e.g. CS101")
    time.sleep(1)
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA", display_line2="OK=Center")
    
    if not course_code:
        display_msg("CANCELLED")
        time.sleep(1)
        return
    
    course_code = course_code.upper()
    
    # Enter course name
    display_msg("ADD COURSE", "Enter Name")
    time.sleep(1)
    course_name = read_keypad_input("COURSE NAME", mode="ALPHA", display_line2="OK=Center")
    
    if not course_name:
        display_msg("CANCELLED")
        time.sleep(1)
        return
    
    # Select department
    dept_options = list(DEPT_MAP.keys())
    selected_dept = select_from_menu("SELECT DEPT", dept_options)
    
    # Save to database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if course already exists
        cursor.execute("SELECT course_code FROM courses WHERE course_code=?", (course_code,))
        if cursor.fetchone():
            display_msg("ERROR", "Course exists")
            conn.close()
            time.sleep(2)
            return
        
        cursor.execute("""
            INSERT INTO courses (course_code, course_name, prof_id, dept_code) 
            VALUES (?, ?, ?, ?)
        """, (course_code, course_name, prof_id, selected_dept))
        
        conn.commit()
        conn.close()
        
        display_msg("SUCCESS!", course_code, "Course added")
        print(f"✅ Course added: {course_code} - {course_name}")
        time.sleep(3)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def view_courses():
    """View all courses"""
    try:
        conn = sqlite3.connect(DB_PATH)
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
            display_msg("NO COURSES", "No courses found")
            time.sleep(2)
            return
        
        print(f"\n📚 Total Courses: {len(courses)}")
        
        # Display courses one by one
        for code, name, prof in courses:
            display_msg(code, name[:16], f"Prof: {prof[:12]}")
            print(f"  {code}: {name} - {prof}")
            time.sleep(2)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def enroll_student_in_course():
    """Enroll a student in a course"""
    print("\n--- Enroll Student in Course ---")
    
    # Get student ID
    display_msg("ENROLLMENT", "Enter Student ID")
    time.sleep(1)
    student_id = read_keypad_input("STUDENT ID", mode="ALPHA", display_line2="OK=Center")
    
    if not student_id:
        display_msg("CANCELLED")
        time.sleep(1)
        return
    
    student_id = student_id.upper()
    
    # Verify student exists
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
    print(f"✅ Student: {student_name}")
    
    # Get available courses
    cursor.execute("SELECT course_code, course_name FROM courses ORDER BY course_code")
    courses = cursor.fetchall()
    
    if not courses:
        display_msg("NO COURSES", "No courses found")
        conn.close()
        time.sleep(2)
        return
    
    # Select course
    course_options = [f"{code}: {name[:10]}" for code, name in courses]
    selected_course = select_from_menu("SELECT COURSE", course_options)
    course_code = selected_course.split(':')[0]
    
    try:
        # Check if already enrolled
        cursor.execute("""
            SELECT enrollment_id FROM course_enrollments 
            WHERE student_id=? AND course_code=?
        """, (student_id, course_code))
        
        if cursor.fetchone():
            display_msg("ALREADY", "Enrolled", course_code)
            time.sleep(2)
        else:
            # Enroll student
            cursor.execute("""
                INSERT INTO course_enrollments (student_id, course_code, status)
                VALUES (?, ?, 'active')
            """, (student_id, course_code))
            
            conn.commit()
            
            display_msg("SUCCESS!", student_name[:16], f"Enrolled {course_code}")
            print(f"✅ Enrolled {student_name} in {course_code}")
            time.sleep(3)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def view_course_enrollments():
    """View enrollments for a course"""
    # Get course code
    display_msg("VIEW ENROLL", "Enter Course Code")
    time.sleep(1)
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA", display_line2="OK=Center")
    
    if not course_code:
        display_msg("CANCELLED")
        time.sleep(1)
        return
    
    course_code = course_code.upper()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.student_id, s.first_name, s.last_name, s.dept
            FROM students s
            JOIN course_enrollments ce ON s.student_id = ce.student_id
            WHERE ce.course_code = ? AND ce.status = 'active'
            ORDER BY s.student_id
        """, (course_code,))
        
        enrollments = cursor.fetchall()
        conn.close()
        
        if not enrollments:
            display_msg("NO STUDENTS", "No enrollments", course_code)
            time.sleep(2)
            return
        
        print(f"\n👥 Enrollments for {course_code}: {len(enrollments)}")
        
        # Display students
        for sid, fname, lname, dept in enrollments:
            display_msg(sid, f"{fname} {lname}"[:16], dept[:16])
            print(f"  {sid}: {fname} {lname} ({dept})")
            time.sleep(2)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:16])
        time.sleep(2)

def admin_settings():
    """Admin settings - Course management"""
    display_msg("ADMIN SETTINGS", "Course Management")
    print("\n⚙️  Admin Settings - Course Management")
    time.sleep(1)
    manage_courses()

def system_info():
    """Display system information"""
    display_msg("SYSTEM INFO", "IITDH v2.0", "Raspberry Pi")
    print("\n💻 System Information:")
    print("   Device: Raspberry Pi")
    print("   Software: IITDH Biometric v2.0")
    print("   Fingerprint: R307S Sensor")
    time.sleep(5)

# --- Main Program Loop ---
try:
    display_msg("IITDH System", "Initializing...", "Please wait")
    time.sleep(2)
    
    while True:
        # Show menu and get selection
        selection = show_menu()
        
        if selection == 0:  # Enroll Student
            print("\n📝 Selected: Enroll Student")
            prof = authenticate_prof()
            if prof:
                enroll_student()
            else:
                print("❌ Authentication Failed.")
                display_msg("AUTH FAILED", "Access Denied")
                time.sleep(2)
                
        elif selection == 1:  # Take Attendance
            print("\n📋 Selected: Take Attendance")
            prof = authenticate_prof()
            if prof:
                classroom_session(prof)
            else:
                print("❌ Authentication Failed.")
                display_msg("AUTH FAILED", "Access Denied")
                time.sleep(2)
        
        elif selection == 2:  # View Stats
            print("\n📊 Selected: View Stats")
            view_stats()
        
        elif selection == 3:  # Admin Settings
            print("\n⚙️  Selected: Admin Settings")
            prof = authenticate_prof()
            if prof:
                admin_settings()
            else:
                display_msg("AUTH FAILED", "Access Denied")
                time.sleep(2)
        
        elif selection == 4:  # System Info
            print("\n💻 Selected: System Info")
            system_info()
                
        elif selection == 5:  # System Shutdown
            print("\n🔌 Selected: System Shutdown")
            display_msg("CONFIRM?", "Press CENTER", "to Shutdown")
            button = wait_for_button()
            if button == "CENTER":
                display_msg("SHUTTING DOWN", "Goodbye!", "")
                print("System shutting down...")
                time.sleep(2)
                GPIO.cleanup()
                os.system("sudo shutdown -h now")
                break
            else:
                print("Shutdown cancelled")
                continue

except KeyboardInterrupt:
    print("\n⚠️  System Shutdown by User")
    display_msg("SHUTDOWN", "Goodbye!")
    time.sleep(1)
    GPIO.cleanup()

except Exception as e:
    print(f"\n❌ Critical Error: {e}")
    display_msg("SYSTEM ERROR", str(e)[:20])
    time.sleep(3)
    GPIO.cleanup()