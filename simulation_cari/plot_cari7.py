#!/usr/bin/env python3
"""
Vizualizace výsledků simulace CARI-7.

Čte:  CARI_7_DVD/flight.DAT  – dávkový příkon a kumulativní dávka po krocích
      CARI_7_DVD/flight.DEG  – trasa letu (čas, výška)

Vykreslí:
  - horní panel:  výška [m n.m.] a dávkový příkon [µSv/h] vs. čas
  - dolní panel:  kumulativní dávka [µSv] vs. čas
"""

import re
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ── Cesty ────────────────────────────────────────────────────────────────────
DAT_FILE = Path("flight.DAT")
DEG_FILE = Path("flight.DEG")
OUT_PNG  = Path("cari7_results.png")
OUT_PNG2 = Path("cari7_dose_vs_alt.png")

FEET_TO_M = 0.3048
# ─────────────────────────────────────────────────────────────────────────────


def parse_dat(path):
    """Načte flight.DAT → seznam dict {step, dose_rate [µSv/h], total [µSv]}."""
    records = []
    with open(path) as f:
        for line in f:
            m = re.match(
                r'\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+)'
                r'\s+([\d.E+\-]+)\s+([\d.E+\-]+)',
                line
            )
            if m:
                records.append({
                    'lat':       float(m.group(1)),
                    'lon':       float(m.group(2)),
                    'depth':     float(m.group(3)),
                    'step':      int(m.group(4)),
                    'dose_rate': float(m.group(5)),   # µSv/h
                    'total':     float(m.group(6)),   # µSv
                })
    return records


def parse_deg(path):
    """Načte flight.DEG → seznam dict {time_min, alt_m} v pořadí waypointů."""
    waypoints = []
    with open(path) as f:
        lines = f.readlines()
    # Přeskočí první 2 řádky (hlavička)
    for line in lines[2:]:
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 8:
            continue
        try:
            lat_d, lat_m = float(parts[0]), float(parts[1])
            lon_d, lon_m = float(parts[3]), float(parts[4])
            alt_ft       = float(parts[6])
            time_min     = float(parts[7])
            waypoints.append({
                'lat':      lat_d + lat_m / 60,
                'lon':      lon_d + lon_m / 60,
                'alt_m':    alt_ft * FEET_TO_M,
                'time_min': time_min,
            })
        except (ValueError, IndexError):
            continue
    return waypoints


