#!/usr/bin/env python3
"""
IITDH Biometric Attendance System
Hardware-graceful version:
  - OLED / I2C Keypad / 5D Joystick are all OPTIONAL
  - If any hardware is missing, falls back to terminal keyboard
  - Fingerprint sensor is the only required hardware
  - Merge v2: re-anchor strategy + self-match confidence check
"""

import time
import serial
import sqlite3
import os
import struct
import sys

# ── Optional hardware imports ────────────────────────────────────────────────
try:
    import smbus
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False

try:
    import readchar
    READCHAR_AVAILABLE = True
except ImportError:
    READCHAR_AVAILABLE = False

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False

try:
    from luma.oled.device import ssd1306
    from luma.core.interface.serial import spi
    from luma.core.render import canvas
    LUMA_AVAILABLE = True
except ImportError:
    LUMA_AVAILABLE = False

from adafruit_fingerprint import Adafruit_Fingerprint

# ── GPIO Pin Configuration ────────────────────────────────────────────────────
JOYSTICK_UP     = 17
JOYSTICK_DOWN   = 6
JOYSTICK_LEFT   = 22
JOYSTICK_RIGHT  = 23
JOYSTICK_CENTER = 26

# ── I2C Keypad Configuration ──────────────────────────────────────────────────
I2C_ADDR = 0x20
ROWS = [4, 5, 6, 7]
COLS = [0, 1, 2, 3]
KEYPAD = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]
LETTERS = {
    '1': ['a', 'b', 'c'], '2': ['d', 'e', 'f'], '3': ['g', 'h', 'i'],
    '4': ['j', 'k', 'l'], '5': ['m', 'n', 'o'], '6': ['p', 'q', 'r'],
    '7': ['s', 't', 'u'], '8': ['v', 'w', 'x'], '9': ['y', 'z']
}

# =============================================================================
#  HARDWARE CONFIG  ← Set these to match what is physically connected
# =============================================================================

HW_OLED_CONNECTED      = True    # SSD1306 OLED via SPI
HW_JOYSTICK_CONNECTED  = False   # 5D Joystick via GPIO  ← set False if not wired
HW_KEYPAD_CONNECTED    = True    # 4x4 I2C keypad
HW_FINGERPRINT_CONNECTED = True  # R307 fingerprint sensor

# =============================================================================
#  APPLICATION CONFIG
# =============================================================================
DB_PATH          = '/home/bio_user_iitdh/new_env/DB/college.db'
DEPT_MAP         = {"CS": "Computer Science", "EE": "Electrical Engineering",
                    "MC": "Math & Computing",  "ME": "Mechanical Engineering",
                    "CH": "Chemical Engineering", "CE": "Civil Engineering"}
PROG_MAP         = {"BT": "B.Tech", "IS": "BSMS", "MT": "M.Tech"}
DEPT_REVERSE     = {v: k for k, v in DEPT_MAP.items()}
PROG_REVERSE     = {v: k for k, v in PROG_MAP.items()}

# ── Fingerprint Merge Config ──────────────────────────────────────────────────
FP_NUM_SCANS      = 4
FP_MAX_RETRIES    = 6
FP_TEMP_SLOT      = 127
FP_MIN_CONFIDENCE = 50    # Hard reject below this
FP_WARN_CONFIDENCE= 100   # Soft warning below this
R307_ADDR_HEX     = 0xFFFFFFFF
START_CODE        = 0xEF01

# =============================================================================
#  HARDWARE INITIALISATION  (all graceful — no exit on failure)
# =============================================================================

OLED_AVAILABLE      = False
JOYSTICK_AVAILABLE  = False
KEYPAD_AVAILABLE    = False
FINGERPRINT_AVAILABLE = False

device = None
finger = None
uart   = None
bus    = None

# ── OLED ──────────────────────────────────────────────────────────────────────
if not HW_OLED_CONNECTED:
    print("⚠️  OLED skipped  (HW_OLED_CONNECTED = False)")
elif LUMA_AVAILABLE:
    try:
        oled_interface = spi(device=0, port=0, bus_speed_hz=1000000,
                             gpio_DC=25, gpio_RST=27, gpio_CS=8)
        device = ssd1306(oled_interface)
        device.contrast(255)
        OLED_AVAILABLE = True
        print("✅ OLED display initialized")
    except Exception as e:
        print(f"⚠️  OLED not available: {e}")
else:
    print("⚠️  OLED not available: luma library missing")

# ── GPIO / Joystick ───────────────────────────────────────────────────────────
if not HW_JOYSTICK_CONNECTED:
    print("⚠️  Joystick skipped  (HW_JOYSTICK_CONNECTED = False)")
elif GPIO_AVAILABLE:
    try:
        GPIO.setmode(GPIO.BCM)
        for pin in [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT,
                    JOYSTICK_RIGHT, JOYSTICK_CENTER]:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        JOYSTICK_AVAILABLE = True
        print("✅ Joystick initialized")
    except Exception as e:
        print(f"⚠️  Joystick not available: {e}")
else:
    print("⚠️  Joystick not available: RPi.GPIO missing")

# ── I2C Keypad ────────────────────────────────────────────────────────────────
if not HW_KEYPAD_CONNECTED:
    print("⚠️  I2C Keypad skipped  (HW_KEYPAD_CONNECTED = False)")
elif SMBUS_AVAILABLE:
    try:
        bus = smbus.SMBus(1)
        bus.write_byte(I2C_ADDR, 0xFF)
        KEYPAD_AVAILABLE = True
        print("✅ I2C Keypad initialized")
    except Exception as e:
        print(f"⚠️  I2C Keypad not available: {e}")
else:
    print("⚠️  I2C Keypad not available: smbus missing")

# ── Fingerprint Sensor ────────────────────────────────────────────────────────
if not HW_FINGERPRINT_CONNECTED:
    print("⚠️  Fingerprint skipped  (HW_FINGERPRINT_CONNECTED = False)")
else:
    try:
        uart   = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=2)
        finger = Adafruit_Fingerprint(uart)
        FINGERPRINT_AVAILABLE = True
        print("✅ Fingerprint sensor initialized")
    except Exception as e:
        print(f"⚠️  Fingerprint sensor not available: {e}")


# ── Detect whether we have a real interactive terminal ────────────────────────
# sys.stdin.isatty() returns True even in Thonny (it uses a pty).
# Opening /dev/tty directly is the only reliable test.
try:
    _tty_test = open('/dev/tty', 'r')
    _tty_test.close()
    import tty as _tty_mod, termios as _termios_mod
    _fd = open('/dev/tty').fileno()
    _saved = _termios_mod.tcgetattr(_fd)
    _tty_mod.setraw(_fd)
    _termios_mod.tcsetattr(_fd, _termios_mod.TCSADRAIN, _saved)
    _REAL_TTY = True
except Exception:
    _REAL_TTY = False

