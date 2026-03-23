import smbus
import time
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

# --- 1. DISPLAY SETUP ---
# SPI configuration
serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
device = ssd1306(serial)

# [CRITICAL FIX] DISABLE HARDWARE SCROLLING
# This command (0x2E) forces the screen to stop moving immediately.
device.command(0x2E) 

# --- 2. UPS SETUP ---
bus = smbus.SMBus(1)
ADDR = 0x2d

def get_battery_percent():
    try:
        val = bus.read_byte_data(ADDR, 0x24)
        return max(0, min(100, val))
    except:
        return 0

def draw_static_battery(draw, percent):
    # --- STATIC COORDINATES ---
    # Top-Right Anchor Point
    ICON_X = 100
    ICON_Y = 2
    ICON_W = 24
    ICON_H = 10
    
    # 1. Draw Battery Shell (Fixed Position)
    draw.rectangle((ICON_X, ICON_Y, ICON_X + ICON_W, ICON_Y + ICON_H), outline="white", fill="black")
    draw.rectangle((ICON_X + ICON_W + 1, ICON_Y + 3, ICON_X + ICON_W + 3, ICON_Y + 7), outline="white", fill="white")
    
    # 2. Draw Fill
    # Width is calculated, but the starting X, Y is always the same
    fill_pixels = int((percent / 100.0) * (ICON_W - 2))
    if fill_pixels > 0:
        draw.rectangle((ICON_X + 2, ICON_Y + 2, ICON_X + fill_pixels, ICON_Y + ICON_H - 2), outline="white", fill="white")

    # 3. Draw Text (Right Aligned)
    # We format the string to be 3 characters wide with padding (e.g. " 95")
    # This prevents the text from shifting the layout
    text_str = f"{percent}%"
    
    # Calculate text width roughly (Standard font is approx 6px wide per char)
    # We manually set the X position so the '%' symbol lands right next to the battery
    # 100% -> x=75 | 95% -> x=81 | 5% -> x=87
    txt_w, txt_h = draw.textsize(text_str) if hasattr(draw, 'textsize') else (len(text_str)*6, 8)
    
    # Anchor the text to the left of the battery (ICON_X - 5 pixels padding - text_width)
    text_x = (ICON_X - 5) - txt_w
    
    draw.text((text_x, ICON_Y), text_str, fill="white")

# --- MAIN LOOP ---
print("Display fixed. Press CTRL+C to exit.")

try:
    while True:
        p = get_battery_percent()
        
        with canvas(device) as draw:
            draw_static_battery(draw, p)
            
        time.sleep(2)

except KeyboardInterrupt:
    device.clear()
    print("\nExiting...")