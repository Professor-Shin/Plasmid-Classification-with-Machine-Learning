# สรุปโครงงาน Plasmid Classification

เอกสารนี้สรุปสิ่งที่ทำไว้ใน repository ปัจจุบัน โดยแยกผลที่ตรวจสอบได้จากไฟล์ผลลัพธ์ออกจากข้อเสนอหรือผลทดลอง prototype ที่ยังต้องยืนยันซ้ำ

## 1. โครงงานทำอะไร

เป้าหมายคือจำแนกลำดับ DNA ของแบคทีเรียว่าเป็น **plasmid** หรือ **chromosome** เพื่อเป็นพื้นฐานสำหรับการวิเคราะห์การถ่ายโอนยีนและยีนดื้อยา โดยต้องการเปรียบเทียบวิธีที่เร็วและไม่ต้อง alignment/database หนัก กับแนวทาง deep learning ที่ใช้ contextual embedding

ใน proposal ตั้งเป้าใช้ DNA-to-protein/ORF extraction ร่วมกับ Transformer เช่น ESM แต่การพัฒนาจริงแบ่งเป็นสองแนวทาง:

1. **Baseline ที่ทำงานครบกว่า:** canonical k-mer frequency + classifiers หลายชนิด
2. **Transformer prototypes:** ESM-2 สำหรับโปรตีน, DNABERT สำหรับ DNA และ hybrid attention ที่รวมสอง modality

### เมื่อนำไปเทียบกับ proposal slide.pdf

ฉันตรวจ `proposal slide.pdf` จำนวน 34 หน้าแล้ว สไลด์ยืนยันแกนหลักของโครงงานตรงกับ repository: ปัญหาคือการแยก plasmid/chromosome ที่เกี่ยวข้องกับ AMR และ HGT, ต้องการลดการพึ่งพา alignment/database ขนาดใหญ่ และเสนอ pipeline `DNA -> ORFs -> ESM-2 embedding -> attention` ร่วมกับ `DNA -> DNABERT -> attention` แล้ว fusion ด้วย MLP

อย่างไรก็ตาม สไลด์เป็นภาพสถานะการนำเสนอ ณ เวลาหนึ่ง ไม่ใช่ source of truth ของทุกตัวเลขใน repository จึงมีความต่างที่ต้องระบุไว้:

- สไลด์ระบุชุดพัฒนาเป็น NCBI RefSeq plasmids/chromosomes 250/250 และชุดทดสอบจาก PLSDB เป็น plasmidomes 500 กับ simulated contigs 500; ขณะที่ artifacts ปัจจุบันมี full benchmark 12,372 plasmid และ 12,372 chromosome ตาม `figures/dataset_stats.json` และมีชุดย่อย 500 ต่อ class ใน `data/raw/benchmark_1000`
- สไลด์สรุป baseline ภายนอกว่า PlasClass F1 = 0.8588 และ DeepLasmid F1 = 0.8490 ซึ่งตรงกับ JSON ใน repository; แต่ตัวเลข mlPlasmid F1 = 0.5498 ในสไลด์ยังตรวจสอบจากผลลัพธ์ที่เก็บอยู่ไม่ได้ และโค้ดที่เกี่ยวข้องมี path แบบ hard-coded
- สไลด์รายงาน ESM-2 attention accuracy = 0.7500 และ F1 = 0.7619 จาก 50 sequences ต่อ class และ test 20 sequences; ตัวเลขนี้ตรงกับ `esm_attn_res.txt` และควรใช้แทนคำว่า “ประมาณ 0.76”
- สไลด์เสนอ hybrid เป็นทิศทางหลัก แต่ผลที่เก็บจริงแสดงว่า hybrid attention ได้ accuracy 0.6000, F1 = 0.4286 และ lightweight hybrid ได้ accuracy 0.6000, F1 = 0.5556 จึงยังเป็น prototype ไม่ใช่โมเดลที่ชนะ baseline
- สไลด์ระบุ next step เป็นการเพิ่ม computational power, ปรับ architecture/hyperparameters และทดลอง ensemble ซึ่งสอดคล้องกับข้อเสนอในเอกสารนี้ แต่ควรทำ evaluation protocol และ data split ให้ถูกต้องก่อนขยายโมเดล

## 2. ข้อมูลและ pipeline ที่ทำ