# ── Mode summary ──────────────────────────────────────────────────────────────
print()
if OLED_AVAILABLE and JOYSTICK_AVAILABLE and KEYPAD_AVAILABLE:
    print("🖥️  Running in FULL HARDWARE mode")
else:
    print("⌨️  Running in KEYBOARD FALLBACK mode")
    if not OLED_AVAILABLE:      print("   • OLED   → terminal output")
    if not JOYSTICK_AVAILABLE:  print("   • Joystick → keyboard arrows / numbers")
    if not KEYPAD_AVAILABLE:    print("   • I2C Keypad → keyboard input")
print()

# =============================================================================
#  DISPLAY LAYER  (OLED or terminal, transparent to callers)
# =============================================================================

def display_msg(line1, line2="", line3=""):
    """Show 3-line message on OLED or print to terminal."""
    if OLED_AVAILABLE:
        try:
            with canvas(device) as draw:
                draw.rectangle(device.bounding_box, outline="white")
                draw.text((5, 10), str(line1)[:21], fill="white")
                draw.text((5, 28), str(line2)[:21], fill="white")
                draw.text((5, 46), str(line3)[:21], fill="white")
        except Exception:
            pass
    else:
        # Terminal fallback: clear line, print neatly
        print(f"\n┌─────────────────────────┐")
        print(f"│ {str(line1):<23} │")
        if line2: print(f"│ {str(line2):<23} │")
        if line3: print(f"│ {str(line3):<23} │")
        print(f"└─────────────────────────┘")

def display_scrolling_menu(options, selected_index, scroll_offset):
    """OLED scrolling menu — only called when OLED is available."""
    if not OLED_AVAILABLE:
        return
    try:
        with canvas(device) as draw:
            draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
            draw.text((5, 2), "IITDH BIOMETRIC", fill="black")
            draw.line([(0, 15), (127, 15)], fill="white", width=1)

            visible_items = 3
            max_scroll = max(0, len(options) - visible_items)
            y_start, item_height = 20, 14

            for i in range(visible_items):
                idx = scroll_offset + i
                if idx >= len(options):
                    break
                y = y_start + i * item_height
                if idx == selected_index:
                    draw.rectangle([(2, y), (125, y + item_height - 2)],
                                   fill="white", outline="white")
                    draw.text((8, y + 2), options[idx][:18], fill="black")
                else:
                    draw.text((8, y + 2), options[idx][:18], fill="white")

            if scroll_offset > 0:
                draw.polygon([(124, 18), (120, 22), (128, 22)], fill="white")
            if scroll_offset < max_scroll:
                draw.polygon([(124, 60), (120, 56), (128, 56)], fill="white")
    except Exception:
        pass

# =============================================================================
#  INPUT LAYER  (joystick/keypad or keyboard — transparent to callers)
# =============================================================================


def _clear_screen():
    """Clear terminal screen — safe for both real TTY and Thonny."""
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")   # ANSI clear for real terminal
    else:
        print("\n" + "─" * 40)           # Thonny: just print a divider


def _read_single_key():
    """
    Single-key read — ONLY called when running in a real SSH/bash terminal
    (JOYSTICK_AVAILABLE=False but we confirmed real tty via _REAL_TTY flag).
    Never called from Thonny.
    """
    if READCHAR_AVAILABLE:
        k = readchar.readkey()
        if k == readchar.key.UP:    return "UP"
        if k == readchar.key.DOWN:  return "DOWN"
        if k == readchar.key.LEFT:  return "LEFT"
        if k == readchar.key.RIGHT: return "RIGHT"
        if k in (readchar.key.ENTER, readchar.key.CR,
                 readchar.key.LF, ' '): return "CENTER"
        k = k.lower()
        if k == 'w': return "UP"
        if k == 's': return "DOWN"
        if k == 'a': return "LEFT"
        if k == 'd': return "RIGHT"
        return "CENTER"
    import tty, termios
    fd    = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            nxt = sys.stdin.read(2)
            if nxt == '[A': return "UP"
            if nxt == '[B': return "DOWN"
            if nxt == '[D': return "LEFT"
            if nxt == '[C': return "RIGHT"
            return "CENTER"
        if ch in ('\r', '\n', ' '): return "CENTER"
        ch = ch.lower()
        if ch == 'w': return "UP"
        if ch == 's': return "DOWN"
        if ch == 'a': return "LEFT"
        if ch == 'd': return "RIGHT"
        return "CENTER"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def wait_for_button(debounce_time=0.3):
    """
    Wait for joystick (hardware) OR arrow keys + Enter (keyboard fallback).
    No prompts printed - navigation feels instant like a real joystick.

    Hardware  ->  physical GPIO pins
    Keyboard  ->  Arrow keys (up/down/left/right)  +  Enter or Space = SELECT
                  WASD also work as a fallback

    Returns: "UP" | "DOWN" | "LEFT" | "RIGHT" | "CENTER"
    """
    if JOYSTICK_AVAILABLE:
        while True:
            if GPIO.input(JOYSTICK_UP)     == GPIO.LOW:
                time.sleep(debounce_time); return "UP"
            if GPIO.input(JOYSTICK_DOWN)   == GPIO.LOW:
                time.sleep(debounce_time); return "DOWN"
            if GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
                time.sleep(debounce_time); return "CENTER"
            if GPIO.input(JOYSTICK_LEFT)   == GPIO.LOW:
                time.sleep(debounce_time); return "LEFT"
            if GPIO.input(JOYSTICK_RIGHT)  == GPIO.LOW:
                time.sleep(debounce_time); return "RIGHT"
            time.sleep(0.05)
    elif _REAL_TTY:
        return _read_single_key()
    else:
        # Thonny / IDE — plain numbered input, no raw tty needed
        key = input("  [1=Up  2=Down  3=Left  4=Right  Enter=Select]: ").strip().lower()
        if key in ('1', 'w', 'up'):    return "UP"
        if key in ('2', 's', 'down'):  return "DOWN"
        if key in ('3', 'a', 'left'):  return "LEFT"
        if key in ('4', 'd', 'right'): return "RIGHT"
        return "CENTER"

