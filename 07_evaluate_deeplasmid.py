#!/usr/bin/env python3
"""
07_evaluate_deeplasmid.py
=========================
Parses predictions from Deeplasmid and calculates evaluation metrics
(Accuracy, F1, Precision, Recall) on the subsampled benchmark.
"""

import json
from pathlib import Path
from glob import glob

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix

RESULTS_DIR = Path("./results/deeplasmid")

def parse_predictions(out_dir: Path, true_label: int) -> tuple[list[int], list[int]]:
    """
    Parses predictions.txt from the deeplasmid output directory.
    Returns lists of true labels and predicted labels (1 for plasmid, 0 for chromosome).
    """
    pred_files = glob(str(out_dir / "outPR.*" / "predictions.txt"))
    if not pred_files:
        print(f"Warning: No predictions.txt found in {out_dir}/outPR.*")
        return [], []
    
    # Take the latest if multiple exist (usually only one)
    pred_file = pred_files[-1]
    
    y_true = []
    y_pred = []
    
    with open(pred_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # Predict 1 if the model output indicates "PLASMID", 0 otherwise
            # Note: Deeplasmid can output PLASMID, CHROMOSOME, AMBIGUOUS, etc.
            if "PLASMID" in line.upper():
                pred = 1
            else:
                pred = 0
                
            y_true.append(true_label)
            y_pred.append(pred)
            
    return y_true, y_pred

def main():
    plasmid_out = RESULTS_DIR / "plasmid_out"
    chromosome_out = RESULTS_DIR / "chromosome_out"
    
    print("Parsing plasmid predictions...")
    y_true_p, y_pred_p = parse_predictions(plasmid_out, true_label=1)
    print(f"  Found {len(y_true_p)} predictions.")
    
    print("Parsing chromosome predictions...")
    y_true_c, y_pred_c = parse_predictions(chromosome_out, true_label=0)
    print(f"  Found {len(y_true_c)} predictions.")
    
    y_true = y_true_p + y_true_c
    y_pred = y_pred_p + y_pred_c
    
    if not y_true:
        print("No predictions to evaluate.")
        return
        
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    cm = confusion_matrix(y_true, y_pred)
    
    print(f"\n=== Deeplasmid Evaluation Results ===")
    print(f"Total Sequences: {len(y_true)}")
    print(f"Accuracy:  {acc:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"Confusion Matrix:\n{cm}")
    
    # Save results
    metrics = {
        "classifier": "Deeplasmid",
        "accuracy": acc,
        "f1": f1,
        "precision": prec,
        "recall": rec,
        "total_evaluated": len(y_true)
    }
    
    out_json = RESULTS_DIR / "deeplasmid_metrics.json"
    with open(out_json, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved metrics to {out_json}")

if __name__ == "__main__":
    main()
