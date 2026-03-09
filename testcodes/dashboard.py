import os
# FORCE the Pi 5 to use the lgpio driver BEFORE importing luma
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

from luma.core.interface.serial import spi
from luma.oled.device import ssd1309
from luma.core.render import canvas
import time
import socket

# Setup SPI for Pi 5
try:
    # On Pi 5, we must use the spi interface explicitly
    serial = spi(device=0, port=0, gpio_DC=25, gpio_RST=27)
    
    # Initialize the 2.42 inch SSD1309 OLED
    device = ssd1309(serial, width=128, height=64)
    print("OLED Initialized Successfully!")
except Exception as e:
    print(f"Hardware Error: {e}")
    print("\nTroubleshooting Steps:")
    print("1. Run: pip install rpi-lgpio gpiod")
    print("2. Run: sudo usermod -a -G spi,gpio $USER (then reboot)")
    exit()

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

try:
    while True:
        with canvas(device) as draw:
            draw.rectangle(device.bounding_box, outline="white", fill="black")
            draw.text((10, 5), "Happy Birthday Soumya", fill="white")
            draw.line((0, 18, 128, 18), fill="white")
            draw.text((10, 25), f"IP: {get_ip()}", fill="white")
            draw.text((10, 45), "STATUS: Ready", fill="white")
        time.sleep(2)
except KeyboardInterrupt:
    print("Stopping...")