def show_menu():
    """
    Main menu.
    - OLED + Joystick  : graphical scrolling menu on display
    - Real TTY         : arrow keys + Enter in terminal
    - Thonny / pipe    : numbered list, type number + Enter
    Returns selected index (int).
    """
    menu_options = [
        "Enroll Student",
        "Take Attendance",
        "View Stats",
        "Admin Settings",
        "System Info",
        "Shutdown"
    ]

    # ── OLED + Joystick hardware path ──────────────────────────────────────
    if OLED_AVAILABLE and JOYSTICK_AVAILABLE:
        selected, scroll_offset, visible = 0, 0, 3
        while True:
            if selected < scroll_offset:
                scroll_offset = selected
            elif selected >= scroll_offset + visible:
                scroll_offset = selected - visible + 1
            display_scrolling_menu(menu_options, selected, scroll_offset)
            btn = wait_for_button()
            if btn == "UP":       selected = (selected - 1) % len(menu_options)
            elif btn == "DOWN":   selected = (selected + 1) % len(menu_options)
            elif btn == "LEFT":   selected = max(0, selected - visible)
            elif btn == "RIGHT":  selected = min(len(menu_options)-1, selected+visible)
            elif btn == "CENTER": return selected

    # ── Thonny / piped stdin — numbered list ───────────────────────────────
    elif not _REAL_TTY:
        print("\n" + "=" * 40)
        print("  IITDH BIOMETRIC ATTENDANCE SYSTEM")
        print("=" * 40)
        for i, opt in enumerate(menu_options):
            print(f"  {i+1}. {opt}")
        print("=" * 40)
        while True:
            try:
                choice = int(input("  Select (1-6): ").strip()) - 1
                if 0 <= choice < len(menu_options):
                    return choice
                print(f"  ❌ Enter 1-{len(menu_options)}")
            except ValueError:
                print("  ❌ Enter a number")

    # ── Real TTY — arrow keys ──────────────────────────────────────────────
    else:  # _REAL_TTY
        selected = 0
        while True:
            _clear_screen()
            print("=" * 40)
            print("  IITDH BIOMETRIC ATTENDANCE SYSTEM")
            print("=" * 40)
            for i, opt in enumerate(menu_options):
                prefix = " \033[7m ▶ " + opt + " \033[0m" if i == selected else f"   {opt}"
                print(prefix)
            print("=" * 40)
            print("  ↑↓ = Navigate    Enter = Select")
            btn = wait_for_button()
            if btn == "UP":       selected = (selected - 1) % len(menu_options)
            elif btn == "DOWN":   selected = (selected + 1) % len(menu_options)
            elif btn == "CENTER": return selected

def select_from_menu(title, options):
    """
    Generic selector — OLED+joystick or terminal numbered list.
    Returns the selected option string.
    """
    if OLED_AVAILABLE and JOYSTICK_AVAILABLE:
        selected, scroll_offset, visible = 0, 0, 3
        while True:
            if selected < scroll_offset:
                scroll_offset = selected
            elif selected >= scroll_offset + visible:
                scroll_offset = selected - visible + 1

            with canvas(device) as draw:
                draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
                draw.text((5, 2), title[:18], fill="black")
                draw.line([(0, 15), (127, 15)], fill="white", width=1)
                y_start, item_height = 20, 14
                max_scroll = max(0, len(options) - visible)
                for i in range(visible):
                    idx = scroll_offset + i
                    if idx >= len(options): break
                    y = y_start + i * item_height
                    if idx == selected:
                        draw.rectangle([(2, y), (125, y+item_height-2)],
                                       fill="white", outline="white")
                        draw.text((8, y+2), options[idx][:18], fill="black")
                    else:
                        draw.text((8, y+2), options[idx][:18], fill="white")
                if scroll_offset > 0:
                    draw.polygon([(124, 18), (120, 22), (128, 22)], fill="white")
                if scroll_offset < max_scroll:
                    draw.polygon([(124, 60), (120, 56), (128, 56)], fill="white")

            btn = wait_for_button()
            if btn == "UP":      selected = (selected - 1) % len(options)
            elif btn == "DOWN":  selected = (selected + 1) % len(options)
            elif btn == "CENTER": return options[selected]
    # ── Thonny / IDE — numbered list ──────────────────────────────────────────
    elif not _REAL_TTY:
        print(f"\n  ── {title} ──")
        print("  " + "─" * 30)
        for i, opt in enumerate(options):
            print(f"  {i+1}. {opt}")
        print("  " + "─" * 30)
        while True:
            try:
                choice = int(input(f"  Select (1-{len(options)}): ").strip()) - 1
                if 0 <= choice < len(options):
                    return options[choice]
                print(f"  ❌ Enter 1-{len(options)}")
            except ValueError:
                print("  ❌ Enter a number")

    # ── Real TTY — arrow keys ─────────────────────────────────────────────
    else:
        selected = 0
        while True:
            _clear_screen()
            print(f"  ── {title} ──")
            print("  " + "─" * 30)
            for i, opt in enumerate(options):
                prefix = " \033[7m ▶ " + opt + " \033[0m" if i == selected else f"   {opt}"
                print(prefix)
            print("  " + "─" * 30)
            print("  ↑↓ Navigate   Enter = Select")
            btn = wait_for_button()
            if btn == "UP":      selected = (selected - 1) % len(options)
            elif btn == "DOWN":  selected = (selected + 1) % len(options)
            elif btn == "CENTER": return options[selected]

def read_keypad_input(prompt, mode="NUMBER", display_line2="", show_as_password=False):
    """
    Read text/number input.
    Hardware: I2C keypad with T9 alpha mode.
    Fallback: direct terminal input().
    """
    if KEYPAD_AVAILABLE:
        return _read_keypad_hardware(prompt, mode, display_line2, show_as_password)
    else:
        return _read_keyboard_terminal(prompt, mode, show_as_password)

def _read_keyboard_terminal(prompt, mode="NUMBER", show_as_password=False):
    """
    Keyboard input for Thonny / environments where /dev/tty is unavailable.

    Since Thonny blocks all raw keyboard access, character-by-character
    reading is impossible. This function:
      1. Shows clear instructions on OLED before input
      2. Uses plain input() / getpass()
      3. Updates OLED with the confirmed value after Enter
      4. Validates and re-prompts on bad input with OLED feedback

    For live char-by-char OLED updates, run via SSH terminal instead.
    """
    hint_oled = "Numbers+Enter" if mode == "NUMBER" else "Text+Enter"
    hint_term = "(numbers only)" if mode == "NUMBER" else "(text)"

    while True:
        # ── Show instruction on OLED BEFORE user types ────────────────────
        display_msg(prompt, hint_oled, "Thonny:type+Enter")
        time.sleep(0.3)   # give OLED time to render before input() blocks

        try:
            if show_as_password:
                import getpass
                value = getpass.getpass(f"  {prompt} {hint_term}: ").strip()
            else:
                print(f"  {prompt} {hint_term}: ", end="", flush=True)
                value = input().strip()

        except KeyboardInterrupt:
            display_msg(prompt, "Cancelled", "")
            return ""

        # ── Validate ──────────────────────────────────────────────────────
        if not value:
            display_msg("Empty input!", "Try again", hint_oled)
            print("  ❌ Cannot be empty — try again")
            time.sleep(1)
            continue

        if mode == "NUMBER" and not value.isdigit():
            display_msg("Numbers only!", "Got: " + value[:10], "Try again")
            print(f"  ❌ Numbers only — got '{value}', try again")
            time.sleep(1)
            continue

        if mode == "CAPS":
            value = value.upper()

        # ── Confirm on OLED ───────────────────────────────────────────────
        masked = "*" * len(value) if show_as_password else value[-20:]
        display_msg(prompt, "Got:", masked)
        time.sleep(0.4)
        return value


