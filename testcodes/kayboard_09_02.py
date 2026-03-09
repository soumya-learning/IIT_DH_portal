import smbus
import time

I2C_ADDR = 0x20
bus = smbus.SMBus(1)

ROWS = [4, 5, 6, 7]
COLS = [0, 1, 2, 3]

KEYPAD = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

# Letter mapping starting from 1
letters = {
    '1': ['a', 'b', 'c'],
    '2': ['d', 'e', 'f'],
    '3': ['g', 'h', 'i'],
    '4': ['j', 'k', 'l'],
    '5': ['m', 'n', 'o'],
    '6': ['p', 'q', 'r'],
    '7': ['s','t', 'u'],
    '8': ['v','w', 'x'],
    '9': ['y', 'z']
}

mode = "NUMBER"   # NUMBER, ALPHA, CAPS
last_key = None
tap_count = 0
last_time = 0
output = ""

def write_pcf(val):
    bus.write_byte(I2C_ADDR, val)

def read_pcf():
    return bus.read_byte(I2C_ADDR)

def confirm_letter():
    global last_key, tap_count, output
    if last_key in letters:
        ch = letters[last_key][tap_count % len(letters[last_key])]
        if mode == "CAPS":
            ch = ch.upper()
        output += ch
        print("Output:", output)
    last_key = None
    tap_count = 0

print("Mode: NUMBER")
write_pcf(0xFF)

while True:
    for r, row in enumerate(ROWS):
        write_pcf(0xFF & ~(1 << row))
        time.sleep(0.01)
        data = read_pcf()

        for c, col in enumerate(COLS):
            if not (data & (1 << col)):
                key = KEYPAD[r][c]
                now = time.time()

                if key == 'A' and mode == "NUMBER":
                    mode = "ALPHA"
                    print("-- ALPHABET MODE (lowercase) --")

                elif key == 'C' and mode == "ALPHA":
                    mode = "CAPS"
                    print("-- CAPS LOCK ON --")

                elif key == '#':
                    confirm_letter()
                    if mode == "CAPS":
                        mode = "ALPHA"
                        print("-- CAPS LOCK OFF (still alphabets) --")
                    elif mode == "ALPHA":
                        mode = "NUMBER"
                        print("-- NUMBER MODE --")

                elif key == 'B':
                    output = output[:-1]
                    print("Output:", output)

                elif key == '*':
                    output = ""
                    print("Output cleared")

                elif mode == "NUMBER" and key.isdigit():
                    output += key
                    print("Output:", output)

                elif mode in ["ALPHA", "CAPS"] and key in letters:
                    if key == last_key and (now - last_time) < 0.8:
                        tap_count += 1
                    else:
                        confirm_letter()
                        last_key = key
                        tap_count = 0
                    last_time = now

                time.sleep(0.3)

    if last_key and (time.time() - last_time) > 0.8:
        confirm_letter()
