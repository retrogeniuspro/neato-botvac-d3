#!/usr/bin/env python3
"""Watchdog for the bq40z50 pre-charge: follows out.txt (output of ./check_battery.sh) and
plays sounds / speaks alerts on macOS (afplay, say, osascript) when something looks wrong.

Usage: python3 tools/battery_watchdog.py [out.txt]      Ctrl+C to stop.
Read-only: it only reads the log file, it never touches the Pico or the battery.
"""
import os
import re
import subprocess
import sys
import time
from collections import deque

LOG = sys.argv[1] if len(sys.argv) > 1 else 'out.txt'

# --- thresholds ---------------------------------------------------------------
CELL_TEMP_MAX = 40.0       # C absolute
CELL_TEMP_RISE = 5.0       # C above baseline
FET_TEMP_MAX = 50.0        # C absolute
FET_TEMP_RISE = 10.0       # C above baseline
GROUP_MV_MAX = 4250        # any cell group
CURRENT_MAX = 150          # mA; expected ~30-90 with the 68 ohm bank
CURRENT_DISCHARGE = -20    # mA; pack being drained instead of charged
GROUP_DROP_MV = 30         # a group falling this far below its peak while charging
SPREAD_MAX = 300           # mV between highest and lowest group
SILENT_SECS = 30           # chip NO ANSWER / FLAKY for this long
STALE_SECS = 30            # log file not updated for this long
CUV_CLEAR_MV = 3000        # milestone: every group at/above this
# 19 V supervised pre-charge: stop points (alarm repeats while current still flows)
STOP_PACK_MV = 12400       # pack voltage
STOP_GROUP_MV = 3500       # any single group
STALL_MA = 10              # milestone: current tapered off

LINE = re.compile(
    r'^\s*(\d+)s\s+OK\s+pack\s+(\d+) mV\s+current\s+(-?\d+) mA\s+cells \[([\d, ]+)\]\s+temp\s+(-?[\d.]+) C'
    r'(?:\s+cell\s+(\S+)\s+FET\s+(\S+))?')

SOUNDS = {'critical': '/System/Library/Sounds/Sosumi.aiff',
          'warning': '/System/Library/Sounds/Funk.aiff',
          'info': '/System/Library/Sounds/Glass.aiff'}
REPEAT = {'critical': 15, 'warning': 120, 'info': None}  # seconds between repeats; None = once


def alert(level, key, text, state):
    now = time.time()
    last = state['alerted'].get(key)
    if last is not None and (REPEAT[level] is None or now - last < REPEAT[level]):
        return
    state['alerted'][key] = now
    print('%s  %-8s %s' % (time.strftime('%H:%M:%S'), level.upper(), text), flush=True)
    subprocess.Popen(['afplay', SOUNDS[level]])
    subprocess.Popen(['say', text])
    if level == 'critical':
        subprocess.Popen(['osascript', '-e', 'display notification "%s" with title "Battery CRITICAL" sound name "Sosumi"' % text])


