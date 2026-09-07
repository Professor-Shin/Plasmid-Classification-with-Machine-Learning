# Notes สำหรับ `project_recap_siwak_ci.pptx`

Deck นี้ปรับตาม The Siwak System CI Guideline: ใช้พื้น Alabaster White `#F8F9FA`, ตัวอักษร Charcoal `#202124`, Active Green `#00C853`, Ocean Blue `#1A73E8`, Warm Orange `#FF5722`, Sunny Yellow `#FBBC05`, grid บาง, card มุมโค้ง และลำดับข้อมูลแบบอ่านจากซ้ายไปขวา

เป้าหมายของการคุยคือขอให้ได้ข้อสรุปเรื่อง research question, data split, baseline set และ minimum experiment ไม่ใช่ประกาศว่า proposed model ชนะแล้ว

## ลำดับการพูด

### 1. Project recap // next experiment

เปิดด้วยสถานะจริง: baseline พร้อมแล้ว, proposed method มี prototype แล้ว, แต่ยังต้อง validate บน full data และ protocol เดียวกัน

### 2. What are we trying to answer?

โจทย์คือจำแนก plasmid/chromosome เพื่อประโยชน์ต่อการศึกษาการแพร่ AMR ผ่าน HGT คำถามวิจัยคือ protein representation + attention เพิ่มคุณค่าจาก k-mer baseline ได้จริงหรือไม่

### 3. What is ready?

แยกสถานะเป็น 3 กลุ่ม:

- Done: data exploration, k-mer/ML baselines, PlasClass และ DeepLasmid เบื้องต้น
- Prototype: ESM-2, DNABERT, attention และ hybrid fusion
- Open: Attention + MLP บน full data, leakage-safe evaluation, generalization และ final claim

### 4. Name the protocol

ต้องไม่ปน protocol:

- Full benchmark: 12,372 plasmids + 12,372 chromosomes
- Development data: 250 + 250 จาก NCBI RefSeq-derived data
- Attention prototype: 50 + 50 และ held-out test 20 sequences

ทุกตัวเลขในรายงานสุดท้ายควรระบุ source, sample count, split และ fragment policy

### 5. What does the baseline say?

ผล `results/baseline_results.csv`:

- Random Forest: Accuracy 0.8717, F1 0.8706, AUC 0.9501
- MLP: F1 0.8523
- Linear SVM: F1 0.7272
- Logistic Regression: F1 0.6619

ผลตามความยาว: RF F1 = 0.6473 ที่ 1 kb และ 0.9026 ที่ 100 kb จุดนี้เป็น motivation ให้ทดสอบ contextual model กับ short contigs แต่ต้องแก้ความเสี่ยง fragment leakage ก่อน

### 6. Keep the comparison honest

หน้านี้แยก external/literature tools ออกจากโมเดลที่เราฝึกเอง:

| Method                 | สถานะ                                       |                 ผล |
| ---------------------- | ------------------------------------------- | -----------------: |
| PlasClass              | รันจริงใน repo                              |          F1 0.8588 |
| DeepLasmid             | รันจริงผ่าน Docker                          |          F1 0.8490 |
| mlplasmids             | มี runner แต่ไม่มี raw output ตรวจสอบซ้ำได้ | F1 0.5498 จากสไลด์ |
| PlasmidHunter / PLASMe | ยังไม่ได้รัน                                |      ไม่มีผล local |

อย่าพูดว่าเครื่องมือที่ไม่มีผล local อ่อนแอ ให้พูดว่ายังขาด reproducible run, dependency setup หรือ protocol ที่เทียบกันได้

### 7. From DNA to context

อธิบาย proposed pipeline:

`DNA -> ORF -> amino-acid tokens -> ESM-2 embedding -> attention pooling -> MLP`

DNABERT เป็น optional second branch สำหรับ ablation/hybrid ไม่ควรทำให้ scope แรกใหญ่เกินไป

### 8. Test the assumptions

สมมติฐาน 3 ข้อ:

1. protein อาจ expose functional signal ที่ k-mer ไม่เห็น
2. pretrained ESM-2 อาจให้ contextual representation ที่มีประโยชน์กว่า count/raw token
3. attention อาจเลือก informative ORF ได้ดีกว่า mean pooling

ทั้งหมดเป็น hypothesis ไม่ใช่ conclusion และต้องพิสูจน์ด้วย ablation

### 9. Lock the evidence

ลำดับงานต่อไป:

1. ทำ manifest: ID, source, species, parent genome, label
2. group split ก่อนสร้าง fragment เพื่อป้องกัน leakage
3. ใช้ test setและ metric rule เดียวกันกับทุก model
4. ทำ ablation: mean vs attention, ESM-only vs DNABERT-only vs hybrid
5. ค่อย scale บน server/full data และทำ repeated runs พร้อม confidence interval

### 10. What should we lock today?

ขอ decision จากอาจารย์ 3 เรื่อง:

- scope: ESM-only หรือ hybrid เป็น main contribution
- split: sequence, genome, species หรือ parent group
- success: F1/recall/PR-AUC/runtime และเกณฑ์ improvement เหนือ RF F1 = 0.8706

## ประโยคตอบคำถามสำคัญ

**ทำไมยังไม่มีผล proposed method ที่ชนะ baseline?**  
เพราะ ESM-2 attention ตอนนี้ได้ F1 0.7619 จาก test เพียง 20 sequences และใช้ protocol คนละชุดกับ RF จึงยังสรุป superiority ไม่ได้

**ทำไมต้อง protein embedding?**  
เป็นสมมติฐานว่า coding region ที่แปลงเป็น protein อาจเปิดเผย functional context ที่ k-mer frequency ไม่ capture ต้องยืนยันด้วย ablation

**ทำไมต้อง attention?**  
mean pooling ให้น้ำหนักทุก ORF เท่ากัน จึงต้องทดสอบว่า attention ช่วยเลือก ORF ที่ informative กว่าได้หรือไม่

**ทำไมไม่รวมทุก external tool ในตารางเดียว?**  
เพราะบางตัวมีผลจริงแล้ว แต่ dataset, preprocessing, threshold และจำนวน predictions ไม่เท่ากัน การรวมทันทีจะทำให้ดูเหมือนเป็น head-to-head comparison ทั้งที่ยังไม่ใช่
