# Repair guide: recovering a deeply discharged "smart" Li-ion pack (bq40z50) that won't charge

This guide is written for Neato Botvac D-series packs with a TI **bq40z50** gauge, but the method applies to most
"smart" Li-ion packs with an SMBus gauge and protection board (vacuum robots, power-tool and laptop-style packs).
For the full story behind it, see the [README](../README.md).

---

## ⚠️ Disclaimer and safety rules

**This is dangerous work. You do it entirely at your own risk.** Li-ion cells can overheat, vent toxic gas, catch fire or
explode. **Over-discharged cells are more dangerous to recharge than normal ones**: internal damage (copper dendrites)
can cause an internal short circuit during charging *or weeks later in normal use*. No warranty of any kind is given,
and the authors accept no liability for any damage, injury or loss. Follow local laws and recycling rules.
**If in doubt, recycle the pack and buy a new one.**

Hard rules:

1. **Never** charge unattended, on a flammable surface, or near flammable objects. Work outdoors or in a fire-safe
   container. Have an extinguisher (or a bucket of sand) at hand.
2. **Never** bypass the protection board, and never charge cells directly through the balance taps.
3. **Stop and recycle the pack** if any of these apply:
   - it is swollen, dented, leaking, smells of solvent, or gets warm on its own
   - any cell group is **below about 1.5 V**, or has sat near 0 V
   - the gauge reports **PFStatus ≠ 0** (permanent failure)
   - during pre-charge, one group **doesn't rise** while the others do, or the temperature rises by **more than 5 °C**
4. Keep the pre-charge current **low**: about 50–100 mA, or whatever the gauge requests (`ChargingCurrent`).
5. Use a **current-limiting resistor**. Never connect a charger or adapter directly to a deeply discharged pack.
6. Take the battery **out of the robot** while working on it.

---

## What you need

