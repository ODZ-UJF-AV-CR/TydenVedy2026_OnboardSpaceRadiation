#!/usr/bin/env bash
# Spuštění simulace CARI-7 pro balon flight_trajectory.csv
# Použití: bash run_simulation.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CARI_DIR="$SCRIPT_DIR/CARI_7_DVD"
BINARY="$CARI_DIR/Linux_Intel_64bit/cari-7(v4_1_3_linux_intel)"

# ── Kontrola prerekvizit ─────────────────────────────────────────────────────
if [ ! -d "$CARI_DIR" ]; then
    echo "Chyba: adresář CARI_7_DVD/ nenalezen."
    echo "Rozbal archiv cari_7exe.zip do $SCRIPT_DIR/ a zkus znovu."
    exit 1
fi

if [ ! -f "$BINARY" ]; then
    echo "Chyba: binárka CARI-7 nenalezena na cestě:"
    echo "  $BINARY"
    exit 1
fi

# ── Krok 1: Generování vstupního souboru flight.DEG ──────────────────────────
echo "=== 1/3  Generuji flight.DEG z flight_trajectory.csv ==="
python3 "$SCRIPT_DIR/csv_to_cari7.py"

# ── Krok 2: Kopírování souborů do CARI_7_DVD/ ────────────────────────────────
echo "=== 2/3  Kopíruji konfiguraci a vstup do CARI_7_DVD/ ==="
cp "$SCRIPT_DIR/CARI.INI"    "$CARI_DIR/CARI.INI"
cp "$SCRIPT_DIR/DEFAULT.INP" "$CARI_DIR/DEFAULT.INP"
cp "$SCRIPT_DIR/flight.DEG"  "$CARI_DIR/flight.DEG"

# ── Krok 3: Spuštění CARI-7 ──────────────────────────────────────────────────
echo "=== 3/3  Spouštím CARI-7 ==="
chmod +x "$BINARY"
(cd "$CARI_DIR" && "$BINARY")

# ── Zkopírování výsledků zpět ────────────────────────────────────────────────
cp "$CARI_DIR/flight.SUM" "$SCRIPT_DIR/flight.SUM"
cp "$CARI_DIR/flight.DAT" "$SCRIPT_DIR/flight.DAT"

echo ""
echo "Hotovo. Výsledky:"
echo "  flight.SUM  – celková dávka"
echo "  flight.DAT  – dávkový příkon po krocích"
echo ""
grep "TOTAL" "$SCRIPT_DIR/flight.SUM" | tail -1
