import os
import subprocess
from pathlib import Path
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

BASE_DIR = Path("d:/train_baseline")
RESULTS_DIR = BASE_DIR / "results" / "baselines"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATA_TRAIN_CHROM = BASE_DIR / "data/train/train_chromosome.fasta"
DATA_TRAIN_PLAS = BASE_DIR / "data/train/train_plasmid.fasta"
DATA_TEST_CHROM = BASE_DIR / "data/raw/benchmark_1000/test_chromosome_1000.fasta"
DATA_TEST_PLAS = BASE_DIR / "data/raw/benchmark_1000/test_plasmid_1000.fasta"

# PlasClass
def run_plasclass(input_fasta, output_file):
    print(f"Running PlasClass on {input_fasta.name}...")
    cmd = [
        "d:/train_baseline/venv/Scripts/python.exe",
        "d:/train_baseline/model/PlasClass/classify_fasta.py",
        "-f", str(input_fasta),
        "-o", str(output_file),
        "-p", "1"
    ]
    subprocess.run(cmd, check=False)

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

# DeepLasmid
def run_deeplasmid(input_fasta, output_dir):
    print(f"Running DeepLasmid on {input_fasta.name}...")
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{input_fasta.absolute()}:/srv/jgi-ml/classifier/dl/in.fasta",
        "-v", f"{output_dir.absolute()}:/srv/jgi-ml/classifier/dl/outdir",
        "billandreo/deeplasmid-cpu-ubuntu2",
        "deeplasmid.sh", "in.fasta", "outdir"
    ]
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def parse_deeplasmid(output_dir, true_label):
    if not output_dir.exists(): return []
    # Find the predictions.txt file inside the generated subdirectories
    pred_files = list(output_dir.rglob("predictions.txt"))
    if not pred_files: return []
    pred_file = pred_files[0]
    preds = []
    with open(pred_file, "r") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                # "PLASMID" or "CHROMOSOME" or "AMBIGUOUS"
                label_str = parts[2].strip()
                if label_str == "PLASMID":
                    pred_label = 1
                elif label_str == "CHROMOSOME":
                    pred_label = 0
                else:
                    # AMBIGUOUS, default to 0 for strict evaluation, or consider it an error
                    pred_label = 0
                preds.append((true_label, pred_label))
    return preds

# mlplasmids
def run_mlplasmids(input_fasta, output_file):
    print(f"Running mlplasmids on {input_fasta.name}...")
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{input_fasta.absolute()}:/input.fasta",
        "-v", f"{output_file.absolute()}:/output.tsv",
        "mlplasmids-runner",
        "run_mlplasmids.R", "/input.fasta", "/output.tsv"
    ]
    subprocess.run(cmd, check=False)

def parse_mlplasmids(output_file, true_label):
    if not output_file.exists(): return []
    try:
        df = pd.read_csv(output_file, sep="\t")
        preds = []
        for _, row in df.iterrows():
            pred_str = str(row.get("Prediction", "")).strip().lower()
            if pred_str == "plasmid":
                preds.append((true_label, 1))
            else:
                preds.append((true_label, 0))
        return preds
    except Exception as e:
        print(f"Error parsing mlplasmids output: {e}")
        return []

def evaluate_predictions(preds, model_name, dataset_name):
    if not preds:
        return {"Model": model_name, "Dataset": dataset_name, "Error": "No predictions"}
    
    y_true = [p[0] for p in preds]
    y_pred = [p[1] for p in preds]
    
    return {
        "Model": model_name,
        "Dataset": dataset_name,
        "Accuracy": accuracy_score(y_true, y_pred),
        "Precision": precision_score(y_true, y_pred, zero_division=0),
        "Recall": recall_score(y_true, y_pred, zero_division=0),
        "F1_Score": f1_score(y_true, y_pred, zero_division=0)
    }

def main():
    results = []
    
    # Define tasks
    tasks = [
        {"name": "Train_250", "chrom": DATA_TRAIN_CHROM, "plas": DATA_TRAIN_PLAS},
        {"name": "Test_1000", "chrom": DATA_TEST_CHROM, "plas": DATA_TEST_PLAS}
    ]
    
    for task in tasks:
        # PLASCLASS
        pc_plas_out = RESULTS_DIR / f"plasclass_{task['name']}_plas.out"
        pc_chrom_out = RESULTS_DIR / f"plasclass_{task['name']}_chrom.out"
        run_plasclass(task['plas'], pc_plas_out)
        run_plasclass(task['chrom'], pc_chrom_out)
        
        preds_pc = parse_plasclass(pc_plas_out, 1) + parse_plasclass(pc_chrom_out, 0)
        results.append(evaluate_predictions(preds_pc, "PlasClass", task['name']))
        
        # DEEPLASMID
        dl_plas_out = RESULTS_DIR / f"deeplasmid_{task['name']}_plas"
        dl_chrom_out = RESULTS_DIR / f"deeplasmid_{task['name']}_chrom"
        run_deeplasmid(task['plas'], dl_plas_out)
        run_deeplasmid(task['chrom'], dl_chrom_out)
        
        preds_dl = parse_deeplasmid(dl_plas_out, 1) + parse_deeplasmid(dl_chrom_out, 0)
        results.append(evaluate_predictions(preds_dl, "DeepLasmid", task['name']))
        
        # MLPLASMIDS
        ml_plas_out = RESULTS_DIR / f"mlplasmids_{task['name']}_plas.tsv"
        ml_chrom_out = RESULTS_DIR / f"mlplasmids_{task['name']}_chrom.tsv"
        run_mlplasmids(task['plas'], ml_plas_out)
        run_mlplasmids(task['chrom'], ml_chrom_out)
        
        preds_ml = parse_mlplasmids(ml_plas_out, 1) + parse_mlplasmids(ml_chrom_out, 0)
        results.append(evaluate_predictions(preds_ml, "mlplasmids", task['name']))
        
    df_results = pd.DataFrame(results)
    print("\n--- Final Evaluation Results ---")
    print(df_results.to_markdown(index=False))
    df_results.to_csv(RESULTS_DIR / "baseline_results.csv", index=False)
    
if __name__ == "__main__":
    main()
