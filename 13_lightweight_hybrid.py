#!/usr/bin/env python3
"""
13_lightweight_hybrid.py
========================
Lightweight End-to-End Hybrid Attention Model.
Designed to be dependency-free (no BLAST, Diamond, Prodigal), requiring no databases,
and highly optimized for speed by selecting Top-N longest ORFs and disjoint DNA windows.
Incorporates LayerNorm and strong Dropout to prevent overfitting on small datasets.
"""

import argparse
import time
import gc
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from Bio import SeqIO
from Bio.Seq import Seq
from transformers import AutoTokenizer, AutoModel, BertTokenizer, BertModel
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score
from tqdm import tqdm

DATA_DIR = Path("./data/raw")
ESM_MODEL_NAME = "facebook/esm2_t6_8M_UR50D"
DNABERT_MODEL_NAME = "zhihan1996/DNA_bert_6"

# --- Common Utilities ---
def load_and_subsample(fasta_path, n_samples, seed):
    records = list(SeqIO.parse(str(fasta_path), "fasta"))
    rng = np.random.default_rng(seed)
    if len(records) > n_samples:
        indices = rng.choice(len(records), size=n_samples, replace=False)
        records = [records[i] for i in indices]
    return [str(r.seq).upper() for r in records]

def extract_top_orfs(dna_seq, min_len=100, top_n=10):
    """Extracts ORFs and returns only the top N longest ones."""
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
    # Sort by length descending and take top N
    orfs.sort(key=len, reverse=True)
    return orfs[:top_n]

def seq2kmer(seq, k=6):
    return " ".join([seq[i:i+k] for i in range(len(seq) - k + 1)])

# --- Feature Extraction (Unpooled) ---
def get_unpooled_esm_features(seqs, device, top_n=10, desc=""):
    print(f"\nLoading {ESM_MODEL_NAME} for Lightweight Feature Extraction...")
    tokenizer = AutoTokenizer.from_pretrained(ESM_MODEL_NAME)
    model = AutoModel.from_pretrained(ESM_MODEL_NAME).to(device)
    model.eval()
    
    X_raw = []
    for seq in tqdm(seqs, desc=f"ESM-2 (Top {top_n} ORFs) {desc}"):
        orfs = extract_top_orfs(seq, min_len=100, top_n=top_n)
        if not orfs:
            X_raw.append(torch.zeros(1, model.config.hidden_size))
            continue
            
        embeddings = []
        batch_size = 8
        for i in range(0, len(orfs), batch_size):
            batch = orfs[i:i+batch_size]
            inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=1024)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
                last_hidden = outputs.last_hidden_state
                mask = inputs['attention_mask'].unsqueeze(-1).expand(last_hidden.size()).float()
                sum_emb = torch.sum(last_hidden * mask, 1)
                sum_mask = torch.clamp(mask.sum(1), min=1e-9)
                embeddings.append((sum_emb / sum_mask).cpu())
                
        seq_emb_unpooled = torch.cat(embeddings, dim=0) # Shape: (<=top_n, 320)
        X_raw.append(seq_emb_unpooled)
        
    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return X_raw

def get_unpooled_dnabert_features(seqs, device, max_windows=10, desc=""):
    print(f"\nLoading {DNABERT_MODEL_NAME} for Lightweight Feature Extraction...")
    tokenizer = BertTokenizer.from_pretrained(DNABERT_MODEL_NAME)
    model = BertModel.from_pretrained(DNABERT_MODEL_NAME).to(device)
    model.eval()
    
    X_raw = []
    window_size = 510 # Disjoint windows
    
    for seq in tqdm(seqs, desc=f"DNABERT (Max {max_windows} Windows) {desc}"):
        seq = "".join([c for c in seq if c in "ATGC"])
        if len(seq) < 10:
            X_raw.append(torch.zeros(1, model.config.hidden_size))
            continue
            
        # Using disjoint windows (step=window_size) instead of overlapping
        windows = [seq[i:i+window_size] for i in range(0, len(seq), window_size)][:max_windows]
        
        embeddings = []
        batch_size = 4
        for i in range(0, len(windows), batch_size):
            batch = windows[i:i+batch_size]
            batch_kmers = [seq2kmer(w, k=6) for w in batch]
            
            inputs = tokenizer(batch_kmers, return_tensors="pt", padding=True, truncation=True, max_length=512)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
                cls_emb = outputs.last_hidden_state[:, 0, :].cpu()
                embeddings.append(cls_emb)
                
        seq_emb_unpooled = torch.cat(embeddings, dim=0) # Shape: (<=max_windows, 768)
        X_raw.append(seq_emb_unpooled)
        
    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return X_raw

# --- PyTorch Attention Model (Robust to Overfitting) ---
class AttentionPooling(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1)
        )

    def forward(self, x):
        attn_weights = self.attention(x) # (seq_len, 1)
        attn_weights = torch.softmax(attn_weights, dim=0)
        context = torch.sum(attn_weights * x, dim=0, keepdim=True) # (1, hidden_size)
        return context