### Benchmark หลัก

- ใช้ PlasmidHunter benchmark (Tian et al., 2024) จาก Zenodo ไม่ใช่ชุดข้อมูลที่สร้างขึ้นเองทั้งหมด
- ใน `figures/dataset_stats.json` มี plasmid 12,372 sequences และ chromosome 12,372 sequences
- ความยาวอยู่ที่ 1,000 ถึง 100,000 bp; median 10,000 bp และ mean ประมาณ 19,981 bp ทั้งสอง class
- GC mean ต่างกันเล็กน้อย: plasmid 47.58% และ chromosome 50.90%
- `05_subsample_data.py` สุ่มข้อมูล 500 sequences ต่อ class ด้วย seed 42 เป็นชุด `benchmark_1000` (ชื่อโฟลเดอร์ไม่ตรงกับจำนวนจริง)

### Baseline pipeline

`02_explore_data.py` สร้างสถิติและกราฟเรื่อง length, GC, class balance และ length-vs-GC จากนั้น `03_baseline.py`:

- แปลง DNA เป็น canonical 5-mer frequency vector ขนาด 512 features
- แบ่งข้อมูลแบบ stratified random split 80/20
- ฝึก Logistic Regression (PlasClass-style), Linear SVM (mlplasmids-style), Random Forest และ MLP
- วัด accuracy, F1, precision, recall, AUC และเวลา train/inference
- บันทึกโมเดลที่ F1 สูงสุดใน `models/best_baseline.pkl`

`04_length_stratified_eval.py` สุ่ม fragment ความยาว 1, 5, 10, 50 และ 100 kb ต่อ class แล้วฝึก/ทดสอบใหม่ในแต่ละความยาว เพื่อดูผลเมื่อ sequence แตกเป็น contig สั้น

### External/pretrained baselines

- `08_pretrained_baselines.py` รัน PlasClass pretrained บนชุด 500 ต่อ class
- `06_run_deeplasmid.py` รัน DeepLasmid ผ่าน Docker และ `07_evaluate_deeplasmid.py` อ่านผลลัพธ์
- มีโค้ดสำหรับ mlplasmids/DeepLasmid ใน `09_evaluate_all_baselines.py` แต่ path ถูก hard-code เป็น `d:/train_baseline` จึงไม่ใช่ pipeline ที่ portable ใน workspace นี้

### Transformer prototypes

- `09_train_esm2.py` และ `10_esm_attention.py`: สแกน ORF จาก 6 reading frames, เก็บ ORF ยาวอย่างน้อย 100 amino acids, สร้าง embedding ด้วย `facebook/esm2_t6_8M_UR50D` แล้ว mean-pool หรือ attention-pool
- `11_dnabert_attention.py`: แบ่ง DNA เป็นหน้าต่าง 510 bp, tokenize เป็น 6-mers และใช้ `zhihan1996/DNA_bert_6`
- `12_hybrid_attention.py`: attention แยกใน ESM และ DNABERT แล้ว concatenate เป็น 1,088 dimensions
- `13_lightweight_hybrid.py`: เลือก top-N ORFs/หน้าต่าง, project แต่ละ modality เหลือ 32 dimensions, รวมเป็น 64 dimensions และ cache embedding เป็น `.pt`
- `14_prepare_training_data.py` ดาวน์โหลด train data จาก NCBI โดยอ่าน `prokaryotes.csv`
- `15_comprehensive_evaluation.py` เป็นการทดลองขนาดเล็กที่ใช้ train ราว 50 ตัวอย่างต่อ class, test 100 ตัวอย่างต่อ class และตัด sequence เหลือ 10 kb เพื่อให้รันได้บน CPU

## 3. ผลลัพธ์ที่ได้

### ผล baseline หลักที่ตรวจสอบได้

จาก `results/baseline_results.csv` บน full sequences:

| Model               |   Accuracy |         F1 | Precision | Recall |    AUC |
| ------------------- | ---------: | ---------: | --------: | -----: | -----: |
| Logistic Regression |     0.6260 |     0.6619 |    0.6038 | 0.7324 | 0.6754 |
| Linear SVM          |     0.7195 |     0.7272 |    0.7077 | 0.7478 | 0.7831 |
| **Random Forest**   | **0.8717** | **0.8706** |    0.8776 | 0.8638 | 0.9501 |
| MLP                 |     0.8586 |     0.8523 |    0.8918 | 0.8161 | 0.9272 |

