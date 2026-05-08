#!/usr/bin/env python3
"""
11_dnabert_attention.py
=======================
DNABERT Prototype with Trainable Attention Mechanism.
Replaces simple Mean Pooling with a neural attention layer to focus on critical DNA windows.
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
from transformers import BertTokenizer, BertModel
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score
from tqdm import tqdm

DATA_DIR = Path("./data/raw")
DNABERT_MODEL_NAME = "zhihan1996/DNA_bert_6"

# --- Common Utilities ---
def load_and_subsample(fasta_path, n_samples, seed):
    records = list(SeqIO.parse(str(fasta_path), "fasta"))
    rng = np.random.default_rng(seed)
    if len(records) > n_samples:
        indices = rng.choice(len(records), size=n_samples, replace=False)
        records = [records[i] for i in indices]
    return [str(r.seq).upper() for r in records]

def seq2kmer(seq, k=6):
    return " ".join([seq[i:i+k] for i in range(len(seq) - k + 1)])

# --- Feature Extraction (Unpooled) ---
def get_unpooled_dnabert_features(seqs, device, max_windows=20, desc=""):
    print(f"\nLoading {DNABERT_MODEL_NAME} for Feature Extraction...")
    tokenizer = BertTokenizer.from_pretrained(DNABERT_MODEL_NAME)
    model = BertModel.from_pretrained(DNABERT_MODEL_NAME).to(device)
    model.eval()
    
    X_raw = []
    window_size = 510
    
    for seq in tqdm(seqs, desc=f"DNABERT Extraction {desc}"):
        seq = "".join([c for c in seq if c in "ATGC"])
        if len(seq) < 10:
            X_raw.append(torch.zeros(1, model.config.hidden_size))
            continue
            
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
                
        seq_emb_unpooled = torch.cat(embeddings, dim=0) # Shape: (num_windows, 768)
        X_raw.append(seq_emb_unpooled)
        
    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return X_raw

# --- PyTorch Attention Model ---
class AttentionPooling(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1)
        )

    def forward(self, x):
        # x shape: (seq_len, hidden_size)
        attn_weights = self.attention(x) # (seq_len, 1)
        attn_weights = torch.softmax(attn_weights, dim=0)
        context = torch.sum(attn_weights * x, dim=0, keepdim=True) # (1, hidden_size)
        return context

class DNABERTAttentionClassifier(nn.Module):
    def __init__(self, hidden_size=768):
        super().__init__()
        self.attn_pool = AttentionPooling(hidden_size)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1)
        )

    def forward(self, x):
        # x is (seq_len, hidden_size)
        context = self.attn_pool(x) # (1, hidden_size)
        logits = self.classifier(context) # (1, 1)
        return logits.squeeze()

# --- Dataset ---
class UnpooledDataset(Dataset):
    def __init__(self, X_list, y_array):
        self.X = X_list
        self.y = torch.tensor(y_array, dtype=torch.float32)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

def collate_fn(batch):
    X = [item[0] for item in batch]
    y = torch.stack([item[1] for item in batch])
    return X, y

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_samples", type=int, default=50, help="Number of sequences per class")
    parser.add_argument("--max_windows", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    # Reproducibility
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Load data
    plasmid_path = DATA_DIR / "test_plasmid.fasta"
    chromosome_path = DATA_DIR / "test_chromosome.fasta"
    print(f"\nLoading {args.n_samples} samples per class...")
    plas_seqs = load_and_subsample(plasmid_path, args.n_samples, args.seed)
    chrom_seqs = load_and_subsample(chromosome_path, args.n_samples, args.seed)
    all_seqs = plas_seqs + chrom_seqs
    y = np.array([1]*len(plas_seqs) + [0]*len(chrom_seqs))

    # Extract Unpooled Features
    X_raw = get_unpooled_dnabert_features(all_seqs, device, max_windows=args.max_windows, desc="All Sequences")

    # Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X_raw, y, test_size=0.2, stratify=y, random_state=args.seed)
    
    train_dataset = UnpooledDataset(X_train, y_train)
    test_dataset = UnpooledDataset(X_test, y_test)
    
    train_loader = DataLoader(train_dataset, batch_size=1, shuffle=True, collate_fn=collate_fn)
    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False, collate_fn=collate_fn)

    # Initialize Model
    model = DNABERTAttentionClassifier(hidden_size=768).to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    print("\nTraining Attention Model...")
    model.train()
    for epoch in range(args.epochs):
        epoch_loss = 0
        for batch_X, batch_y in train_loader:
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            
            logits = []
            for x in batch_X:
                x = x.to(device)
                logit = model(x)
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
        for batch_X, batch_y in test_loader:
            for x in batch_X:
                x = x.to(device)
                logit = model(x)
                prob = torch.sigmoid(logit).item()
                y_preds.append(1 if prob > 0.5 else 0)
            y_trues.extend(batch_y.numpy())

    print("\n=== DNABERT Attention Prototype Results ===")
    print(classification_report(y_trues, y_preds, target_names=["Chromosome", "Plasmid"]))
    print(f"Accuracy: {accuracy_score(y_trues, y_preds):.4f}")
    print(f"F1-score: {f1_score(y_trues, y_preds):.4f}")

if __name__ == "__main__":
    main()
