# MicroPython for Raspberry Pi Pico: checks once a second whether the bq40z50 answers on SMBus.
# READ-ONLY. Same wiring as bq40z50_read.py: GP4 = SDA -> DT (cyan), GP5 = SCL -> CL (yellow), GND -> P- (black).
from machine import I2C, Pin
import time

ADDR = 0x0B

Pin(4, Pin.IN, Pin.PULL_UP)
Pin(5, Pin.IN, Pin.PULL_UP)
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=20000)


def word(cmd):
    i2c.writeto(ADDR, bytes([cmd]), False)
    b = i2c.readfrom(ADDR, 2)
    return b[0] | (b[1] << 8)


def kelvin10_to_c(v):
    c = (v - 2731) / 10
    return None if c < -40 else c  # unconnected sensor inputs read near absolute zero


def temps():
    # DAStatus2 (0x0072) via ManufacturerBlockAccess: Int, TS1..TS4, Cell, FET (0.1 K each)
    i2c.writeto(ADDR, bytes([0x44, 2, 0x72, 0x00]))
    time.sleep_ms(20)
    i2c.writeto(ADDR, bytes([0x44]), False)
    b = i2c.readfrom(ADDR, 17)
    d = b[3:1 + b[0]]
    return [kelvin10_to_c(d[2 * i] | d[2 * i + 1] << 8) for i in range(len(d) // 2)][:7]


SAFETY = ['CUV', 'COV', 'OCC1', 'OCC2', 'OCD1', 'OCD2', 'AOLD', 'AOLDL', 'ASCC', 'ASCCL', 'ASCD', 'ASCDL',
          'OTC', 'OTD', 'CUVC', '', 'OTF', '', 'PTO', 'PTOS', 'CTO', 'CTOS', 'OC', 'CHGC', 'CHGV', '', 'UTC', 'UTD']


def block32(cmd):
    # SafetyStatus (0x51) / OperationStatus (0x54) are 4-byte SMBus block reads
    i2c.writeto(ADDR, bytes([cmd]), False)
    b = i2c.readfrom(ADDR, 5)
    return b[1] | b[2] << 8 | b[3] << 16 | b[4] << 24


def fmt(c):
    return ' n/a' if c is None else '%4.1f' % c


t0 = time.time()
last = None
print('Checking for battery chip every second. Press Ctrl+C to stop.')
while True:
    t = time.time() - t0
    try:
        present = ADDR in i2c.scan()
    except Exception:
        present = False
    if present:
        try:
            pack = word(0x09)
            cells = [word(0x3F), word(0x3E), word(0x3D), word(0x3C)]
            i2c.writeto(ADDR, bytes([0x0A]), False)
            b = i2c.readfrom(ADDR, 2)
            cur = b[0] | b[1] << 8
            cur = cur - 0x10000 if cur & 0x8000 else cur
            temp = (word(0x08) - 2731) / 10
            try:
                tt = temps()
                extra = '  cell %s  FET %s  chip %s  TS1-4 %s C' % (
                    fmt(tt[5]), fmt(tt[6]), fmt(tt[0]), '/'.join(fmt(x).strip() for x in tt[1:5]))
            except Exception:
                extra = ''
            try:
                safety = block32(0x51)
                dsg = block32(0x54) & 0x2
                names = [n for i, n in enumerate(SAFETY) if n and safety & (1 << i)]
                extra += '  safety %s  output %s' % (','.join(names) or 'none', 'ON' if dsg else 'off')
            except Exception:
                pass
            print('%5ds  OK      pack %5d mV  current %5d mA  cells %s  temp %4.1f C%s' % (
                t, pack, cur, cells, temp, extra))
        except Exception as e:
            print('%5ds  FLAKY   chip seen but read failed (%s) - check wire contact' % (t, e))
    elif last is not False:
        # only print the "no answer" message when the state changes, then a dot per second
        print('%5ds  NO ANSWER  chip silent (shut down, or DT/CL/GND not connected)' % t)
    else:
        print('.', end='')
    last = present
    time.sleep(1)
