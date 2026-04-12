import smbus
import time

bus = smbus.SMBus(1)
ADDR = 0x2d

def get_word(reg):
    try:
        low = bus.read_byte_data(ADDR, reg)
        high = bus.read_byte_data(ADDR, reg + 1)
        return (high << 8) | low
    except:
        return 0

def check_battery_health():
    # Read individual cell voltages (mV to V)
    c1 = get_word(0x30) / 1000.0
    c2 = get_word(0x32) / 1000.0
    c3 = get_word(0x34) / 1000.0
    c4 = get_word(0x36) / 1000.0
    cells = [c1, c2, c3, c4]
    
    avg_v = sum(cells) / 4
    max_diff = max(cells) - min(cells)
    
    print("\n--- Individual Battery Health ---")
    for i, v in enumerate(cells, 1):
        status = "OK"
        # If a cell is 0.1V away from the average, it's suspicious
        if abs(v - avg_v) > 0.1:
            status = "⚠️ UNBALANCED / WEAK"
        if v < 2.5:
            status = "❌ DEAD / DISCONNECTED"
            
        print(f"Battery {i}: {v:.3f}V | {status}")
    
    print(f"\nVoltage Spread: {max_diff:.3f}V")
    
    if max_diff > 0.2:
        print("CRITICAL: One or more batteries are failing. Replace the set!")
    elif max_diff > 0.05:
        print("WARNING: Batteries are becoming unbalanced.")
    else:
        print("HEALTH: All batteries are well-matched.")

try:
    while True:
        check_battery_health()
        time.sleep(5)
except KeyboardInterrupt:
    print("Exiting...")