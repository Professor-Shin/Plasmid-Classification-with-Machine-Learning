# เอกสารประกอบสไลด์ Recap โครงงาน

ไฟล์นี้ใช้พูดประกอบ `project_recap_for_advisor.pptx` ในการคุยกับอาจารย์ เป้าหมายของการคุยครั้งนี้ไม่ใช่การนำเสนอว่าโมเดลสุดท้ายเสร็จแล้ว แต่เพื่อขอความเห็นและล็อกคำถามวิจัย, data split, baseline และชุดการทดลองที่จะทำต่อ

## แกนที่ควรย้ำ

โครงงานมี baseline ที่ทำงานแล้วและมีผลที่ชัดเจน แต่ proposed method ยังอยู่ในขั้น prototype โดยเฉพาะส่วน `Protein Embedding -> Attention + MLP` ที่ยังไม่ได้ validate บน full dataset ภายใต้ protocol เดียวกับ baseline

อย่าใช้ผล prototype ขนาดเล็กเพื่อสรุปว่า ESM-2 หรือ attention ดีกว่า Random Forest แล้ว ให้พูดว่าเป็นสัญญาณเบื้องต้นที่ทำให้ควรทดลองต่อ

## Notes รายสไลด์

### Slide 1: Project Recap

เปิดการคุยว่าเป็นการ recap สถานะจริงและขอ decision สำหรับงานระยะต่อไป

### Slide 2: Research question and motivation

อธิบายโจทย์ชีววิทยาอย่างสั้น: plasmid เป็นพาหะสำคัญของ AMR และ HGT จึงต้องการจำแนก plasmid กับ chromosome จาก DNA sequence

ประโยคสำคัญคือ “เราต้องการวัดว่า contextual protein representation ช่วยเพิ่มประโยชน์เหนือ k-mer baseline จริงหรือไม่”

### Slide 3: Current progress

แบ่งสถานะเป็นสามกลุ่ม:

- ทำแล้ว: data exploration, baseline, external tools, prototype architecture
- กำลังทำ: protein tokenization, ESM-2 embedding, attention design, fair comparison
- ยังไม่มีหลักฐาน: Attention + MLP บน full data, generalization ข้าม species, final model

การแบ่งแบบนี้ช่วยป้องกันไม่ให้ architecture ใน proposal ถูกเข้าใจว่าเป็นระบบที่เสร็จแล้ว

### Slide 4: Data and evaluation setup

ชี้แจงว่ามีหลาย protocol ใน project:

- full benchmark ใน artifacts: 12,372 ต่อ class
- development data จาก NCBI: 250 ต่อ class
- prototype attention: 50 ต่อ class และ test 20 sequences

ต้องขอให้อาจารย์ช่วยเลือก protocol หลักสำหรับรายงานฉบับสุดท้าย เพราะตัวเลขจากคนละ protocol เทียบกันไม่ได้

### Slide 5: Baseline results

ผลหลักจาก `results/baseline_results.csv`:

- Random Forest: Accuracy 0.8717, F1 0.8706, AUC 0.9501
- MLP: F1 0.8523
- Linear SVM: F1 0.7272
- Logistic Regression: F1 0.6619

ดังนั้น Random Forest + canonical 5-mer คือ baseline ที่ต้องชนะหรืออย่างน้อยต้องอธิบาย trade-off ให้ได้ หาก proposed method จะมีความซับซ้อนมากกว่า

### Slide 6: External and literature baselines

หน้านี้ต้องแยกออกจากตาราง baseline ที่เราฝึกเอง เพื่อไม่ให้ดูเหมือนใช้ข้อมูลหรือ protocol เดียวกันทั้งหมด:

