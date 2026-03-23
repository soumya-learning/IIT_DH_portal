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
    oled_interface = spi(device=0, port=0, bus_speed_hz=1000000, gpio_DC=25, gpio_RST=24, gpio_CS=8)
    device = ssd1306(oled_interface)
    device.contrast(255)

    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
except Exception as e:
    print(f"Hardware Setup Error: {e}")

def display_msg(line1, line2=""):
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 15), line1, fill="white")
        draw.text((5, 35), line2, fill="white")

def enroll_student():
    print("\n--- Student Registration ---")
    user_input = input("Enter (ID, First Name, Last Name, Password): ")
    
    try:
        data = [item.strip() for item in user_input.split(',')]
        if len(data) != 4:
            print("❌ Error: Format must be: ID, First, Last, Pass")
            return
        
        s_id = data[0].upper()
        f_name, l_name, pwd = data[1], data[2], data[3]
        
        # Smart-Key Logic
        full_dept = DEPT_MAP.get(s_id[0:2], "Unknown")
        full_year = int(f"20{s_id[2:4]}")
        full_prog = PROG_MAP.get(s_id[4:6], "Unknown")

        print(f"STEP 1: Checking DB for {s_id}...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (s_id,))
        if cursor.fetchone():
            print(f"❌ Error: ID {s_id} already exists.")
            conn.close()
            return
        conn.close()

        print("STEP 2: Waiting for first finger scan...")
        display_msg("Place finger", "Scan 1")
        uart.reset_input_buffer()
        while finger.get_image() != 0: 
            pass # Script hangs here if sensor doesn't see finger
        
        print("STEP 3: Converting Scan 1...")
        if finger.image_2_tz(1) != 0:
            print("❌ Error: Conversion 1 failed")
            return

        print("STEP 4: Waiting for second finger scan...")
        display_msg("Remove finger", "Wait...")
        time.sleep(2)
        display_msg("Place finger", "Scan 2")
        while finger.get_image() != 0: pass
        
        print("STEP 5: Converting Scan 2 and creating model...")
        if finger.image_2_tz(2) != 0:
            print("❌ Error: Conversion 2 failed")
            return

        if finger.create_model() == 0:
            print("STEP 6: Extracting template from sensor...")
            template = finger.get_fpdata() # If this fails, code stops here
            
            print("STEP 7: Writing to SQLite...")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            sql = """INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            
            cursor.execute(sql, (s_id, f_name, l_name, pwd, full_dept, full_year, full_prog, sqlite3.Binary(bytearray(template))))
            conn.commit()
            print("STEP 8: Commit complete!")
            
            # Final check
            cursor.execute("SELECT student_id FROM students WHERE student_id=?", (s_id,))
            if cursor.fetchone():
                print(f"✅ SUCCESS: {f_name} is now in the DB.")
                display_msg("Success!", f"{f_name} Saved")
            else:
                print("❌ FATAL: Database accepted query but row is missing.")
            conn.close()
        else:
            print("❌ Error: Fingerprints did not match.")
            display_msg("Fail", "No Match")

    except Exception as e:
        print(f"❌ CRASH: {e}")

def verify_student():
    s_id = input("Enter Student ID to login: ").strip()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, template FROM students WHERE student_id=?", (s_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[1]:
        name, template_data = result[0], result[1]
        
        try:
            # 1. Clear any junk from the serial buffer before starting
            uart.reset_input_buffer()
            
            # 2. Upload stored template to sensor buffer 2
            print(f"Uploading template for {name}...")
            finger.send_fpdata(list(template_data), "char", 2)
            
            # 3. CRITICAL: Give the sensor a moment to breathe after the big data transfer
            time.sleep(0.5) 
            
            display_msg(f"Hello {name}", "Scan Finger")
            print(f"Waiting for {name} to scan finger...")
            
            # 4. Wait for live scan with stabilized loop
            timeout = time.time() + 10
            while time.time() < timeout:
                # get_image() returns 0 (OK), 2 (No finger), or others (Error)
                result_code = finger.get_image()
                
                if result_code == 0:
                    finger.image_2_tz(1)
                    if finger.compare_templates() == 0:
                        display_msg("Verified!", f"Welcome {name}")
                        print(f"✅ Access Granted for {name}")
                        return
                    else:
                        display_msg("Failed", "Try Again")
                        time.sleep(1)
                
                # Small delay to prevent the Pi 5 from overwhelming the UART bus
                time.sleep(0.1)
                
            display_msg("Timed Out", "No Finger")
            
        except RuntimeError as e:
            print(f"⚠️ Communication Error: {e}")
            print("Try again - the Serial bus just got out of sync.")
            uart.reset_input_buffer() # Clean up for the next attempt
    else:
        print("❌ Student ID not found.")

# --- Main Interface ---
try:
    while True:
        display_msg("E: Enroll", "V: Verify")
        choice = input("\n[E]nroll, [V]erify, or [Q]uit: ").lower()
        if choice == 'e':
            enroll_student()
        elif choice == 'v':
            verify_student()
        elif choice == 'q':
            break
except KeyboardInterrupt:
    print("\nSystem Shutdown")