#!/bin/bash
# Talks to a bq40z50 battery gauge through a Raspberry Pi Pico running MicroPython (see pico/).
# Usage: tools/check_battery.sh            once-a-second status line (Ctrl+C to stop)
#        tools/check_battery.sh read       one full status dump
#        tools/check_battery.sh monitor    charge log every 10 s with warnings
#        tools/check_battery.sh lifetime   lifetime / history counters
# Tip: log to a file for the watchdog:  tools/check_battery.sh > out.txt
set -e
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/mpremote ]; then
  echo "Setting up mpremote (one time)..." >&2
  python3 -m venv .venv
  .venv/bin/pip -q install mpremote pyserial
fi

case "$1" in
  read)     script=pico/bq40z50_read.py ;;
  monitor)  script=pico/bq40z50_monitor.py ;;
  lifetime) script=pico/bq40z50_lifetime.py ;;
  *)        script=pico/bq40z50_ping.py ;;
esac

if ! ls /dev/cu.usbmodem* /dev/ttyACM* >/dev/null 2>&1; then
  echo "Pico not found on USB. Plug it in (without holding BOOTSEL) and try again." >&2
  exit 1
fi

exec .venv/bin/mpremote connect auto run "$script"