def _read_keypad_hardware(prompt, mode="NUMBER", display_line2="", show_as_password=False):
    """Original I2C keypad T9 input (unchanged from your code)."""
    output = ""
    last_key = None
    tap_count = 0
    last_time = 0
    current_mode = mode
    current_preview = ""
    flicker_state = True
    last_flicker_time = 0

    bus.write_byte(I2C_ADDR, 0xFF)

    while True:
        current_time = time.time()
        if current_time - last_flicker_time > 0.3:
            flicker_state = not flicker_state
            last_flicker_time = current_time

        if show_as_password:
            display_msg(prompt, display_line2, "*" * len(output))
        else:
            display_msg(prompt, display_line2, output + (current_preview if flicker_state else ""))

        if JOYSTICK_AVAILABLE and GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
            if last_key and last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS": ch = ch.upper()
                output += ch
                last_key = None; tap_count = 0; current_preview = ""
            if output:
                time.sleep(0.3)
                return output
            time.sleep(0.3)

        for r, row in enumerate(ROWS):
            bus.write_byte(I2C_ADDR, 0xFF & ~(1 << row))
            time.sleep(0.01)
            data = bus.read_byte(I2C_ADDR)
            for c, col in enumerate(COLS):
                if not (data & (1 << col)):
                    key = KEYPAD[r][c]
                    now = time.time()

                    if key == 'A' and not show_as_password:
                        current_mode = "ALPHA"
                        display_msg(prompt, "ALPHA MODE", output); time.sleep(0.5)
                    elif key == '#' and not show_as_password:
                        current_mode = "NUMBER"
                        display_msg(prompt, "NUMBER MODE", output); time.sleep(0.5)
                    elif key == 'C':
                        if current_mode == "ALPHA":
                            current_mode = "CAPS"
                            display_msg(prompt, "CAPS MODE", output)
                        elif current_mode == "CAPS":
                            current_mode = "ALPHA"
                            display_msg(prompt, "ALPHA MODE", output)
                        time.sleep(0.5)
                    elif key == 'B':
                        if current_preview:
                            current_preview = ""; last_key = None; tap_count = 0
                        else:
                            output = output[:-1]
                    elif key == '*':
                        output = ""; last_key = None; tap_count = 0; current_preview = ""
                        display_msg(prompt, "CLEARED", ""); time.sleep(0.5)
                    elif key.isdigit():
                        if current_mode == "NUMBER" or show_as_password:
                            output += key
                        elif current_mode in ["ALPHA", "CAPS"] and key in LETTERS:
                            if key != last_key:
                                if last_key and last_key in LETTERS:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS": ch = ch.upper()
                                    output += ch
                                last_key = key; tap_count = 0
                            else:
                                if (now - last_time) < 1.0:
                                    tap_count += 1
                                else:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS": ch = ch.upper()
                                    output += ch; tap_count = 0
                            ch = LETTERS[key][tap_count % len(LETTERS[key])]
                            if current_mode == "CAPS": ch = ch.upper()
                            current_preview = ch
                            last_time = now
                    time.sleep(0.3)

        if last_key and (time.time() - last_time) > 1.0:
            if last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS": ch = ch.upper()
                output += ch
            last_key = None; tap_count = 0; current_preview = ""

# =============================================================================
#  FINGERPRINT — MERGE v2  (re-anchor + self-match confidence)
# =============================================================================

def _fp_wait_for_finger(timeout_sec=12):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if finger.get_image() == 0:
            return True
        time.sleep(0.1)
    return False

def _fp_wait_for_removal(timeout_sec=6):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if finger.get_image() != 0:
            time.sleep(0.3)
            return
        time.sleep(0.1)

def _raw_match_buffers():
    """Send R307 raw Match (0x03) over UART. Returns score or None."""
    try:
        pkt_id   = 0x01
        length   = 0x0003
        cmd      = 0x03
        checksum = pkt_id + (length >> 8) + (length & 0xFF) + cmd
        packet   = (struct.pack('>H', START_CODE) + struct.pack('>I', R307_ADDR_HEX) +
                    struct.pack('>B', pkt_id) + struct.pack('>H', length) +
                    struct.pack('>B', cmd)    + struct.pack('>H', checksum))
        uart.reset_input_buffer()
        uart.write(packet)
        time.sleep(0.15)
        resp = uart.read(14)
        if len(resp) < 14: return None
        confirm = resp[9]
        score   = struct.unpack('>H', resp[10:12])[0]
        if confirm == 0x00: return score
        if confirm == 0x08: return 0
        return None
    except Exception:
        return None

def _confidence_label(score):
    if score is None:        return "❓ Unknown"
    if score <= FP_MIN_CONFIDENCE:  return f"🔴 POOR ({score}/200)"
    if score <= FP_WARN_CONFIDENCE: return f"🟡 WEAK ({score}/200)"
    if score <= 150:                return f"🟢 GOOD ({score}/200)"
    return f"✅ EXCELLENT ({score}/200)"

