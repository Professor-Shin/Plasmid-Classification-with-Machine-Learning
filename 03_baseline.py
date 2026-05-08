#!/usr/bin/env python3
"""
03_baseline.py
==============
Baseline plasmid classification using k-mer frequency features.

Reproduces the approach from:
  • PlasClass  (Pellow et al., 2020) — k-mer + Logistic Regression
  • mlplasmids (Arredondo-Alonso et al., 2018) — 5-mer + SVM (multi-species reimplementation in Python)

Evaluated on:
  • PlasmidHunter benchmark dataset (Tian et al., 2024)
    Zenodo: https://zenodo.org/records/10433596

Usage:
    python 03_baseline.py [--k 5] [--subsample 0] [--seed 42]

Requirements:
    pip install biopython scikit-learn numpy pandas matplotlib seaborn tqdm joblib
"""

import argparse
import time
import json
import warnings
from pathlib import Path
from itertools import product
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from tqdm import tqdm
import joblib

from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import normalize
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    roc_auc_score, confusion_matrix, classification_report,
    ConfusionMatrixDisplay,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

try:
    from Bio import SeqIO
except ImportError:
    raise ImportError("pip install biopython")

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR    = Path("./data/raw")
MODEL_DIR   = Path("./models")
RESULTS_DIR = Path("./results")
FIG_DIR     = Path("./figures")
for d in [MODEL_DIR, RESULTS_DIR, FIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ═════════════════════════════════════════════════════════════════════════════
# 1. K-mer Feature Extraction
# ═════════════════════════════════════════════════════════════════════════════

def _canonical(kmer: str) -> str:
    """Return the lexicographically smaller of kmer and its reverse complement."""
    comp = str.maketrans("ACGT", "TGCA")
    rc = kmer.translate(comp)[::-1]
    return min(kmer, rc)


def build_kmer_vocab(k: int, canonical: bool = True) -> list[str]:
    """Build sorted list of (canonical) k-mer strings."""
    bases = "ACGT"
    all_kmers = ["".join(p) for p in product(bases, repeat=k)]
    if canonical:
        vocab = sorted(set(_canonical(km) for km in all_kmers))
    else:
        vocab = sorted(all_kmers)
    return vocab


def sequence_to_kmer_vector(
    seq: str,
    k: int,
    vocab_index: dict[str, int],
    canonical: bool = True,
    normalize_counts: bool = True,
) -> np.ndarray:
    """
    Convert a DNA sequence to a k-mer frequency vector.

    Args:
        seq:              DNA string (uppercase expected)
        k:                k-mer length
        vocab_index:      dict mapping k-mer string → column index
        canonical:        use canonical k-mers (counts both strands once)
        normalize_counts: L1-normalize the frequency vector

    Returns:
        1-D numpy array of shape (len(vocab_index),)
    """
    seq = seq.upper()
    vec = np.zeros(len(vocab_index), dtype=np.float32)
    n = len(seq)
    if n < k:
        return vec

    for i in range(n - k + 1):
        kmer = seq[i : i + k]
        if "N" in kmer:          # skip ambiguous bases
            continue
        key = _canonical(kmer) if canonical else kmer
        idx = vocab_index.get(key)
        if idx is not None:
            vec[idx] += 1.0

    if normalize_counts and vec.sum() > 0:
        vec /= vec.sum()

    return vec


def extract_kmer_features(
    fasta_path: Path,
    k: int,
    vocab_index: dict[str, int],
    label: int,
    subsample: int = 0,
    desc: str = "",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Load FASTA and extract k-mer feature matrix.

    Args:
        subsample: if > 0, randomly subsample this many sequences

    Returns:
        X: np.ndarray shape (n_sequences, n_kmers)
        y: np.ndarray shape (n_sequences,)  filled with `label`
    """
    records = list(SeqIO.parse(str(fasta_path), "fasta"))

    if subsample > 0 and subsample < len(records):
        rng = np.random.default_rng(42)
        indices = rng.choice(len(records), size=subsample, replace=False)
        records = [records[i] for i in indices]

    X_list = []
    for rec in tqdm(records, desc=desc or fasta_path.name, leave=False):
        vec = sequence_to_kmer_vector(str(rec.seq), k, vocab_index)
        X_list.append(vec)

    X = np.vstack(X_list)
    y = np.full(len(X_list), label, dtype=np.int8)
    return X, y


# ═════════════════════════════════════════════════════════════════════════════
# 2. Model Definitions
# ═════════════════════════════════════════════════════════════════════════════

def get_classifiers() -> dict:
    """
    Return a dict of sklearn-compatible classifiers to benchmark.

    Baseline 1 — PlasClass-style:
        Logistic Regression on k-mer frequency (Pellow et al., 2020)

    Baseline 2 — mlplasmids-style:
        Linear SVM on pentamer (5-mer) frequency (Arredondo-Alonso et al., 2018)
        Here reimplemented in Python (original is R package).

    Additional baselines for comparison:
        Random Forest, MLP
    """
    return {
        "LogisticRegression\n(PlasClass-style)": LogisticRegression(
            C=1.0, max_iter=1000, solver="lbfgs", n_jobs=-1, random_state=42
        ),
        "LinearSVM\n(mlplasmids-style)": LinearSVC(
            C=1.0, max_iter=2000, random_state=42
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200, max_depth=None, n_jobs=-1, random_state=42
        ),
        "MLP\n(2-layer)": MLPClassifier(
            hidden_layer_sizes=(256, 128),
            activation="relu",
            max_iter=200,
            early_stopping=True,
            validation_fraction=0.1,
            random_state=42,
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. Evaluation
# ═════════════════════════════════════════════════════════════════════════════

def evaluate_classifier(
    clf,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    clf_name: str,
) -> dict:
    """Train and evaluate a single classifier. Returns metrics dict."""
    t0 = time.perf_counter()
    clf.fit(X_train, y_train)
    train_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    y_pred = clf.predict(X_test)
    infer_time = time.perf_counter() - t1

    # Try to get probability estimates for AUC
    auc = None
    if hasattr(clf, "predict_proba"):
        y_prob = clf.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)
    elif hasattr(clf, "decision_function"):
        y_score = clf.decision_function(X_test)
        auc = roc_auc_score(y_test, y_score)

    metrics = {
        "classifier": clf_name.replace("\n", " "),
        "accuracy":   accuracy_score(y_test, y_pred),
        "f1":         f1_score(y_test, y_pred, pos_label=1),
        "precision":  precision_score(y_test, y_pred, pos_label=1),
        "recall":     recall_score(y_test, y_pred, pos_label=1),
        "auc":        auc,
        "train_time_s": train_time,
        "infer_time_s": infer_time,
        "cm":         confusion_matrix(y_test, y_pred),
    }
    return metrics


def cross_validate_classifier(
    clf,
    X: np.ndarray,
    y: np.ndarray,
    cv: int = 5,
    clf_name: str = "",
) -> dict:
    """5-fold cross-validation wrapper."""
    scoring = ["accuracy", "f1", "precision", "recall", "roc_auc"]
    scores = cross_validate(
        clf, X, y, cv=StratifiedKFold(cv, shuffle=True, random_state=42),
        scoring=scoring, n_jobs=-1, return_train_score=False,
    )
    return {
        "classifier": clf_name.replace("\n", " "),
        "cv_accuracy_mean":  scores["test_accuracy"].mean(),
        "cv_accuracy_std":   scores["test_accuracy"].std(),
        "cv_f1_mean":        scores["test_f1"].mean(),
        "cv_f1_std":         scores["test_f1"].std(),
        "cv_precision_mean": scores["test_precision"].mean(),
        "cv_recall_mean":    scores["test_recall"].mean(),
        "cv_auc_mean":       scores["test_roc_auc"].mean(),
        "cv_auc_std":        scores["test_roc_auc"].std(),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 4. Plotting
# ═════════════════════════════════════════════════════════════════════════════

def plot_confusion_matrices(
    cms: list[tuple[str, np.ndarray]], out: Path
) -> None:
    """Grid of confusion matrices for all classifiers."""
    n = len(cms)
    ncols = min(n, 2)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(6 * ncols, 5 * nrows))
    axes = np.array(axes).flatten()

    for ax, (name, cm) in zip(axes, cms):
        disp = ConfusionMatrixDisplay(cm, display_labels=["Chromosome", "Plasmid"])
        disp.plot(ax=ax, colorbar=False, cmap="Blues")
        ax.set_title(name.replace("\n", " "), fontsize=11, fontweight="bold")

    for ax in axes[len(cms):]:
        ax.set_visible(False)

    fig.suptitle("Confusion Matrices — Baseline Classifiers",
                 fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(out / "05_confusion_matrices.png", dpi=150,
                bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/05_confusion_matrices.png")


def plot_metrics_comparison(results: list[dict], out: Path) -> None:
    """Grouped bar chart comparing all classifiers on key metrics."""
    metrics_to_plot = ["accuracy", "f1", "precision", "recall"]
    labels = [r["classifier"] for r in results]
    x = np.arange(len(labels))
    width = 0.18
    colors = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63"]

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (metric, color) in enumerate(zip(metrics_to_plot, colors)):
        vals = [r[metric] for r in results]
        bars = ax.bar(x + (i - 1.5) * width, vals, width,
                      label=metric.capitalize(), color=color,
                      alpha=0.85, edgecolor="white")
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.005,
                    f"{h:.3f}", ha="center", va="bottom", fontsize=7.5,
                    rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title(
        "Baseline Classifier Performance — PlasmidHunter Benchmark",
        fontsize=13, fontweight="bold"
    )
    ax.legend(loc="lower right", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.axhline(0.9, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.text(len(labels) - 0.4, 0.91, "0.9 target", fontsize=9, color="gray")
    plt.tight_layout()
    plt.savefig(out / "06_metrics_comparison.png", dpi=150,
                bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/06_metrics_comparison.png")


def plot_kmer_importance(
    clf, vocab: list[str], top_n: int = 30, out: Path = FIG_DIR
) -> None:
    """
    Plot most discriminative k-mers (LogisticRegression coefficients).
    Only works for LR; skip silently for others.
    """
    if not hasattr(clf, "coef_"):
        return
    coefs = clf.coef_[0]
    idx_sorted = np.argsort(np.abs(coefs))[::-1][:top_n]
    top_kmers = [vocab[i] for i in idx_sorted]
    top_coefs = coefs[idx_sorted]

    colors = ["#2196F3" if c > 0 else "#FF5722" for c in top_coefs]
    fig, ax = plt.subplots(figsize=(8, 8))
    bars = ax.barh(range(top_n), top_coefs[np.argsort(top_coefs)],
                   color=[colors[i] for i in np.argsort(top_coefs)])
    ax.set_yticks(range(top_n))
    ax.set_yticklabels(
        [top_kmers[i] for i in np.argsort(top_coefs)], fontsize=8,
        fontfamily="monospace"
    )
    ax.set_xlabel("Logistic Regression Coefficient", fontsize=11)
    ax.set_title(f"Top-{top_n} Most Discriminative k-mers\n"
                 "(blue = plasmid signal, red = chromosome signal)",
                 fontsize=12)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(out / "07_kmer_importance.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Saved: {out}/07_kmer_importance.png")


# ═════════════════════════════════════════════════════════════════════════════
# 5. Main
# ═════════════════════════════════════════════════════════════════════════════

def main(k: int = 5, subsample: int = 0, seed: int = 42) -> None:
    np.random.seed(seed)

    plasmid_path    = DATA_DIR / "test_plasmid.fasta"
    chromosome_path = DATA_DIR / "test_chromosome.fasta"

    for p in [plasmid_path, chromosome_path]:
        if not p.exists():
            raise FileNotFoundError(
                f"File not found: {p}\n"
                "Please run 01_download_data.sh first."
            )

    # ── Build k-mer vocabulary ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Building {k}-mer vocabulary (canonical)...")
    vocab   = build_kmer_vocab(k, canonical=True)
    vocab_index = {km: i for i, km in enumerate(vocab)}
    print(f"  Vocabulary size: {len(vocab):,} k-mers")

    # ── Extract features ──────────────────────────────────────────────────
    print("\nExtracting k-mer features...")
    X_plas, y_plas = extract_kmer_features(
        plasmid_path,    k, vocab_index, label=1,
        subsample=subsample, desc="plasmid"
    )
    X_chrom, y_chrom = extract_kmer_features(
        chromosome_path, k, vocab_index, label=0,
        subsample=subsample, desc="chromosome"
    )

    X = np.vstack([X_plas, X_chrom])
    y = np.concatenate([y_plas, y_chrom])
    print(f"  Feature matrix: {X.shape}  (plasmid={y_plas.shape[0]:,}, "
          f"chromosome={y_chrom.shape[0]:,})")

    # ── Train/test split (stratified 80/20) ───────────────────────────────
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=seed
    )
    print(f"  Train: {X_train.shape[0]:,}  |  Test: {X_test.shape[0]:,}")

    # ── Train and evaluate each classifier ────────────────────────────────
    classifiers = get_classifiers()
    all_results = []
    cms = []
    trained_clfs = {}

    print(f"\n{'='*60}")
    print("Training and evaluating classifiers...")
    print(f"{'='*60}")

    for name, clf in classifiers.items():
        clean_name = name.replace("\n", " ")
        print(f"\n[{clean_name}]")
        metrics = evaluate_classifier(
            clf, X_train, y_train, X_test, y_test, clf_name=name
        )
        trained_clfs[name] = clf
        all_results.append(metrics)
        cms.append((clean_name, metrics["cm"]))

        print(f"  Accuracy:  {metrics['accuracy']:.4f}")
        print(f"  F1:        {metrics['f1']:.4f}")
        print(f"  Precision: {metrics['precision']:.4f}")
        print(f"  Recall:    {metrics['recall']:.4f}")
        if metrics["auc"] is not None:
            print(f"  AUC-ROC:   {metrics['auc']:.4f}")
        print(f"  Train time: {metrics['train_time_s']:.2f}s  "
              f"| Infer time: {metrics['infer_time_s']:.4f}s")
        print(f"\n  Classification Report (test set):")
        from sklearn.metrics import classification_report
        print(classification_report(
            y_test,
            clf.predict(X_test),
            target_names=["Chromosome", "Plasmid"],
            digits=4
        ))

    # ── Save results ──────────────────────────────────────────────────────
    results_df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "cm"} for r in all_results
    ])
    results_df.to_csv(RESULTS_DIR / "baseline_results.csv", index=False)
    print(f"\n[OK] Results saved to {RESULTS_DIR}/baseline_results.csv")

    with open(RESULTS_DIR / "baseline_results.json", "w") as f:
        json.dump(
            [{k: (v.tolist() if hasattr(v, "tolist") else v)
              for k, v in r.items()} for r in all_results],
            f, indent=2
        )

    # ── Save best model ───────────────────────────────────────────────────
    best_idx  = max(range(len(all_results)),
                    key=lambda i: all_results[i]["f1"])
    best_name = all_results[best_idx]["classifier"]
    best_clf  = trained_clfs[list(classifiers.keys())[best_idx]]
    joblib.dump(best_clf, MODEL_DIR / "best_baseline.pkl")
    joblib.dump(vocab_index, MODEL_DIR / "vocab_index.pkl")
    print(f"[OK] Best model saved: {best_name}")

    # ── Generate plots ────────────────────────────────────────────────────
    print("\n=== Generating result figures ===")
    plot_confusion_matrices(cms, FIG_DIR)
    plot_metrics_comparison(all_results, FIG_DIR)

    lr_key = [k for k in trained_clfs if "LogisticRegression" in k]
    if lr_key:
        plot_kmer_importance(
            trained_clfs[lr_key[0]], vocab, top_n=30, out=FIG_DIR
        )

    # ── Print summary table ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("FINAL RESULTS SUMMARY")
    print(f"{'='*60}")
    cols = ["classifier", "accuracy", "f1", "precision", "recall", "auc"]
    col_widths = [35, 10, 10, 10, 10, 10]
    header = "".join(f"{c:<{w}}" for c, w in zip(cols, col_widths))
    print(header)
    print("-" * sum(col_widths))
    for r in all_results:
        row = (
            f"{r['classifier']:<35}"
            f"{r['accuracy']:<10.4f}"
            f"{r['f1']:<10.4f}"
            f"{r['precision']:<10.4f}"
            f"{r['recall']:<10.4f}"
            f"{(r['auc'] or 0.0):<10.4f}"
        )
        print(row)

    print(f"\nBest F1: {best_name}  ({all_results[best_idx]['f1']:.4f})")
    print("\nDone! Check ./results/ and ./figures/ for output.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baseline plasmid classifier")
    parser.add_argument("--k", type=int, default=5,
                        help="k-mer length (default: 5, same as mlplasmids)")
    parser.add_argument("--subsample", type=int, default=0,
                        help="subsample N sequences per class (0 = use all)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    main(k=args.k, subsample=args.subsample, seed=args.seed)