def main():
    if not DAT_FILE.exists():
        raise FileNotFoundError(f"Nenalezen {DAT_FILE} – spusť nejdřív simulaci CARI-7.")
    if not DEG_FILE.exists():
        raise FileNotFoundError(f"Nenalezen {DEG_FILE}")

    dat = parse_dat(DAT_FILE)
    deg = parse_deg(DEG_FILE)

    if not dat:
        raise ValueError("flight.DAT neobsahuje žádná data.")

    # Čas: CARI-7 produkuje ~1 krok/min → step i ≈ čas i minut
    # (DEG se použije jen pro celkovou dobu letu)
    total_flight_min = deg[-1]['time_min'] if deg else dat[-1]['step']
    n_dat = len(dat)
    time_min   = [d['step'] / n_dat * total_flight_min for d in dat]

    # Výška z DEPTH (tlak hPa) pomocí standardní atmosféry, kalibrovaná na
    # první bod (ground_depth → ground_alt ze souboru DEG)
    ground_depth = dat[0]['depth']          # hPa na zemi
    ground_alt_m = deg[0]['alt_m']          # m n.m. na startu
    def depth_to_alt(depth_hpa):
        """Standardní barometrická formule (ISA), offset na skutečnou výšku startu."""
        import math
        h_isa  = lambda p: 44330.0 * (1.0 - (p / 1013.25) ** 0.1902)
        return h_isa(depth_hpa) - h_isa(ground_depth) + ground_alt_m

    alt_m      = [depth_to_alt(d['depth'])  for d in dat]
    dose_rate  = [d['dose_rate']            for d in dat]   # µSv/h
    total_dose = [d['total']                for d in dat]   # µSv

    total_final = dat[-1]['total']
    max_alt     = max(alt_m)
    max_dr      = max(dose_rate)

    # ── Graf ─────────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                   gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle(
        f"CARI-7  |  Let 16. 6. 2026, 10:00 SELČ  |  Celková dávka: {total_final*1000:.2f} nSv",
        fontsize=13, fontweight='bold'
    )

    # — Horní panel: výška + dávkový příkon ——————————————————————————————————
    color_alt = '#2196F3'
    color_dr  = '#E53935'

    ax1.fill_between(time_min, alt_m, alpha=0.18, color=color_alt)
    l1, = ax1.plot(time_min, alt_m, color=color_alt, linewidth=1.8,
                   label='Výška [m n.m.]')
    ax1.set_ylabel('Výška [m n.m.]', color=color_alt)
    ax1.tick_params(axis='y', labelcolor=color_alt)
    ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    ax1r = ax1.twinx()
    l2, = ax1r.plot(time_min, [d * 1000 for d in dose_rate],
                    color=color_dr, linewidth=1.8, linestyle='--',
                    label='Dávkový příkon [nSv/h]')
    ax1r.set_ylabel('Dávkový příkon [nSv/h]', color=color_dr)
    ax1r.tick_params(axis='y', labelcolor=color_dr)

    ax1.annotate(f'max {max_alt:.0f} m', xy=(time_min[alt_m.index(max_alt)], max_alt),
                 xytext=(8, 8), textcoords='offset points',
                 fontsize=8, color=color_alt)
    ax1r.annotate(f'max {max_dr*1000:.0f} nSv/h',
                  xy=(time_min[dose_rate.index(max_dr)], max_dr * 1000),
                  xytext=(8, -14), textcoords='offset points',
                  fontsize=8, color=color_dr)

    lines = [l1, l2]
    ax1.legend(lines, [l.get_label() for l in lines], loc='upper right', fontsize=9)
    ax1.grid(True, alpha=0.3)

    # — Dolní panel: kumulativní dávka ————————————————————————————————————————
    color_td = '#388E3C'
    ax2.fill_between(time_min, [d * 1000 for d in total_dose],
                     alpha=0.2, color=color_td)
    ax2.plot(time_min, [d * 1000 for d in total_dose],
             color=color_td, linewidth=1.8, label='Kumulativní dávka [nSv]')
    ax2.axhline(total_final * 1000, color=color_td, linestyle=':', linewidth=1,
                alpha=0.6)
    ax2.text(time_min[-1] * 0.02, total_final * 1000 * 1.05,
             f'{total_final*1000:.2f} nSv celkem', fontsize=9, color=color_td)
    ax2.set_ylabel('Kumulativní dávka [nSv]', color=color_td)
    ax2.set_xlabel('Čas od startu [min]')
    ax2.tick_params(axis='y', labelcolor=color_td)
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(OUT_PNG, dpi=150, bbox_inches='tight')
    print(f"Graf uložen: {OUT_PNG}")
    plt.show()

    # ── Graf 2: výška (Y) vs. dávkový příkon (X) ──────────────────────────
    fig2, ax = plt.subplots(figsize=(6, 8))

    dr_nsvh = [d * 1000 for d in dose_rate]

    # Rozdělíme na stoupání / sestup podle průběhu výšky
    peak_idx = alt_m.index(max(alt_m))
    ax.scatter(dr_nsvh[:peak_idx+1], alt_m[:peak_idx+1],
               color='#1565C0', s=40, label='Stoupání', zorder=3)
    ax.scatter(dr_nsvh[peak_idx:], alt_m[peak_idx:],
               color='#B71C1C', s=40, label='Sestup', zorder=3)
    ax.plot(dr_nsvh[:peak_idx+1], alt_m[:peak_idx+1],
            color='#1565C0', linewidth=1.2, alpha=0.5)
    ax.plot(dr_nsvh[peak_idx:], alt_m[peak_idx:],
            color='#B71C1C', linewidth=1.2, alpha=0.5)

    ax.set_xlabel('Dávkový příkon [nSv/h]', fontsize=11)
    ax.set_ylabel('Výška [m n.m.]', fontsize=11)
    ax.set_title('Závislost dávkového příkonu na výšce\n'
                 'CARI-7  |  Let 16. 6. 2026', fontsize=12, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    fig2.tight_layout()
    fig2.savefig(OUT_PNG2, dpi=150, bbox_inches='tight')
    print(f"Graf uložen: {OUT_PNG2}")
    plt.show()


if __name__ == '__main__':
    main()
