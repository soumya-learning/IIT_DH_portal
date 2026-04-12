import os
import time
import RPi.GPIO as GPIO
import modules.hardware as hw
from modules.config  import CREDS_PATH
from modules.keypad  import read_keypad_input


def system_access():
    """
    Secure exit to desktop:
      1. Load keyword + password from .sysaccess_creds file
      2. Prompt via keypad — keyword first, then password
      3. Match → GPIO cleanup → os._exit(42)
         (start.sh catches exit code 42 and opens desktop)
    """
    creds = _load_creds()
    secret_keyword  = creds.get('KEYWORD', '')
    secret_password = creds.get('PASSWORD', '')

    if not secret_keyword or not secret_password:
        hw.display_msg("SYS ACCESS", "Creds missing!", "Contact Admin")
        time.sleep(3)
        return

    entered_kw = read_keypad_input("KEYWORD", mode="ALPHA",
                                   display_line2="CENTER=OK",
                                   show_as_password=True)
    if not entered_kw or entered_kw != secret_keyword:
        hw.display_msg("ACCESS DENIED", "Wrong keyword", "")
        time.sleep(3)
        return

    entered_pw = read_keypad_input("PASSWORD", mode="NUMBER",
                                   display_line2="CENTER=OK",
                                   show_as_password=True)
    if not entered_pw or entered_pw != secret_password:
        hw.display_msg("ACCESS DENIED", "Wrong password", "")
        time.sleep(3)
        return

    hw.display_msg("ACCESS GRANTED", "Loading Desktop", "Please wait...")
    time.sleep(2)
    GPIO.cleanup()
    os._exit(42)      # caught by start.sh to open desktop


def system_info():
    """
    System Info sub-menu:
      - Device Info  → show version string
      - System Access → secure exit to desktop
      - Back
    """
    sub_options   = ["Device Info", "System Access", "Back"]
    selected      = 0
    scroll_offset = 0

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + 3:
            scroll_offset = selected - 2

        hw.display_scrolling_menu(sub_options, selected, scroll_offset)
        btn = hw.wait_for_button()

        if btn == "UP":
            selected = (selected - 1) % len(sub_options)
        elif btn == "DOWN":
            selected = (selected + 1) % len(sub_options)
        elif btn == "CENTER":
            if selected == 0:
                hw.display_msg("SYSTEM INFO", "IITDH v2.0", "Raspberry Pi")
                time.sleep(5)
            elif selected == 1:
                system_access()
                return
            elif selected == 2:
                return
        elif btn == "LEFT":
            return


# ─────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────

def _load_creds():
    creds = {}
    try:
        with open(CREDS_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, val = line.split('=', 1)
                    creds[key.strip()] = val.strip()
    except Exception as e:
        print(f"❌ Could not load creds: {e}")
    return creds