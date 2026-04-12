"""
IITDH Attendance System — Secure Exit Handler
==============================================

Runs as a background daemon thread inside the main attendance script.
Listens for a secret keyword typed into the terminal, then prompts
for a password. On success, exits cleanly.

EXIT CODES (must match SuccessExitStatus in attendance.service):
  os._exit(0)  — clean quit, systemd does NOT restart
  os._exit(42) — desktop requested, start.sh launches startx, systemd does NOT restart

EXIT FLOW:
  1. Type  "exit"  + Enter  →  password prompt
  2. Correct password       →  exits with code 0  (attendance app stops, no restart)
  3. Wrong password × 3     →  locked for 30s, app keeps running

TO CHANGE THE PASSWORD:
  python3 -c "import hashlib; print(hashlib.sha256('YOUR_NEW_PW'.encode()).hexdigest())"
  Paste output as EXIT_PASSWORD_HASH below.
"""

import hashlib
import os
import sys
import threading
import time

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

SECRET_KEYWORD = "exit"

# Default password: IITDH@2025
EXIT_PASSWORD_HASH = "ee3dbd86c34f632b2a2b28c493990eed714e81b09133dbb6ad2507b8dd4647f3"

MAX_ATTEMPTS    = 3
LOCKOUT_SECONDS = 30


# ─────────────────────────────────────────────
# EXIT HANDLER
# ─────────────────────────────────────────────

class ExitHandler:
    """
    Background daemon thread — monitors stdin for the secret keyword.
    Call .start() once near the top of 01marchrunningcode.py.
    """

    def __init__(self):
        self._thread = threading.Thread(
            target=self._listen_keyboard,
            name="ExitHandler",
            daemon=True
        )
        self._locked_until = 0

    def start(self):
        self._thread.start()
        print("[ExitHandler] Running — type the keyword to trigger secure exit")

    # ── PRIVATE ───────────────────────────────

    def _listen_keyboard(self):
        """Read stdin line by line, wait for SECRET_KEYWORD."""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:        # EOF / stdin closed
                    time.sleep(1)
                    continue
                if line.strip().lower() == SECRET_KEYWORD.lower():
                    self._trigger_exit_prompt()
            except Exception:
                time.sleep(1)

    def _trigger_exit_prompt(self):
        """Password prompt — called when keyword is detected."""
        now = time.time()
        if now < self._locked_until:
            remaining = int(self._locked_until - now)
            print(f"\n🔒 Too many failed attempts. Locked for {remaining}s.")
            return

        print("\n" + "=" * 50)
        print("  SECURE EXIT — IITDH Attendance System")
        print("=" * 50)

        attempts = 0
        while attempts < MAX_ATTEMPTS:
            try:
                import getpass
                password = getpass.getpass("  Enter exit password: ")
            except (EOFError, KeyboardInterrupt):
                print("\n  Exit cancelled.")
                return

            if self._check_password(password):
                self._do_exit()
                return
            else:
                attempts += 1
                remaining_tries = MAX_ATTEMPTS - attempts
                if remaining_tries > 0:
                    print(f"  ❌ Wrong password. {remaining_tries} attempt(s) left.")
                else:
                    self._locked_until = time.time() + LOCKOUT_SECONDS
                    print(f"  🔒 Access denied. Locked for {LOCKOUT_SECONDS}s.")
                    print("  Attendance system continuing...\n")

    def _check_password(self, entered: str) -> bool:
        entered_hash = hashlib.sha256(entered.encode()).hexdigest()
        return entered_hash == EXIT_PASSWORD_HASH

    def _do_exit(self):
        """Authenticated exit — stop the attendance app cleanly."""
        print("\n  ✅ Access granted. Exiting attendance system...")
        print("=" * 50)
        time.sleep(1)
        print("  Goodbye. Closing attendance system.")
        # Exit code 0 — systemd will NOT restart (SuccessExitStatus=0 42)
        os._exit(0)


# ─────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("ExitHandler test mode")
    print(f"  Secret keyword  : '{SECRET_KEYWORD}'")
    print(f"  Default password: IITDH@2025")
    print()
    handler = ExitHandler()
    handler.start()
    print("Simulating attendance app... (type 'exit' to test)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nTest ended.")
