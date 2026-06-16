#!/usr/bin/env python3
"""
Převod flight_trajectory.csv do formátu GPX 1.1 (trasa letu).

Opravy dat (shodně s csv_to_cari7.py):
  - Chybějící LAT/LON: lineární interpolace
  - Výška: AltBar (pokud validní) → AltGPS → interpolace
  - Outlier výšky (mimo rozsah 0–10 000 m) se interpoluje ze sousedů
  - Deduplikace po sobě jdoucích identických bodů

Čas: CSV nemá absolutní timestamp, body jsou vzorkovány po 1.5 s.
     Relativní čas se odvodí z pořadí, absolutní začátek určuje START_TIME.
     Vložení času lze vypnout přepínačem WITH_TIME.

Výstup: soubor flight.gpx v aktuálním adresáři
"""

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Konfigurace ─────────────────────────────────────────────────────────────
INPUT_CSV    = Path("../data/flight_trajectory.csv")
OUTPUT_GPX   = Path("flight.gpx")
TRACK_NAME   = "flight_trajectory"
WITH_TIME    = True                   # vložit <time> do bodů
# Známé je pouze datum letu, denní čas startu je odhad – uprav dle potřeby:
START_TIME   = datetime(2026, 6, 14, 0, 0, 0, tzinfo=timezone.utc)
SAMPLE_INTERVAL_S = 1.5               # interval vzorkování GPS [s]
ALT_MAX_M    = 10_000                 # [m] – výšky mimo tento rozsah jsou outlier
ALT_MIN_M    = 0
# ────────────────────────────────────────────────────────────────────────────


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


def xml_escape(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))


def main():
    if not INPUT_CSV.exists():
        sys.exit(f"Chyba: soubor {INPUT_CSV} nenalezen.")

    # ── Načtení CSV ──────────────────────────────────────────────────────────
    raw = []
    with open(INPUT_CSV, newline='') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            raw.append({
                'orig_idx': idx,
                'lat':     parse_float(row['LAT']),
                'lon':     parse_float(row['LON']),
                'alt_gps': parse_float(row['AltGPS']),
                'alt_bar': parse_float(row['AltBar']),
            })

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
    raw = [r for r in raw if r['lat'] is not None and r['alt'] is not None]

    # ── Deduplikace po sobě jdoucích identických bodů ────────────────────────
    points = [raw[0]]
    for r in raw[1:]:
        p = points[-1]
        if r['lat'] == p['lat'] and r['lon'] == p['lon'] and r['alt'] == p['alt']:
            continue
        points.append(r)

    print(f"Po deduplikaci: {len(points)} unikátních bodů.")

    # ── Čas bodů (z původního indexu při daném intervalu) ────────────────────
    idx0 = points[0]['orig_idx']
    for r in points:
        dt = (r['orig_idx'] - idx0) * SAMPLE_INTERVAL_S
        r['time'] = START_TIME + timedelta(seconds=dt)

    # ── Zápis GPX souboru ─────────────────────────────────────────────────────
    with open(OUTPUT_GPX, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<gpx version="1.1" creator="csv_to_gpx.py" '
                'xmlns="http://www.topografix.com/GPX/1/1">\n')
        f.write('  <metadata>\n')
        f.write(f'    <name>{xml_escape(TRACK_NAME)}</name>\n')
        if WITH_TIME:
            f.write(f'    <time>{START_TIME:%Y-%m-%dT%H:%M:%SZ}</time>\n')
        f.write('  </metadata>\n')
        f.write('  <trk>\n')
        f.write(f'    <name>{xml_escape(TRACK_NAME)}</name>\n')
        f.write('    <trkseg>\n')
        for r in points:
            f.write(f'      <trkpt lat="{r["lat"]:.7f}" lon="{r["lon"]:.7f}">\n')
            f.write(f'        <ele>{r["alt"]:.1f}</ele>\n')
            if WITH_TIME:
                f.write(f'        <time>{r["time"]:%Y-%m-%dT%H:%M:%SZ}</time>\n')
            f.write('      </trkpt>\n')
        f.write('    </trkseg>\n')
        f.write('  </trk>\n')
        f.write('</gpx>\n')

    # ── Shrnutí ───────────────────────────────────────────────────────────────
    max_alt_m = max(r['alt'] for r in points)
    min_alt_m = min(r['alt'] for r in points)
    duration  = (points[-1]['time'] - points[0]['time']).total_seconds() / 60.0
    print(f"\nVýsledek → {OUTPUT_GPX}")
    print(f"  Body:        {len(points)}")
    print(f"  Délka letu:  {duration:.1f} min")
    print(f"  Výška:       {min_alt_m:.0f} – {max_alt_m:.0f} m n.m.")


if __name__ == '__main__':
    main()
