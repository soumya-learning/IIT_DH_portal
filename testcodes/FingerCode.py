import time
import serial
import adafruit_fingerprint

# --- CONFIGURATION ---
# Your setup confirmed this port works
SERIAL_PORT = "/dev/ttyUSB0"  
BAUD_RATE = 57600 

def get_fingerprint_sensor():
    try:
        uart = serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=1)
        finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)
        return finger
    except Exception as e:
        print(f"❌ ERROR: {e}")
        exit()

def check_connection():
    finger = get_fingerprint_sensor()
    print(f"Attempting to connect via {SERIAL_PORT}...")
    
    if finger.read_sysparam() != adafruit_fingerprint.OK:
        print("❌ FAILURE: Sensor not found.")
        return

    print("✅ SUCCESS: Fingerprint sensor detected!")
    print("-" * 30)
    print(f"Model Parameters:")
    print(f" - Capacity: {finger.library_size} templates")
    print(f" - Security Level: {finger.security_level}")
    
    # --- FIXED LINE BELOW ---
    # We check if address is bytes or int to prevent crashing
    addr = finger.device_address
    if isinstance(addr, bytes):
        print(f" - Device Address: {addr.hex()}")
    else:
        print(f" - Device Address: {hex(addr)}")
    # ------------------------
    
    print("-" * 30)
    print("\nWaiting for finger... (Press Ctrl+C to exit)")

    while True:
        # get_image() returns OK (0) if successful
        result = finger.get_image()
        if result == adafruit_fingerprint.OK:
            print("Finger detected! Image taken.")
            
            # Optional: detailed verify to ensure image is readable
            if finger.image_2_tz(1) == adafruit_fingerprint.OK:
                print(" -> Image converted to template OK.")
            else:
                print(" -> Failed to convert image.")
                
        elif result != adafruit_fingerprint.NOFINGER:
            # Print specific error if something else happens
            print(f"Error capturing image: {result}")
            
        time.sleep(0.1)

if __name__ == "__main__":
    check_connection()