#!/usr/bin/env bash
# =============================================================================
# 01_download_data.sh
# Download PlasmidHunter benchmark dataset from Zenodo (record 10433596)
# Run this first before any Python scripts
# =============================================================================

set -euo pipefail

DATA_DIR="./data/raw"
mkdir -p "$DATA_DIR"

echo "=== Downloading PlasmidHunter benchmark dataset from Zenodo ==="
echo "Source: https://zenodo.org/records/10433596"
echo ""

# Zenodo provides direct download links per file
# We download the benchmark FASTA files used in the PlasmidHunter paper

BASE_URL="https://zenodo.org/records/10433596/files"

# These are the benchmark contig files from PlasmidHunter paper
# Contigs with known labels (plasmid / chromosome)
FILES=(
    "test_plasmid.fasta"
    "test_chromosome.fasta"
)

for f in "${FILES[@]}"; do
    if [ -f "$DATA_DIR/$f" ]; then
        echo "[SKIP] $f already exists"
    else
        echo "[DOWNLOAD] $f ..."
        curl -L -o "$DATA_DIR/$f" "$BASE_URL/$f?download=1"
        echo "[OK] $f downloaded"
    fi
done

echo ""
echo "=== Checking downloaded files ==="
for f in "${FILES[@]}"; do
    count=$(grep -c "^>" "$DATA_DIR/$f" 2>/dev/null || echo "0")
    size=$(du -sh "$DATA_DIR/$f" 2>/dev/null | cut -f1 || echo "N/A")
    echo "  $f — $count sequences, $size"
done

echo ""
echo "Done. Now run: python 02_explore_data.py"
