import time
import sqlite3
from modules.config import DB_PATH
import modules.hardware as hw


def authenticate_prof():
    """
    Verify a professor by fingerprint scan.
    Loads all prof templates from DB, compares on-sensor.
    Returns prof name string on success, None on failure/timeout.
    """
    print("\n--- Professor Authorization Required ---")
    hw.display_msg("ADMIN REQUIRED", "Scan Prof Finger")

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, template FROM profs")
    profs  = cursor.fetchall()
    conn.close()

    if not profs:
        hw.display_msg("ERROR", "No Profs Found")
        time.sleep(2)
        return None

    hw.uart.reset_input_buffer()
    timeout = time.time() + 15

    while time.time() < timeout:
        if hw.finger.get_image() == 0:
            hw.finger.image_2_tz(1)
            for name, template in profs:
                hw.finger.send_fpdata(list(template), "char", 2)
                if hw.finger.compare_templates() == 0:
                    hw.display_msg("AUTHORIZED", f"Prof. {name}")
                    time.sleep(1.5)
                    return name
        time.sleep(0.1)

    hw.display_msg("TIMEOUT", "Auth Failed")
    time.sleep(2)
    return None
