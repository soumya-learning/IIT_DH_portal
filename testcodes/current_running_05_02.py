import time
import serial
import sqlite3
import os
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

# --- Mapping Dictionaries ---
DEPT_MAP = {"CS": "Computer Science", "EE": "Electrical Engineering", "MC": "Math & Computing", 
            "ME": "Mechanical Engineering", "CH": "Chemical Engineering", "CE": "Civil Engineering"}
PROG_MAP = {"BT": "B.Tech", "IS": "BSMS", "MT": "M.Tech"}

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
    
    Args:
        options: List of menu items
        selected_index: Currently selected item index
        scroll_offset: Top visible item index
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
            
            # Draw menu text
            draw.text((8, y_pos + 2), options[item_index], fill=text_color)
        
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
    Enrolls student with FIXED 4-scan cumulative merging.
    
    HOW IT WORKS:
    - Scan 1: Captured to Buffer 1 (base template)
    - Scan 2: Stored in Buffer 2, merged with Buffer 1, result stays in Buffer 1
    - Scan 3: Stored in Buffer 2, merged with updated Buffer 1, result stays in Buffer 1
    - Scan 4: Stored in Buffer 2, merged with updated Buffer 1, final template in Buffer 1
    """
    print("\n--- Student Registration (Fixed 4-Scan Merge) ---")
    
    # Get student details via keyboard input
    display_msg("Student Enroll", "Use Keyboard")
    user_input = input("Enter (ID, First Name, Last Name, Password): ")
    
    try:
        data = [item.strip() for item in user_input.split(',')]
        if len(data) != 4:
            print("❌ Error: Format must be: ID, First, Last, Pass")
            display_msg("ERROR", "Invalid Format")
            time.sleep(2)
            return
        
        s_id = data[0].upper()
        f_name, l_name, pwd = data[1], data[2], data[3]
        
        # Mapping and Duplicate Checks
        full_dept = DEPT_MAP.get(s_id[0:2], "Unknown")
        full_year = int(f"20{s_id[2:4]}")
        full_prog = PROG_MAP.get(s_id[4:6], "Unknown")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (s_id,))
        if cursor.fetchone():
            print(f"❌ Error: ID {s_id} already exists.")
            display_msg("ERROR", f"{s_id} exists")
            conn.close()
            time.sleep(2)
            return
        conn.close()

        # --- STEP 1: INITIAL SCAN (Scan 1) - BASE TEMPLATE ---
        print("\n📌 SCAN 1/4: Creating base template...")
        display_msg("SCAN 1 of 4", "Place finger")
        uart.reset_input_buffer()
        
        while finger.get_image() != 0: 
            time.sleep(0.1)
        
        if finger.image_2_tz(1) != 0:
            print("❌ Bad image quality")
            display_msg("ERROR", "Bad Image")
            time.sleep(2)
            return
        
        print("✅ Scan 1 captured in Buffer 1")
        
        # --- STEP 2-4: ITERATIVE MERGING WITH RETRY ---
        for scan_num in range(2, 5):  # Scans 2, 3, 4
            retry_count = 0
            max_retries = 3
            scan_successful = False
            
            while not scan_successful and retry_count < max_retries:
                # Wait for finger removal
                print(f"\n📌 SCAN {scan_num}/4: Remove finger...")
                display_msg(f"SCAN {scan_num} of 4", "Remove finger")
                time.sleep(1.5)
                
                # Ensure finger is removed
                while finger.get_image() == 0:
                    time.sleep(0.1)
                
                # Request new scan
                print(f"📌 SCAN {scan_num}/4: Place finger again...")
                display_msg(f"SCAN {scan_num} of 4", "Place finger")
                
                while finger.get_image() != 0:
                    time.sleep(0.1)
                
                # Store new scan in Buffer 2
                if finger.image_2_tz(2) != 0:
                    print("❌ Bad image quality, try again...")
                    display_msg("Bad Image", "Try Again")
                    retry_count += 1
                    time.sleep(1)
                    continue
                
                # CRITICAL: Merge Buffer 2 with Buffer 1
                # Result stays in Buffer 1 (cumulative template)
                print(f"🔄 Merging scan {scan_num} with base template...")
                display_msg(f"SCAN {scan_num} of 4", "Merging...")
                
                if finger.create_model() == 0:
                    print(f"✅ Scan {scan_num} matched and merged successfully!")
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
                display_msg("FAILED", "Too many retries")
                time.sleep(2)
                return

        # --- STEP 3: DOWNLOAD FINAL MERGED TEMPLATE FROM BUFFER 1 ---
        print("\n💾 Downloading final merged template...")
        display_msg("Saving...", "Please wait")
        
        template = finger.get_fpdata("char", 1)  # Get from Buffer 1
        
        if not template:
            print("❌ Failed to download template")
            display_msg("ERROR", "Save Failed")
            time.sleep(2)
            return
        
        # Save to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        sql = "INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        cursor.execute(sql, (s_id, f_name, l_name, pwd, full_dept, full_year, full_prog, sqlite3.Binary(bytearray(template))))
        conn.commit()
        conn.close()
        
        display_msg("SUCCESS!", f"{f_name} Enrolled")
        print(f"✅ Successfully enrolled: {f_name} {l_name} ({s_id})")
        print(f"   4 scans merged into high-quality template")
        time.sleep(3)

    except Exception as e:
        print(f"❌ CRASH: {e}")
        display_msg("ERROR", str(e)[:20])
        time.sleep(2)

def classroom_session(prof_name):
    """Continuous loop for student verification and attendance logging."""
    print(f"\n🎓 Attendance Session Open (Authorized by {prof_name})")
    display_msg("CLASS OPEN", f"By: {prof_name}", "Scan Finger")
    time.sleep(2)
    
    session_start = time.time()
    attendance_count = 0
    
    while True:
        display_msg("CLASS SESSION", f"Count: {attendance_count}", "Scan or Prof=Exit")
        uart.reset_input_buffer()
        
        if finger.get_image() == 0:
            finger.image_2_tz(1)
            
            # Check if it's the Professor stopping the session
            is_prof = False
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT template FROM profs")
            for (p_temp,) in cursor.fetchall():
                finger.send_fpdata(list(p_temp), "char", 2)
                if finger.compare_templates() == 0:
                    is_prof = True
                    break
            
            if is_prof:
                print("🛑 Professor detected. Closing session.")
                session_duration = int((time.time() - session_start) / 60)
                display_msg("SESSION CLOSED", f"Total: {attendance_count}", f"Time: {session_duration}min")
                conn.close()
                time.sleep(3)
                break

            # Search Students
            cursor.execute("SELECT student_id, first_name, template FROM students")
            students = cursor.fetchall()
            
            found = False
            for s_id, s_name, s_template in students:
                finger.send_fpdata(list(s_template), "char", 2)
                if finger.compare_templates() == 0:
                    print(f"✅ {s_name} ({s_id}) Verified")
                    display_msg("VERIFIED!", s_name, s_id)
                    
                    # Log to attendance table
                    cursor.execute("INSERT INTO attendance (student_id, student_name, authorized_by, timestamp) VALUES (?, ?, ?, datetime('now', 'localtime'))", 
                                   (s_id, s_name, prof_name))
                    conn.commit()
                    attendance_count += 1
                    found = True
                    time.sleep(2)
                    break
            
            if not found:
                print("❌ Unknown Fingerprint")
                display_msg("FAILED", "Unknown User")
                time.sleep(1.5)
            
            conn.close()
        time.sleep(0.1)

def view_stats():
    """Display attendance statistics"""
    display_msg("Loading Stats", "Please wait...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get total students
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0]
        
        # Get today's attendance
        cursor.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE date(timestamp) = date('now', 'localtime')")
        today_attendance = cursor.fetchone()[0]
        
        conn.close()
        
        display_msg("STATISTICS", f"Students: {total_students}", f"Today: {today_attendance}")
        print(f"\n📊 Statistics:")
        print(f"   Total Students: {total_students}")
        print(f"   Today's Attendance: {today_attendance}")
        
        time.sleep(5)
        
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")
        display_msg("ERROR", "Stats Failed")
        time.sleep(2)

def admin_settings():
    """Placeholder for admin settings"""
    display_msg("ADMIN SETTINGS", "Coming Soon...")
    print("\n⚙️  Admin Settings - Feature in development")
    time.sleep(3)

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
