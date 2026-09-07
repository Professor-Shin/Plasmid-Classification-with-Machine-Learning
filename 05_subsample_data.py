#!/usr/bin/env python3
"""
05_subsample_data.py
====================
Subsamples the benchmark datasets to a smaller balanced set for testing computationally
expensive baseline models like Deeplasmid.
"""

import json
import random
from pathlib import Path

try:
    from Bio import SeqIO
except ImportError:
    raise ImportError("pip install biopython")

DATA_DIR = Path("./data/raw")
OUT_DIR = DATA_DIR / "benchmark_1000"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def subsample_fasta(input_fasta: Path, output_fasta: Path, n_samples: int, seed: int = 42):
    print(f"Loading {input_fasta.name}...")
    records = list(SeqIO.parse(input_fasta, "fasta"))
    
    random.seed(seed)
    sampled_records = random.sample(records, n_samples)
    
    print(f"Writing {n_samples} sampled records to {output_fasta.name}...")
    SeqIO.write(sampled_records, output_fasta, "fasta")
    
    return [rec.id for rec in sampled_records]

def main():
    plasmid_path = DATA_DIR / "test_plasmid.fasta"
    chromosome_path = DATA_DIR / "test_chromosome.fasta"
    
    plasmid_out = OUT_DIR / "test_plasmid_1000.fasta"
    chromosome_out = OUT_DIR / "test_chromosome_1000.fasta"
    
    N_SAMPLES = 500
    SEED = 42
    
    plasmid_ids = subsample_fasta(plasmid_path, plasmid_out, N_SAMPLES, seed=SEED)
    chromosome_ids = subsample_fasta(chromosome_path, chromosome_out, N_SAMPLES, seed=SEED)
    
    # Save the split IDs for future benchmarking consistency
    split_info = {
        "seed": SEED,
        "n_samples_per_class": N_SAMPLES,
        "plasmid_ids": plasmid_ids,
        "chromosome_ids": chromosome_ids
    }
    
    with open(OUT_DIR / "subsample_ids.json", "w") as f:
        json.dump(split_info, f, indent=2)
        
    print(f"Subsampling complete. Split information saved to {OUT_DIR / 'subsample_ids.json'}")

if __name__ == "__main__":
    main()
