"""
modules/reg_fingerprint.py
IITDH Attendance System — Fingerprint Enrollment Engine

4-scan iterative merge with re-anchor strategy and self-match
confidence verification. All hardware access goes through the
shared hw module (hw.finger, hw.uart, hw.display_msg) — no
separate serial or OLED initialisation needed.

Public API:
  scan_fingerprint() → bytes | None
      Runs the full merge + verify pipeline.
      Returns template bytes on success, None on failure/poor quality.
"""

import struct
import time

import modules.hardware as hw
from modules.config import (FP_NUM_SCANS, FP_MAX_RETRIES, FP_TEMP_SLOT,
                             FP_MIN_CONFIDENCE, FP_WARN_CONFIDENCE)

# R307 sensor raw packet constants (used only in 1:1 compare fallback)
_R307_ADDR  = 0xFFFFFFFF
_START_CODE = 0xEF01


# ─────────────────────────────────────────────
# FINGER PLACEMENT / REMOVAL HELPERS
# ─────────────────────────────────────────────

def _wait_for_finger(timeout_sec=12):
    """Block until a finger is detected. Returns True on success."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if hw.finger.get_image() == 0:
            return True
        time.sleep(0.1)
    return False


def _wait_for_removal(timeout_sec=6):
    """Block until the finger is lifted."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if hw.finger.get_image() != 0:
            time.sleep(0.3)   # debounce
            return
        time.sleep(0.1)


# ─────────────────────────────────────────────
# RAW UART 1:1 MATCH (FALLBACK)
# ─────────────────────────────────────────────

def _raw_match_buffers():
    """
    Send R307 Match command (0x03) directly over UART.
    Compares CharBuffer1 vs CharBuffer2.
    Returns score 0-200, or None on communication error.
    """
    try:
        pkt_id   = 0x01
        length   = 0x0003
        cmd      = 0x03
        checksum = pkt_id + (length >> 8) + (length & 0xFF) + cmd

        packet = (
            struct.pack('>H', _START_CODE) +
            struct.pack('>I', _R307_ADDR)  +
            struct.pack('>B', pkt_id)      +
            struct.pack('>H', length)      +
            struct.pack('>B', cmd)         +
            struct.pack('>H', checksum)
        )

        hw.uart.reset_input_buffer()
        hw.uart.write(packet)
        time.sleep(0.15)

        response = hw.uart.read(14)
        if len(response) < 14:
            return None

        confirm_code = response[9]
        score        = struct.unpack('>H', response[10:12])[0]

        if confirm_code == 0x00:
            return score
        elif confirm_code == 0x08:
            return 0      # buffers don't match
        return None

    except Exception:
        return None


def _confidence_label(score):
    """Human-readable label for a self-match confidence score."""
    if score is None:
        return "Unknown"
    if score <= FP_MIN_CONFIDENCE:
        return f"POOR ({score}/200)"
    if score <= FP_WARN_CONFIDENCE:
        return f"WEAK ({score}/200)"
    if score <= 150:
        return f"GOOD ({score}/200)"
    return f"EXCELLENT ({score}/200)"


# ─────────────────────────────────────────────
# CORE MERGE LOGIC
# ─────────────────────────────────────────────