class LightweightHybridAttentionClassifier(nn.Module):
    def __init__(self, esm_hidden=320, dnabert_hidden=768):
        super().__init__()
        self.esm_attn = AttentionPooling(esm_hidden)
        self.dnabert_attn = AttentionPooling(dnabert_hidden)
        
        # Projection layers to reduce dimensionality drastically before fusion
        self.esm_proj = nn.Sequential(
            nn.Linear(esm_hidden, 32),
            nn.ReLU(),
            nn.Dropout(0.3)
        )
        self.dnabert_proj = nn.Sequential(
            nn.Linear(dnabert_hidden, 32),
            nn.ReLU(),
            nn.Dropout(0.3)
        )
        
        hybrid_hidden = 32 + 32
        
        # Smaller classifier to prevent overfitting on 80 training samples
        self.classifier = nn.Sequential(
            nn.LayerNorm(hybrid_hidden),
            nn.Dropout(0.5),
            nn.Linear(hybrid_hidden, 16),
            nn.LayerNorm(16),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(16, 1)
        )

    def forward(self, x_esm, x_dnabert):
        context_esm = self.esm_attn(x_esm)
        context_dnabert = self.dnabert_attn(x_dnabert)
        
        proj_esm = self.esm_proj(context_esm)
        proj_dnabert = self.dnabert_proj(context_dnabert)
        
        context_hybrid = torch.cat([proj_esm, proj_dnabert], dim=1) # (1, 64)
        logits = self.classifier(context_hybrid) # (1, 1)
        return logits.squeeze()

# --- Dataset ---
class HybridUnpooledDataset(Dataset):
    def __init__(self, X_esm_list, X_dnabert_list, y_array):
        self.X_esm = X_esm_list
        self.X_dnabert = X_dnabert_list
        self.y = torch.tensor(y_array, dtype=torch.float32)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X_esm[idx], self.X_dnabert[idx], self.y[idx]

def collate_fn(batch):
    X_esm = [item[0] for item in batch]
    X_dnabert = [item[1] for item in batch]
    y = torch.stack([item[2] for item in batch])
    return X_esm, X_dnabert, y

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_samples", type=int, default=50, help="Number of sequences per class")
    parser.add_argument("--top_orfs", type=int, default=10, help="Max ORFs to extract per sequence")
    parser.add_argument("--max_windows", type=int, default=10, help="Max DNA windows per sequence")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    plasmid_path = DATA_DIR / "test_plasmid.fasta"
    chromosome_path = DATA_DIR / "test_chromosome.fasta"
    print(f"\nLoading {args.n_samples} samples per class...")
    plas_seqs = load_and_subsample(plasmid_path, args.n_samples, args.seed)
    chrom_seqs = load_and_subsample(chromosome_path, args.n_samples, args.seed)
    all_seqs = plas_seqs + chrom_seqs
    y = np.array([1]*len(plas_seqs) + [0]*len(chrom_seqs))

    cache_file_esm = DATA_DIR / "cache_esm_lightweight.pt"
    cache_file_dnabert = DATA_DIR / "cache_dnabert_lightweight.pt"

    if cache_file_esm.exists() and cache_file_dnabert.exists():
        print("Loading cached raw features from disk...")
        X_esm_raw = torch.load(cache_file_esm)
        X_dnabert_raw = torch.load(cache_file_dnabert)
    else:
        X_esm_raw = get_unpooled_esm_features(all_seqs, device, top_n=args.top_orfs, desc="All Sequences")
        X_dnabert_raw = get_unpooled_dnabert_features(all_seqs, device, max_windows=args.max_windows, desc="All Sequences")
        torch.save(X_esm_raw, cache_file_esm)
        torch.save(X_dnabert_raw, cache_file_dnabert)
        print("Saved raw features to cache.")

    indices = np.arange(len(y))
    idx_train, idx_test = train_test_split(indices, test_size=0.2, stratify=y, random_state=args.seed)
    
    train_dataset = HybridUnpooledDataset([X_esm_raw[i] for i in idx_train], [X_dnabert_raw[i] for i in idx_train], y[idx_train])
    test_dataset = HybridUnpooledDataset([X_esm_raw[i] for i in idx_test], [X_dnabert_raw[i] for i in idx_test], y[idx_test])
    
    train_loader = DataLoader(train_dataset, batch_size=1, shuffle=True, collate_fn=collate_fn)
    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False, collate_fn=collate_fn)

    model = LightweightHybridAttentionClassifier(esm_hidden=320, dnabert_hidden=768).to(device)
    
    # Weight decay heavily increased and LR reduced to prevent overfitting on tiny dataset
    optimizer = optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-2)
    
    # Adding pos_weight because plasmids might have different feature dynamics, but here it's balanced.
    criterion = nn.BCEWithLogitsLoss()

    print("\nTraining Lightweight Hybrid Attention Model...")
    model.train()
    for epoch in range(args.epochs):
        epoch_loss = 0
        for batch_X_esm, batch_X_dnabert, batch_y in train_loader:
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            
            logits = []
            for x_esm, x_dnabert in zip(batch_X_esm, batch_X_dnabert):
                x_esm, x_dnabert = x_esm.to(device), x_dnabert.to(device)
                logit = model(x_esm, x_dnabert)
                logits.append(logit)
            
            logits = torch.stack(logits)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            
        if (epoch + 1) % 5 == 0:
            print(f"Epoch {epoch+1}/{args.epochs} | Loss: {epoch_loss/len(train_loader):.4f}")

    print("\nEvaluating Model...")
    model.eval()
    y_preds = []
    y_trues = []
    with torch.no_grad():
        for batch_X_esm, batch_X_dnabert, batch_y in test_loader:
            for x_esm, x_dnabert in zip(batch_X_esm, batch_X_dnabert):
                x_esm, x_dnabert = x_esm.to(device), x_dnabert.to(device)
                logit = model(x_esm, x_dnabert)
                prob = torch.sigmoid(logit).item()
                y_preds.append(1 if prob > 0.5 else 0)
            y_trues.extend(batch_y.numpy())

    print("\n=== Lightweight Hybrid Attention Results ===")
    print(classification_report(y_trues, y_preds, target_names=["Chromosome", "Plasmid"]))
    print(f"Accuracy: {accuracy_score(y_trues, y_preds):.4f}")
    print(f"F1-score: {f1_score(y_trues, y_preds):.4f}")

if __name__ == "__main__":
    main()
