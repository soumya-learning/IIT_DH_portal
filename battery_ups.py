import smbus
import time

bus = smbus.SMBus(1)
ADDR = 0x2d

def get_word(reg):
    """Read a 16-bit word from the MCU (Little-Endian)."""
    try:
        low = bus.read_byte_data(ADDR, reg)
        high = bus.read_byte_data(ADDR, reg + 1)
        return (high << 8) | low
    except:
        return 0

def read_ups_smart():
    # 1. Voltage and Current (to calculate Watts)
    voltage_mv = get_word(0x20)
    current_ma = get_word(0x22)
    
    # Handle signed 16-bit integer for current (mA)
    if current_ma > 32767:
        current_ma -= 65536
    
    # 2. Power in Watts
    watts = (voltage_mv * abs(current_ma)) / 1000000.0
    
    # 3. Percentage (Register 0x24)
    percent = bus.read_byte_data(ADDR, 0x24)
    
    # 4. Minutes Remaining (Register 0x28)
    # This value is calculated by the HAT's fuel gauge
    mins_remaining = get_word(0x28)
    
    return voltage_mv/1000.0, current_ma, watts, percent, mins_remaining

print(f"{'Voltage':<8} | {'Watts':<8} | {'Battery':<8} | {'Time Remaining'}")
print("-" * 55)

try:
    while True:
        v, ma, w, p, mins = read_ups_smart()
        
        # Format the time string
        if ma > 0:
            time_label = f"Full in {mins}m" if mins < 1000 else "Charging..."
        elif ma < 0:
            if mins > 0 and mins < 65535:
                hours = mins // 60
                m = mins % 60
                time_label = f"{hours}h {m}m left"
            else:
                time_label = "Calculating..."
        else:
            time_label = "Idle"

        print(f"{v:>6.2f}V  | {w:>6.2f}W  | {p:>6}%  | {time_label}")
        time.sleep(2)

except KeyboardInterrupt:
    print("\nExiting...")