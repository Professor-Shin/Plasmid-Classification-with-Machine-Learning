import pandas as pd
import os
import re
import time
from Bio import Entrez, SeqIO
from pathlib import Path
import numpy as np

import argparse

# --- Configuration ---
Entrez.email = "your.email@example.com"
DATA_DIR = Path("./data/train")
RAW_CSV = Path("./prokaryotes.csv")

def parse_replicons(replicon_str):
    """
    Parses the 'Replicons' column to extract accessions.
    Example: 'chromosome:CP027224.1' or 'chromosome 1:NZ_CP071311.1/CP071311.1; plasmid p.1:NZ_CP071313.1'
    Returns: list of (type, accession) tuples
    """
    if pd.isna(replicon_str):
        return []
    
    parts = replicon_str.split(";")
    results = []
    for p in parts:
        p = p.strip()
        # Find type (chromosome or plasmid)
        rtype = "chromosome" if "chromosome" in p.lower() else "plasmid" if "plasmid" in p.lower() else None
        if not rtype:
            continue
            
        # Find accession - look for things like CP027224.1 or NZ_CP071311.1
        # It's usually after ':' and might have '/' separating multiple IDs
        match = re.search(r':([^/]+)', p)
        if match:
            acc = match.group(1).strip()
            # Clean up if there are multiple IDs or extra text
            acc = acc.split(" ")[0]
            results.append((rtype, acc))
            
    return results

def download_sequence(accession, save_path):
    """Downloads a sequence from NCBI and saves as FASTA."""
    if save_path.exists():
        print(f"  [SKIP] Already exists: {save_path.name}")
        return True
        
    try:
        print(f"  [DOWNLOAD] Fetching {accession}...")
        handle = Entrez.efetch(db="nucleotide", id=accession, rettype="fasta", retmode="text")
        record = SeqIO.read(handle, "fasta")
        handle.close()
        SeqIO.write(record, save_path, "fasta")
        time.sleep(0.4)  # Be nice to NCBI (3 requests/sec limit without API key)
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to download {accession}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_samples", type=int, default=250)
    args = parser.parse_args()
    
    n_samples = args.n_samples

    # 1. Setup Directories
    (DATA_DIR / "plasmids").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "chromosomes").mkdir(parents=True, exist_ok=True)
    
    # 2. Load CSV
    print(f"Loading {RAW_CSV}...")
    df = pd.read_csv(RAW_CSV)
    
    # 3. Collect Candidates
    plasmid_accs = []
    chromosome_accs = []
    
    print("Parsing replicons...")
    for _, row in df.iterrows():
        replicons = parse_replicons(row['Replicons'])
        for rtype, acc in replicons:
            if rtype == "plasmid" and len(plasmid_accs) < n_samples:
                plasmid_accs.append(acc)
            elif rtype == "chromosome" and len(chromosome_accs) < n_samples:
                chromosome_accs.append(acc)
                
        if len(plasmid_accs) >= n_samples and len(chromosome_accs) >= n_samples:
            break
            
    print(f"Found {len(plasmid_accs)} plasmids and {len(chromosome_accs)} chromosomes candidates.")
    
    # 4. Download
    print("\nStarting downloads...")
    
    downloaded_plasmids = []
    for i, acc in enumerate(plasmid_accs):
        fname = DATA_DIR / "plasmids" / f"{acc}.fasta"
        if download_sequence(acc, fname):
            downloaded_plasmids.append(fname)
        if len(downloaded_plasmids) >= n_samples:
            break
            
    downloaded_chromosomes = []
    for i, acc in enumerate(chromosome_accs):
        fname = DATA_DIR / "chromosomes" / f"{acc}.fasta"
        if download_sequence(acc, fname):
            downloaded_chromosomes.append(fname)
        if len(downloaded_chromosomes) >= n_samples:
            break
            
    # 5. Merge into single files for training
    print("\nMerging files for training...")
    
    def merge_fastas(file_list, output_path):
        with open(output_path, "w") as out_f:
            for f in file_list:
                for record in SeqIO.parse(f, "fasta"):
                    SeqIO.write(record, out_f, "fasta")
                    
    merge_fastas(downloaded_plasmids, DATA_DIR / "train_plasmid.fasta")
    merge_fastas(downloaded_chromosomes, DATA_DIR / "train_chromosome.fasta")
    
    print(f"\n[DONE] Training data prepared in {DATA_DIR}")
    print(f"  - Plasmids: {len(downloaded_plasmids)}")
    print(f"  - Chromosomes: {len(downloaded_chromosomes)}")

if __name__ == "__main__":
    main()