ข้อสรุปที่รองรับได้คือ Random Forest + 5-mer เป็น baseline ที่ดีที่สุดในชุดทดลองนี้ โดยดีกว่า linear models อย่างชัดเจน และเร็วกว่าการฝึก MLP มาก (ประมาณ 13 วินาที เทียบกับ 266 วินาที)

### ผลตามความยาว fragment

จาก `results/length_stratified_results.csv`:

- 1 kb: Random Forest F1 = 0.6473; MLP สูงสุดที่ 0.6985
- 5 kb: Random Forest F1 = 0.7755
- 10 kb: Random Forest F1 = 0.8421
- 50 kb: Random Forest F1 = 0.8889
- 100 kb: Random Forest F1 = 0.9026

แนวโน้มหลักคือ k-mer profile มีสัญญาณเพียงพอขึ้นเมื่อ sequence ยาวขึ้น แต่ยังไม่ควรสรุปว่า 10 kb เป็น threshold สากล เพราะการทดลองนี้สุ่ม fragment และไม่ได้แยกตาม parent sequence อย่างอิสระ

### ผล external baselines

- PlasClass pretrained: accuracy 0.8580, F1 0.8588, precision 0.8538, recall 0.8640 จาก 1,000 sequencesใน `results/pretrained_baselines/pretrained_results.json`
- DeepLasmid: accuracy 0.8681, F1 0.8490, precision 0.9917, recall 0.7422 จาก 963 predictions ใน `results/deeplasmid/deeplasmid_metrics.json`

ผลนี้ชี้ว่า Random Forest baseline แข่งขันได้ใน benchmark นี้ แต่ยังไม่ใช่หลักฐานว่าเหนือกว่าเครื่องมือภายนอก เพราะ dataset, preprocessing, จำนวนตัวอย่าง และ evaluation protocol ไม่ได้เหมือนกันทั้งหมด

### ผล Transformer/hybrid

ผลจาก log ที่สอดคล้องกับสไลด์ (`esm_attn_res.txt`, `dnabert_attn_res.txt`, `hybrid_attn_res.txt`, `lightweight_res.txt`) มีดังนี้:

- ESM-2 attention: accuracy 0.7500, plasmid F1 = 0.7619 บนชุด 50 sequences ต่อ class, test 20 sequences
- DNABERT attention: accuracy 0.7000, plasmid F1 = 0.6250 ภายใต้ชุดทดลองลักษณะเดียวกัน
- Hybrid attention: accuracy 0.6000, plasmid F1 = 0.4286; training loss ลดถึง 0.0059 แต่ generalization ต่ำ สอดคล้องกับอาการ overfit
- Lightweight hybrid: accuracy 0.6000, plasmid F1 = 0.5556
- ใน `results/comprehensive_results.csv` มีอีกการทดลองหนึ่งที่รายงาน baseline F1 = 0.8854, hybrid F1 = 0.3757 และ lightweight hybrid F1 = 0.0 จึงต้องแยกเป็นคนละ protocol ไม่ควรนำตัวเลขมาปนกัน

ดังนั้นผล Transformer ตอนนี้ควรเรียกว่า **prototype evidence** ไม่ใช่ผลสรุปสุดท้าย เนื่องจากขนาด test เล็ก, protocol ระหว่างรายงานไม่เหมือนกัน และมีผลใน artifacts ที่ไม่ตรงกัน ผลที่ยืนยันได้เพียงว่า prototype ยังไม่ชนะ Random Forest baseline

## 4. จุดแข็งของสิ่งที่ทำสำเร็จ

- มี end-to-end baseline ที่รันซ้ำได้และบันทึก metrics/model/figures
- เปรียบเทียบทั้ง linear และ non-linear classifiers ไม่ได้หยุดที่โมเดลเดียว
- ทดลองผลกระทบของ sequence length ซึ่งใกล้กับปัญหา contig จาก metagenomic assembly
- ทดลองเปรียบเทียบกับ PlasClass pretrained และ DeepLasmid
- สร้าง prototype สำหรับ ORF + ESM-2, DNA + DNABERT และ dual-modality attention
- มีแนวคิดลดค่าใช้จ่ายด้วย top-N filtering, projection layers และ feature caching

