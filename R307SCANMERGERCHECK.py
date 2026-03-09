#!/usr/bin/env python3
"""
R307 Fingerprint Merge Quality Checker v2
==========================================
Fixes from v1:
  ✅ No re-upload needed — CharBuffer1 already holds merged template
  ✅ Uses store_model() directly after merge, then finger_search()
  ✅ Falls back to 1:1 compare (CharBuffer1 vs CharBuffer2) if search fails
  ✅ Resets CharBuffer2 between rejected merge attempts to avoid stale data
  ✅ Skips get_fpdata() — was returning 768 bytes with 66% zeros (adafruit quirk)

Flow:
  4-scan merge → CharBuffer1 has final template
       ↓
  store_model(TEMP_SLOT, 1) → save to sensor flash
       ↓
  Scan same finger → image_2_tz(1) → finger_search() → confidence score
       ↓
  Fallback: image_2_tz(2) → compare CharBuffer1 vs CharBuffer2 (raw 0x03 cmd)
       ↓
  Report + cleanup
"""

import serial
import time
import struct
from adafruit_fingerprint import Adafruit_Fingerprint

# ─── Configuration ────────────────────────────────────────────────────────────

SERIAL_PORT          = "/dev/ttyUSB0"
BAUD_RATE            = 57600
TEMP_SLOT            = 127
NUM_SCANS            = 4
MAX_MERGE_RETRIES    = 6

# Confidence thresholds (R307 score range: 0–200)
THRESHOLD_POOR       = 50
THRESHOLD_ACCEPTABLE = 100
THRESHOLD_GOOD       = 150

# R307 packet constants for raw Match command (0x03)
R307_ADDR            = 0xFFFFFFFF
R307_PASSWORD        = 0x00000000
START_CODE           = 0xEF01

# ─── Sensor Init ──────────────────────────────────────────────────────────────

try:
    uart   = serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=2)
    finger = Adafruit_Fingerprint(uart)
    print(f"✅ R307 connected on {SERIAL_PORT}\n")
except Exception as e:
    print(f"❌ Cannot connect to R307: {e}")
    exit(1)

# ─── Raw 1:1 Match Command (fallback) ─────────────────────────────────────────

def raw_match_buffers():
    """
    Send R307 Match command (0x03) directly over UART.
    Compares CharBuffer1 vs CharBuffer2.
    Returns match score (int) or None on error.

    Packet structure (R307 datasheet §4.8):
      EF01 | ADDR(4) | PKT_ID(01) | LEN(0003) | CMD(03) | SUM
    """
    try:
        # Build packet
        addr    = struct.pack('>I', R307_ADDR)
        pkt_id  = 0x01
        length  = 0x0003          # 2 bytes payload + 2 bytes checksum
        cmd     = 0x03            # Match command
        checksum = pkt_id + (length >> 8) + (length & 0xFF) + cmd

        packet = (
            struct.pack('>H', START_CODE) +   # EF01
            addr                            + # FFFFFFFF
            struct.pack('>B', pkt_id)       + # 01
            struct.pack('>H', length)       + # 0003
            struct.pack('>B', cmd)          + # 03
            struct.pack('>H', checksum)       # checksum
        )

        uart.reset_input_buffer()
        uart.write(packet)
        time.sleep(0.1)

        # Read response: EF01(2) + ADDR(4) + PKT_ID(1) + LEN(2) + CC(1) + SCORE(2) + SUM(2)
        response = uart.read(14)

        if len(response) < 14:
            print(f"   ⚠️  Short response: {len(response)} bytes")
            return None

        confirm_code = response[9]
        score        = struct.unpack('>H', response[10:12])[0]

        if confirm_code == 0x00:
            return score
        elif confirm_code == 0x08:
            print("   ℹ️  Buffers don't match (confirm code 0x08)")
            return 0
        else:
            print(f"   ⚠️  Match command error: {hex(confirm_code)}")
            return None

    except Exception as e:
        print(f"   ❌ Raw match error: {e}")
        return None

# ─── Helpers ──────────────────────────────────────────────────────────────────

def separator(char="─", width=60):
    print(char * width)

def wait_for_finger(prompt, timeout_sec=15):
    print(f"👆 {prompt}")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if finger.get_image() == 0:
            return True
        time.sleep(0.1)
    print("⏱️  Timeout — no finger detected")
    return False