| Method                 | สถานะใน repository                           |               ผลที่มี | ประเด็นสำคัญ                               |
| ---------------------- | -------------------------------------------- | --------------------: | ------------------------------------------ |
| PlasClass              | รันจริง                                      |           F1 = 0.8588 | pretrained และ lightweight                 |
| DeepLasmid             | รันจริงผ่าน Docker                           |           F1 = 0.8490 | precision สูง แต่ recall ต่ำกว่า           |
| mlplasmids             | มี runner code แต่ไม่มี output ที่ตรวจสอบได้ | สไลด์ระบุ F1 = 0.5498 | ต้องใช้ Docker/R และมีข้อจำกัดด้าน species |
| PlasmidHunter / PLASMe | ยังไม่ได้รันใน workspace                     |         ไม่มีผล local | alignment/database และ dependency สูง      |

ประเด็นสำคัญคือ **ไม่มีวิธีใดถูกตัดออกเพราะอ่อนแอโดยอัตโนมัติ** ปัญหาปัจจุบันคือ reproducibility, dependency, path ที่ hard-code และ protocol ไม่ตรงกัน ส่วน DeepLasmid กับ PlasClass มีผลเบื้องต้นแล้ว แต่ยังไม่ควรจัดอันดับเทียบกับ RF จนกว่าจะใช้ test set และ metric rule เดียวกัน

### Slide 7: Baseline interpretation

ผลตาม fragment length แสดงว่า RF F1 เพิ่มจาก 0.6473 ที่ 1 kb เป็น 0.9026 ที่ 100 kb จึงมี motivation ให้ contextual model ช่วยใน short contig

แต่ต้องพูด caveat ว่าการสร้าง fragment และ random split ในโค้ดปัจจุบันอาจทำให้ parent sequence เดียวกันข้าม train/test ได้ งานต่อไปต้อง split ตาม parent genome หรือ species ก่อนสร้าง fragment

### Slide 8: Proposed method

อธิบาย architecture ที่ต้องการทดสอบ:

1. DNA -> ORF -> amino acid tokens -> ESM-2 embedding
2. attention pooling เพื่อ aggregate ORF embeddings
3. MLP classifier
4. อาจมี DNA/DNABERT branch แล้วค่อย fusion เป็น hybrid

ให้เน้นว่า protein branch เป็นแกนที่ควรเริ่มก่อน เพราะมี prototype ESM-2 attention ที่พอมีสัญญาณ ส่วน hybrid มีความเสี่ยง overfit สูงกว่า

### Slide 9: Assumptions

สมมติฐานต้องถูกเขียนเป็นสิ่งที่จะทดสอบ ไม่ใช่ข้อเท็จจริง:

- coding region จำนวนมากอาจทำให้ protein representation มีประโยชน์
- pretrained ESM-2 อาจให้ contextual signal ที่ k-mer ไม่มี
- attention อาจช่วยเลือก ORF ที่สำคัญกว่า mean pooling

คำว่า “83%-90% coding region” ควรใช้เป็น motivation หรือ literature-backed assumption เท่านั้นจนกว่าจะมี citation และการวัดกับ dataset ของเราเอง เพราะตัวเลขอาจเปลี่ยนตามชนิดของแบคทีเรียและ definition ของ coding region

### Slide 10: Limitations

จุดที่ควรยอมรับตรง ๆ:

- ทดลอง Transformer ด้วย 50 + / 50 - เป็นหลัก
- test มีเพียง 20 sequences ใน attention log
- split เดียวและไม่มี confidence interval
- มีความเสี่ยง fragment leakage
- comprehensive evaluator ใช้ k-mer extraction ไม่ตรงกับ canonical vocabulary ของโมเดล baseline

ผล ESM-2 attention ที่ F1 = 0.7619 จึงเป็น preliminary result ไม่ใช่ final comparison

### Slide 11: Next experiment

ลำดับที่แนะนำ:

1. ทำ manifest ของ sequence ID, source, species, parent genome และ label
2. กำหนด group split ก่อนสร้าง fragment
3. ใช้ evaluation protocol เดียวกับทุก model
4. ทำ ablation: mean pooling vs attention, ESM-only vs DNABERT-only vs hybrid
5. จึงค่อย scale บน server/full data และรายงาน repeated runs กับ confidence interval

