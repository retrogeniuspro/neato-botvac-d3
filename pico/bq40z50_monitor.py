# MicroPython for Raspberry Pi Pico: READ-ONLY charge monitor for a bq40z50 pack.
# Same wiring as bq40z50_read.py. Prints one line every INTERVAL seconds, plus warnings.
from machine import I2C, Pin
import time

ADDR = 0x0B
INTERVAL = 10

Pin(4, Pin.IN, Pin.PULL_UP)
Pin(5, Pin.IN, Pin.PULL_UP)
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=20000)


def word(cmd, signed=False):
    i2c.writeto(ADDR, bytes([cmd]), False)
    b = i2c.readfrom(ADDR, 2)
    v = b[0] | (b[1] << 8)
    return v - 0x10000 if signed and v & 0x8000 else v


def block32(cmd):
    i2c.writeto(ADDR, bytes([cmd]), False)
    b = i2c.readfrom(ADDR, 5)
    return b[1] | b[2] << 8 | b[3] << 16 | b[4] << 24


t0 = time.time()
start_temp = None
print('time_s  pack_mV  mA  temp_C  cell1  cell2  cell3  cell4  spread  safety  opstat  warnings')
while True:
    try:
        cells = [word(0x3F), word(0x3E), word(0x3D), word(0x3C)]
        pack = word(0x09)
        cur = word(0x0A, True)
        temp = (word(0x08) - 2731) / 10
        safety = block32(0x51)
        op = block32(0x54)
        if start_temp is None:
            start_temp = temp
        spread = max(cells) - min(cells)
        warn = []
        if temp - start_temp > 5:
            warn.append('TEMP_RISE')
        if temp > 40:
            warn.append('HOT')
        if cur > 200:
            warn.append('CURRENT_HIGH')
        if max(cells) > 4250:
            warn.append('CELL_HIGH')
        if spread > 600:
            warn.append('SPREAD_GROWING')
        if op & (1 << 12):
            warn.append('PERMANENT_FAIL')
        print('%6d  %5d  %4d  %5.1f  %5d  %5d  %5d  %5d  %5d  %08X  %08X  %s' % (
            time.time() - t0, pack, cur, temp, cells[0], cells[1], cells[2], cells[3], spread,
            safety, op, ' '.join(warn) or '-'))
    except Exception as e:
        print('%6d  read error: %s' % (time.time() - t0, e))
    time.sleep(INTERVAL)
