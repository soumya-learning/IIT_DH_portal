import time
import serial
import sqlite3
from adafruit_fingerprint import Adafruit_Fingerprint
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

# --- Mapping Dictionaries ---
DEPT_MAP = {"CS": "Computer Science", "EE": "Electrical Engineering", "MC": "Math & Computing", 
            "ME": "Mechanical Engineering", "CH": "Chemical Engineering", "CE": "Civil Engineering"}
PROG_MAP = {"BT": "B.Tech", "IS": "BSMS", "MT": "M.Tech"}

DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# --- Hardware Setup ---
try:
    # OLED via SPI
    oled_interface = spi(device=0, port=0, bus_speed_hz=1000000, gpio_DC=25, gpio_RST=24, gpio_CS=8)
    device = ssd1306(oled_interface)
    device.contrast(255)

    # R307S via USB-UART or GPIO-UART
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
except Exception as e:
    print(f"Hardware Setup Error: {e}")

def display_msg(line1, line2=""):
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 15), line1, fill="white")
        draw.text((5, 35), line2, fill="white")

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
                    return name
    return None

def enroll_student():
    """Enrolls student with 4-scan cumulative merging and retry logic."""
    print("\n--- Student Registration (4-Scan Merge) ---")
    user_input = input("Enter (ID, First Name, Last Name, Password): ")
    
    try:
        data = [item.strip() for item in user_input.split(',')]
        if len(data) != 4:
            print("❌ Error: Format must be: ID, First, Last, Pass")
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
            conn.close()
            return
        conn.close()

        # --- STEP 1: INITIAL SCAN (Scan 1) ---
        display_msg("Place finger", "Scan 1 of 4")
        uart.reset_input_buffer()
        while finger.get_image() != 0: pass
        finger.image_2_tz(1) 

        # --- STEP 2: ITERATIVE MERGING WITH RETRY (Scans 2, 3, 4) ---
        current_step = 2
        while current_step <= 4:
            display_msg("Remove finger", "Wait...")
            time.sleep(1.5)
            while finger.get_image() == 0: pass # Ensure removal
            
            display_msg("Place finger", f"Scan {current_step} of 4")
            while finger.get_image() != 0: pass
            
            # Extract to Buffer 2 for comparison
            if finger.image_2_tz(2) != 0:
                print("Bad image, try again...")
                continue
            
            # Attempt to merge with the existing "Master" in Buffer 1
            display_msg("Merging...", f"Processing {current_step}")
            if finger.create_model() == 0:
                print(f"✅ Scan {current_step} matched and merged.")
                current_step += 1 # Only move to next scan if successful
            else:
                display_msg("No Match", "Try Again")
                print(f"⚠️ Scan {current_step} didn't match the previous base. Please re-scan.")
                time.sleep(1)

        # --- STEP 3: DOWNLOAD & SAVE ---
        template = finger.get_fpdata(1) 
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        sql = "INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        cursor.execute(sql, (s_id, f_name, l_name, pwd, full_dept, full_year, full_prog, sqlite3.Binary(bytearray(template))))
        conn.commit()
        conn.close()
        
        display_msg("Success!", f"{f_name} Saved")
        print(f"✅ Registered: {f_name} with Merged 4-Scan Template")

    except Exception as e:
        print(f"❌ CRASH: {e}")
def classroom_session(prof_name):
    """Continuous loop for student verification and attendance logging."""
    print(f"\n🎓 Attendance Session Open (Authorized by {prof_name})")
    time.sleep(2)
    
    while True:
        display_msg("CLASS OPEN", "Scan Finger")
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
                display_msg("SESSION CLOSED", "Goodbye")
                conn.close()
                time.sleep(2)
                break

            # Search Students
            cursor.execute("SELECT student_id, first_name, template FROM students")
            students = cursor.fetchall()
            
            found = False
            for s_id, s_name, s_template in students:
                finger.send_fpdata(list(s_template), "char", 2)
                if finger.compare_templates() == 0:
                    print(f"✅ {s_name} ({s_id}) Verified")
                    display_msg("Verified!", s_name)
                    
                    # Log to attendance table
                    cursor.execute("INSERT INTO attendance (student_id, student_name, authorized_by) VALUES (?, ?, ?)", 
                                   (s_id, s_name, prof_name))
                    conn.commit()
                    found = True
                    time.sleep(2) # Stop double-scanning
                    break
            
            if not found:
                print("❌ Unknown Fingerprint")
                display_msg("Failed", "Unknown User")
                time.sleep(1)
            
            conn.close()
        time.sleep(0.1)

# --- Main Program Loop ---
try:
    while True:
        display_msg("IITDH Attendance", "P: Start | E: Enroll")
        print("\n--- IITDH BIOMETRIC SYSTEM ---")
        choice = input("[P] Start Class Session, [E]nroll Student, [Q]uit: ").lower()
        
        if choice == 'p':
            prof = authenticate_prof()
            if prof:
                classroom_session(prof)
            else:
                print("❌ Authentication Failed.")
                
        elif choice == 'e':
            if authenticate_prof():
                enroll_student()
                
        elif choice == 'q':
            display_msg("Shutting down", "System Off")
            break
except KeyboardInterrupt:
    print("\nSystem Shutdown by User")