## 5. จุดบกพร่องและความเสี่ยงที่ต้องแก้

### 5.1 Evaluation leakage จาก fragment

`04_length_stratified_eval.py` สร้างหลาย fragments จาก full sequences แล้วสุ่ม train/test ที่ระดับ fragment หาก fragments จาก parent sequence เดียวกันไปอยู่คนละฝั่ง โมเดลอาจจำลักษณะของ parent ได้ ทำให้คะแนนสูงเกินจริง วิธีแก้คือ split ตาม genome/organism/parent ก่อนสร้าง fragment และห้ามให้ parent เดียวกันข้าม train/test

### 5.2 ข้อมูล benchmark อาจมี confounder

จำนวน, ความยาว และการกระจายของสอง class ใน `dataset_stats.json` เหมือนกันอย่างผิดสังเกต และ GC/length อาจเป็นสัญญาณแยก class แทน biology ของ plasmid โดยตรง ต้องตรวจ metadata, species overlap, duplicate sequence และ near-duplicate ระหว่างชุด train/test

### 5.3 Comprehensive evaluation มี feature mismatch

ใน `03_baseline.py` vocabulary เป็น canonical k-mers แต่ extractor ที่ฝังอยู่ใน `15_comprehensive_evaluation.py` ใช้ k-mer แบบไม่ canonical และ lookup ด้วย key ตรง ๆ จึงไม่ใช่ feature representation เดียวกับตอน train ผล `Baseline (Best)` ใน `comprehensive_results.csv` จึงเปรียบเทียบกับ baseline หลักไม่ได้จนกว่าจะแก้ให้ใช้ฟังก์ชันเดียวกัน

### 5.4 Transformer ยังทดลองบนข้อมูลน้อยและ protocol ไม่คงที่

prototype หลายตัวใช้เพียง 50 หรือ 100 sequences, split เดียว และ train model head ตั้งแต่ต้น จึงมี variance สูงและเสี่ยง overfit การใช้ผลเหล่านี้สนับสนุนข้อสรุปว่า attention “พิสูจน์แล้วว่าดีกว่า” ยังเร็วเกินไป ต้องใช้ repeated/grouped split, validation set และ confidence interval

### 5.5 Preprocessing อาจทิ้งข้อมูลสำคัญ

ESM ใช้เฉพาะ ORF ยาวอย่างน้อย 100 aa จึงทิ้ง non-coding regions และ short genes; DNABERT จำกัดจำนวนหน้าต่างและหลายจุดตัด sequence ที่ 10 kb หรือใช้เฉพาะหน้าต่างต้น ๆ ปัญหานี้ยิ่งสำคัญกับ contig สั้นและ plasmid ที่มีสัญญาณกระจายตัว

### 5.6 Reproducibility และ code hygiene

- path ใน `09_evaluate_all_baselines.py` และ `parse_results.py` ผูกกับ `d:/train_baseline`
- `08_pretrained_baselines.py` มีชื่อ `benchmark_1000` แต่สร้างจาก 500 ต่อ class
- evaluator ของ DeepLasmid มีหลาย parser และจัดการ `AMBIGUOUS` ไม่เหมือนกัน
- รายงานบางฉบับอ้างผล/สคริปต์ prototype ที่ไม่ตรงกับชื่อไฟล์หรือ artifacts ปัจจุบัน
- ยังไม่มี automated tests สำหรับ data split, k-mer extraction, parser และ metric calculation
- จำนวนข้อมูลและชื่อแหล่งข้อมูลในสไลด์กับ artifacts ปัจจุบันไม่ตรงกันทั้งหมด จึงควรทำ manifest กลางที่บันทึก source, จำนวนจริง, split และวันที่สร้างผลทุกครั้ง

## 6. ควรทำอะไรต่อ ตามลำดับความสำคัญ

### ขั้นที่ 1: ทำ evaluation ให้ถูกต้องก่อน