def _run_merge():
    """
    Phase 1: Perform iterative merge across FP_NUM_SCANS scans.
    On success, CharBuffer1 holds the final merged template.

    Re-anchor strategy:
      After 3 consecutive merge rejections, re-capture a fresh scan
      into CharBuffer1 to reset the similarity baseline. This addresses
      the R307's ~70-80% internal similarity gate.

    Returns (success: bool, merge_log: list of (scan, attempt, code))
    """
    merge_log = []

    # ── Scan 1: capture base into CharBuffer1 ────────────────────
    print(f"\n  SCAN 1/{FP_NUM_SCANS}: Place finger on sensor...")
    hw.display_msg("SCAN 1 of 4", "Place finger")

    ok = False
    for attempt in range(1, FP_MAX_RETRIES + 1):
        if not _wait_for_finger():
            print(f"    Timeout (attempt {attempt}/{FP_MAX_RETRIES})")
            hw.display_msg("TIMEOUT", f"Try {attempt}/{FP_MAX_RETRIES}")
            continue

        code = hw.finger.image_2_tz(1)
        if code == 0:
            print("    Scan 1 captured → CharBuffer1")
            hw.display_msg("SCAN 1 of 4", "Captured!")
            _wait_for_removal()
            ok = True
            break

        print(f"    Bad image (code {hex(code)}), retry...")
        hw.display_msg("Bad Image", f"Try {attempt}/{FP_MAX_RETRIES}")
        _wait_for_removal()
        time.sleep(0.5)

    if not ok:
        print("  Failed to capture scan 1")
        hw.display_msg("FAILED", "Scan 1 failed")
        return False, merge_log

    # ── Scans 2-N: merge into CharBuffer1 ────────────────────────
    for scan_num in range(2, FP_NUM_SCANS + 1):
        scan_ok       = False
        consec_reject = 0

        for attempt in range(1, FP_MAX_RETRIES + 1):
            print(f"\n  SCAN {scan_num}/{FP_NUM_SCANS}: Remove then place finger...")
            hw.display_msg(f"SCAN {scan_num} of 4", "Remove finger")
            _wait_for_removal()
            time.sleep(0.5)

            hw.display_msg(f"SCAN {scan_num} of 4", "Place finger")
            if not _wait_for_finger():
                print(f"    Timeout (attempt {attempt}/{FP_MAX_RETRIES})")
                hw.display_msg("TIMEOUT", f"Retry {attempt}/{FP_MAX_RETRIES}")
                continue

            # Capture into CharBuffer2
            img_code = hw.finger.image_2_tz(2)
            if img_code != 0:
                print(f"    Bad image (code {hex(img_code)}), retry...")
                hw.display_msg("Bad Image", f"Retry {attempt}/{FP_MAX_RETRIES}")
                _wait_for_removal()
                time.sleep(0.5)
                continue

            # Merge CharBuffer1 + CharBuffer2 → updated CharBuffer1
            hw.display_msg(f"SCAN {scan_num} of 4", "Merging...")
            merge_code = hw.finger.create_model()
            merge_log.append((scan_num, attempt, merge_code))

            if merge_code == 0:
                print(f"    Scan {scan_num} merged successfully")
                hw.display_msg(f"SCAN {scan_num} of 4", "Success!")
                _wait_for_removal()
                consec_reject = 0
                scan_ok = True
                break

            elif merge_code == 0x0A:
                # Sensor's similarity gate rejected the merge
                consec_reject += 1
                print(f"    Merge rejected — similarity too low "
                      f"(attempt {attempt}/{FP_MAX_RETRIES})")
                print("    Tip: press more firmly, centre finger on sensor")
                hw.display_msg("No Match", f"Retry {attempt}/{FP_MAX_RETRIES}")
                _wait_for_removal()

                # Re-anchor: refresh CharBuffer1 after 3 consecutive rejects
                if consec_reject >= 3:
                    print("\n    Re-anchoring base (3 rejects in a row)...")
                    hw.display_msg("RE-ANCHOR", "Place finger")
                    if _wait_for_finger(timeout_sec=10):
                        rc = hw.finger.image_2_tz(1)
                        if rc == 0:
                            print("      CharBuffer1 re-anchored")
                            hw.display_msg("Re-anchored", "Try again")
                        else:
                            print(f"      Re-anchor image bad ({hex(rc)})")
                        _wait_for_removal()
                    consec_reject = 0
                time.sleep(0.8)

            else:
                print(f"    Merge error (code {hex(merge_code)})")
                hw.display_msg("Merge Error", f"Code {hex(merge_code)}")
                _wait_for_removal()
                time.sleep(0.5)

        if not scan_ok:
            print(f"  Failed scan {scan_num} after {FP_MAX_RETRIES} attempts")
            hw.display_msg("FAILED", f"Scan {scan_num} failed")
            time.sleep(2)
            return False, merge_log

    print("\n  All scans merged — CharBuffer1 has final template")
    return True, merge_log


# ─────────────────────────────────────────────
# SELF-MATCH VERIFICATION
# ─────────────────────────────────────────────

def _run_self_match_verify():
    """
    Phase 2: Store merged template to FP_TEMP_SLOT, re-scan same
    finger, verify confidence via finger_search(). Falls back to
    raw 1:1 UART compare if search fails.
    Returns confidence score or None.
    """
    print("\n  Storing template to temp slot for verification...")
    hw.display_msg("VERIFYING...", "Storing temp")

    store_code = hw.finger.store_model(FP_TEMP_SLOT, 1)
    if store_code != 0:
        print(f"    store_model failed ({hex(store_code)}) — 1:1 fallback")
        return _run_11_compare_fallback()

    print(f"    Stored in slot {FP_TEMP_SLOT}")
    time.sleep(0.5)

    print("\n  Scan SAME finger again to verify quality...")
    hw.display_msg("VERIFY SCAN", "Same finger")

    for attempt in range(1, 4):
        if not _wait_for_finger():
            print(f"    Timeout on verify (attempt {attempt}/3)")
            continue

        img_code = hw.finger.image_2_tz(1)
        if img_code != 0:
            print(f"    Bad image ({hex(img_code)})")
            _wait_for_removal()
            continue

        search_code = hw.finger.finger_search()
        _wait_for_removal()

        if search_code == 0:
            score = hw.finger.confidence
            print(f"    Self-match: slot {hw.finger.finger_id}, "
                  f"confidence {score}/200")
            return score
        else:
            print(f"    finger_search failed ({hex(search_code)}) — 1:1 fallback")
            return _run_11_compare_fallback()

    return None


