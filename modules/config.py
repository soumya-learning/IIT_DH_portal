# ─────────────────────────────────────────────
# IITDH Attendance System — Central Config
# All constants in one place. Import from here.
# ─────────────────────────────────────────────

# ── Paths ──────────────────────────────────────────────────────────
DB_PATH    = '/home/bio_user_iitdh/new_env/DB/college.db'
CREDS_PATH = '/home/bio_user_iitdh/new_env/.sysaccess_creds'

# ── Sync ───────────────────────────────────────────────────────────
# No periodic auto-sync. Sync happens:
#   1. Once after boot (when WiFi is confirmed up)
#   2. Automatically when WiFi returns after a failed sync
#   3. Before every shutdown
AUTO_SYNC_BOOT_DELAY = 60   # seconds after boot before first sync attempt

# ── Fingerprint Enrollment ──────────────────────────────────────────
FP_NUM_SCANS       = 5    # total scans (1 base + 4 merge iterations)
FP_MAX_RETRIES     = 6    # max attempts per individual scan
FP_TEMP_SLOT       = 127  # sensor flash slot used for self-match verify only
FP_MIN_CONFIDENCE  = 50   # below this → reject template, force re-enroll
FP_WARN_CONFIDENCE = 100  # below this → warn but allow save

# ── Supabase ───────────────────────────────────────────────────────
import os
SUPABASE_URL = os.environ.get("SUPABASE_URL",
               "https://peagkvkhhsbdytevnhia.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY",
               "sb_secret_Q0zxaI4Myb6lY0IWZKgjLw_pXGH5zXj")

# ── GPIO — Joystick ────────────────────────────────────────────────
JOYSTICK_UP     = 17    # Pin 11
JOYSTICK_DOWN   = 6     # Pin 31
JOYSTICK_LEFT   = 22    # Pin 15
JOYSTICK_RIGHT  = 23    # Pin 16
JOYSTICK_CENTER = 26    # Pin 37

# ── I2C Keypad ─────────────────────────────────────────────────────
I2C_ADDR = 0x20
ROWS     = [4, 5, 6, 7]
COLS     = [0, 1, 2, 3]
KEYPAD   = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]
LETTERS = {
    '1': ['a', 'b', 'c'],
    '2': ['d', 'e', 'f'],
    '3': ['g', 'h', 'i'],
    '4': ['j', 'k', 'l'],
    '5': ['m', 'n', 'o'],
    '6': ['p', 'q', 'r'],
    '7': ['s', 't', 'u'],
    '8': ['v', 'w', 'x'],
    '9': ['y', 'z']
}

# ── Department & Program Maps ──────────────────────────────────────
DEPT_MAP = {
    "CS": "Computer Science",
    "EE": "Electrical Engineering",
    "MC": "Math & Computing",
    "ME": "Mechanical Engineering",
    "CH": "Chemical Engineering",
    "CE": "Civil Engineering"
}
PROG_MAP = {
    "BT": "B.Tech",
    "IS": "BSMS",
    "MT": "M.Tech"
}
DEPT_REVERSE = {v: k for k, v in DEPT_MAP.items()}
PROG_REVERSE = {v: k for k, v in PROG_MAP.items()}

# Used by cloud_sync — maps full names stored locally to cloud codes
DEPT_NAME_TO_CODE = {v: k for k, v in DEPT_MAP.items()}
PROG_NAME_TO_CODE = {v: k for k, v in PROG_MAP.items()}

# ── Hardware ───────────────────────────────────────────────────────
SERIAL_PORT         = "/dev/ttyAMA0"
BAUD_RATE           = 57600
UPS_ADDR            = 0x2d
SCREENSAVER_TIMEOUT = 45    # seconds before screensaver activates

# ── Navigation ─────────────────────────────────────────────────────
class BackToMainMenu(BaseException):
    """
    Raised when the D key is pressed — immediately returns to main menu.
    Inherits from BaseException (not Exception) so broad `except Exception`
    blocks in courses.py, enrollment.py etc. cannot accidentally swallow it.
    The explicit `except BackToMainMenu` in the main loop still catches it.
    """
    pass