def wait_for_removal(timeout_sec=6):
    print("   ↑ Lift finger...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if finger.get_image() != 0:
            time.sleep(0.3)
            return
        time.sleep(0.1)

def score_bar(score, max_score=200):
    if score is None:
        return "N/A"
    pct    = min(int((score / max_score) * 100), 100)
    filled = int(30 * pct / 100)
    bar    = "█" * filled + "░" * (30 - filled)
    return f"[{bar}] {pct}%  (raw={score})"

def verdict(score):
    if score is None:
        return "❓ INCONCLUSIVE"
    if score == 0:
        return "🔴 NO MATCH — template failed self-verification completely"
    if score <= THRESHOLD_POOR:
        return f"🔴 POOR ({score}) — do NOT store, re-enroll with better placement"
    if score <= THRESHOLD_ACCEPTABLE:
        return f"🟡 WEAK ({score}) — usable but may cause false rejects"
    if score <= THRESHOLD_GOOD:
        return f"🟢 GOOD ({score}) — safe to store"
    return f"✅ EXCELLENT ({score}) — perfect merge"

# ─── Phase 1: 4-Scan Merge ────────────────────────────────────────────────────

def phase1_merge():
    """
    Returns: (success: bool, merge_log: list)
    After success, CharBuffer1 holds the final merged template.
    """
    separator("═")
    print("  PHASE 1 — 4-SCAN MERGE")
    separator("═")
    merge_log = []

    # ── Scan 1 → CharBuffer1 ──
    ok = False
    for attempt in range(1, MAX_MERGE_RETRIES + 1):
        if not wait_for_finger(f"SCAN 1/{NUM_SCANS} — Place finger (attempt {attempt}/{MAX_MERGE_RETRIES})"):
            continue
        code = finger.image_2_tz(1)
        if code == 0:
            print("   ✅ Scan 1 → CharBuffer1")
            wait_for_removal()
            ok = True
            break
        print(f"   ❌ Bad image (code {hex(code)}), retry...")
        wait_for_removal()

    if not ok:
        return False, merge_log

    # ── Scans 2-4: → CharBuffer2, then merge ──
    for scan_num in range(2, NUM_SCANS + 1):
        scan_ok = False

        for attempt in range(1, MAX_MERGE_RETRIES + 1):

            if not wait_for_finger(
                f"SCAN {scan_num}/{NUM_SCANS} — Same finger (attempt {attempt}/{MAX_MERGE_RETRIES})"
            ):
                continue

            # Capture into CharBuffer2
            img_code = finger.image_2_tz(2)
            if img_code != 0:
                print(f"   ❌ Bad image (code {hex(img_code)}), retry...")
                wait_for_removal()
                time.sleep(0.5)
                continue

            # Merge CharBuffer1 + CharBuffer2
            merge_code = finger.create_model()
            merge_log.append((scan_num, attempt, merge_code))

            if merge_code == 0:
                print(f"   ✅ Scan {scan_num} merged → CharBuffer1 updated")
                wait_for_removal()
                scan_ok = True
                break

            elif merge_code == 0x0A:
                print(f"   ⚠️  REJECTED — sensor similarity gate failed (attempt {attempt})")
                print(f"      Tip: Press more firmly and align to centre of sensor")
                wait_for_removal()

                # ── KEY FIX: re-capture Scan 1 equivalent into CharBuffer1 ──
                # On repeated rejections, CharBuffer1 may have drifted.
                # Re-anchor it from a fresh scan on attempt 3+.
                if attempt >= 3:
                    print(f"   🔄 Re-anchoring CharBuffer1 (re-scan attempt {attempt})...")
                    if wait_for_finger("   Place finger to re-anchor base (attempt {attempt})"):
                        reanchor = finger.image_2_tz(1)
                        if reanchor == 0:
                            print("      ✅ CharBuffer1 re-anchored")
                        wait_for_removal()
                time.sleep(0.8)

            else:
                print(f"   ❌ Merge error {hex(merge_code)}, retry...")
                wait_for_removal()
                time.sleep(0.5)

        if not scan_ok:
            print(f"❌ Could not merge scan {scan_num} after {MAX_MERGE_RETRIES} attempts")
            return False, merge_log

    print("\n✅ All scans merged — CharBuffer1 has final template")
    return True, merge_log

# ─── Phase 2: Store + Self-Match ──────────────────────────────────────────────

def phase2_verify():
    """
    CharBuffer1 already holds the merged template.
    Store it → temp slot → scan same finger → search → get confidence.
    Falls back to raw 1:1 compare if search fails.
    Returns confidence score or None.
    """
    separator("═")
    print("  PHASE 2 — SELF-MATCH VERIFICATION")
    separator("═")

    # Store CharBuffer1 → TEMP_SLOT (no re-upload needed!)
    print(f"📥 Storing CharBuffer1 → sensor slot {TEMP_SLOT}...")
    store_code = finger.store_model(TEMP_SLOT, 1)
    if store_code != 0:
        print(f"   ❌ store_model() failed (code {hex(store_code)})")
        print("   Falling back to 1:1 buffer compare...")
        return phase2_fallback_compare()

    print(f"   ✅ Template stored in slot {TEMP_SLOT}")
    time.sleep(0.5)

    # Now scan same finger and search
    print("\n🔍 Scan the SAME finger for verification...")
    for attempt in range(1, 4):
        if not wait_for_finger(f"VERIFICATION — Same finger (attempt {attempt}/3)"):
            continue

        img_code = finger.image_2_tz(1)
        if img_code != 0:
            print(f"   ❌ Bad image (code {hex(img_code)})")
            wait_for_removal()
            continue

        search_code = finger.finger_search()
        wait_for_removal()

        if search_code == 0:
            score    = finger.confidence
            slot     = finger.finger_id
            print(f"   ✅ Match found in slot {slot} — confidence: {score}")
            return score
        else:
            print(f"   ❌ Search failed (code {hex(search_code)}) on attempt {attempt}")
            print("      Trying 1:1 buffer compare as fallback...")
            return phase2_fallback_compare()

    return None

def phase2_fallback_compare():
    """
    1:1 compare: CharBuffer1 (stored template) vs CharBuffer2 (new scan).
    Uses raw UART Match command 0x03.
    """
    print("\n🔁 FALLBACK — 1:1 Buffer Compare")

    # Load template from TEMP_SLOT back into CharBuffer1
    print(f"   Loading slot {TEMP_SLOT} → CharBuffer1...")
    load_code = finger.load_model(TEMP_SLOT, 1)
    if load_code != 0:
        print(f"   ❌ load_model failed (code {hex(load_code)})")
        return None
    print("   ✅ CharBuffer1 loaded")

    # Scan into CharBuffer2
    print("\n   Scan same finger for 1:1 compare...")
    for attempt in range(1, 4):
        if not wait_for_finger(f"   COMPARE SCAN — Same finger (attempt {attempt}/3)"):
            continue

        img_code = finger.image_2_tz(2)
        if img_code != 0:
            print(f"   ❌ Bad image (code {hex(img_code)})")
            wait_for_removal()
            continue

        # Run raw Match command
        print("   ⚙️  Running raw Match (0x03) command...")
        score = raw_match_buffers()
        wait_for_removal()

        if score is not None:
            print(f"   ✅ 1:1 match score: {score}")
            return score

    print("   ❌ 1:1 compare also failed")
    return None

# ─── Phase 3: Cleanup ─────────────────────────────────────────────────────────

def phase3_cleanup():
    try:
        code = finger.delete_model(TEMP_SLOT)
        if code == 0:
            print(f"\n🗑️  Cleaned up slot {TEMP_SLOT}")
        else:
            print(f"\n⚠️  Could not delete slot {TEMP_SLOT} (code {hex(code)}) — delete manually")
    except Exception as e:
        print(f"\n⚠️  Cleanup error: {e}")

# ─── Phase 4: Report ──────────────────────────────────────────────────────────

def phase4_report(merge_log, score):
    separator("═")
    print("  MERGE QUALITY REPORT")
    separator("═")

    # Per-scan summary
    print("\n📋 Per-Scan Merge Log:")
    last_scan = None
    for scan_num, attempt, code in merge_log:
        status = "✅ MERGED" if code == 0 else (
            "⚠️  REJECTED" if code == 0x0A else f"❌ ERROR {hex(code)}"
        )
        # Only print scan header once
        if scan_num != last_scan:
            print(f"\n   Scan {scan_num}:")
            last_scan = scan_num
        print(f"     attempt {attempt}: {status}")

    # Rejection rate
    total   = len(merge_log)
    rejects = sum(1 for _, _, c in merge_log if c == 0x0A)
    if total > 0:
        pct = rejects / total * 100
        print(f"\n   Rejection rate: {rejects}/{total} ({pct:.0f}%)")
        if pct > 50:
            print("   ⚠️  High rejection rate — sensor surface may be dirty,")
            print("       or finger placement is inconsistent")

    # Confidence
    print(f"\n🎯 Self-Match Confidence:")
    print(f"   {score_bar(score)}")
    print(f"   {verdict(score)}")

    # Recommendations
    print()
    separator()
    print("  RECOMMENDATIONS")
    separator()
    if score is None or score <= THRESHOLD_POOR:
        print("  • Clean the sensor glass with dry cloth")
        print("  • Press finger flat — avoid angled placement")
        print("  • Ensure same finger area covers sensor each scan")
        print("  • Try enrolling again in better lighting/conditions")
    elif score <= THRESHOLD_ACCEPTABLE:
        print("  • Template is borderline — re-enroll if attendance issues occur")
        print("  • Instruct user to press more firmly during enrollment")
    else:
        print("  • Template is healthy — safe to store in production DB")
    separator()

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    separator("═")
    print("  R307 FINGERPRINT MERGE QUALITY CHECKER v2")
    separator("═")
    print(f"  Port       : {SERIAL_PORT}")
    print(f"  Scans      : {NUM_SCANS}")
    print(f"  Temp slot  : {TEMP_SLOT}")
    print(f"  Thresholds : Poor≤{THRESHOLD_POOR} | Acceptable≤{THRESHOLD_ACCEPTABLE} | "
          f"Good≤{THRESHOLD_GOOD} | Excellent>{THRESHOLD_GOOD}")
    separator()
    input("\n⏎  Press Enter to begin...\n")

    # Phase 1
    success, merge_log = phase1_merge()
    if not success:
        print("\n❌ Merge phase failed — aborting")
        phase4_report(merge_log, None)
        return

    # Phase 2
    score = phase2_verify()

    # Phase 3
    phase3_cleanup()

    # Phase 4
    phase4_report(merge_log, score)

if __name__ == "__main__":
    main()