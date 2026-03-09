import serial
from adafruit_fingerprint import Adafruit_Fingerprint

# Setup Serial
try:
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
except:
    uart = serial.Serial("/dev/ttyACM0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)

def clear_sensor():
    print("Attempting to erase all fingerprint templates...")
    if finger.empty_library() == 0:
        print("✅ Success: Sensor flash memory is now empty.")
    else:
        print("❌ Error: Failed to clear sensor memory.")

if __name__ == "__main__":
    confirm = input("This will delete ALL fingerprints from the sensor flash. Type 'yes' to proceed: ")
    if confirm.lower() == 'yes':
        clear_sensor()
    else:
        print("Operation cancelled.")