#!/usr/bin/env python3
"""
04_length_stratified_eval.py
============================
Evaluate baseline classifiers on sequence fragments of different lengths.

Reproduces the PlasClass paper benchmark methodology:
  - Sample fixed-length fragments (1kb, 5kb, 10kb) from full sequences
  - Evaluate each classifier at each fragment length
  - Shows how performance degrades on shorter contigs (typical in real assemblies)

Usage:
    python 04_length_stratified_eval.py [--n_frags 500] [--seed 42]
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import joblib

from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score
from tqdm import tqdm

warnings.filterwarnings("ignore")

try:
    from Bio import SeqIO
except ImportError:
    raise ImportError("pip install biopython")

import importlib.util
spec = importlib.util.spec_from_file_location("baseline", str(Path(__file__).parent / "03_baseline.py"))
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)

build_kmer_vocab = baseline.build_kmer_vocab
sequence_to_kmer_vector = baseline.sequence_to_kmer_vector
extract_kmer_features = baseline.extract_kmer_features
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR    = Path("./data/raw")
RESULTS_DIR = Path("./results")
FIG_DIR     = Path("./figures")


def sample_fragments(
    fasta_path: Path,
    frag_len: int,
    n_frags: int,
    rng: np.random.Generator,
) -> list[str]:
    """
    Sample `n_frags` random fixed-length fragments from sequences in a FASTA.
    Sequences shorter than `frag_len` are skipped.
    """
    records = [r for r in SeqIO.parse(str(fasta_path), "fasta")
               if len(r.seq) >= frag_len]
    if not records:
        return []

    fragments = []
    while len(fragments) < n_frags:
        rec = records[rng.integers(0, len(records))]
        seq = str(rec.seq).upper()
        max_start = len(seq) - frag_len
        start = rng.integers(0, max_start + 1)
        fragments.append(seq[start : start + frag_len])

    return fragments


def run_length_stratified_eval(
    k: int = 5,
    n_frags: int = 500,
    frag_lengths: list[int] = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    For each fragment length, train and evaluate classifiers on sampled fragments.
    Returns a DataFrame with results.
    """
    if frag_lengths is None:
        frag_lengths = [1_000, 5_000, 10_000, 50_000]

    rng = np.random.default_rng(seed)
    vocab   = build_kmer_vocab(k, canonical=True)
    vocab_index = {km: i for i, km in enumerate(vocab)}

    plasmid_path    = DATA_DIR / "test_plasmid.fasta"
    chromosome_path = DATA_DIR / "test_chromosome.fasta"

    rows = []
    classifiers = {
        "LogReg (PlasClass-style)": LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs", random_state=seed),
        "LinearSVM (mlplasmids-style)": LinearSVC(C=1.0, max_iter=2000, random_state=seed),
        "RandomForest":               RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=seed),
        "MLP (2-layer)":              MLPClassifier(hidden_layer_sizes=(256, 128), max_iter=200,
                                                     early_stopping=True, random_state=seed),
    }

    print(f"\n{'='*60}")
    print(f"Length-stratified evaluation (k={k}, n_frags={n_frags} per class)")
    print(f"Fragment lengths: {[f'{l//1000}kb' for l in frag_lengths]}")
    print(f"{'='*60}")

    for frag_len in frag_lengths:
        frag_kb = frag_len // 1000
        print(f"\n--- Fragment length: {frag_kb}kb ---")

        plas_frags  = sample_fragments(plasmid_path,    frag_len, n_frags, rng)
        chrom_frags = sample_fragments(chromosome_path, frag_len, n_frags, rng)

        if not plas_frags or not chrom_frags:
            print(f"  [SKIP] Not enough sequences >= {frag_len} bp")
            continue

        print(f"  Sampled: {len(plas_frags)} plasmid | {len(chrom_frags)} chromosome fragments")

        # Build feature matrices for this fragment length
        def frags_to_X(frags):
            return np.vstack([
                sequence_to_kmer_vector(s, k, vocab_index) for s in frags
            ])

        X_plas  = frags_to_X(plas_frags)
        X_chrom = frags_to_X(chrom_frags)

        X = np.vstack([X_plas, X_chrom])
        y = np.array([1] * len(plas_frags) + [0] * len(chrom_frags), dtype=np.int8)

        # Use 80/20 split
        from sklearn.model_selection import train_test_split
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=seed
        )

        for clf_name, clf in classifiers.items():
            clf_fresh = type(clf)(**clf.get_params())   # fresh instance
            clf_fresh.fit(X_tr, y_tr)
            y_pred = clf_fresh.predict(X_te)

            acc = accuracy_score(y_te, y_pred)
            f1  = f1_score(y_te, y_pred, pos_label=1)
            pr  = precision_score(y_te, y_pred, pos_label=1)
            rc  = recall_score(y_te, y_pred, pos_label=1)

            print(f"  {clf_name:<35}  F1={f1:.3f}  Acc={acc:.3f}  "
                  f"Prec={pr:.3f}  Rec={rc:.3f}")
            rows.append({
                "fragment_length_bp": frag_len,
                "fragment_length_kb": frag_kb,
                "classifier": clf_name,
                "accuracy": acc,
                "f1": f1,
                "precision": pr,
                "recall": rc,
            })

    return pd.DataFrame(rows)


def plot_length_stratified(df: pd.DataFrame, out: Path) -> None:
    """Line plot: F1 vs fragment length for each classifier."""
    fig, ax = plt.subplots(figsize=(9, 5))
    colors  = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0"]
    markers = ["o", "s", "^", "D"]

    for (clf_name, group), color, marker in zip(
        df.groupby("classifier"), colors, markers
    ):
        group = group.sort_values("fragment_length_kb")
        ax.plot(
            group["fragment_length_kb"], group["f1"],
            label=clf_name, color=color, marker=marker,
            linewidth=2, markersize=7
        )

    ax.set_xlabel("Fragment length (kb)", fontsize=11)
    ax.set_ylabel("F1-score (plasmid class)", fontsize=11)
    ax.set_title(
        "F1-score vs Fragment Length\n(PlasmidHunter benchmark, k=5)",
        fontsize=13, fontweight="bold"
    )
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=9, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f"{int(x)}kb"))
    plt.tight_layout()
    path = out / "08_length_stratified_f1.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {path}")


def main(n_frags: int = 500, seed: int = 42) -> None:
    df = run_length_stratified_eval(
        k=5, n_frags=n_frags,
        frag_lengths=[1_000, 5_000, 10_000, 50_000, 100_000],
        seed=seed,
    )
    df.to_csv(RESULTS_DIR / "length_stratified_results.csv", index=False)
    print(f"\n[OK] Saved: {RESULTS_DIR}/length_stratified_results.csv")
    plot_length_stratified(df, FIG_DIR)
    print("\nDone!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_frags", type=int, default=500,
                        help="Number of fragments per class per length (default 500)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(n_frags=args.n_frags, seed=args.seed)
