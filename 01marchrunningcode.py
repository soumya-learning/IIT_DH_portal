#!/usr/bin/env python3
"""
IITDH Biometric Attendance System
Main entry point — all logic lives in modules/

Sync policy:
  • Boot sync  — once after boot, when WiFi is confirmed up
  • Shutdown   — before every poweroff (warns if WiFi down)
  • WiFi watcher — retries automatically when WiFi returns after failure
  • Manual     — Cloud Sync menu always available

Background sync rules (IMPORTANT):
  • Background threads NEVER write to the OLED — only terminal/journal
  • _hw_lock (threading.Lock) must be held to use OLED or run a session
  • _idle (threading.Event) signals the menu is showing — sync waits for it
  • Both _idle AND _hw_lock must be free before background sync runs
"""

import os
import sys
import time
import socket
import threading
import RPi.GPIO as GPIO

from exit_handler         import ExitHandler
import modules.hardware   as hw
from modules.config       import (JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT,
                                  JOYSTICK_RIGHT, JOYSTICK_CENTER,
                                  SCREENSAVER_TIMEOUT, BackToMainMenu,
                                  AUTO_SYNC_BOOT_DELAY)
from modules.screensaver  import screensaver
from modules.auth         import authenticate_prof
from modules.attendance   import classroom_session
from modules.status       import view_prof_status
from modules.registration import main_menu as registration_menu
from modules.sysinfo      import system_info
from modules.cloud_sync   import run_full_sync, run_attendance_sync
from modules.cloud_pull   import run_full_pull, run_students_pull

# ── Boot ──────────────────────────────────────────────────────────────
ExitHandler().start()

if not hw.init_hardware():
    exit(1)

# ── Concurrency controls ──────────────────────────────────────────────
#
# _idle   : Event — SET when main thread is sitting at the menu doing nothing.
#           CLEARED the moment any menu option is selected (session active).
#           Background threads call _idle.wait() before attempting any sync.
#
# _hw_lock: Lock — must be held by whoever owns the OLED + active session.
#           Main thread acquires it around every menu action.
#           Background sync acquires it (non-blocking try) before syncing.
#           If it can't acquire, it means a session is in progress → skip.
#
# Together they eliminate the race condition where a background sync could
# start writing to OLED at the same instant an attendance session starts.

_idle    = threading.Event()
_idle.set()

_hw_lock = threading.Lock()

# ── Sync-pending flag ─────────────────────────────────────────────────
# Set when sync failed due to no WiFi. Cleared when a sync succeeds.
# WiFi watcher thread watches this and retries when WiFi returns.
_sync_pending = threading.Event()

# ── Menu ──────────────────────────────────────────────────────────────
MENU = [
    "Take Attendance",
    "Registration",
    "Status",
    "Cloud Sync",
    "Admin Settings",
    "Shutdown",
]


# ─────────────────────────────────────────────
# WIFI + DB HELPERS
# ─────────────────────────────────────────────

def _is_wifi_up(host="8.8.8.8", port=53, timeout=3):
    """TCP connect to Google DNS — fast, no DNS lookup needed."""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()
        return True
    except OSError:
        return False


def _reset_failed_sync_records():
    """
    Reset synced=-1 rows → synced=0 before every sync attempt.
    Prevents records from being permanently stuck after a WiFi failure.
    """
    import sqlite3
    from modules.config import DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("UPDATE attendance SET synced = 0 WHERE synced = -1")
        conn.commit()
        conn.close()
        print("[Sync] Reset synced=-1 records → 0 for retry")
    except Exception as e:
        print(f"[Sync] Could not reset failed records: {e}")


# ─────────────────────────────────────────────
# BACKGROUND SYNC  (terminal-only, no OLED)
# Used by boot sync and WiFi watcher.
# Returns True on success, False on failure.
# ─────────────────────────────────────────────

def _background_sync(label):
    """
    Safe background sync — NEVER runs while any operation is in progress.

    Blocked during: attendance session, registration, add course, enroll,
                    status view, cloud sync menu, admin settings, shutdown.
    Only runs when the system is sitting idle at the main menu.

    Flow:
      1. Wait for _idle — blocks until main thread is at the menu
      2. Acquire _hw_lock — blocks for the full duration of any active
         operation (no timeout). Main thread holds this lock the entire
         time any menu action is running.
      3. Re-check _idle after lock — if user just selected something,
         abort this cycle cleanly.
      4. Check WiFi, sync silently (no OLED, no sleeps), release lock.
    """
    # Step 1: block until system is idle at the main menu
    _idle.wait()

    # Step 2: acquire lock — NO timeout. Waits as long as needed.
    # If registration/attendance is running, this blocks until it finishes.
    # Sync will never interrupt an ongoing operation.
    _hw_lock.acquire()

    try:
        # Step 3: re-check idle — guards against the tiny race where the
        # user selects a menu item between step 1 and step 2.
        if not _idle.is_set():
            print(f"[{label}] Operation started just as lock was acquired — aborting")
            return False

        # Step 4: check WiFi (no OLED in background)
        if not _is_wifi_up():
            print(f"[{label}] WiFi DOWN — sync skipped, pending flag set")
            _sync_pending.set()
            return False

        # Step 5: push attendance → then pull latest data from cloud
        # Both run silent (no OLED, no sleeps) so display is never touched
        print(f"[{label}] WiFi up — starting background sync")
        _reset_failed_sync_records()

        print(f"[{label}] Step 1/2 — pushing attendance records")
        run_attendance_sync(silent=True)
        _sync_pending.clear()
        print(f"[{label}] Step 1/2 done ✓")

        print(f"[{label}] Step 2/2 — pulling latest data from cloud")
        run_full_pull(silent=True)
        print(f"[{label}] Step 2/2 done ✓  — sync complete")
        return True

    except Exception as e:
        print(f"[{label}] Sync error: {e}")
        _sync_pending.set()
        return False

    finally:
        # Always release — even on exception
        _hw_lock.release()


