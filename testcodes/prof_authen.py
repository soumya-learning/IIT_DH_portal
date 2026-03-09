import time
import serial
import sqlite3
import os
from adafruit_fingerprint import Adafruit_Fingerprint
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

#Configuration
DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'
MASTER_PASSWORD = "IITDH_ADMIN" 

#Hardware Setup
try:
# OLED SPI Setup
    oled_interface = spi(device=0, port=0, bus_speed_hz=1000000, gpio_DC=25, gpio_RST=24, gpio_CS=8)
    device = ssd1306(oled_interface)
    device.contrast(255)

# Fingerprint Sensor Setup
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
except Exception as e:
    print(f"❌ Hardware Connection Error: {e}")
    exit()

def display_msg(line1, line2=""):
    
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 15), line1, fill="white")
        draw.text((5, 35), line2, fill="white")

def setup_prof_table():
   
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profs (
            prof_id TEXT PRIMARY KEY,
            name TEXT,
            template BLOB
        )
    """)
    conn.commit()
    conn.close()

def enroll_prof():
    display_msg("ADMIN SYSTEM", "Enter Password")
    print("\n Professor Enrollment System")
    auth = input("Enter Master Password to proceed: ")
    if auth != MASTER_PASSWORD:
        display_msg("ACCESS DENIED", "Wrong Password")
        print("❌ Unauthorized access!")
        return

    prof_id = input("Enter Professor ID (e.g., P001): ").strip().upper()
    name = input("Enter Professor Name: ").strip()

    print(f"\nReady to enroll Prof. {name}.")
    display_msg(f"Enroll: {name}", "Place Finger")
    
    try:
        # Step 1: Capture First Scan
        print("Place finger on sensor...")
        while finger.get_image() != 0: pass
        finger.image_2_tz(1)
        
        display_msg("LIFT FINGER", "Wait...")
        print("Remove finger...")
        time.sleep(2)
        
        # Step 2: Capture Second Scan
        display_msg("PLACE AGAIN", "Confirming...")
        print("Place same finger again to confirm...")
        while finger.get_image() != 0: pass
        finger.image_2_tz(2)

        # Step 3: Create Model and Extract Template
        if finger.create_model() == 0:
            display_msg("SAVING...", "Please Wait")
            print("Creating template...")
            template = finger.get_fpdata()
            
            # Step 4: Save to Database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO profs (prof_id, name, template) 
                    VALUES (?, ?, ?)
                """, (prof_id, name, sqlite3.Binary(bytearray(template))))
                conn.commit()
                display_msg("SUCCESS!", f"Prof {name}")
                print(f"✅ Success! Prof. {name} registered.")
            except sqlite3.IntegrityError:
                display_msg("ERROR", "ID Exists")
                print(f"❌ Error: Professor ID {prof_id} already exists.")
            finally:
                conn.close()
        else:
            display_msg("MATCH FAIL", "Try Again")
            print("❌ Error: Fingerprints did not match. Try again.")

    except Exception as e:
        display_msg("CRASH", "Check Terminal")
        print(f"❌ Enrollment Crash: {e}")

if __name__ == "__main__":
    setup_prof_table()
    while True:
        enroll_prof()
        cont = input("\nEnroll another professor? (y/n): ").lower()
        if cont != 'y':
            break
    display_msg("SYSTEM READY", "Admin Logged Out")
    print("Exiting Professor Enrollment.")