def _run_merge():
    """
    4-scan iterative merge with re-anchor strategy.
    Returns (success, merge_log).
    On success, CharBuffer1 holds the merged template.
    """
    merge_log = []

    # Scan 1 → CharBuffer1
    print(f"\n📌 SCAN 1/{FP_NUM_SCANS}: Place finger on sensor...")
    display_msg("SCAN 1 of 4", "Place finger")
    ok = False
    for attempt in range(1, FP_MAX_RETRIES + 1):
        if not _fp_wait_for_finger():
            print(f"   ⏱️  Timeout (attempt {attempt}/{FP_MAX_RETRIES})")
            display_msg("TIMEOUT", f"Try {attempt}/{FP_MAX_RETRIES}")
            continue
        code = finger.image_2_tz(1)
        if code == 0:
            print("   ✅ Scan 1 captured → CharBuffer1")
            display_msg("SCAN 1 of 4", "Captured!")
            _fp_wait_for_removal()
            ok = True; break
        print(f"   ❌ Bad image (code {hex(code)}), retry...")
        display_msg("Bad Image", f"Try {attempt}/{FP_MAX_RETRIES}")
        _fp_wait_for_removal()
    if not ok:
        display_msg("FAILED", "Scan 1 failed"); time.sleep(2)
        return False, merge_log

    # Scans 2-4
    for scan_num in range(2, FP_NUM_SCANS + 1):
        scan_ok = False
        consec_reject = 0
        for attempt in range(1, FP_MAX_RETRIES + 1):
            print(f"\n📌 SCAN {scan_num}/{FP_NUM_SCANS}: Remove finger, then place again...")
            display_msg(f"SCAN {scan_num} of 4", "Remove finger")
            _fp_wait_for_removal()
            time.sleep(0.5)

            display_msg(f"SCAN {scan_num} of 4", "Place finger")
            if not _fp_wait_for_finger():
                print(f"   ⏱️  Timeout (attempt {attempt}/{FP_MAX_RETRIES})")
                display_msg("TIMEOUT", f"Retry {attempt}/{FP_MAX_RETRIES}")
                continue

            img_code = finger.image_2_tz(2)
            if img_code != 0:
                print(f"   ❌ Bad image (code {hex(img_code)}), retry...")
                display_msg("Bad Image", f"Retry {attempt}/{FP_MAX_RETRIES}")
                _fp_wait_for_removal(); time.sleep(0.5); continue

            display_msg(f"SCAN {scan_num} of 4", "Merging...")
            merge_code = finger.create_model()
            merge_log.append((scan_num, attempt, merge_code))

            if merge_code == 0:
                print(f"   ✅ Scan {scan_num} merged → CharBuffer1 updated")
                display_msg(f"SCAN {scan_num} of 4", "Success!")
                _fp_wait_for_removal()
                consec_reject = 0; scan_ok = True; break

            elif merge_code == 0x0A:
                consec_reject += 1
                print(f"   ⚠️  Merge rejected — similarity too low (attempt {attempt})")
                print(f"      Tip: Press firmly, centre finger on sensor")
                display_msg("No Match", f"Retry {attempt}/{FP_MAX_RETRIES}")
                _fp_wait_for_removal()

                # Re-anchor: refresh CharBuffer1 after 3 consecutive rejects
                if consec_reject >= 3:
                    print(f"\n   🔄 Re-anchoring base (3 rejects)...")
                    display_msg("RE-ANCHOR", "Place finger")
                    if _fp_wait_for_finger(timeout_sec=10):
                        if finger.image_2_tz(1) == 0:
                            print("      ✅ CharBuffer1 re-anchored")
                            display_msg("Re-anchored", "Try again")
                        _fp_wait_for_removal()
                    consec_reject = 0
                time.sleep(0.8)
            else:
                print(f"   ❌ Merge error (code {hex(merge_code)})")
                display_msg("Merge Error", f"Code {hex(merge_code)}")
                _fp_wait_for_removal(); time.sleep(0.5)

        if not scan_ok:
            print(f"❌ Failed scan {scan_num} after {FP_MAX_RETRIES} attempts")
            display_msg("FAILED", f"Scan {scan_num} failed"); time.sleep(2)
            return False, merge_log

    print("\n✅ All 4 scans merged — CharBuffer1 has final template")
    return True, merge_log

def _run_self_match_verify():
    """Store merged template → scan same finger → get confidence score."""
    print("\n💾 Storing merged template to temp slot...")
    display_msg("VERIFYING...", "Storing temp")

    store_code = finger.store_model(FP_TEMP_SLOT, 1)
    if store_code != 0:
        print(f"   ⚠️  store_model failed ({hex(store_code)}) — trying 1:1 fallback")
        return _run_11_compare_fallback()

    print(f"   ✅ Stored in slot {FP_TEMP_SLOT}")
    time.sleep(0.5)
    print("\n🔍 Scan SAME finger again to verify merge quality...")
    display_msg("VERIFY SCAN", "Same finger")

    for attempt in range(1, 4):
        if not _fp_wait_for_finger():
            print(f"   ⏱️  Timeout on verify (attempt {attempt}/3)")
            continue
        img_code = finger.image_2_tz(1)
        if img_code != 0:
            print(f"   ❌ Bad image ({hex(img_code)})")
            _fp_wait_for_removal(); continue

        search_code = finger.finger_search()
        _fp_wait_for_removal()
        if search_code == 0:
            score = finger.confidence
            print(f"   ✅ Self-match confidence: {score}/200")
            return score
        else:
            print(f"   ⚠️  finger_search failed ({hex(search_code)}) — trying 1:1 fallback")
            return _run_11_compare_fallback()
    return None

def _run_11_compare_fallback():
    """Load template from TEMP_SLOT, scan again, run raw 0x03 Match."""
    print("\n   🔁 Fallback: 1:1 buffer compare...")
    display_msg("FALLBACK", "1:1 Compare")

    if finger.load_model(FP_TEMP_SLOT, 1) != 0:
        return None

    print("   📌 Place same finger for 1:1 compare...")
    display_msg("1:1 COMPARE", "Place finger")
    for attempt in range(1, 4):
        if not _fp_wait_for_finger(): continue
        if finger.image_2_tz(2) != 0:
            _fp_wait_for_removal(); continue
        score = _raw_match_buffers()
        _fp_wait_for_removal()
        if score is not None:
            print(f"   ✅ 1:1 match score: {score}/200")
            return score
    return None

def _cleanup_fp_temp():
    try:
        if finger.delete_model(FP_TEMP_SLOT) == 0:
            print(f"   🗑️  Temp slot {FP_TEMP_SLOT} cleared")
    except Exception:
        pass

def _print_merge_report(merge_log, confidence):
    print("\n" + "─"*45)
    print("  MERGE QUALITY REPORT")
    print("─"*45)
    total   = len(merge_log)
    rejects = sum(1 for _, _, c in merge_log if c == 0x0A)
    if total > 0:
        pct = rejects / total * 100
        print(f"  Merge rejections : {rejects}/{total} ({pct:.0f}%)")
        if pct > 60:
            print("  ⚠️  High rejection — clean sensor or check placement")
    print(f"  Self-match score : {_confidence_label(confidence)}")
    print("─"*45)
    display_msg("QUALITY CHECK", _confidence_label(confidence)[:21])

def scan_fingerprint():
    """
    Full 4-scan merge + self-match quality verification.
    Returns template bytes on success, None on failure/poor quality.
    """
    if not FINGERPRINT_AVAILABLE:
        print("❌ Fingerprint sensor not available")
        display_msg("ERROR", "No sensor")
        return None
    try:
        print("\n--- Starting 4-Scan Fingerprint Registration (v2) ---")
        display_msg("FINGERPRINT", "4 scans needed")
        time.sleep(1.5)

        success, merge_log = _run_merge()
        if not success:
            display_msg("FAILED", "Merge failed"); time.sleep(2)
            return None

        display_msg("VERIFYING", "Self-match...")
        confidence = _run_self_match_verify()
        _cleanup_fp_temp()
        _print_merge_report(merge_log, confidence)

        if confidence is not None and confidence <= FP_MIN_CONFIDENCE:
            print(f"\n❌ Template too poor (score={confidence}) — NOT saving")
            print("   Re-enroll: press flat and firmly each scan")
            display_msg("REJECTED", f"Score:{confidence}", "Re-enroll"); time.sleep(3)
            return None

        if confidence is not None and confidence <= FP_WARN_CONFIDENCE:
            print(f"\n⚠️  Weak template (score={confidence}) — saving with warning")
            display_msg("WEAK TEMPLATE", f"Score:{confidence}", "Saved anyway"); time.sleep(2)

        print("\n💾 Downloading final template...")
        display_msg("SAVING...", "Downloading")

        finger.load_model(FP_TEMP_SLOT, 1)   # reload if available, else CharBuffer1 still valid
        template = finger.get_fpdata("char", 1)

        if not template:
            print("❌ Template download failed")
            display_msg("ERROR", "Download failed"); time.sleep(2)
            return None

        print(f"✅ Template ready — {len(template)} bytes (confidence: {confidence}/200)")
        display_msg("SUCCESS!", f"Score:{confidence}", "FP captured"); time.sleep(1)
        return template

    except Exception as e:
        print(f"❌ Fingerprint error: {e}")
        display_msg("ERROR", str(e)[:21])
        return None

