import time
import RPi.GPIO as GPIO
from luma.core.render import canvas
from modules.config import (JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT,
                             JOYSTICK_RIGHT, JOYSTICK_CENTER, UPS_ADDR)
import modules.hardware as hw


def get_battery_percent():
    try:
        percent = hw.bus.read_byte_data(UPS_ADDR, 0x24)
        return min(percent, 100)
    except:
        return -1


def draw_battery_icon(draw, x, y, percent):
    draw.rectangle([(x, y), (x + 18, y + 9)], outline="white")
    draw.rectangle([(x + 19, y + 3), (x + 21, y + 6)], fill="white")
    fill_width = int((percent / 100) * 16)
    if fill_width > 0:
        draw.rectangle([(x + 1, y + 1), (x + 1 + fill_width, y + 8)], fill="white")


def screensaver():
    """
    Energy-efficient screensaver:
      - Redraws only once per minute (not every second)
      - Shows HH:MM only — no seconds
      - Polls joystick at 10 Hz — fast enough to feel instant
    """
    print("[Screensaver] Activated")
    last_draw = 0

    while True:
        now = time.time()

        # ── Redraw once per minute only ───────────────────────────
        if now - last_draw >= 60.0:
            percent      = get_battery_percent()
            current_time = time.strftime("%H:%M")       # no seconds
            current_date = time.strftime("%d %b %Y")

            if percent == -1:
                batt_label = "Batt: N/A"
            elif percent > 80:
                batt_label = f"{percent}%  Good"
            elif percent > 30:
                batt_label = f"{percent}%  OK"
            else:
                batt_label = f"{percent}%  LOW!"

            with canvas(hw.device) as draw:
                draw.rectangle([(0, 0), (127, 63)], outline="white")
                draw.text((38, 4),  "-- IITDH --",  fill="white")
                draw.line([(1, 15), (126, 15)],      fill="white", width=1)
                draw.text((28, 22), current_time,    fill="white")
                draw.text((22, 36), current_date,    fill="white")
                draw.line([(1, 48), (126, 48)],      fill="white", width=1)
                if percent != -1:
                    draw_battery_icon(draw, 4, 53, percent)
                    draw.text((30, 53), batt_label,  fill="white")
                else:
                    draw.text((5, 53), "Battery: N/A", fill="white")

            last_draw = now

        # ── Joystick wake check ───────────────────────────────────
        if (GPIO.input(JOYSTICK_UP)     == GPIO.LOW or
            GPIO.input(JOYSTICK_DOWN)   == GPIO.LOW or
            GPIO.input(JOYSTICK_LEFT)   == GPIO.LOW or
            GPIO.input(JOYSTICK_RIGHT)  == GPIO.LOW or
            GPIO.input(JOYSTICK_CENTER) == GPIO.LOW):

            print("[Screensaver] Deactivated")
            # Wait for release
            while (GPIO.input(JOYSTICK_UP)     == GPIO.LOW or
                   GPIO.input(JOYSTICK_DOWN)    == GPIO.LOW or
                   GPIO.input(JOYSTICK_LEFT)    == GPIO.LOW or
                   GPIO.input(JOYSTICK_RIGHT)   == GPIO.LOW or
                   GPIO.input(JOYSTICK_CENTER)  == GPIO.LOW):
                time.sleep(0.05)
            time.sleep(0.1)
            # Force immediate redraw on wake so time is current
            last_draw = 0
            return

        time.sleep(0.1)     # 10 Hz — fast button response, low CPU
