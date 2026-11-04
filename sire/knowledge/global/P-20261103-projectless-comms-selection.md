### P-20261103: Projectless 聊天开启协作时先确定项目，不凭旧 active 标记选通道

**日期**: 2026-11-04
**项目**: SIRE / 跨项目本机协作通讯
**关键词**: projectless, Claude, Codex, 协作通讯, 通道选择, active, last_activity, 会话绑定, 空闲超时

**需求场景 / 现象**: 用户在未关联项目的 Codex 聊天说开始与 Claude 协作。共享通讯目录有多个历史项目；只读发现时唯一保存为 active=true 的 Claude 状态来自前一天，且 persistent=false、last_activity 已超过默认一小时空闲期。该标记不足以证明当前在线，也不足以决定用户指向哪个项目。

**根因**: 通讯状态是保存的会话状态；项目选择缺少上下文时，历史 active 标记与用户本次目标没有确定关系。生成的 projectless 工作目录也不是用户指定的业务项目。

**方案 / 架构**: 先只读项目、绑定和会话元数据；不读取其他会话消息正文、不对猜测的项目执行 start 或 resume。向用户只询问本次项目目录或通道。用户明确后，用当前聊天真实 thread id 在该项目执行 session start，再按统一协议 resume、展示并处理未读消息、发送启动通知和配置兜底心跳。

**关键文件与接口**:
- workflow/shared/sire/references/comms-protocol.md：启动、绑定、原文展示、去重与心跳规则。
- workflow/shared/sire/scripts/sire_comms.py：projects、session start、resume、send、ack。
- sire_paths.comms_dir() 下 projects/<项目>/bindings.json、session_Claude.json：只读发现的元数据；每次核对 persistent、last_activity 与更新时间。

**实施步骤**: 读取当前聊天身份和候选元数据；项目不明则询问用户，同时继续独立准备；取得项目后只以本端身份绑定，不代替 Claude 启动或重绑；按当前项目和会话配置单个兜底心跳，默认保留一小时空闲自动结束。

**验证方法**: 本次用户指定 MES 后，真实 start 返回 active=true、persistent=false；只读绑定文件和心跳配置确认目标项目与当前聊天一致；启动通知实际发送，收到的 info 实际确认。独立 R6/R8 静态复核通过。端到端送达与定时触发未测试，不能由配置成功推断为通过。

**踩坑**: 不把旧 active=true 一律当成在线或一律当成过期；结合时间和持久模式读状态，同时由用户明确本次目标。不要向知识记录固化一次性的会话 id。

**状态**: 已完成
