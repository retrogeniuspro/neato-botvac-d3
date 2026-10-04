#!/usr/bin/env python3
"""Send commands to the Neato Botvac over its USB serial port and print the replies.
Usage: .venv/bin/python tools/neato.py GetCharger GetErr ...
       .venv/bin/python tools/neato.py --watch [seconds]   (charging log every N s, default 10)
"""
import glob
import sys
import time

import serial


def find_port():
    ports = [p for p in glob.glob('/dev/cu.usbmodem*') if 'xxxx' in p or len(glob.glob('/dev/cu.usbmodem*')) == 1]
    if not ports:
        sys.exit('Robot not found on USB (no /dev/cu.usbmodem*). Is it switched on?')
    return ports[0]


s = serial.Serial(find_port(), 115200, timeout=0.5)


def cmd(c):
    s.reset_input_buffer()
    s.write((c + '\n').encode())
    out = b''
    t = time.time()
    while time.time() - t < 3:
        d = s.read(4096)
        if d:
            out += d
            if b'\x1a' in d:
                break
        elif out:
            break
    return out.decode(errors='replace').replace('\x1a', '')


def table(c):
    return dict(l.split(',', 1) for l in cmd(c).splitlines()[1:] if ',' in l)


def pretty(reply):
    """Align the robot's comma-separated replies into columns; other lines pass through."""
    lines = [l.rstrip() for l in reply.splitlines()[1:]]  # first line echoes the command
    rows = [[f.strip() for f in l.rstrip(',').split(',')] if ',' in l else None for l in lines]
    ncols = max((len(r) for r in rows if r), default=0)
    widths = [max((len(r[i]) for r in rows if r and i < len(r)), default=0) for i in range(ncols)]
    out = []
    for l, r in zip(lines, rows):
        if r is None:
            if l.strip():
                out.append('  ' + l.strip())
        else:
            out.append('  ' + '   '.join(f.ljust(widths[i]) for i, f in enumerate(r)).rstrip())
    return '\n'.join(out)


WATCH = [  # (header, width, getter)
    ('time', 8, lambda ch, an: time.strftime('%H:%M:%S')),
    ('fuel%', 5, lambda ch, an: ch.get('FuelPercent')),
    ('charging', 8, lambda ch, an: 'yes' if ch.get('ChargingActive') == '1' else 'no'),
    ('enabled', 7, lambda ch, an: 'yes' if ch.get('ChargingEnabled') == '1' else 'no'),
    ('dock', 4, lambda ch, an: 'yes' if ch.get('ExtPwrPresent') == '1' else 'no'),
    ('V_batt', 6, lambda ch, an: ch.get('VBattV')),
    ('I_mA', 5, lambda ch, an: an.get('BatteryCurrent')),
    ('temp_C', 6, lambda ch, an: ch.get('BattTempCAvg')),
    ('V_dock', 6, lambda ch, an: ch.get('VExtV')),
    ('fault', 5, lambda ch, an: 'YES' if ch.get('BatteryFailure') == '1' else 'no'),
]

if len(sys.argv) > 1 and sys.argv[1] == '--watch':
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    header = '  '.join(h.rjust(w) for h, w, _ in WATCH)
    n = 0
    while True:
        if n % 20 == 0:
            print(header + '\n' + '-' * len(header), flush=True)
        ch = table('GetCharger')
        an = {k: v.split(',')[1] for k, v in table('GetAnalogSensors').items() if v.count(',') >= 1}
        print('  '.join(str(g(ch, an) if g(ch, an) is not None else '?').rjust(w) for _, w, g in WATCH), flush=True)
        n += 1
        time.sleep(interval)
else:
    for c in sys.argv[1:]:
        print('===== %s =====' % c)
        print(pretty(cmd(c)))
        print()
