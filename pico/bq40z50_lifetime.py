# MicroPython for Raspberry Pi Pico: READ-ONLY dump of the bq40z50 lifetime (history) data blocks.
# Same wiring as bq40z50_read.py. Lifetime collection may be disabled on some packs (all zeros).
from machine import I2C, Pin
import time

ADDR = 0x0B

Pin(4, Pin.IN, Pin.PULL_UP)
Pin(5, Pin.IN, Pin.PULL_UP)
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=20000)


def mfg_block(sub):
    # ManufacturerBlockAccess (0x44): write subcommand, read back [len, sub_lo, sub_hi, data...]
    i2c.writeto(ADDR, bytes([0x44, 2, sub & 0xFF, sub >> 8]))
    time.sleep_ms(30)
    i2c.writeto(ADDR, bytes([0x44]), False)
    b = i2c.readfrom(ADDR, 33)
    return bytes(b[3:1 + b[0]])


def w(d, i, signed=False):
    v = d[2 * i] | d[2 * i + 1] << 8
    return v - 65536 if signed and v & 0x8000 else v


for sub, name in ((0x0060, 'Lifetime1'), (0x0061, 'Lifetime2'), (0x0062, 'Lifetime3'),
                  (0x0063, 'Lifetime4'), (0x0064, 'Lifetime5')):
    try:
        d = mfg_block(sub)
        print('%-10s raw %s' % (name, d.hex()))
    except Exception as e:
        print(name, 'ERROR', e)

d = mfg_block(0x0060)
if len(d) >= 26:
    print('Group max mV       ', [w(d, i) for i in range(4)])
    print('Group min mV       ', [w(d, i) for i in range(4, 8)])
    print('Max delta mV       ', w(d, 8))
    print('Max charge mA      ', w(d, 9, True))
    print('Max discharge mA   ', w(d, 10, True))
d = mfg_block(0x0063)
if len(d) >= 8:
    print('COV events          %d (last at cycle %d)' % (w(d, 0), w(d, 1)))
    print('CUV events          %d (last at cycle %d)' % (w(d, 2), w(d, 3)))