def clear(key, state):
    state['alerted'].pop(key, None)


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def check(m, state):
    pack, cur = int(m.group(2)), int(m.group(3))
    cells = [int(x) for x in m.group(4).split(',')]
    temp = float(m.group(5))
    fet = num(m.group(7))

    base = state['baseline']
    if base is None:
        state['samples'].append((temp, fet))
        if len(state['samples']) >= 10:
            temps = sorted(t for t, _ in state['samples'])
            fets = sorted(f for _, f in state['samples'] if f is not None)
            state['baseline'] = base = (temps[len(temps) // 2], fets[len(fets) // 2] if fets else None)
            print('baseline: cell %.1f C, FET %s C' % (base[0], base[1]), flush=True)

    state['peaks'] = [max(p, c) for p, c in zip(state['peaks'], cells)] if state['peaks'] else cells[:]
    spread = max(cells) - min(cells)

    sm = re.search(r'safety (\S+)', m.string)
    safety = sm.group(1) if sm else None
    if safety and 'CUV' in safety:
        state['saw_cuv'] = True
    charging = cur > 5

    conds = [
        ('critical', 'stop_cleared', charging and state.get('saw_cuv') and safety == 'none',
         'Protection cleared. Disconnect the power supply now.'),
        ('critical', 'stop_pack', charging and pack >= STOP_PACK_MV,
         'Pack reached %.1f volts. Disconnect the power supply now.' % (pack / 1000)),
        ('critical', 'stop_group', charging and max(cells) >= STOP_GROUP_MV,
         'A cell group reached %.2f volts. Disconnect the power supply now.' % (max(cells) / 1000)),
        ('critical', 'cell_hot', temp > CELL_TEMP_MAX, 'Battery temperature %.0f degrees. Disconnect charger.' % temp),
        ('critical', 'cell_rise', base is not None and temp - base[0] > CELL_TEMP_RISE,
         'Battery heating up, %.1f degrees above start. Disconnect charger.' % (temp - (base or (temp,))[0])),
        ('critical', 'fet_hot', fet is not None and fet > FET_TEMP_MAX, 'Protection switch temperature %.0f degrees. Disconnect charger.' % (fet or 0)),
        ('critical', 'fet_rise', fet is not None and base is not None and base[1] is not None and fet - base[1] > FET_TEMP_RISE,
         'Protection switch heating up. Disconnect charger.'),
        ('critical', 'group_high', max(cells) > GROUP_MV_MAX, 'Cell group over voltage, %d millivolts. Disconnect charger.' % max(cells)),
        ('critical', 'current_high', cur > CURRENT_MAX, 'Charge current too high, %d milliamps. Disconnect charger.' % cur),
        ('warning', 'discharging', cur < CURRENT_DISCHARGE, 'Battery is discharging, %d milliamps. Check the charger.' % cur),
        ('warning', 'group_drop', cur > 5 and any(p - c > GROUP_DROP_MV for p, c in zip(state['peaks'], cells)),
         'A cell group voltage is falling while charging. Possible bad cell.'),
        ('warning', 'spread', spread > SPREAD_MAX, 'Cell groups out of balance by %d millivolts.' % spread),
        ('info', 'cuv_clear', min(cells) >= CUV_CLEAR_MV, 'All cell groups above 3 volts. Protection should clear.'),
        ('info', 'tapered', cur < STALL_MA and pack > 11000, 'Charge current has tapered off at %.1f volts.' % (pack / 1000)),
    ]
    for level, key, bad, text in conds:
        if bad:
            alert(level, key, text, state)
        elif level != 'info':
            clear(key, state)

    now = time.time()
    if now - state['last_summary'] >= 60:
        state['last_summary'] = now
        print('%s  status   pack %5d mV  %3d mA  groups %s  spread %3d mV  temp %.1f C  FET %s C  safety %s' % (
            time.strftime('%H:%M:%S'), pack, cur, cells, spread, temp, m.group(7) or '?', safety or '?'), flush=True)


def main():
    state = {'alerted': {}, 'baseline': None, 'samples': [], 'peaks': None, 'last_summary': 0}
    print('Watching %s  (Ctrl+C to stop)' % LOG, flush=True)
    subprocess.Popen(['say', 'Battery watchdog started'])

    while not os.path.exists(LOG):
        alert('warning', 'nolog', 'Log file not found.', state)
        time.sleep(2)

    f = open(LOG, 'rb')
    # prime the baseline from the last lines already in the file, then follow new lines
    for raw in deque(f, maxlen=20):
        m = LINE.match(raw.decode(errors='replace'))
        if m:
            check(m, state)
    pos = f.tell()
    silent_since = None
    last_data = time.time()

    while True:
        size = os.path.getsize(LOG)
        if size < pos:  # file was truncated / restarted
            print('log restarted', flush=True)
            f.seek(0)
        raw = f.readline()
        line = raw.decode(errors='replace')
        if not raw:
            pos = f.tell()
            if time.time() - last_data > STALE_SECS:
                alert('warning', 'stale', 'Battery log has stopped updating.', state)
            time.sleep(0.5)
            continue
        if not line.endswith('\n'):  # partial line, wait for the rest
            f.seek(f.tell() - len(raw))
            # the ping script prints one dot per second (no newline) while the chip is silent
            if line.strip().strip('.') == '' or 'NO ANSWER' in line:
                silent_since = silent_since or time.time()
                if time.time() - silent_since > SILENT_SECS:
                    alert('warning', 'silent', 'Battery chip is not answering. Charger may be disconnected.', state)
            elif time.time() - last_data > STALE_SECS:
                alert('warning', 'stale', 'Battery log has stopped updating.', state)
            time.sleep(0.5)
            continue
        last_data = time.time()
        clear('stale', state)

        m = LINE.match(line)
        if m:
            silent_since = None
            clear('silent', state)
            check(m, state)
        elif 'NO ANSWER' in line or 'FLAKY' in line or line.strip().strip('.') == '':
            silent_since = silent_since or time.time()
            if time.time() - silent_since > SILENT_SECS:
                alert('warning', 'silent', 'Battery chip is not answering. Charger may be disconnected.', state)
        pos = f.tell()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
