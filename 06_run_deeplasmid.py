#!/usr/bin/env python3
"""
06_run_deeplasmid.py
====================
Runs the billandreo/deeplasmid-cpu-ubuntu2 Docker container on the subsampled
benchmark datasets to generate predictions.
"""

import subprocess
import os
from pathlib import Path

# Important: Use absolute paths for Docker volume mounts on Windows
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw" / "benchmark_1000"
RESULTS_DIR = BASE_DIR / "results" / "deeplasmid"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_NAME = "billandreo/deeplasmid-cpu-ubuntu2"

def run_deeplasmid(input_fasta_path: Path, output_dir_path: Path):
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    # Absolute paths formatted for Windows Docker Desktop
    host_input_path = str(input_fasta_path.absolute())
    host_output_path = str(output_dir_path.absolute())
    
    container_input = "/srv/jgi-ml/classifier/dl/in.fasta"
    container_output = "/srv/jgi-ml/classifier/dl/outdir"
    
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_input_path}:{container_input}",
        "-v", f"{host_output_path}:{container_output}",
        IMAGE_NAME,
        "deeplasmid.sh", "in.fasta", "outdir"
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    print(f"Processing {input_fasta_path.name}...")
    
    try:
        # We don't use -it because we're running it automated without a TTY
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        print(f"Success! Output saved to {output_dir_path}")
        # print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running Docker command for {input_fasta_path.name}:")
        print(e.stderr)
        print(e.stdout)

def main():
    # 1. Run on Plasmids
    plasmid_fasta = DATA_DIR / "test_plasmid_1000.fasta"
    plasmid_out = RESULTS_DIR / "plasmid_out"
    if plasmid_fasta.exists():
        run_deeplasmid(plasmid_fasta, plasmid_out)
    else:
        print(f"Error: {plasmid_fasta} not found.")

    # 2. Run on Chromosomes
    chromosome_fasta = DATA_DIR / "test_chromosome_1000.fasta"
    chromosome_out = RESULTS_DIR / "chromosome_out"
    if chromosome_fasta.exists():
        run_deeplasmid(chromosome_fasta, chromosome_out)
    else:
        print(f"Error: {chromosome_fasta} not found.")

if __name__ == "__main__":
    main()