# =============================================================================
#  PROFESSOR AUTHENTICATION
# =============================================================================

def authenticate_prof():
    """Returns professor name string if fingerprint verified, else None."""
    print("\n--- Professor Authorization Required ---")
    display_msg("ADMIN REQUIRED", "Scan Prof Finger")

    if not FINGERPRINT_AVAILABLE:
        # Terminal fallback for testing without sensor
        name = input("  [NO SENSOR] Enter professor name to bypass auth: ").strip()
        return name if name else None

    conn    = sqlite3.connect(DB_PATH)
    cursor  = conn.cursor()
    cursor.execute("SELECT name, template FROM profs")
    profs   = cursor.fetchall()
    conn.close()

    if not profs:
        print("❌ No professors enrolled in system.")
        display_msg("ERROR", "No Profs Found"); time.sleep(2)
        return None

    uart.reset_input_buffer()
    timeout = time.time() + 15
    while time.time() < timeout:
        if finger.get_image() == 0:
            finger.image_2_tz(1)
            for name, template in profs:
                finger.send_fpdata(list(template), "char", 2)
                if finger.compare_templates() == 0:
                    print(f"✅ Authorized by Prof. {name}")
                    display_msg("AUTHORIZED", f"Prof. {name}"); time.sleep(1.5)
                    return name
        time.sleep(0.1)

    display_msg("TIMEOUT", "Auth Failed"); time.sleep(2)
    return None

# =============================================================================
#  STUDENT ENROLLMENT
# =============================================================================

def enroll_student():
    print("\n--- Interactive Student Registration ---")
    try:
        # Step 1: Branch
        display_msg("ENROLLMENT", "Select Branch", "Use Joystick/Kbd")
        time.sleep(1)
        selected_branch = select_from_menu("SELECT BRANCH", list(DEPT_MAP.values()))
        branch_code = DEPT_REVERSE[selected_branch]
        print(f"✅ Branch: {selected_branch} ({branch_code})")

        # Step 2: Program
        display_msg("ENROLLMENT", "Select Program")
        time.sleep(1)
        selected_program = select_from_menu("SELECT PROGRAM", list(PROG_MAP.values()))
        program_code = PROG_REVERSE[selected_program]
        print(f"✅ Program: {selected_program} ({program_code})")

        # Step 3: Batch Year
        display_msg("ENROLLMENT", "Enter Batch Year")
        time.sleep(1)
        batch_year = read_keypad_input("BATCH YEAR", mode="NUMBER",
                                       display_line2="4 digits,OK=Ctr")
        if len(batch_year) != 4 or not batch_year.isdigit():
            display_msg("ERROR", "Invalid Year"); time.sleep(2); return
        year_short = batch_year[2:4]
        print(f"✅ Batch Year: {batch_year}")

        # Step 4: Roll suffix
        display_msg("ENROLLMENT", "Last 3 Digits")
        time.sleep(1)
        roll_suffix = read_keypad_input("ROLL SUFFIX", mode="NUMBER",
                                        display_line2="3 digits,OK=Ctr")
        if len(roll_suffix) != 3 or not roll_suffix.isdigit():
            display_msg("ERROR", "Need 3 digits"); time.sleep(2); return
        roll_no = f"{branch_code}{year_short}{program_code}{roll_suffix}"
        print(f"✅ Generated Roll No: {roll_no}")
        display_msg("ROLL NUMBER", roll_no, "Confirm?")
        time.sleep(2)

        # Duplicate check
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
        if cursor.fetchone():
            print(f"❌ ID {roll_no} already exists.")
            display_msg("ERROR", f"{roll_no} exists"); conn.close(); time.sleep(2); return
        conn.close()

        # Step 5: First name
        display_msg("ENROLLMENT", "Enter First Name")
        time.sleep(1)
        first_name = read_keypad_input("FIRST NAME", mode="ALPHA",
                                       display_line2="C=CAPS,OK=Ctr")
        print(f"✅ First Name: {first_name}")

        # Step 6: Last name
        display_msg("ENROLLMENT", "Enter Last Name")
        time.sleep(1)
        last_name = read_keypad_input("LAST NAME", mode="ALPHA",
                                      display_line2="C=CAPS,OK=Ctr")
        print(f"✅ Last Name: {last_name}")

        # Step 7: Password
        display_msg("ENROLLMENT", "Enter Password")
        time.sleep(1)
        password = read_keypad_input("PASSWORD", mode="NUMBER",
                                     display_line2="Numbers,OK=Ctr", show_as_password=True)
        print("✅ Password set (hidden)")

        # Summary
        display_msg("SUMMARY", f"{first_name} {last_name}", roll_no)
        print(f"\n  Summary → {first_name} {last_name} | {roll_no}")
        time.sleep(2)

        # Step 8: Fingerprint
        template = scan_fingerprint()
        if not template:
            print("\n⚠️  Fingerprint failed/rejected")
            retry = input("  Save without fingerprint? (yes/no): ").strip().lower()
            if retry not in ('yes', 'y'):
                display_msg("CANCELLED"); return
            template = b'\x00' * 512
            print("⚠️  Using placeholder fingerprint")

        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO students
              (student_id, first_name, last_name, password, dept, year, program, template)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (roll_no, first_name, last_name, password, selected_branch,
              int(batch_year), selected_program, sqlite3.Binary(bytearray(template))))
        conn.commit(); conn.close()

        display_msg("SUCCESS!", f"{first_name} {last_name}", roll_no)
        print(f"✅ Enrolled: {first_name} {last_name} ({roll_no})")
        time.sleep(3)

    except Exception as e:
        print(f"❌ Error: {e}")
        display_msg("ERROR", str(e)[:21]); time.sleep(2)

# =============================================================================
#  CLASSROOM ATTENDANCE SESSION
# =============================================================================