# ─────────────────────────────────────────────
# BOOT SYNC THREAD
# Runs once after boot. Retries every 30s until WiFi is up.
# ─────────────────────────────────────────────

def _boot_sync_worker():
    print(f"[BootSync] Waiting {AUTO_SYNC_BOOT_DELAY}s for hardware to settle...")
    time.sleep(AUTO_SYNC_BOOT_DELAY)

    attempt = 0
    while True:
        attempt += 1
        print(f"[BootSync] Attempt {attempt}...")

        # If attendance is being taken right now, wait for it to finish
        _idle.wait()

        if _background_sync("BootSync"):
            print("[BootSync] Done — thread exiting")
            return   # success — boot sync thread is no longer needed

        # Failed (WiFi down or busy) — wait 30s and try again
        print("[BootSync] Retrying in 30s...")
        time.sleep(30)


def _start_boot_sync():
    t = threading.Thread(target=_boot_sync_worker, name="BootSync", daemon=True)
    t.start()
    print("[BootSync] Thread started")


# ─────────────────────────────────────────────
# WIFI WATCHER THREAD
# Polls every 30s. When _sync_pending is set and WiFi returns, retries.
# ─────────────────────────────────────────────

_WIFI_POLL = 30   # seconds between checks

def _wifi_watcher_worker():
    print("[WiFiWatcher] Started")
    while True:
        time.sleep(_WIFI_POLL)

        if not _sync_pending.is_set():
            continue    # nothing pending — keep watching silently

        if not _is_wifi_up():
            print("[WiFiWatcher] WiFi still down — will retry")
            continue

        print("[WiFiWatcher] WiFi restored and sync pending — attempting retry")
        if _background_sync("WiFiWatcher"):
            print("[WiFiWatcher] Pending sync resolved ✓")
        # If it fails again, _sync_pending stays set → retried next cycle


def _start_wifi_watcher():
    t = threading.Thread(target=_wifi_watcher_worker, name="WiFiWatcher", daemon=True)
    t.start()
    print("[WiFiWatcher] Thread started")


# ─────────────────────────────────────────────
# REGISTRATION LAUNCHER
# ─────────────────────────────────────────────

def launch_registration():
    hw.display_msg("REGISTRATION", "Loading...", "")
    time.sleep(0.3)
    try:
        registration_menu()
    except BackToMainMenu:
        pass
    except Exception as e:
        hw.display_msg("REG ERROR", str(e)[:20], "")
        print(f"[Registration] Error: {e}")
        import traceback
        traceback.print_exc()
        time.sleep(3)
    hw.display_msg("IITDH System", "Ready", "")
    time.sleep(0.5)


# ─────────────────────────────────────────────
# CLOUD SYNC SUB-MENU  (manual, main thread)
# ─────────────────────────────────────────────

def cloud_sync_menu():
    options = [
        "Full Sync  (push all)",
        "Att. Only  (quick push)",
        "Full Pull  (pull all)",
        "Students   (quick pull)",
        "Back",
    ]
    selected      = 0
    scroll_offset = 0
    visible       = 3

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible:
            scroll_offset = selected - visible + 1

        hw.display_scrolling_menu(options, selected, scroll_offset)
        btn = hw.wait_for_button()

        if btn == "UP":
            selected = (selected - 1) % len(options)
        elif btn == "DOWN":
            selected = (selected + 1) % len(options)
        elif btn == "CENTER":
            if selected == 4:
                return
            # Manual sync — check WiFi first, then sync (main thread owns OLED)
            if not _is_wifi_up():
                hw.display_msg("NO WIFI", "Cannot sync", "Check network")
                time.sleep(3)
                continue
            _reset_failed_sync_records()
            if   selected == 0: run_full_sync()
            elif selected == 1: run_attendance_sync()
            elif selected == 2: run_full_pull()
            elif selected == 3: run_students_pull()
            _sync_pending.clear()
        elif btn == "LEFT":
            return


# ─────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────

