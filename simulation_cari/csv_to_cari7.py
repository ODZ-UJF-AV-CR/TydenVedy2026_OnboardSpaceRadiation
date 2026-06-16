#!/usr/bin/env python3
"""
Převod flight_trajectory.csv do vstupního formátu CARI-7 (*.DEG).

Opravy dat:
  - Chybějící LAT/LON (řádky 323–430): lineární interpolace
  - Outlier výšky (AltGPS mimo rozsah 0–10 000 m): interpolace ze sousedů
  - Priorita výšky: AltGPS (pokud validní) → AltBar → interpolace
  - Deduplikace po sobě jdoucích identických bodů

Výstup: soubor flight.DEG v aktuálním adresáři
"""

import csv
import sys
from pathlib import Path

# ── Konfigurace ─────────────────────────────────────────────────────────────
INPUT_CSV    = Path("../data/flight_trajectory.csv")
OUTPUT_DEG   = Path("flight.DEG")
FLIGHT_DATE  = "06/2026"      # MM/YYYY – datum letu (hlavička DEG)
FLIGHT_DATE_ISO = "2026/06/14" # yyyy/mm/dd – pro DEFAULT.INP
FLIGHT_NAME  = "flight_trajectory"
SAMPLE_HZ    = 1 / 1.5        # interval vzorkování GPS = 1.5 s
MAX_WAYPOINTS = 200           # max. počet waypointů ve výstupním souboru
ALT_MAX_M    = 10_000         # [m] – výšky mimo tento rozsah jsou outlier
ALT_MIN_M    = 0
# ────────────────────────────────────────────────────────────────────────────

METERS_TO_FEET = 3.28084


def parse_float(s):
    s = s.strip()
    return float(s) if s else None


def interpolate_column(rows, key):
    """Lineární interpolace None hodnot; krajní None se doplní kopií krajní platné hodnoty."""
    n = len(rows)
    i = 0
    while i < n:
        if rows[i][key] is None:
            j = i + 1
            while j < n and rows[j][key] is None:
                j += 1
            prev = i - 1
            if prev >= 0 and rows[prev][key] is not None and j < n:
                v0, v1 = rows[prev][key], rows[j][key]
                steps = j - prev
                for k in range(i, j):
                    t = (k - prev) / steps
                    rows[k][key] = v0 + t * (v1 - v0)
            elif prev >= 0 and rows[prev][key] is not None:
                for k in range(i, n):
                    rows[k][key] = rows[prev][key]
            elif j < n:
                for k in range(0, j):
                    rows[k][key] = rows[j][key]
            i = j
        else:
            i += 1


def decimal_to_deg_min(dd):
    d = int(abs(dd))
    m = (abs(dd) - d) * 60.0
    return d, m


def main():
    if not INPUT_CSV.exists():
        sys.exit(f"Chyba: soubor {INPUT_CSV} nenalezen.")

    # ── Načtení CSV ──────────────────────────────────────────────────────────
    raw = []
    with open(INPUT_CSV, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat     = parse_float(row['LAT'])
            lon     = parse_float(row['LON'])
            alt_gps = parse_float(row['AltGPS'])
            alt_bar = parse_float(row['AltBar'])
            raw.append({'lat': lat, 'lon': lon,
                        'alt_gps': alt_gps, 'alt_bar': alt_bar})

    print(f"Načteno {len(raw)} řádků.")

    # ── Výběr výšky: AltBar (pokud validní) → AltGPS → None ────────────────
    def pick_alt(r):
        b = r['alt_bar']
        g = r['alt_gps']
        if b is not None and ALT_MIN_M < b < ALT_MAX_M:
            return b
        if g is not None and ALT_MIN_M < g < ALT_MAX_M:
            return g
        return None

    for r in raw:
        r['alt'] = pick_alt(r)

    # ── Statistiky před opravou ───────────────────────────────────────────────
    n_miss_pos = sum(1 for r in raw if r['lat'] is None)
    n_miss_alt = sum(1 for r in raw if r['alt'] is None)
    print(f"  Chybějící LAT/LON: {n_miss_pos} řádků")
    print(f"  Nevalidní výška:   {n_miss_alt} řádků  →  interpolace...")

    # ── Interpolace ───────────────────────────────────────────────────────────
    interpolate_column(raw, 'lat')
    interpolate_column(raw, 'lon')
    interpolate_column(raw, 'alt')

    # Kontrola – nemělo by zbýt nic chybějícího
    remaining = sum(1 for r in raw if r['lat'] is None or r['alt'] is None)
    if remaining:
        print(f"  Varování: {remaining} řádků stále bez platných hodnot (odstraněny).")
    raw = [r for r in raw if r['lat'] is not None and r['alt'] is not None]

    # ── Deduplikace po sobě jdoucích identických bodů ────────────────────────
    deduped = [raw[0]]
    for i, r in enumerate(raw[1:], 1):
        p = deduped[-1]
        if r['lat'] == p['lat'] and r['lon'] == p['lon'] and r['alt'] == p['alt']:
            continue
        r['orig_idx'] = i
        deduped.append(r)
    deduped[0]['orig_idx'] = 0
    for r in deduped:
        if 'orig_idx' not in r:
            r['orig_idx'] = 0

    print(f"Po deduplikaci: {len(deduped)} unikátních bodů.")

    # ── Čas v minutách (z původního indexu při daném Hz) ─────────────────────
    t0 = deduped[0]['orig_idx'] / SAMPLE_HZ / 60.0
    for r in deduped:
        r['time_min'] = r['orig_idx'] / SAMPLE_HZ / 60.0 - t0

    # ── Podvzorkování ─────────────────────────────────────────────────────────
    if len(deduped) > MAX_WAYPOINTS:
        step = len(deduped) // MAX_WAYPOINTS
        waypoints = deduped[::step]
        if waypoints[-1] is not deduped[-1]:
            waypoints.append(deduped[-1])
    else:
        waypoints = deduped

    # ── Zápis DEG souboru ─────────────────────────────────────────────────────
    with open(OUTPUT_DEG, 'w') as f:
        f.write(f"{FLIGHT_DATE}, {FLIGHT_NAME}\n")
        f.write("DEG MIN N/S DEG MIN E/W FEET TIME(MIN)\n")
        for r in waypoints:
            lat_d, lat_m = decimal_to_deg_min(r['lat'])
            lon_d, lon_m = decimal_to_deg_min(r['lon'])
            ns = 'N' if r['lat'] >= 0 else 'S'
            ew = 'E' if r['lon'] >= 0 else 'W'
            alt_ft = r['alt'] * METERS_TO_FEET
            f.write(f"{lat_d}, {lat_m:.4f}, {ns}, {lon_d}, {lon_m:.4f}, {ew}, "
                    f"{alt_ft:.0f}, {r['time_min']:.2f}\n")

    # ── Shrnutí ───────────────────────────────────────────────────────────────
    max_alt_m  = max(r['alt'] for r in waypoints)
    total_time = waypoints[-1]['time_min']
    print(f"\nVýsledek → {OUTPUT_DEG}")
    print(f"  Waypointy:     {len(waypoints)}")
    print(f"  Délka letu:    {total_time:.1f} min")
    print(f"  Max. výška:    {max_alt_m:.0f} m  ({max_alt_m * METERS_TO_FEET:.0f} ft)")
    print(f"\nNastavení DEFAULT.INP pro tento let:")
    print(f"  Řádek 1 (datum): {FLIGHT_DATE_ISO}")
    print(f"  Řádek 5 (soubor): {OUTPUT_DEG.name}")


if __name__ == '__main__':
    main()
