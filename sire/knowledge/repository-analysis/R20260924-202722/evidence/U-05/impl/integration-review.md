# U-05 整体 Review 与数据库归档结果

状态：COMPLETE。U-01 至 U-05 的 R6 Review、R7 功能验收、R8 安全复核和 R9 整体 Review 均通过。

## 范围与依赖
- 清单覆盖 14 个顶层 Git 仓库、3 个无 Git 源码项目；9 个 EncoderPlotter 快照与 recalibration 的四类共享子模块纳入分析。
- U-01 至 U-04 独立执行并由 R6 复核；U-05 在依赖完成后汇总并写入数据库。
- U-01..U-03 读写集不冲突，按 SIRE 并行安排；U-04 独立分析；U-05 等待前四单元。

## R6 独立 Review 结果
- U-01 PASS：Git 状态、入口、架构与 recalibration 子模块 gitlink/缺失模块风险属实；after-build 产物路径已明确为 release/driver.bin、release/BUILD_INFO.txt，并说明未运行构建。
- U-02 PASS：五个快照的状态和子模块 pin、EP4 dirty TPB overlay、CI/dev-setup 的四项测试、IAP 默认关闭和门禁文档差异均有明确边界。
- U-03 PASS：逐版本构建/测试、0703_03 缺少 CI/dev-setup/qa_api、本地 submodule refs、未跟踪硬件脚本及 HTTP API 适用范围均已复核。
- U-04 PASS：claude-code IPC 与缺文件状态、MES README/source 差异、credential generator PBKDF2 参数/未遮蔽输入/IPC 风险均已复核。
- U-05 PASS：22 条知识记录与 5 条任务记录逐条核对；正文、来源、状态、范围与验收证据一致。

## 数据库归档与 R7 验收
- 写入前备份：@USER_HOME@/SIRE-DB-Backups/sire_vectors-20260924-205427.sqlite3，integrity_check=ok，基线为 98 knowledge、573 tasks、1,372 chunks。
- 写入后快照：@USER_HOME@/SIRE-DB-Backups/sire_vectors-20260924-211221.sqlite3，integrity_check=ok。
- 新增 22 条 knowledge_records（14 Git 仓库、3 无 Git 项目、4 子模块类别、1 总览）和 5 条 task_records；五条任务状态均为 complete。
- 语义/全文索引覆盖新增记录：新增知识 embedding 22 条；首次同步也补齐 2 条既有知识向量。
- 当前总数：120 knowledge_records、578 task_records、1,372 chunks、1,226 embeddings、5,684 keywords。R7-DB-01..05 全部 PASS。
- 语义查询分别命中 EncoderPlotter_0903_01 IAP 记录（score 0.929740）与 driverSoftware 架构记录（0.863834）；唯一 sentinel 的 FTS/向量结果均为 0。
- 所有 22 个新知识来源路径都存在；run 目录无 .env 文件，敏感赋值模式为 0 命中；没有新增全源码 chunks。PRAGMA integrity_check=ok。

## 整体 Review、优化与限制
- 覆盖完整，数据库只保存项目摘要、架构/入口、模块依赖、Git 基线、pin、构建/测试路径、风险和来源路径；未导入完整源代码、秘密、测量数据、日志或二进制。
- 按审查意见修复了分析范围与措辞：逐仓区分构建/测试；限定 HTTP IAP/qa_api 覆盖范围；区分 EP4 未提交 overlay 和 EP5 干净提交；校正 IPC 清单、sub_common 职责与凭据输出说明。
- 源码中仍需关注的风险已归档，不属于本次静态分析授权的业务代码变更：recalibration 子模块与 parent gitlink 不匹配且引用当前缺失模块；driver 首次运行可能更改 DBANK Option Bytes；driverSoftware 的版本标识不一致；EncoderPlotter Electron 配置启用 nodeIntegration 且关闭 contextIsolation；credential generator 暴露通用 exec/fs API；mes 使用 TypeORM synchronize 并启动 seed。
- 未运行仓库测试/构建/发布/固件或设备操作。测试/构建命令只作静态入口记录。R10 跳过：没有 UI、发布或设备操作路径；原因已写入 R7 清单。

## 故障与修复记录
- 首次 SQLite 写入尝试因连接处于隐式事务而执行 BEGIN IMMEDIATE 失败；显式提交连接初始化事务后重试成功，第一次没有提交记录。
- 一次 PowerShell 管道改稿造成 U-02 局部编码乱码；重写为 UTF-8 并复核 Unicode 后交独立审查者复审，最终 PASS。
- 第一次 R7 缺 query 测试 harness 用系统 GBK 解码 UTF-8 stderr 而失败；改为接收原始字节并按 UTF-8 解码后，CLI exit 2 且数据库哈希/计数保持不变。
- 上述失败均已修复，没有同一错误重试三次仍未解决的情况。

## 最终状态
- R6：U-01、U-02、U-03、U-04、U-05 全部 PASS。
- R7：数据库五项验收全部 PASS；项目测试未运行。
- R8：PASS；只存摘要，无敏感值/源码 chunks。
- R9：PASS；覆盖、依赖、风险与索引完整性均复核。
- R10：跳过，原因是本任务没有 UI/发布/设备路径。
- 知识与任务归档：完成；22 条 knowledge_records、5 条 task_records，任务状态 complete，数据库 integrity_check=ok。
