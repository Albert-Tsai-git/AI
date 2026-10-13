# G0 知识检索

- 检索词：飞书 卡片 发送 失败 重试 outbox 阻塞 / Qoder Stop 钩子 桌面轮次 上报
- 命中：P-20260932（SIRE 遥测三端采集缺口与修复）、F-027（飞书 ⇄ Claude Code 双向闭环：Stop Hook 发卡片、msg_map 回帖续跑）、E-011/E-012（sire_qoder install/verify 判据）、P-20260931（RSI 半生效与强制化）
- 判定：部分可参考
- 依据：F-027 已有「桌面一轮结束 → Stop Hook 取最后一条 assistant 原文 → 飞书卡片」的完整Claude 侧先例，卡片构造（标题=✅执行者·目录名，正文分块、≤800 字）可直接复用；但按 `session_id` 保序的 outbox 头阻塞、Qoder stdin 的 GBK 解码、钩子列表在会话 initialize 快照这三点库里没有记录，属本轮新增。