1. กำหนด data manifest ที่มี sequence ID, species/strain, parent genome, source และ label
2. ลบ duplicate/near-duplicate และทำ group split ตาม species หรือ genome accession
3. แยก train, validation และ locked test set ก่อนสร้าง fragments
4. แก้ทุก pipeline ให้ใช้ feature extractor เดียวกัน โดยเฉพาะ canonical k-mer ใน `15_comprehensive_evaluation.py`
5. รัน repeated group splits หรืออย่างน้อย 5-fold group cross-validation พร้อม confidence interval

### ขั้นที่ 2: สร้างตาราง benchmark กลาง

ใช้ชุด test เดียวกันและ threshold/evaluation rule เดียวกันกับ Random Forest, Logistic Regression, SVM, MLP, PlasClass, DeepLasmid และ transformer models รายงาน confusion matrix, F1 ของ plasmid, macro-F1, PR-AUC, recall, runtime และ resource usage แยกตาม length bin

### ขั้นที่ 3: ทำ Transformer ให้เป็นงานวิจัยที่ยืนยันได้

- เริ่มจาก ESM-only attention เพราะ prototype ดูมีสัญญาณดีที่สุด
- ใช้ train data จริงจำนวนมากขึ้นจาก `data/train` และ freeze backbone ในรอบแรก
- เปรียบเทียบ mean pooling, attention pooling และ top-k pooling ภายใต้ split เดียวกัน
- ใช้ ablation แยกผลของ ORF selection, DNA windows, projection และ hybrid fusion
- ตรวจ performance แยกตามความยาวและ species ไม่ใช่ดูค่าเฉลี่ยเดียว

### ขั้นที่ 4: ทำระบบให้ใช้งานได้

รวม preprocessing และ inference เป็น command เดียว, เอา hard-coded paths ออก, pin model/dependency versions, บันทึก config/seed/manifest ทุกครั้ง และเพิ่ม unit tests ให้ parser กับ feature extraction ก่อนอ้างผลในรายงานฉบับสุดท้าย

## 7. ข้อสรุปสำหรับการนำเสนอ

เมื่อเทียบกับสไลด์ที่นำเสนอจริง ภาพรวมของโครงงานยังสอดคล้องกัน แต่ควรอัปเดตสาระในการนำเสนอให้แยก “ผลล่าสุดที่ตรวจสอบได้” ออกจาก “แผนงาน/ความคาดหวัง” อย่างชัดเจน สิ่งที่โครงงานพิสูจน์ได้ ณ ตอนนี้คือ **การจำแนก plasmid/chromosome ด้วย 5-mer ทำได้ดีบน benchmark นี้ โดย Random Forest ได้ F1 ประมาณ 0.87 และประสิทธิภาพลดลงชัดเจนเมื่อ sequence สั้น** และ ESM-2 attention มีผล prototype ที่น่าสนใจ (F1 = 0.7619) แต่ยังไม่สามารถสรุปว่าเหนือกว่า baseline ได้ เพราะใช้ test เพียง 20 sequences

โครงการยังไม่ได้บรรลุ claim ในสไลด์เรื่อง lightweight hybrid ที่พร้อมใช้งานหรือ hybrid ที่เป็นทางเลือกดีที่สุด ผลปัจจุบันควรนำเสนอว่าเป็นการสร้าง architecture และ proof-of-concept ที่ยังต้องยืนยันบนข้อมูลเต็มและ split ที่ป้องกัน leakage

ข้อความที่ควรใช้เป็นทิศทางต่อไปคือ: **แก้ protocol และ leakage ให้เรียบร้อยก่อน แล้วจึงขยาย ESM/DNABERT บน group-split dataset เพื่อวัดว่าการใช้ contextual representation เพิ่มประโยชน์เหนือ k-mer baseline จริงหรือไม่**

## ไฟล์อ้างอิงหลัก

- [README.md](README.md)
- [proposal.md](proposal.md)
- [03_baseline.py](03_baseline.py)
- [04_length_stratified_eval.py](04_length_stratified_eval.py)
- [09_train_esm2.py](09_train_esm2.py)
- [12_hybrid_attention.py](12_hybrid_attention.py)
- [13_lightweight_hybrid.py](13_lightweight_hybrid.py)
- [15_comprehensive_evaluation.py](15_comprehensive_evaluation.py)
- [results/evaluation_report.md](results/evaluation_report.md)
- [results/attention_evaluation_report.md](results/attention_evaluation_report.md)
- [results/comprehensive_results.csv](results/comprehensive_results.csv)