def classroom_session(prof_name):
    print(f"\n🎓 Attendance Session (Authorized by {prof_name})")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE name=?", (prof_name,))
    prof_result = cursor.fetchone()
    if not prof_result:
        display_msg("ERROR", "Prof not found"); conn.close(); time.sleep(2); return
    prof_id = prof_result[0]

    cursor.execute("""
        SELECT course_code, course_name FROM courses
        WHERE prof_id=? ORDER BY course_code
    """, (prof_id,))
    courses = cursor.fetchall()
    conn.close()

    if not courses:
        display_msg("NO COURSES", "None for this prof")
        print("❌ No courses assigned"); time.sleep(3); return

    course_options = [f"{code}: {name[:12]}" for code, name in courses]
    display_msg("SELECT COURSE", "Use Joystick/Kbd")
    time.sleep(1)
    selected_course = select_from_menu("SELECT COURSE", course_options)
    course_code = selected_course.split(':')[0]
    course_name = [n for c, n in courses if c == course_code][0]

    print(f"✅ Course: {course_code} - {course_name}")
    display_msg("COURSE", course_code, course_name[:16]); time.sleep(2)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.student_id, s.first_name, s.template
        FROM students s
        JOIN course_enrollments ce ON s.student_id = ce.student_id
        WHERE ce.course_code=? AND ce.status='active'
    """, (course_code,))
    enrolled = cursor.fetchall()
    conn.close()

    if not enrolled:
        display_msg("NO STUDENTS", "No enrollments")
        print(f"❌ No students enrolled in {course_code}"); time.sleep(3); return

    if not FINGERPRINT_AVAILABLE:
        print("❌ Fingerprint sensor required for attendance")
        display_msg("ERROR", "No FP sensor"); time.sleep(3); return

    display_msg("CLASS OPEN", course_code, "Scan Finger")
    print(f"📚 {course_name} | {len(enrolled)} students enrolled")
    print("   Prof scan = end session")
    time.sleep(2)

    session_start = time.time()
    attendance_count = 0
    attended = set()

    while True:
        display_msg("CLASS SESSION", f"{course_code} ({attendance_count})", "Scan or Prof=Exit")
        uart.reset_input_buffer()

        if finger.get_image() == 0:
            finger.image_2_tz(1)

            # Check if it's the professor ending the session
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT template FROM profs WHERE prof_id=?", (prof_id,))
            prof_tmpl = cursor.fetchone()
            if prof_tmpl:
                finger.send_fpdata(list(prof_tmpl[0]), "char", 2)
                if finger.compare_templates() == 0:
                    duration = int((time.time() - session_start) / 60)
                    display_msg("SESSION CLOSED", f"Total: {attendance_count}",
                                f"Time: {duration}min")
                    print(f"🛑 Session closed. {attendance_count} present. {duration} min.")
                    conn.close(); time.sleep(3); break

            # Search enrolled students
            found = False
            for s_id, s_name, s_template in enrolled:
                finger.send_fpdata(list(s_template), "char", 2)
                if finger.compare_templates() == 0:
                    if s_id in attended:
                        display_msg("ALREADY MARKED", s_name[:16], "Present today")
                        print(f"⚠️  {s_name} already marked"); time.sleep(2)
                    else:
                        display_msg("VERIFIED!", s_name[:16], s_id)
                        print(f"✅ {s_name} ({s_id})")
                        cursor.execute("""
                            INSERT INTO attendance
                            (course_code, student_id, student_name, authorized_by,
                             timestamp, session_date)
                            VALUES (?, ?, ?, ?, datetime('now','localtime'),
                                    date('now','localtime'))
                        """, (course_code, s_id, s_name, prof_id))
                        conn.commit()
                        attendance_count += 1
                        attended.add(s_id)
                        time.sleep(2)
                    found = True; break

            if not found:
                display_msg("FAILED", "Not enrolled in", course_code)
                print("❌ Unknown or not enrolled"); time.sleep(1.5)

            conn.close()
        time.sleep(0.1)

# =============================================================================
#  VIEW STATS
# =============================================================================

def view_stats():
    display_msg("Loading Stats", "Please wait...")
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students");   total_s = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM courses");    total_c = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM profs");      total_p = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) FROM attendance
            WHERE date(session_date)=date('now','localtime')
        """)
        today_unique = cursor.fetchone()[0]
        cursor.execute("""
            SELECT COUNT(*) FROM attendance
            WHERE date(session_date)=date('now','localtime')
        """)
        today_total = cursor.fetchone()[0]
        conn.close()

        display_msg("STATISTICS", f"Students: {total_s}", f"Courses: {total_c}")
        print(f"\n📊 Statistics:")
        print(f"   Students  : {total_s}")
        print(f"   Courses   : {total_c}")
        print(f"   Professors: {total_p}")
        print(f"   Today     : {today_unique} unique / {today_total} scans")
        time.sleep(3)
        display_msg("TODAY", f"Unique: {today_unique}", f"Scans: {today_total}")
        time.sleep(3)
    except Exception as e:
        print(f"❌ Error: {e}"); display_msg("ERROR", str(e)[:21]); time.sleep(2)

# =============================================================================
#  COURSE MANAGEMENT
# =============================================================================

def add_course():
    print("\n--- Add New Course ---")
    prof = authenticate_prof()
    if not prof:
        display_msg("AUTH FAILED", "Cannot add course"); time.sleep(2); return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT prof_id FROM profs WHERE name=?", (prof,))
    prof_r = cursor.fetchone()
    if not prof_r:
        display_msg("ERROR", "Prof not found"); conn.close(); time.sleep(2); return
    prof_id = prof_r[0]; conn.close()

    display_msg("ADD COURSE", "Enter Code")
    time.sleep(1)
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA",
                                    display_line2="OK=Center").upper()
    if not course_code:
        display_msg("CANCELLED"); time.sleep(1); return

    display_msg("ADD COURSE", "Enter Name")
    time.sleep(1)
    course_name = read_keypad_input("COURSE NAME", mode="ALPHA",
                                    display_line2="OK=Center")
    if not course_name:
        display_msg("CANCELLED"); time.sleep(1); return

    selected_dept = select_from_menu("SELECT DEPT", list(DEPT_MAP.keys()))

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT course_code FROM courses WHERE course_code=?", (course_code,))
        if cursor.fetchone():
            display_msg("ERROR", "Course exists"); conn.close(); time.sleep(2); return
        cursor.execute("""
            INSERT INTO courses (course_code, course_name, prof_id, dept_code)
            VALUES (?, ?, ?, ?)
        """, (course_code, course_name, prof_id, selected_dept))
        conn.commit(); conn.close()
        display_msg("SUCCESS!", course_code, "Course added")
        print(f"✅ Course added: {course_code} - {course_name}"); time.sleep(3)
    except Exception as e:
        print(f"❌ Error: {e}"); display_msg("ERROR", str(e)[:16]); time.sleep(2)

