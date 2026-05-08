#!/usr/bin/env python3
"""
02_explore_data.py
==================
Exploratory Data Analysis on PlasmidHunter benchmark dataset.
Generates statistics and figures for the slide presentation.

Requirements: pip install biopython matplotlib seaborn numpy pandas
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from pathlib import Path
from collections import Counter

# ── Try to import BioPython ───────────────────────────────────────────────────
try:
    from Bio import SeqIO
    from Bio.SeqUtils import gc_fraction
except ImportError:
    print("ERROR: BioPython not installed. Run: pip install biopython")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR   = Path("./data/raw")
FIG_DIR    = Path("./figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)


def load_fasta(path: Path, label: int, label_name: str) -> pd.DataFrame:
    """Load a FASTA file and return a DataFrame with sequence statistics."""
    records = []
    for rec in SeqIO.parse(str(path), "fasta"):
        seq = str(rec.seq).upper()
        length = len(seq)
        gc = gc_fraction(seq) * 100
        n_count = seq.count("N")
        records.append({
            "seq_id": rec.id,
            "label": label,
            "label_name": label_name,
            "length": length,
            "gc_content": gc,
            "n_fraction": n_count / length if length > 0 else 0,
        })
    return pd.DataFrame(records)


def print_stats(df: pd.DataFrame) -> None:
    """Print summary statistics grouped by label."""
    print("\n" + "="*60)
    print("DATASET STATISTICS")
    print("="*60)
    for name, group in df.groupby("label_name"):
        print(f"\n[{name.upper()}]  n={len(group):,}")
        print(f"  Length  — median: {group.length.median():,.0f} bp"
              f"  |  mean: {group.length.mean():,.0f} bp"
              f"  |  min: {group.length.min():,} bp"
              f"  |  max: {group.length.max():,} bp")
        print(f"  GC (%)  — median: {group.gc_content.median():.1f}%"
              f"  |  mean: {group.gc_content.mean():.1f}%")
        print(f"  N-frac  — median: {group.n_fraction.median():.4f}")


def plot_length_distribution(df: pd.DataFrame, out: Path) -> None:
    """Histogram of sequence lengths for plasmid vs chromosome."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=False)
    colors = {"plasmid": "#2196F3", "chromosome": "#FF5722"}

    for ax, (name, group) in zip(axes, df.groupby("label_name")):
        lengths_kb = group["length"] / 1000
        ax.hist(lengths_kb, bins=60, color=colors[name], alpha=0.85,
                edgecolor="white", linewidth=0.4)
        ax.set_title(f"{name.capitalize()} (n={len(group):,})",
                     fontsize=13, fontweight="bold")
        ax.set_xlabel("Sequence length (kb)", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x:.0f}"))
        ax.spines[["top", "right"]].set_visible(False)
        med = lengths_kb.median()
        ax.axvline(med, color="black", linestyle="--", linewidth=1.2,
                   label=f"Median = {med:.1f} kb")
        ax.legend(fontsize=9)

    fig.suptitle("Sequence Length Distribution — PlasmidHunter Benchmark",
                 fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(out / "01_length_distribution.png", dpi=150,
                bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/01_length_distribution.png")


def plot_gc_distribution(df: pd.DataFrame, out: Path) -> None:
    """Overlapping density plot of GC content."""
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = {"plasmid": "#2196F3", "chromosome": "#FF5722"}

    for name, group in df.groupby("label_name"):
        group["gc_content"].plot.kde(ax=ax, label=name.capitalize(),
                                     color=colors[name], linewidth=2)

    ax.set_xlabel("GC Content (%)", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.set_title("GC Content Distribution — Plasmid vs Chromosome",
                 fontsize=13, fontweight="bold")
    ax.legend(fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(out / "02_gc_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/02_gc_distribution.png")


def plot_class_balance(df: pd.DataFrame, out: Path) -> None:
    """Bar chart showing class balance."""
    counts = df["label_name"].value_counts()
    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(counts.index, counts.values,
                  color=["#2196F3", "#FF5722"], edgecolor="white",
                  linewidth=0.5, width=0.5)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 30,
                f"{val:,}", ha="center", va="bottom", fontsize=11,
                fontweight="bold")
    ax.set_ylabel("Number of sequences", fontsize=11)
    ax.set_title("Class Balance", fontsize=13, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, counts.max() * 1.15)
    plt.tight_layout()
    plt.savefig(out / "03_class_balance.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/03_class_balance.png")


def plot_length_vs_gc(df: pd.DataFrame, out: Path) -> None:
    """Scatter plot: length vs GC content."""
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"plasmid": "#2196F3", "chromosome": "#FF5722"}
    for name, group in df.groupby("label_name"):
        sample = group.sample(min(2000, len(group)), random_state=42)
        ax.scatter(sample["length"] / 1000, sample["gc_content"],
                   label=name.capitalize(), alpha=0.3, s=8,
                   color=colors[name])
    ax.set_xlabel("Sequence length (kb)", fontsize=11)
    ax.set_ylabel("GC Content (%)", fontsize=11)
    ax.set_title("Length vs GC Content", fontsize=13, fontweight="bold")
    ax.legend(fontsize=11, markerscale=3)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(out / "04_length_vs_gc.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/04_length_vs_gc.png")


def save_stats_json(df: pd.DataFrame, out: Path) -> None:
    """Save key statistics to JSON for later reference."""
    stats = {}
    for name, group in df.groupby("label_name"):
        stats[name] = {
            "n_sequences": int(len(group)),
            "length_median_bp": float(group.length.median()),
            "length_mean_bp": float(group.length.mean()),
            "length_min_bp": int(group.length.min()),
            "length_max_bp": int(group.length.max()),
            "gc_mean": float(group.gc_content.mean()),
            "gc_std": float(group.gc_content.std()),
        }
    with open(out / "dataset_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(f"[OK] Saved: {out}/dataset_stats.json")


def main():
    plasmid_path    = DATA_DIR / "test_plasmid.fasta"
    chromosome_path = DATA_DIR / "test_chromosome.fasta"

    # ── Check files exist ──────────────────────────────────────────────────
    for p in [plasmid_path, chromosome_path]:
        if not p.exists():
            print(f"ERROR: File not found: {p}")
            print("Please run 01_download_data.sh first.")
            sys.exit(1)

    print("Loading sequences...")
    df_plasmid    = load_fasta(plasmid_path,    label=1, label_name="plasmid")
    df_chromosome = load_fasta(chromosome_path, label=0, label_name="chromosome")
    df = pd.concat([df_plasmid, df_chromosome], ignore_index=True)

    print(f"Total sequences loaded: {len(df):,}")
    print_stats(df)

    print("\n=== Generating figures ===")
    plot_length_distribution(df, FIG_DIR)
    plot_gc_distribution(df, FIG_DIR)
    plot_class_balance(df, FIG_DIR)
    plot_length_vs_gc(df, FIG_DIR)
    save_stats_json(df, FIG_DIR)

    # ── Save processed dataframe ───────────────────────────────────────────
    df.drop(columns=["seq_id"]).to_csv(
        FIG_DIR / "dataset_stats_full.csv", index=False)
    print(f"[OK] Saved: {FIG_DIR}/dataset_stats_full.csv")
    print("\nDone! Now run: python 03_baseline.py")


if __name__ == "__main__":
    main()
