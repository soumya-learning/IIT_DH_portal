import time
import RPi.GPIO as GPIO
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

# Manual Reset to wake up the chip
RST_PIN = 25
GPIO.setmode(GPIO.BCM)
GPIO.setup(RST_PIN, GPIO.OUT)
GPIO.output(RST_PIN, GPIO.LOW)
time.sleep(0.1)
GPIO.output(RST_PIN, GPIO.HIGH)

try:
    # Use a slower baudrate (8MHz) which is more stable for jumper wires
    serial_interface = spi(device=0, port=0, bus_speed_hz=8000000, 
                           gpio_DC=24, gpio_RST=25, gpio_CS=16)
    
    device = ssd1306(serial_interface)

    with canvas(device) as draw:
        # Fill screen white to test all pixels
        draw.rectangle(device.bounding_box, outline="white", fill="white")
    
    print("Screen should be completely white now.")
    time.sleep(5)
    
    with canvas(device) as draw:
        draw.text((10, 20), "WIRING VERIFIED!", fill="black")

except Exception as e:
    print(f"Error: {e}")
finally:
    GPIO.cleanup()