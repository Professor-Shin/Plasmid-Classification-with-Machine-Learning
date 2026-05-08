import os
from Bio import SeqIO

raw_dir = r"d:\files\data\raw\benchmark_data\simulated_contigs"
out_plasmid = r"d:\files\data\raw\test_plasmid.fasta"
out_chromosome = r"d:\files\data\raw\test_chromosome.fasta"

plasmids = []
chromosomes = []

for f in os.listdir(raw_dir):
    path = os.path.join(raw_dir, f)
    if not os.path.isfile(path): continue
    for rec in SeqIO.parse(path, "fasta"):
        desc = rec.description.lower()
        if "plasmid" in desc:
            plasmids.append(rec)
        elif "chromosome" in desc:
            chromosomes.append(rec)

SeqIO.write(plasmids, out_plasmid, "fasta")
SeqIO.write(chromosomes, out_chromosome, "fasta")
print(f"Saved {len(plasmids)} plasmids and {len(chromosomes)} chromosomes.")
