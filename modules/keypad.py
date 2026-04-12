import time
import RPi.GPIO as GPIO
from modules.config import (I2C_ADDR, ROWS, COLS, KEYPAD, LETTERS,
                             JOYSTICK_CENTER, BackToMainMenu)
import modules.hardware as hw


def read_keypad_input(prompt, mode="NUMBER", display_line2="", show_as_password=False):
    """
    Read input from I2C 4x4 matrix keypad.

    Modes:
      NUMBER  — digits only
      ALPHA   — multi-tap letters (like old phone keypad)
      CAPS    — same as ALPHA but uppercase

    Keys:
      A  → switch to ALPHA mode
      #  → switch to NUMBER mode
      C  → toggle ALPHA / CAPS
      B  → backspace (or cancel current multi-tap preview)
      *  → clear entire input
      Joystick CENTER → confirm and return

    Returns the entered string, or None if keypad unavailable.
    """
    if not hw.KEYBOARD_AVAILABLE:
        hw.display_msg("NO KEYBOARD", "Keypad missing", "Check I2C 0x20")
        time.sleep(3)
        return None

    output          = ""
    last_key        = None
    tap_count       = 0
    last_time       = 0
    current_mode    = mode
    current_preview = ""
    flicker_state   = True
    last_flicker    = 0

    hw.bus.write_byte(I2C_ADDR, 0xFF)

    while True:
        now = time.time()

        # ── Cursor flicker ────────────────────────────────────────
        if now - last_flicker > 0.3:
            flicker_state = not flicker_state
            last_flicker  = now

        # ── Display ───────────────────────────────────────────────
        if show_as_password:
            hw.display_msg(prompt, display_line2, "*" * len(output))
        elif current_preview and flicker_state:
            _display_with_flicker(prompt, display_line2, output, current_preview)
        else:
            hw.display_msg(prompt, display_line2, output + current_preview)

        # ── Joystick CENTER = confirm ─────────────────────────────
        if GPIO.input(JOYSTICK_CENTER) == GPIO.LOW:
            if last_key and last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS":
                    ch = ch.upper()
                output += ch
                last_key = None; tap_count = 0; current_preview = ""
            if output:
                time.sleep(0.3)
                return output
            time.sleep(0.3)

        # ── Scan keypad matrix ────────────────────────────────────
        for r, row in enumerate(ROWS):
            hw.bus.write_byte(I2C_ADDR, 0xFF & ~(1 << row))
            time.sleep(0.01)
            data = hw.bus.read_byte(I2C_ADDR)

            for c, col in enumerate(COLS):
                if not (data & (1 << col)):
                    key = KEYPAD[r][c]
                    now = time.time()

                    # ── Mode switches ─────────────────────────────
                    if key == 'A':
                        if current_mode not in ("ALPHA", "CAPS") and not show_as_password:
                            current_mode = "ALPHA"
                            hw.display_msg(prompt, "ALPHA MODE", output)
                            time.sleep(0.5)

                    elif key == '#':
                        if current_mode != "NUMBER" and not show_as_password:
                            current_mode = "NUMBER"
                            hw.display_msg(prompt, "NUMBER MODE", output)
                            time.sleep(0.5)

                    elif key == 'C':
                        if current_mode == "ALPHA":
                            current_mode = "CAPS"
                            hw.display_msg(prompt, "CAPS MODE", output)
                            time.sleep(0.5)
                        elif current_mode == "CAPS":
                            current_mode = "ALPHA"
                            hw.display_msg(prompt, "ALPHA MODE", output)
                            time.sleep(0.5)

                    # ── Backspace ─────────────────────────────────
                    elif key == 'B':
                        if current_preview:
                            current_preview = ""
                            last_key = None; tap_count = 0
                        else:
                            output = output[:-1]

                    # ── Clear all ─────────────────────────────────
                    elif key == '*':
                        output = ""; last_key = None
                        tap_count = 0; current_preview = ""
                        hw.display_msg(prompt, "CLEARED", "")
                        time.sleep(0.5)

                    # ── D = universal back to main menu ───────────
                    elif key == 'D':
                        raise BackToMainMenu()

                    # ── Digit ─────────────────────────────────────
                    elif key.isdigit():
                        if current_mode == "NUMBER" or show_as_password:
                            output += key

                        elif current_mode in ("ALPHA", "CAPS") and key in LETTERS:
                            if key != last_key:
                                # Commit previous letter
                                if last_key and last_key in LETTERS:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS": ch = ch.upper()
                                    output += ch
                                last_key  = key
                                tap_count = 0
                            else:
                                # Same key — cycle through letters
                                if (now - last_time) < 1.0:
                                    tap_count += 1
                                else:
                                    ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                                    if current_mode == "CAPS": ch = ch.upper()
                                    output += ch
                                    tap_count = 0

                            ch = LETTERS[key][tap_count % len(LETTERS[key])]
                            if current_mode == "CAPS": ch = ch.upper()
                            current_preview = ch
                            last_time = now

                    time.sleep(0.3)

        # ── Auto-commit multi-tap after 1s idle ───────────────────
        if last_key and (time.time() - last_time) > 1.0:
            if last_key in LETTERS:
                ch = LETTERS[last_key][tap_count % len(LETTERS[last_key])]
                if current_mode == "CAPS": ch = ch.upper()
                output += ch
            last_key = None; tap_count = 0; current_preview = ""


def _display_with_flicker(line1, line2, line3, flicker_text):
    """Show cursor-style flicker character at end of line3."""
    from luma.core.render import canvas
    with canvas(hw.device) as draw:
        draw.rectangle(hw.device.bounding_box, outline="white")
        draw.text((5, 10), line1,  fill="white")
        draw.text((5, 28), line2,  fill="white")
        draw.text((5, 46), line3,  fill="white")
        if flicker_text:
            x_pos = 5 + len(line3) * 6
            draw.rectangle([(x_pos, 46), (x_pos + 8, 58)],
                           fill="white", outline="white")
            draw.text((x_pos + 1, 46), flicker_text, fill="black")
