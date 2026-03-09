import time
import serial
import board
import busio
from adafruit_fingerprint import Adafruit_Fingerprint
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

# --- 1. OLED Setup (Updated for your working pins & 1MHz) ---
try:
    # Match your working Hello World Table:
    # Pin 24 = GPIO 8 (CS)
    # Pin 22 = GPIO 25 (DC)
    # Pin 13 = GPIO 24 (RST)
    oled_interface = spi(
        device=0, 
        port=0, 
        bus_speed_hz=1000000, # Set to 1MHz for stability
        gpio_DC=25, 
        gpio_RST=24, 
        gpio_CS=8
    )
    device = ssd1306(oled_interface)
    device.contrast(255) # Keep it bright
except Exception as e:
    print(f"OLED Error: {e}. Try running 'sudo pkill python' first.")

# --- 2. Fingerprint Sensor Setup (USB) ---
try:
    # Check /dev/ttyUSB0 first, then /dev/ttyACM0
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
except:
    try:
        uart = serial.Serial("/dev/ttyACM0", baudrate=57600, timeout=1)
        finger = Adafruit_Fingerprint(uart)
    except Exception as e:
        print(f"Fingerprint Error: {e}")

def display_msg(line1, line2=""):
    with canvas(device) as draw:
        # Border added for visual confirmation of screen limits
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 15), line1, fill="white")
        draw.text((5, 35), line2, fill="white")

def enroll_process(id_num):
    display_msg("Place finger", "Step 1: Scan")
    while finger.get_image() != 0: pass
    finger.image_2_tz(1)
    
    display_msg("Remove finger", "Wait...")
    time.sleep(2)
    
    display_msg("Place finger", "Step 2: Confirm")
    while finger.get_image() != 0: pass
    finger.image_2_tz(2)

    if finger.create_model() == 0:
        if finger.store_model(id_num) == 0:
            display_msg("Successful!", f"Saved to ID {id_num}")
        else:
            display_msg("Error", "Storage Failed")
    else:
        display_msg("Finger not matched", "Try Again")
    time.sleep(2)

def verify_process():
    display_msg("Place your finger", "Verifying...")
    # Add a small delay to allow user to place finger
    time.sleep(1) 
    if finger.get_image() == 0:
        if finger.image_2_tz(1) == 0:
            if finger.finger_search() == 0:
                display_msg("Successful!", f"Found ID: {finger.finger_id}")
            else:
                display_msg("Unsuccessful", "No Match Found")
            time.sleep(2)
    else:
        display_msg("No finger detected", "Try again")
        time.sleep(1)

# --- Main Loop ---
try:
    while True:
        display_msg("E: Enroll New", "V: Verify Finger")
        choice = input("Enter 'e' or 'v' (or 'q' to quit): ").lower()
        if choice == 'e':
            try:
                target_id = int(input("Enter ID (1-127): "))
                enroll_process(target_id)
            except ValueError:
                print("Please enter a valid number.")
        elif choice == 'v':
            verify_process()
        elif choice == 'q':
            break
except KeyboardInterrupt:
    print("\nExiting...")