- Multimeter
- Raspberry Pi Pico (or Pico W), USB cable, 3 jumper wires, optionally 2 × 4.7–10 kΩ resistors
- A computer with Python 3 (macOS/Linux; the watchdog's sound alarms are macOS-only)
- A DC source that **always** outputs voltage (*not* a "smart" charger): a 12 V adapter, and/or a 15–20 V laptop adapter
- Resistors to build a current-limiting bank (any small resistors work, see the calculator below)
- Tape, insulated work surface, fire-safety equipment

---

## Step 1: Is it the robot or the battery?

1. Connect the robot's micro-USB port (under the dust bin) to the computer; switch the robot on and put it on the dock.
2. `.venv/bin/python tools/neato.py GetCharger GetAnalogSensors`
3. Interpretation:

| Observation | Likely cause |
|---|---|
| `ExtPwrPresent=0` | Dock, adapter or contacts: clean the contacts, check the dock supply |
| `ChargingActive=1` but `BatteryCurrent=0` and `VBattV` far below 12 V | **Deeply discharged pack, so continue with this guide** |
| `BatteryFailure=1` | Robot flagged the battery |
| `BatteryOverTemp=1` or odd `BattTempCAvg` | Temperature sensor or overheating |
| Charges at ~2 A | Nothing wrong with charging |

## Step 2: Measure the pack

With the battery removed:

| Measurement | Healthy | Deeply discharged |
|---|---|---|
| P+ to P− (connector red/black) | 12–16.8 V | **0 V** (output switch open) or 8–10 V |
| B+ to B− on the board (cell stack) | 12–16.8 V | 6–10 V |
| Each group (B−→B1, B1→B2, B2→B3, B3→B+) | 3.0–4.2 V | 1.5–2.5 V |

If any group is below about 1.5 V, or the groups differ wildly (for example two at 4 V and two at 0 V), **stop**: the
pack has dead cells.

## Step 3: Connect the Pico to the gauge

1. Flash MicroPython: hold **BOOTSEL**, plug the Pico in, copy the `RPI_PICO` `.uf2` from
   <https://micropython.org/download/RPI_PICO/> onto the `RPI-RP2` drive.
2. Identify CL and DT by tracing the connector wires to the pads labelled **CL** and **DT** on the board (on the
   KBSDJ01 board: yellow = CL, cyan = DT).
3. Wire it:

```
 Battery connector              Raspberry Pi Pico (USB at top)
 DT (data)   ─────────────────  GP4   pin 6
 CL (clock)  ─────────────────  GP5   pin 7
 P− (black)  ─────────────────  GND   pin 3
 P+ (red)    ── TAPE IT OFF, never connect to the Pico (8–17 V destroys it)
 TH          ── not connected
 Optional: 4.7–10 kΩ from pin 6 and from pin 7 to 3V3(OUT), pin 36
```

4. `tools/check_battery.sh`: you should see `OK` lines. Then `tools/check_battery.sh read` for the full picture.

## Step 4: Interpret the gauge

| Field | Good sign | Bad sign |
|---|---|---|
| `PFStatus` | `0`, so recoverable | Anything else: **permanent failure, so recycle** |
| `SafetyStatus` | `CUV` only: just under-voltage | Overcurrent/overtemperature flags that don't clear |
| `OperationStatus` | `CHG` set (charge allowed), `XDSG` (output off): normal in CUV | `PF` set |
| `ChargingStatus` | `LV`: pre-charge region | — |
| `Req. charge mA` | Small (e.g. 88 mA): the pre-charge current to aim for | — |
| Cell groups | Within a few hundred mV of each other, sum = pack voltage | One group far lower, or sum ≠ pack voltage (broken tap) |
| `tools/check_battery.sh lifetime` | — | Many CUV events: the pack is routinely run flat (fuel-gauge problem) |

**Gauge silent (`NO ANSWER`) and 0 V at P+/P− but about 8 V at B+/B−?** The gauge is in **shutdown**. It wakes up when
voltage is applied to P+/P− (Step 5). There is no other reset over SMBus.

**Not a bq40z50?** Other gauges (e.g. Panasonic's) answer the standard Smart Battery registers (voltage, capacity,
cycles, cell voltages), but the TI status registers will show meaningless values. Don't interpret those.

## Step 5: Pre-charge through a resistor bank

### Resistor calculator

```
I     = (V_supply − 0.5 V − V_pack) / R        0.5 V ≈ the protection MOSFET's body-diode drop
R     = (V_supply − 0.5 V − V_pack) / I_target
P_tot = I² × R                                 per resistor (n equal ones in parallel) = P_tot / n
```

Keep each resistor below about **60 %** of its rating. Examples with 0.125 W resistors:

| Supply | Bank | Current (pack 9 → 12 V) | Notes |
|---|---|---|---|
| 12 V adapter | 10 × 680 Ω parallel = 68 Ω | ~40 → ~0 mA | **Self-limiting** at ~11.6 V; safe to leave running, but can't clear CUV on its own |
| 12 V adapter | 20 × 680 Ω parallel = 34 Ω | ~75 → ~0 mA | Faster, same end point |
| 19–20 V laptop | 10 × 1.5 kΩ parallel = 150 Ω | ~65 → ~45 mA | **Not self-limiting: must be supervised and stopped** |
| 19–20 V laptop | 10 × 680 Ω parallel = 68 Ω | ~130 mA | ❌ resistors at ~90 % of rating, current too high |

Measure the finished bank with the multimeter before connecting it.

### Wiring

```
 Supply (+) ──[ resistor bank ]── P+ (red)
 Supply (−) ───────────────────── P− (black)   ← Pico GND stays here too
```

Check the supply's polarity with the multimeter first. Don't use "smart" car chargers: they see 0 V and won't start, and
their "recondition" modes send high-voltage pulses.

### Run it supervised

```bash
tools/check_battery.sh > out.txt                # terminal 1: live log
python3 tools/battery_watchdog.py out.txt       # terminal 2: alarms (macOS)
tail -f out.txt                                 # terminal 3: watch it yourself
```

Expected:

- The gauge wakes (if it was in shutdown) and current settles at the calculated value.
- All groups rise; the spread between them shrinks; the temperature stays within a couple of °C of the start.
- If the source is ≤ 12 V the current tapers towards zero around 11.5 V. Switch to a higher-voltage source with a larger
  resistor (see table) for the last stretch.

**Stop immediately** (the watchdog will alarm) when:

- `safety none  output ON` appears: **CUV cleared, which is the normal finish** (observed at exactly 3000 mV on the lowest group)
- the pack reaches 12.4 V or any group reaches 3.5 V while still on the bench supply
- any group stops rising, the temperature rises more than 5 °C, or the current exceeds about 150 mA

## Step 6: Hand over to the robot

1. Disconnect the supply and the Pico. Put the battery back in the robot and dock it.
2. `.venv/bin/python tools/neato.py --watch 60`: expect `charging yes`, about **2 A**, and a rising `V_batt`.
3. Stay nearby during this first full charge; take it off the dock if the battery goes above about 45 °C.

## Step 7: After-care and health check

- **Rest test**: when full, remove the pack, wait 12–24 h, then `tools/check_battery.sh read` again. A group that lost
  tens of mV more than the others has a self-discharging cell. Replace the pack (or that cell pair, if you are qualified).
- Do 2–3 full charge/discharge cycles so the gauge relearns capacity; expect some capacity loss after a deep discharge.
- **Keep the robot on its dock.** If it still dies away from the dock, the pack's fuel gauge is unreliable: replace it.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Pico not found on USB` | Plug in without BOOTSEL; check `ls /dev/cu.usbmodem*`; use a data-capable cable |
| Pico shows up as something other than MicroPython | Re-flash the MicroPython `.uf2` |
| `NO ANSWER`, connector 0 V, cells ~8 V | Gauge in shutdown: apply supply voltage to P+/P− |
| `NO ANSWER`, connector shows voltage | Wiring: check continuity from Pico pins 6/7/3 to the DT/CL/P− **pads**; swap CL/DT if unsure |
| `FLAKY` | Loose contact: solder or clamp the jumper wires |
| Pico drops off USB while you handle the wires | USB cable bumped, or a bare wire touched something: tape off P+ |
| Robot or smart charger won't start | Pack still in CUV (0 V at terminals): finish the pre-charge |
| Current far lower than calculated | Supply sagging, or the bank's resistance is higher than intended: measure both |
| FET temperature reads a constant offset (e.g. +9 °C) | Sensor offset on this board. Watch for a *rise*, not the absolute value |