def view_courses():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name
            FROM courses c JOIN profs p ON c.prof_id=p.prof_id
            ORDER BY c.course_code
        """)
        courses = cursor.fetchall(); conn.close()
        if not courses:
            display_msg("NO COURSES", "None found"); time.sleep(2); return
        print(f"\n📚 Total Courses: {len(courses)}")
        for code, name, prof in courses:
            display_msg(code, name[:16], f"Prof: {prof[:12]}")
            print(f"  {code}: {name} — {prof}"); time.sleep(2)
    except Exception as e:
        print(f"❌ Error: {e}"); display_msg("ERROR", str(e)[:16]); time.sleep(2)

def enroll_student_in_course():
    print("\n--- Enroll Student in Course ---")
    display_msg("ENROLLMENT", "Enter Student ID")
    time.sleep(1)
    student_id = read_keypad_input("STUDENT ID", mode="ALPHA",
                                   display_line2="OK=Center").upper()
    if not student_id:
        display_msg("CANCELLED"); time.sleep(1); return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, last_name FROM students WHERE student_id=?",
                   (student_id,))
    student = cursor.fetchone()
    if not student:
        display_msg("ERROR", "Student not found"); conn.close(); time.sleep(2); return

    student_name = f"{student[0]} {student[1]}"
    print(f"✅ Student: {student_name}")

    cursor.execute("SELECT course_code, course_name FROM courses ORDER BY course_code")
    courses = cursor.fetchall()
    if not courses:
        display_msg("NO COURSES", "None found"); conn.close(); time.sleep(2); return

    course_options = [f"{c}: {n[:10]}" for c, n in courses]
    selected = select_from_menu("SELECT COURSE", course_options)
    course_code = selected.split(':')[0]

    try:
        cursor.execute("""
            SELECT enrollment_id FROM course_enrollments
            WHERE student_id=? AND course_code=?
        """, (student_id, course_code))
        if cursor.fetchone():
            display_msg("ALREADY", "Enrolled", course_code); time.sleep(2)
        else:
            cursor.execute("""
                INSERT INTO course_enrollments (student_id, course_code, status)
                VALUES (?, ?, 'active')
            """, (student_id, course_code))
            conn.commit()
            display_msg("SUCCESS!", student_name[:16], f"→ {course_code}")
            print(f"✅ Enrolled {student_name} in {course_code}"); time.sleep(3)
        conn.close()
    except Exception as e:
        print(f"❌ Error: {e}"); display_msg("ERROR", str(e)[:16]); time.sleep(2)

def view_course_enrollments():
    display_msg("VIEW ENROLL", "Enter Course Code")
    time.sleep(1)
    course_code = read_keypad_input("COURSE CODE", mode="ALPHA",
                                    display_line2="OK=Center").upper()
    if not course_code:
        display_msg("CANCELLED"); time.sleep(1); return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.first_name, s.last_name, s.dept
            FROM students s
            JOIN course_enrollments ce ON s.student_id=ce.student_id
            WHERE ce.course_code=? AND ce.status='active'
            ORDER BY s.student_id
        """, (course_code,))
        rows = cursor.fetchall(); conn.close()
        if not rows:
            display_msg("NO STUDENTS", "No enrollments", course_code); time.sleep(2); return
        print(f"\n👥 {course_code}: {len(rows)} students")
        for sid, fn, ln, dept in rows:
            display_msg(sid, f"{fn} {ln}"[:16], dept[:16])
            print(f"  {sid}: {fn} {ln} ({dept})"); time.sleep(2)
    except Exception as e:
        print(f"❌ Error: {e}"); display_msg("ERROR", str(e)[:16]); time.sleep(2)

def manage_courses():
    course_menu = ["Add Course", "View Courses", "Enroll Students",
                   "View Enrollments", "Back"]
    while True:
        selected = select_from_menu("COURSE MGMT", course_menu)
        if selected == "Add Course":          add_course()
        elif selected == "View Courses":      view_courses()
        elif selected == "Enroll Students":   enroll_student_in_course()
        elif selected == "View Enrollments":  view_course_enrollments()
        elif selected == "Back":              return

def admin_settings():
    display_msg("ADMIN SETTINGS", "Course Management")
    print("\n⚙️  Admin Settings — Course Management")
    time.sleep(1)
    manage_courses()

def system_info():
    hw_status = []
    hw_status.append(f"OLED    : {'✅' if OLED_AVAILABLE else '❌ (terminal)'}")
    hw_status.append(f"Joystick: {'✅' if JOYSTICK_AVAILABLE else '❌ (keyboard)'}")
    hw_status.append(f"Keypad  : {'✅' if KEYPAD_AVAILABLE else '❌ (keyboard)'}")
    hw_status.append(f"FP Snsr : {'✅' if FINGERPRINT_AVAILABLE else '❌ unavailable'}")

    display_msg("SYSTEM INFO", "IITDH v2.1", "Raspberry Pi")
    print("\n💻 System Information:")
    print("   Device   : Raspberry Pi")
    print("   Software : IITDH Biometric v2.1 (graceful hw)")
    for s in hw_status: print(f"   {s}")
    time.sleep(5)

# =============================================================================
#  MAIN LOOP
# =============================================================================

try:
    display_msg("IITDH System", "Initializing...", "Please wait")
    print("\n" + "="*45)
    print("  IITDH BIOMETRIC ATTENDANCE SYSTEM v2.1")
    print("="*45)
    time.sleep(2)

    while True:
        selection = show_menu()

        if selection == 0:   # Enroll Student
            print("\n📝 Enroll Student")
            prof = authenticate_prof()
            if prof: enroll_student()
            else:
                print("❌ Authentication failed.")
                display_msg("AUTH FAILED", "Access Denied"); time.sleep(2)

        elif selection == 1: # Take Attendance
            print("\n📋 Take Attendance")
            prof = authenticate_prof()
            if prof: classroom_session(prof)
            else:
                print("❌ Authentication failed.")
                display_msg("AUTH FAILED", "Access Denied"); time.sleep(2)

        elif selection == 2: # View Stats
            print("\n📊 View Stats")
            view_stats()

        elif selection == 3: # Admin Settings
            print("\n⚙️  Admin Settings")
            prof = authenticate_prof()
            if prof: admin_settings()
            else:
                display_msg("AUTH FAILED", "Access Denied"); time.sleep(2)

        elif selection == 4: # System Info
            print("\n💻 System Info")
            system_info()

        elif selection == 5: # Shutdown
            print("\n🔌 Shutdown selected")
            display_msg("CONFIRM?", "Press Enter/CENTER", "to Shutdown")
            confirm = input("  Type 'shutdown' to confirm (or Enter to cancel): ").strip().lower()
            if confirm == "shutdown":
                display_msg("SHUTTING DOWN", "Goodbye!")
                print("System shutting down...")
                time.sleep(2)
                if GPIO_AVAILABLE: GPIO.cleanup()
                os.system("sudo shutdown -h now")
                break
            else:
                print("Shutdown cancelled")

except KeyboardInterrupt:
    print("\n⚠️  Interrupted by user")
    display_msg("SHUTDOWN", "Goodbye!")
    time.sleep(1)

except Exception as e:
    print(f"\n❌ Critical Error: {e}")
    display_msg("SYSTEM ERROR", str(e)[:21])
    time.sleep(3)

finally:
    if GPIO_AVAILABLE:
        try: GPIO.cleanup()
        except Exception: pass