def _run_11_compare_fallback():
    """Load template from TEMP_SLOT, scan new finger into CharBuffer2,
    run raw 0x03 Match command. Returns score or None."""
    print("\n    Fallback: 1:1 raw UART Match (0x03)...")
    hw.display_msg("FALLBACK", "1:1 Compare")

    load_code = hw.finger.load_model(FP_TEMP_SLOT, 1)
    if load_code != 0:
        print(f"    load_model failed ({hex(load_code)})")
        return None

    print("    Place same finger for 1:1 compare...")
    hw.display_msg("1:1 COMPARE", "Place finger")

    for _ in range(3):
        if not _wait_for_finger():
            continue
        img_code = hw.finger.image_2_tz(2)
        if img_code != 0:
            _wait_for_removal()
            continue
        score = _raw_match_buffers()
        _wait_for_removal()
        if score is not None:
            print(f"    1:1 match score: {score}/200")
            return score

    print("    1:1 compare also failed")
    return None


def _cleanup_temp_slot():
    """Remove the temporary verification slot from sensor flash."""
    try:
        code = hw.finger.delete_model(FP_TEMP_SLOT)
        if code == 0:
            print(f"    Temp slot {FP_TEMP_SLOT} cleaned up")
        else:
            print(f"    Could not delete slot {FP_TEMP_SLOT} ({hex(code)})")
    except Exception as e:
        print(f"    Cleanup error: {e}")


def _print_merge_report(merge_log, confidence):
    """Print a concise quality summary to terminal."""
    print("\n" + "─" * 50)
    print("  MERGE QUALITY REPORT")
    print("─" * 50)

    total   = len(merge_log)
    rejects = sum(1 for _, _, c in merge_log if c == 0x0A)
    if total > 0:
        pct = rejects / total * 100
        print(f"  Rejections : {rejects}/{total} ({pct:.0f}%)")
        if pct > 60:
            print("  WARNING: high rejection rate — sensor may be dirty")

    print(f"  Self-match : {_confidence_label(confidence)}")

    if confidence is None:
        verdict = "INCONCLUSIVE — could not verify template"
    elif confidence <= FP_MIN_CONFIDENCE:
        verdict = "POOR — template rejected, re-enroll"
    elif confidence <= FP_WARN_CONFIDENCE:
        verdict = "WEAK — saved with warning"
    elif confidence <= 150:
        verdict = "GOOD — template healthy"
    else:
        verdict = "EXCELLENT — perfect merge"

    print(f"  Verdict    : {verdict}")
    print("─" * 50)


# ─────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────

def scan_fingerprint():
    """
    Full 4-scan merge pipeline with self-match quality verification.

    Phases:
      1. Merge    — iterative multi-scan merge with re-anchor
      2. Verify   — self-match score via finger_search / 1:1 fallback
      3. Cleanup  — remove temp sensor slot
      4. Report   — print quality summary to terminal
      5. Decision — reject if score < FP_MIN_CONFIDENCE
      6. Download — pull final template bytes from CharBuffer1

    Returns template bytes (list) on success, None on failure.
    """
    try:
        print("\n--- Fingerprint Registration (v2 Merge + Verify) ---")
        hw.display_msg("FINGERPRINT", "4 scans needed")
        time.sleep(1.5)

        # Phase 1
        success, merge_log = _run_merge()
        if not success:
            hw.display_msg("FAILED", "Merge failed")
            time.sleep(2)
            return None

        # Phase 2
        hw.display_msg("VERIFYING", "Self-match...")
        confidence = _run_self_match_verify()

        # Phase 3
        _cleanup_temp_slot()

        # Phase 4
        _print_merge_report(merge_log, confidence)

        # Phase 5 — quality gate
        if confidence is not None and confidence <= FP_MIN_CONFIDENCE:
            print(f"\n  Template quality too poor (score={confidence}) — NOT saving")
            print("  Re-enroll: press finger flat and firmly each scan")
            hw.display_msg("REJECTED", f"Score:{confidence}", "Re-enroll")
            time.sleep(3)
            return None

        if confidence is not None and confidence <= FP_WARN_CONFIDENCE:
            print(f"\n  Weak template (score={confidence}) — saving with warning")
            hw.display_msg("WEAK TEMPLATE", f"Score:{confidence}", "Saved anyway")
            time.sleep(2)

        # Phase 6 — download from CharBuffer1
        # Reload from temp slot: the verify scan may have overwritten CharBuffer1
        print("\n  Downloading final template...")
        hw.display_msg("SAVING...", "Downloading")
        hw.finger.load_model(FP_TEMP_SLOT, 1)
        template = hw.finger.get_fpdata("char", 1)

        if not template:
            print("  Failed to download template")
            hw.display_msg("ERROR", "Download failed")
            time.sleep(2)
            return None

        score_str = str(confidence) if confidence is not None else "N/A"
        print(f"  Template: {len(template)} bytes  confidence: {score_str}/200")
        hw.display_msg("FP SUCCESS!", f"Score:{score_str}", "Captured")
        time.sleep(1)
        return template

    except Exception as e:
        print(f"  Fingerprint error: {e}")
        hw.display_msg("FP ERROR", str(e)[:20])
        time.sleep(2)
        return None