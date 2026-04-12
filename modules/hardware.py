import time, serial, smbus
from contextlib import contextmanager
import RPi.GPIO as GPIO
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas
from adafruit_fingerprint import Adafruit_Fingerprint
from modules.config import *

# Shared hardware objects — imported by all other modules
device   = None
uart     = None
finger   = None
bus      = smbus.SMBus(1)
KEYBOARD_AVAILABLE = False

# ─────────────────────────────────────────────
# BACK-LOCK FLAG
# When True, the D key / BackToMainMenu is silently ignored.
# Use back_locked() context manager — never set directly.
#
# LOCKED during:
#   • Active attendance session (only prof fingerprint closes it)
#
# NOT locked during (D works normally):
#   • Course selection BEFORE session starts (can cancel)
#   • Enrollment between scan attempts (can cancel)
#   • All menu navigation and text entry
# ─────────────────────────────────────────────
_BACK_LOCKED = False


def lock_back():
    global _BACK_LOCKED
    _BACK_LOCKED = True
    print("[BackLock] D key DISABLED")


def unlock_back():
    global _BACK_LOCKED
    _BACK_LOCKED = False
    print("[BackLock] D key enabled")


@contextmanager
def back_locked():
    """
    Context manager — disables D key for the duration of the with-block.
    Always re-enables on exit, even if an exception is raised.

    Usage:
        with hw.back_locked():
            run_attendance_session()   # D disabled
        # D automatically re-enabled here
    """
    lock_back()
    try:
        yield
    finally:
        unlock_back()


def init_hardware(max_attempts=5, retry_delay=2):
    global device, uart, finger, KEYBOARD_AVAILABLE
    for attempt in range(1, max_attempts + 1):
        try:
            oled_iface = spi(device=0, port=0, bus_speed_hz=1000000,
                             gpio_DC=25, gpio_RST=27, gpio_CS=8)
            device = ssd1306(oled_iface)
            device.contrast(255)

            uart   = serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=1)
            finger = Adafruit_Fingerprint(uart)

            GPIO.setmode(GPIO.BCM)
            for pin in [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT,
                        JOYSTICK_RIGHT, JOYSTICK_CENTER]:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            try:
                bus.write_byte(I2C_ADDR, 0xFF)
                KEYBOARD_AVAILABLE = True
                print("✅ I2C Keyboard detected")
            except:
                KEYBOARD_AVAILABLE = False
                print("⚠️  No I2C keyboard")

            print(f"✅ Hardware ready (attempt {attempt})")
            return True
        except Exception as e:
            print(f"⚠️  Attempt {attempt}/{max_attempts}: {e}")
            if attempt < max_attempts:
                time.sleep(retry_delay)
    return False


def display_msg(line1, line2="", line3=""):
    with canvas(device) as draw:
        draw.rectangle(device.bounding_box, outline="white")
        draw.text((5, 10), line1, fill="white")
        draw.text((5, 28), line2, fill="white")
        draw.text((5, 46), line3, fill="white")


def display_scrolling_menu(options, selected_index, scroll_offset):
    with canvas(device) as draw:
        draw.rectangle([(0,0),(127,14)], fill="white", outline="white")
        draw.text((5, 2), "IITDH BIOMETRIC", fill="black")
        draw.line([(0,15),(127,15)], fill="white", width=1)
        visible, y_start, item_h = 3, 20, 14
        max_scroll = max(0, len(options) - visible)
        for i in range(visible):
            idx = scroll_offset + i
            if idx >= len(options): break
            y = y_start + i * item_h
            if idx == selected_index:
                draw.rectangle([(2,y),(125,y+item_h-2)], fill="white")
                draw.text((8, y+2), options[idx][:18], fill="black")
            else:
                draw.text((8, y+2), options[idx][:18], fill="white")
        if scroll_offset > 0:
            draw.polygon([(124,18),(120,22),(128,22)], fill="white")
        if scroll_offset < max_scroll:
            draw.polygon([(124,60),(120,56),(128,56)], fill="white")


def scan_d_key():
    """
    Return True if D key is pressed AND back-lock is off.
    When _BACK_LOCKED is True, returns False silently — key press
    is physically detected but completely ignored.
    """
    if _BACK_LOCKED:
        return False
    if not KEYBOARD_AVAILABLE:
        return False
    try:
        bus.write_byte(I2C_ADDR, 0xFF & ~(1 << ROWS[3]))
        time.sleep(0.005)
        data = bus.read_byte(I2C_ADDR)
        bus.write_byte(I2C_ADDR, 0xFF)
        return not bool(data & (1 << COLS[3]))
    except Exception:
        return False


def wait_for_button(debounce_time=0.3):
    """
    Block until joystick button pressed. Returns button name.
    D key raises BackToMainMenu unless _BACK_LOCKED — in that case
    D is silently ignored and polling continues.
    """
    while True:
        for pin, name in [(JOYSTICK_UP,    "UP"),
                          (JOYSTICK_DOWN,  "DOWN"),
                          (JOYSTICK_CENTER,"CENTER"),
                          (JOYSTICK_LEFT,  "LEFT"),
                          (JOYSTICK_RIGHT, "RIGHT")]:
            if GPIO.input(pin) == GPIO.LOW:
                time.sleep(debounce_time)
                return name
        if scan_d_key():
            time.sleep(debounce_time)
            raise BackToMainMenu()
        time.sleep(0.05)


def select_from_menu(title, options):
    selected, scroll_offset, visible = 0, 0, 3
    while True:
        if selected < scroll_offset: scroll_offset = selected
        elif selected >= scroll_offset + visible: scroll_offset = selected - visible + 1
        with canvas(device) as draw:
            draw.rectangle([(0,0),(127,14)], fill="white", outline="white")
            draw.text((5, 2), title[:18], fill="black")
            draw.line([(0,15),(127,15)], fill="white", width=1)
            max_scroll = max(0, len(options) - visible)
            for i in range(visible):
                idx = scroll_offset + i
                if idx >= len(options): break
                y = 20 + i * 14
                if idx == selected:
                    draw.rectangle([(2,y),(125,y+12)], fill="white")
                    draw.text((8, y+2), options[idx][:18], fill="black")
                else:
                    draw.text((8, y+2), options[idx][:18], fill="white")
            if scroll_offset > 0:
                draw.polygon([(124,18),(120,22),(128,22)], fill="white")
            if scroll_offset < max_scroll:
                draw.polygon([(124,60),(120,56),(128,56)], fill="white")
        btn = wait_for_button()
        if btn == "UP":     selected = (selected - 1) % len(options)
        elif btn == "DOWN": selected = (selected + 1) % len(options)
        elif btn == "CENTER": return options[selected]