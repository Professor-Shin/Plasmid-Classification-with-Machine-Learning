import os
from pathlib import Path
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

RESULTS_DIR = Path("d:/train_baseline/results/baselines")

# Parse PlasClass
def parse_plasclass(output_file, true_label):
    if not output_file.exists(): return []
    with open(output_file, "r") as f:
        preds = []
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                prob = float(parts[1])
                pred_label = 1 if prob >= 0.5 else 0
                preds.append((true_label, pred_label))
        return preds

# Parse DeepLasmid
def parse_deeplasmid(output_dir, true_label):
    if not output_dir.exists(): return []
    pred_files = list(output_dir.rglob("predictions.txt"))
    if not pred_files: return []
    pred_file = pred_files[0]
    preds = []
    with open(pred_file, "r") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                label_str = parts[2].strip()
                if label_str == "PLASMID":
                    pred_label = 1
                elif label_str == "CHROMOSOME":
                    pred_label = 0
                else:
                    pred_label = 0
                preds.append((true_label, pred_label))
    return preds

def evaluate_predictions(preds, model_name, dataset_name):
    if not preds:
        return {"Model": model_name, "Dataset": dataset_name, "Error": "No predictions"}
    
    y_true = [p[0] for p in preds]
    y_pred = [p[1] for p in preds]
    
    return {
        "Model": model_name,
        "Dataset": dataset_name,
        "Accuracy": round(accuracy_score(y_true, y_pred), 4),
        "Precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "Recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "F1_Score": round(f1_score(y_true, y_pred, zero_division=0), 4)
    }

def main():
    results = []
    tasks = ["Train_250", "Test_1000"]
    
    for task in tasks:
        # PLASCLASS
        pc_plas_out = RESULTS_DIR / f"plasclass_{task}_plas.out"
        pc_chrom_out = RESULTS_DIR / f"plasclass_{task}_chrom.out"
        preds_pc = parse_plasclass(pc_plas_out, 1) + parse_plasclass(pc_chrom_out, 0)
        results.append(evaluate_predictions(preds_pc, "PlasClass", task))
        
        # DEEPLASMID
        dl_plas_out = RESULTS_DIR / f"deeplasmid_{task}_plas"
        dl_chrom_out = RESULTS_DIR / f"deeplasmid_{task}_chrom"
        preds_dl = parse_deeplasmid(dl_plas_out, 1) + parse_deeplasmid(dl_chrom_out, 0)
        results.append(evaluate_predictions(preds_dl, "DeepLasmid", task))

    df_results = pd.DataFrame(results)
    
    # We will output as CSV and also string print so we don't need tabulate
    csv_path = RESULTS_DIR / "baseline_results.csv"
    df_results.to_csv(csv_path, index=False)
    print(df_results.to_string(index=False))

if __name__ == "__main__":
    main()
