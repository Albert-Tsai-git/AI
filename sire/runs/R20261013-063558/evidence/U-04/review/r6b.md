# R6B 检索可用性 — F-056
必须改：关键词补 黑屏 / 起不来 / npm start / nsis。已执行；其余按评审意见可不改。

评审给出的机制级实测（判据来自 sire_vector_db.py 与 sire_kb.py）：
- 语义向量只吃 title + 关键词行 + body[:1500]，窗外的硬结论靠关键词行召回；
- `chunks()` 按整文件 1800/240 切，不与记录边界对齐，故关键小节要自带定位语；
- `sync_knowledge_records` 只取正文里第一条含「关键词」的行 → 实测七条各只有一行，无冲突；
- `sire_kb.py` 的 exact 匹配不按空格切 token，多词短语拿不到分 → 关键词一律拆成单词或标识符；
- 检索是 DB 优先、库空才回退 md → 未 index 前 search 取不到新记录，属预期。