### Slide 12: Questions for advisor

ต้องพยายามให้ออกจากการประชุมด้วยคำตอบอย่างน้อย 4 เรื่อง:

- final research question จะเน้น ESM-only หรือ hybrid
- split หลักเป็นระดับ sequence, species หรือ genome
- ชุด test และ metric หลักคืออะไร
- เกณฑ์ใดถือว่า proposed method ดีกว่า baseline

คำถามเรื่อง “ต้องได้กี่เปอร์เซ็นต์” ควรเปลี่ยนเป็น “ต้องเพิ่ม metric เท่าไรภายใต้ protocol เดียวกัน และต้องแลกกับ runtime/complexity เท่าไร”

### Slide 13: Takeaway

ปิดด้วยข้อสรุปสามบรรทัด:

1. Baseline และ code base พร้อมต่อยอด
2. Proposed representation/attention มีเหตุผลและมี prototype แต่ยังไม่ validate
3. งานต่อไปต้องล็อก evaluation protocol ก่อนเพิ่มความซับซ้อนของโมเดล

## ตัวเลขอ้างอิงจาก repository

| รายการ                  |                                  ค่า | แหล่ง                                                  |
| ----------------------- | -----------------------------------: | ------------------------------------------------------ |
| Full benchmark          | 12,372 plasmids + 12,372 chromosomes | `figures/dataset_stats.json`                           |
| Random Forest F1        |                               0.8706 | `results/baseline_results.csv`                         |
| RF F1 ที่ 1 kb          |                               0.6473 | `results/length_stratified_results.csv`                |
| RF F1 ที่ 100 kb        |                               0.9026 | `results/length_stratified_results.csv`                |
| PlasClass pretrained F1 |                               0.8588 | `results/pretrained_baselines/pretrained_results.json` |
| DeepLasmid F1           |                               0.8490 | `results/deeplasmid/deeplasmid_metrics.json`           |
| mlplasmids F1           |                       0.5498 (สไลด์) | ยังไม่มี raw output ใน repository                      |
| ESM-2 attention F1      |                               0.7619 | `esm_attn_res.txt`                                     |
| Hybrid attention F1     |                               0.4286 | `hybrid_attn_res.txt`                                  |
| Lightweight hybrid F1   |                               0.5556 | `lightweight_res.txt`                                  |

## ประโยคตอบคำถามที่อาจารย์ถาม

**ถาม: ตอนนี้ proposed method ดีกว่า baseline หรือยัง?**  
ตอบ: ยังไม่สรุปครับ ผล ESM-2 attention เบื้องต้นได้ F1 0.7619 จาก test เพียง 20 sequences ขณะที่ RF baseline ได้ 0.8706 จาก full benchmark protocol คนละชุด จึงต้อง rerun ภายใต้ split และ test set เดียวกัน

**ถาม: ทำไมต้องใช้ protein embedding?**  
ตอบ: เป็นสมมติฐานว่าการแปลง coding region เป็น protein และใช้ pretrained ESM-2 อาจ expose functional context ที่ frequency-based k-mer ไม่ได้ capture แต่จะพิสูจน์ด้วย ablation ไม่ใช่ assume ว่าดีกว่าโดยอัตโนมัติ

**ถาม: ทำไมต้อง attention?**  
ตอบ: mean pooling ให้น้ำหนักทุก ORF เท่ากัน เราต้องการทดสอบว่า attention ช่วยเลือก ORF ที่ informative ได้หรือไม่ โดยต้องเปรียบเทียบกับ mean pooling ภายใต้ data split เดียวกัน

**ถาม: ทำไมยังใช้ข้อมูลน้อย?**  
ตอบ: เป็นข้อจำกัดด้าน compute ใน prototype ปัจจุบัน ขั้นต่อไปคือย้ายไปรัน server, ใช้ data เต็ม และเก็บ cache embedding เพื่อให้ทดลองซ้ำได้