def show_menu():
    selected      = 0
    scroll_offset = 0
    visible       = 3

    while True:
        if selected < scroll_offset:
            scroll_offset = selected
        elif selected >= scroll_offset + visible:
            scroll_offset = selected - visible + 1

        hw.display_scrolling_menu(MENU, selected, scroll_offset)

        deadline = time.time() + SCREENSAVER_TIMEOUT
        button   = None

        while time.time() < deadline:
            for pin, name in [
                (JOYSTICK_UP,     "UP"),
                (JOYSTICK_DOWN,   "DOWN"),
                (JOYSTICK_CENTER, "CENTER"),
                (JOYSTICK_LEFT,   "LEFT"),
                (JOYSTICK_RIGHT,  "RIGHT"),
            ]:
                if GPIO.input(pin) == GPIO.LOW:
                    time.sleep(0.3)
                    button = name
                    break
            if button:
                break
            time.sleep(0.05)

        if button is None:
            screensaver()
            continue

        if   button == "UP":     selected = (selected - 1) % len(MENU)
        elif button == "DOWN":   selected = (selected + 1) % len(MENU)
        elif button == "CENTER": return selected
        elif button == "LEFT":   selected = max(0, selected - visible)
        elif button == "RIGHT":  selected = min(len(MENU) - 1, selected + visible)


# ─────────────────────────────────────────────
# START BACKGROUND THREADS
# ─────────────────────────────────────────────

_start_boot_sync()
_start_wifi_watcher()


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

try:
    hw.display_msg("IITDH System", "Ready", "")
    time.sleep(0.5)

    while True:
        selection = show_menu()

        # ── Mark system busy ──────────────────────────────────────
        # 1. Clear _idle first so background threads stop waiting
        # 2. Acquire _hw_lock so any thread that already passed _idle.wait()
        #    and is attempting _hw_lock.acquire() is blocked until we finish
        _idle.clear()
        _hw_lock.acquire()

        try:
            # ── 0: Take Attendance ────────────────────────────────
            if selection == 0:
                prof = authenticate_prof()
                if prof:
                    classroom_session(prof)
                else:
                    hw.display_msg("AUTH FAILED", "Access Denied", "")
                    time.sleep(2)

            # ── 1: Registration ───────────────────────────────────
            elif selection == 1:
                launch_registration()

            # ── 2: Status ─────────────────────────────────────────
            elif selection == 2:
                view_prof_status()

            # ── 3: Cloud Sync ─────────────────────────────────────
            elif selection == 3:
                cloud_sync_menu()

            # ── 4: Admin Settings ─────────────────────────────────
            elif selection == 4:
                system_info()

            # ── 5: Shutdown ───────────────────────────────────────
            elif selection == 5:
                hw.display_msg("CONFIRM?", "Press CENTER", "to Shutdown")
                if hw.wait_for_button() == "CENTER":
                    if _is_wifi_up():
                        # ── Step 1: Full sync (push all) ──────────
                        hw.display_msg("SYNCING...", "Step 1 of 2", "Pushing data...")
                        _reset_failed_sync_records()
                        try:
                            run_full_sync()
                            _sync_pending.clear()
                            print("[Shutdown] Pre-shutdown full sync complete")
                        except Exception as e:
                            print(f"[Shutdown] Full sync error: {e}")
                            hw.display_msg("SYNC ERROR", str(e)[:20], "Continuing...")
                            time.sleep(2)

                        # ── Step 2: Full pull ──────────────────────
                        hw.display_msg("PULLING...", "Step 2 of 2", "Fetching data...")
                        try:
                            run_full_pull()
                            print("[Shutdown] Pre-shutdown full pull complete")
                        except Exception as e:
                            print(f"[Shutdown] Full pull error: {e}")
                            hw.display_msg("PULL ERROR", str(e)[:20], "Continuing...")
                            time.sleep(2)

                        hw.display_msg("SYNC DONE", "All data saved", "Shutting down...")
                        time.sleep(2)

                    else:
                        hw.display_msg("NO WIFI", "Data NOT synced", "Shutting down...")
                        print("[Shutdown] WiFi down — sync skipped")
                        time.sleep(3)

                    hw.display_msg("SHUTTING DOWN", "Goodbye!", "")
                    time.sleep(2)
                    GPIO.cleanup()
                    os.system("sudo shutdown -h now")
                    break

        except BackToMainMenu:
            hw.display_msg("MAIN MENU", "", "")
            time.sleep(0.5)

        finally:
            # ── Release in correct order ──────────────────────────
            # Release lock first, then set idle — background threads
            # will see _idle set only after the lock is free.
            _hw_lock.release()
            _idle.set()

except KeyboardInterrupt:
    hw.display_msg("SHUTDOWN", "Goodbye!", "")
    time.sleep(1)
    GPIO.cleanup()

except Exception as e:
    print(f"\n❌ Critical Error: {e}")
    import traceback
    traceback.print_exc()
    hw.display_msg("SYSTEM ERROR", str(e)[:20], "")
    time.sleep(3)
    GPIO.cleanup()