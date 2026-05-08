# Plasmid-Classification-with-Machine-Learning
My Bechelor Degree of Computer Science senior project

---

# Plasmid Classification — Baseline Pipeline

**Senior Project 2301399 | Siwak Saiphaisri | 6634468023**

---

## Baseline Methods

| Script | Method | Reference |
|--------|--------|-----------|
| `03_baseline.py` | k-mer (5-mer) + Logistic Regression | PlasClass (Pellow et al., 2020) |
| `03_baseline.py` | k-mer (5-mer) + Linear SVM | mlplasmids approach — reimplemented in Python (Arredondo-Alonso et al., 2018) |
| `03_baseline.py` | k-mer + Random Forest | Ablation |
| `03_baseline.py` | k-mer + MLP | Ablation |
| `04_length_stratified_eval.py` | All above at 1kb/5kb/10kb/50kb fragments | PlasClass benchmark methodology |

## Benchmark Dataset

- **Source:** PlasmidHunter benchmark (Tian et al., 2024, *Briefings in Bioinformatics*)
- **Zenodo:** https://zenodo.org/records/10433596
- **Files:** `test_plasmid.fasta`, `test_chromosome.fasta`

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download benchmark data
bash 01_download_data.sh

# 3. Exploratory Data Analysis (generates figures 01–04)
python 02_explore_data.py

# 4. Train & evaluate baselines (generates figures 05–07)
python 03_baseline.py --k 5

# 5. Length-stratified evaluation (figure 08)
python 04_length_stratified_eval.py --n_frags 500
```

## Output Structure

```
figures/
  01_length_distribution.png    # sequence length histogram
  02_gc_distribution.png        # GC content density
  03_class_balance.png          # class count bar chart
  04_length_vs_gc.png           # scatter: length vs GC
  05_confusion_matrices.png     # CM for all classifiers
  06_metrics_comparison.png     # grouped bar: Acc/F1/Prec/Rec
  07_kmer_importance.png        # top k-mers by LR coefficient
  08_length_stratified_f1.png   # F1 vs fragment length

results/
  baseline_results.csv          # metrics table (all classifiers)
  baseline_results.json         # same, JSON format
  length_stratified_results.csv # per-length metrics

models/
  best_baseline.pkl             # best classifier (joblib)
  vocab_index.pkl               # k-mer vocabulary dict
```

## Notes on Baseline Choice

### Why PlasClass (not PlasmidHunter) as primary baseline?

PlasmidHunter uses gene content profile + DIAMOND alignment against a 3.9M protein database. While it achieves ~97% accuracy, it requires:
- Heavy external dependencies (DIAMOND, Prodigal)
- A large pre-built protein database
- Minutes–hours of runtime per sample

This makes it unsuitable as a fast, reproducible baseline for comparison.

**PlasClass** (k-mer + LogReg) is the standard lightweight baseline:
- No external tools required
- Runs in seconds
- Well-cited (400+ citations), reproducible
- PlasmidHunter paper itself uses PlasClass as the main comparison

### Why reimplementing mlplasmids in Python?

The original mlplasmids is an R package and is species-specific (E. coli / K. pneumoniae / E. faecium only). Our Python reimplementation uses the same approach (5-mer + SVM) but is species-agnostic, allowing evaluation on the full PlasmidHunter benchmark.

### Recommended k-mer lengths

| k | Vocab size (canonical) | Notes |
|---|---|---|
| 4 | 136 | Too small, loses information |
| **5** | **512** | **Sweet spot: mlplasmids default** |
| 6 | 2,080 | Slightly better, higher memory |
| 7 | 8,320 | Diminishing returns, high memory |

Run with `--k 6` or `--k 7` for ablation study.
