#!/usr/bin/env python3
"""
08_pretrained_baselines.py
==========================
Evaluates the pretrained PlasClass model on the benchmark_1000 dataset.
(PlasmidHunter and mlplasmids are skipped due to heavy external dependencies
and/or incompatible environments for this quick benchmark run).
"""

import os
import subprocess
import json
import time
from pathlib import Path
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw" / "benchmark_1000"
RESULTS_DIR = BASE_DIR / "results" / "pretrained_baselines"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PLASCLASS_DIR = BASE_DIR / "PlasClass"

def setup_plasclass():
    if not PLASCLASS_DIR.exists():
        print("Cloning PlasClass repository...")
        try:
            subprocess.run(["git", "clone", "https://github.com/Shamir-Lab/PlasClass.git"], check=True)
            print("PlasClass cloned successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to clone PlasClass: {e}")
            return False
            
    # Install dependencies required by PlasClass
    try:
        subprocess.run(["python", "-m", "pip", "install", "networkx", "scipy", "scikit-learn"], check=True)
    except:
        pass
        
    return True

def run_plasclass(input_fasta: Path, output_file: Path):
    if not input_fasta.exists():
        print(f"Error: {input_fasta} does not exist.")
        return False
        
    print(f"Running PlasClass on {input_fasta.name}...")
    cmd = [
        "python", "classify_fasta.py",
        "-f", str(input_fasta.absolute()),
        "-o", str(output_file.absolute()),
        "-p", "4"  # use 4 cores
    ]
    
    try:
        # Run from inside the PLASCLASS_DIR
        subprocess.run(cmd, cwd=PLASCLASS_DIR, check=True, capture_output=True, text=True)
        print(f"Success. Predictions saved to {output_file.name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running PlasClass on {input_fasta.name}:")
        print(e.stderr)
        return False

def evaluate_plasclass(plasmid_preds_file: Path, chromosome_preds_file: Path):
    """
    PlasClass output is a tab-separated file: sequence_header \t probability
    Probability > 0.5 is considered a plasmid.
    """
    y_true = []
    y_pred = []
    
    # Plasmids (true label = 1)
    if plasmid_preds_file.exists():
        df_p = pd.read_csv(plasmid_preds_file, sep="\t", header=None)
        y_true.extend([1] * len(df_p))
        y_pred.extend((df_p[1] > 0.5).astype(int).tolist())
    
    # Chromosomes (true label = 0)
    if chromosome_preds_file.exists():
        df_c = pd.read_csv(chromosome_preds_file, sep="\t", header=None)
        y_true.extend([0] * len(df_c))
        y_pred.extend((df_c[1] > 0.5).astype(int).tolist())
        
    if not y_true:
        print("No predictions found to evaluate.")
        return None
        
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    
    print("\n=== PlasClass (Pretrained) Evaluation ===")
    print(f"Total Sequences: {len(y_true)}")
    print(f"Accuracy:  {acc:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    
    return {
        "classifier": "PlasClass (Pretrained)",
        "accuracy": acc,
        "f1": f1,
        "precision": prec,
        "recall": rec
    }

def main():
    print("Starting Pretrained Baselines Evaluation...")
    results = []
    
    # --- PlasClass ---
    if setup_plasclass():
        plasmid_out = RESULTS_DIR / "plasclass_plasmid.txt"
        chromosome_out = RESULTS_DIR / "plasclass_chromosome.txt"
        
        t0 = time.time()
        ok1 = run_plasclass(DATA_DIR / "test_plasmid_1000.fasta", plasmid_out)
        ok2 = run_plasclass(DATA_DIR / "test_chromosome_1000.fasta", chromosome_out)
        t1 = time.time()
        
        if ok1 and ok2:
            metrics = evaluate_plasclass(plasmid_out, chromosome_out)
            if metrics:
                metrics["infer_time_s"] = t1 - t0
                results.append(metrics)
                
    # Save results
    if results:
        out_json = RESULTS_DIR / "pretrained_results.json"
        with open(out_json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved pretrained baseline metrics to {out_json}")

if __name__ == "__main__":
    main()
