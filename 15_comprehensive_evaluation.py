import argparse
import time
import gc
import json
import joblib
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from Bio import SeqIO
from Bio.Seq import Seq
from transformers import AutoTokenizer, AutoModel, BertTokenizer, BertModel
from sklearn.metrics import classification_report, accuracy_score, f1_score, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm

# --- Paths ---
TRAIN_DIR = Path("./data/train")
TEST_DIR = Path("./data/raw")
RESULTS_DIR = Path("./results")
FIG_DIR = Path("./figures")
MODEL_DIR = Path("./models")

for d in [RESULTS_DIR, FIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- Models ---
ESM_MODEL_NAME = "facebook/esm2_t6_8M_UR50D"
DNABERT_MODEL_NAME = "zhihan1996/DNA_bert_6"

# --- Utils ---
def load_all_sequences(fasta_path, max_seq_len=10000):
    records = list(SeqIO.parse(str(fasta_path), "fasta"))
    seqs = []
    for r in records:
        s = str(r.seq).upper()
        if len(s) > max_seq_len:
            s = s[:max_seq_len] # Take the first part for speed
        if s:
            seqs.append(s)
    return seqs

def extract_top_orfs(dna_seq, min_len=100, top_n=5):
    seq_obj = Seq(dna_seq)
    orfs = []
    for strand, seq in [(1, seq_obj), (-1, seq_obj.reverse_complement())]:
        for frame in range(3):
            try:
                l = len(seq) - frame
                padded = seq[frame:frame + (l - l % 3)]
                peps = str(padded.translate()).split("*")
                orfs.extend([p for p in peps if len(p) >= min_len])
            except:
                continue
    orfs.sort(key=len, reverse=True)
    return orfs[:top_n]

def seq2kmer(seq, k=6):
    return " ".join([seq[i:i+k] for i in range(len(seq) - k + 1)])

# --- Feature Extraction ---
def get_features(seqs, device, top_n=5, max_windows=5, desc=""):
    print(f"\n[Feature Extraction] {desc}")
    
    # ESM-2
    esm_tokenizer = AutoTokenizer.from_pretrained(ESM_MODEL_NAME)
    esm_model = AutoModel.from_pretrained(ESM_MODEL_NAME).to(device)
    esm_model.eval()
    
    # DNABERT
    dna_tokenizer = BertTokenizer.from_pretrained(DNABERT_MODEL_NAME)
    dna_model = BertModel.from_pretrained(DNABERT_MODEL_NAME).to(device)
    dna_model.eval()
    
    X_esm = []
    X_dna = []
    
    for seq in tqdm(seqs, desc=f"Extracting features ({desc})"):
        # ESM Features (ORFs)
        orfs = extract_top_orfs(seq, min_len=100, top_n=top_n)
        if not orfs:
            X_esm.append(torch.zeros(1, esm_model.config.hidden_size))
        else:
            inputs = esm_tokenizer(orfs, return_tensors="pt", padding=True, truncation=True, max_length=1024).to(device)
            with torch.no_grad():
                outputs = esm_model(**inputs)
                mask = inputs['attention_mask'].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
                sum_emb = torch.sum(outputs.last_hidden_state * mask, 1)
                sum_mask = torch.clamp(mask.sum(1), min=1e-9)
                X_esm.append((sum_emb / sum_mask).cpu())
        
        # DNABERT Features (Windows)
        seq_clean = "".join([c for c in seq if c in "ATGC"])
        window_size = 510
        windows = [seq_clean[i:i+window_size] for i in range(0, len(seq_clean), window_size)][:max_windows]
        if not windows:
            X_dna.append(torch.zeros(1, dna_model.config.hidden_size))
        else:
            kmers = [seq2kmer(w, k=6) for w in windows]
            inputs = dna_tokenizer(kmers, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
            with torch.no_grad():
                outputs = dna_model(**inputs)
                X_dna.append(outputs.last_hidden_state[:, 0, :].cpu())
                
    del esm_model, dna_model
    gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache()
    
    return X_esm, X_dna

# --- Architectures ---
class AttentionPooling(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.attention = nn.Sequential(nn.Linear(hidden_size, hidden_size // 2), nn.Tanh(), nn.Linear(hidden_size // 2, 1))
    def forward(self, x):
        weights = torch.softmax(self.attention(x), dim=0)
        return torch.sum(weights * x, dim=0, keepdim=True)

class Model12_HybridAttention(nn.Module):
    def __init__(self):
        super().__init__()
        self.esm_attn = AttentionPooling(320)
        self.dna_attn = AttentionPooling(768)
        self.classifier = nn.Sequential(nn.Linear(320 + 768, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, 1))
    def forward(self, x_esm, x_dna):
        c_esm, c_dna = self.esm_attn(x_esm), self.dna_attn(x_dna)
        return self.classifier(torch.cat([c_esm, c_dna], dim=1)).squeeze()

class Model13_LightweightHybrid(nn.Module):
    def __init__(self):
        super().__init__()
        self.esm_attn = AttentionPooling(320)
        self.dna_attn = AttentionPooling(768)
        self.esm_proj = nn.Sequential(nn.Linear(320, 32), nn.ReLU(), nn.Dropout(0.3))
        self.dna_proj = nn.Sequential(nn.Linear(768, 32), nn.ReLU(), nn.Dropout(0.3))
        self.classifier = nn.Sequential(nn.LayerNorm(64), nn.Dropout(0.5), nn.Linear(64, 16), nn.LayerNorm(16), nn.ReLU(), nn.Dropout(0.5), nn.Linear(16, 1))
    def forward(self, x_esm, x_dna):
        c_esm, c_dna = self.esm_attn(x_esm), self.dna_attn(x_dna)
        p_esm, p_dna = self.esm_proj(c_esm), self.dna_proj(c_dna)
        return self.classifier(torch.cat([p_esm, p_dna], dim=1)).squeeze()

# --- Dataset ---
class HybridDataset(Dataset):
    def __init__(self, X_esm, X_dna, y):
        self.X_esm, self.X_dna, self.y = X_esm, X_dna, torch.tensor(y, dtype=torch.float32)
    def __len__(self): return len(self.y)
    def __getitem__(self, idx): return self.X_esm[idx], self.X_dna[idx], self.y[idx]

def collate_fn(batch):
    return [i[0] for i in batch], [i[1] for i in batch], torch.stack([i[2] for i in batch])

def train_model(model, train_loader, device, epochs=15):
    model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    criterion = nn.BCEWithLogitsLoss()
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for b_esm, b_dna, b_y in train_loader:
            b_y = b_y.to(device)
            optimizer.zero_grad()
            logits = torch.stack([model(e.to(device), d.to(device)) for e, d in zip(b_esm, b_dna)])
            loss = criterion(logits, b_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        if (epoch+1) % 5 == 0:
            print(f"  Epoch {epoch+1}/{epochs} | Loss: {total_loss/len(train_loader):.4f}")
    return model

def evaluate_model(model, test_loader, device):
    model.eval()
    y_preds, y_trues = [], []
    with torch.no_grad():
        for b_esm, b_dna, b_y in test_loader:
            for e, d in zip(b_esm, b_dna):
                logit = model(e.to(device), d.to(device))
                y_preds.append(1 if torch.sigmoid(logit).item() > 0.5 else 0)
            y_trues.extend(b_y.numpy())
    return np.array(y_trues), np.array(y_preds)

def load_from_dir(directory, n_samples, max_seq_len=10000):
    files = list(Path(directory).glob("*.fasta"))
    seqs = []
    for f in files[:n_samples]:
        seqs.extend(load_all_sequences(f, max_seq_len))
    return seqs[:n_samples]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_train", type=int, default=50, help="Samples to use for training")
    parser.add_argument("--epochs", type=int, default=15)
    args = parser.parse_args()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # 1. Load Data
    print("\n[1/4] Loading Data...")
    train_plas = load_from_dir(TRAIN_DIR / "plasmids", args.n_train)
    train_chrom = load_from_dir(TRAIN_DIR / "chromosomes", args.n_train)
    
    # Subsampling test set to 100 per class for CPU feasibility
    test_plas = load_all_sequences(TEST_DIR / "test_plasmid.fasta", max_seq_len=10000)[:100]
    test_chrom = load_all_sequences(TEST_DIR / "test_chromosome.fasta", max_seq_len=10000)[:100]
    
    y_train = [1]*len(train_plas) + [0]*len(train_chrom)
    y_test = [1]*len(test_plas) + [0]*len(test_chrom)
    
    # 2. Extract Features
    X_esm_train, X_dna_train = get_features(train_plas + train_chrom, device, desc="Train Set")
    X_esm_test, X_dna_test = get_features(test_plas + test_chrom, device, desc="Test Set")
    
    train_loader = DataLoader(HybridDataset(X_esm_train, X_dna_train, y_train), batch_size=4, shuffle=True, collate_fn=collate_fn)
    test_loader = DataLoader(HybridDataset(X_esm_test, X_dna_test, y_test), batch_size=4, shuffle=False, collate_fn=collate_fn)
    
    # 3. Train & Evaluate Models
    results = []
    
    # Baseline
    print("\n[2/4] Evaluating Baseline...")
    try:
        best_clf = joblib.load(MODEL_DIR / "best_baseline.pkl")
        vocab_idx = joblib.load(MODEL_DIR / "vocab_index.pkl")
        
        # We need a quick k-mer extractor for the baseline
        def extract_kmer_features(seqs, k=5, vocab_index=vocab_idx):
            X = np.zeros((len(seqs), len(vocab_index)), dtype=np.float32)
            for i, seq in enumerate(tqdm(seqs, desc="Baseline K-mers")):
                for j in range(len(seq) - k + 1):
                    kmer = seq[j:j+k]
                    # Simplified: not using canonical for speed in this report
                    idx = vocab_index.get(kmer)
                    if idx is not None: X[i, idx] += 1
                if X[i].sum() > 0: X[i] /= X[i].sum()
            return X
        
        X_test_kmer = extract_kmer_features(test_plas + test_chrom)
        y_pred_base = best_clf.predict(X_test_kmer)
        results.append({"model": "Baseline (Best)", "acc": accuracy_score(y_test, y_pred_base), "f1": f1_score(y_test, y_pred_base)})
        print(f"  Baseline Acc: {results[-1]['acc']:.4f}")
    except Exception as e:
        print(f"  [SKIP] Baseline failed: {e}")

    # Model 12
    print("\n[3/4] Training Model 12 (Hybrid Attention)...")
    m12 = train_model(Model12_HybridAttention(), train_loader, device, epochs=args.epochs)
    y_true_12, y_pred_12 = evaluate_model(m12, test_loader, device)
    results.append({"model": "Model 12 (Hybrid Attention)", "acc": accuracy_score(y_true_12, y_pred_12), "f1": f1_score(y_true_12, y_pred_12)})
    print(f"  Model 12 Acc: {results[-1]['acc']:.4f}")
    
    # Model 13
    print("\n[4/4] Training Model 13 (Lightweight Hybrid)...")
    m13 = train_model(Model13_LightweightHybrid(), train_loader, device, epochs=args.epochs)
    y_true_13, y_pred_13 = evaluate_model(m13, test_loader, device)
    results.append({"model": "Model 13 (Lightweight Hybrid)", "acc": accuracy_score(y_true_13, y_pred_13), "f1": f1_score(y_true_13, y_pred_13)})
    print(f"  Model 13 Acc: {results[-1]['acc']:.4f}")
    
    # 4. Save & Report
    df_res = pd.DataFrame(results)
    df_res.to_csv(RESULTS_DIR / "comprehensive_results.csv", index=False)
    print(f"\nFinal Results:\n{df_res}")
    
    # Plotting
    plt.figure(figsize=(10, 6))
    sns.barplot(x="model", y="f1", data=df_res, palette="viridis")
    plt.title("Model Performance Comparison (F1-score)")
    plt.ylim(0, 1.1)
    plt.savefig(FIG_DIR / "comparison_f1.png")
    
    print(f"\n[DONE] Results saved to {RESULTS_DIR}")

if __name__ == "__main__":
    main()
