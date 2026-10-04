# MicroPython for Raspberry Pi Pico: READ-ONLY dump of a bq40z50 battery gauge over SMBus.
# Wiring: GP4 (pin 6) = SDA -> pack DT, GP5 (pin 7) = SCL -> pack CL, GND (pin 3/8/38) -> pack P- (black).
# Never connect pack P+ (red) or TH to the Pico.
from machine import I2C, Pin
import time

ADDR = 0x0B  # standard Smart Battery address (7-bit)

# Enable the Pico's weak internal pull-ups as a fallback; external 4.7k-10k to 3V3 is better.
Pin(4, Pin.IN, Pin.PULL_UP)
Pin(5, Pin.IN, Pin.PULL_UP)
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=20000)


def word(cmd):
    i2c.writeto(ADDR, bytes([cmd]), False)
    b = i2c.readfrom(ADDR, 2)
    return b[0] | (b[1] << 8)


def sword(cmd):
    v = word(cmd)
    return v - 0x10000 if v & 0x8000 else v


def block(cmd, maxlen=32):
    i2c.writeto(ADDR, bytes([cmd]), False)
    b = i2c.readfrom(ADDR, maxlen + 1)
    n = min(b[0], maxlen)
    return bytes(b[1:1 + n])


def mfg_block(sub):
    # ManufacturerBlockAccess (0x44): write subcommand, read back [sub_lo, sub_hi, data...]
    i2c.writeto(ADDR, bytes([0x44, 2, sub & 0xFF, sub >> 8]))
    time.sleep_ms(20)
    d = block(0x44)
    return d[2:] if len(d) >= 2 else d


def le32(d):
    v = 0
    for i, x in enumerate(d[:4]):
        v |= x << (8 * i)
    return v


def flags(v, names):
    return ' '.join(n for i, n in enumerate(names) if n and v & (1 << i)) or '-'


SAFETY = ['CUV', 'COV', 'OCC1', 'OCC2', 'OCD1', 'OCD2', 'AOLD', 'AOLDL', 'ASCC', 'ASCCL', 'ASCD', 'ASCDL',
          'OTC', 'OTD', 'CUVC', '', 'OTF', '', 'PTO', 'PTOS', 'CTO', 'CTOS', 'OC', 'CHGC', 'CHGV', '', 'UTC', 'UTD']
PF = ['SUV', 'SOV', 'SOCC', 'SOCD', 'SOT', '', 'SOTF', 'QIM', 'CB', 'IMP', 'CD', 'VIMR', 'VIMA', '', '', '',
      'CFETF', 'DFETF', 'THERM', 'FUSE', 'AFER', 'AFEC', '2LVL', 'PTC', 'IFC', '', 'DFW', '', 'TS1', 'TS2', 'TS3', 'TS4']
OPSTAT = ['PRES', 'DSG', 'CHG', 'PCHG', '', 'FUSE', '', 'BTP_INT', 'SEC0', 'SEC1', 'SDV', 'SS', 'PF', 'XDSG',
          'XCHG', 'SLEEP', 'SDM', 'LED', 'AUTH', 'AUTOCALM', 'CAL', 'CAL_OFFSET', 'XL', 'SLEEPM', 'INIT',
          'SMBLCAL', 'SLPAD', 'SLPCC', 'CB', 'EMSHUT']
CHGSTAT = ['UT', 'LT', 'STL', 'RT', 'STH', 'HT', 'OT', 'PV', 'LV', 'MV', 'HV', 'IN', 'SU', 'MCHG', 'VCT',
           'CCR', 'CVR', 'CCC', 'NCT']
BATTSTAT = ['EC0', 'EC1', 'EC2', 'EC3', 'FD', 'FC', 'DSG', 'INIT', 'RTA', 'RCA', '', 'TDA', 'OTA', '', 'TCA', 'OCA']


def show(label, fn):
    try:
        print(label, fn())
    except Exception as e:
        print(label, 'ERROR', e)


print('I2C scan:', [hex(a) for a in i2c.scan()])

show('Manufacturer      ', lambda: block(0x20))
show('Device            ', lambda: block(0x21))
show('Chemistry         ', lambda: block(0x22))
show('Serial            ', lambda: word(0x1C))
show('Pack voltage mV   ', lambda: word(0x09))
show('Current mA        ', lambda: sword(0x0A))
show('Temperature C     ', lambda: (word(0x08) - 2731) / 10)
show('RSOC %            ', lambda: word(0x0D))
show('Remaining mAh     ', lambda: word(0x0F))
show('FullCharge mAh    ', lambda: word(0x10))
show('Design mAh        ', lambda: word(0x18))
show('Design mV         ', lambda: word(0x19))
show('Cycle count       ', lambda: word(0x17))
show('Req. charge mA    ', lambda: word(0x14))
show('Req. charge mV    ', lambda: word(0x15))
show('Cell1..4 mV       ', lambda: [word(0x3F), word(0x3E), word(0x3D), word(0x3C)])


def temps():
    # DAStatus2 (0x0072): Int, TS1..TS4, Cell, FET temperatures in 0.1 K; unconnected inputs read ~-273 C
    d = mfg_block(0x0072)
    out = []
    for i, name in enumerate(('chip', 'TS1', 'TS2', 'TS3', 'TS4', 'cell', 'FET')):
        if 2 * i + 1 < len(d):
            c = ((d[2 * i] | d[2 * i + 1] << 8) - 2731) / 10
            out.append('%s %s' % (name, 'n/a' if c < -40 else '%.1f' % c))
    return '  '.join(out)


show('Temperatures C    ', temps)


def status(label, direct_cmd, sub, names):
    for how, fn in (('direct', lambda: block(direct_cmd)), ('0x44', lambda: mfg_block(sub))):
        try:
            d = fn()
            v = le32(d)
            print('%-18s 0x%08X  %s  (%s)' % (label, v, flags(v, names), how))
            return
        except Exception as e:
            err = e
    print(label, 'ERROR', err)


show('BatteryStatus     ', lambda: '0x%04X %s' % (word(0x16), flags(word(0x16), BATTSTAT)))
status('SafetyAlert', 0x50, 0x0050, SAFETY)
status('SafetyStatus', 0x51, 0x0051, SAFETY)
status('PFAlert', 0x52, 0x0052, PF)
status('PFStatus', 0x53, 0x0053, PF)
status('OperationStatus', 0x54, 0x0054, OPSTAT)
status('ChargingStatus', 0x55, 0x0055, CHGSTAT)
