# U-09 检索验收现场输出

```
knowledge_records: 156
chunks: 7908
keywords: 24981
task_records: 2818
integrity_check: ok
 入库: ('F-050', 'DPB单圈标定采集圆环置灰', 'F', 'backend', 'reference', 'global', 61)
 入库: ('F-051', 'ECharts采集图例说明与禁用圈独立深灰', 'F', 'frontend', 'reference', 'global', 61)
 入库: ('F-052', '下线检测信息确认人工决定与订单号录入', 'F', 'embedded', 'reference', 'global', 54)
 入库: ('F-053', 'driverSoftware2 后端地图：server.py 装配、reader 三变体与运行形态', 'F', 'embedded', 'task', 'global', 312)
 入库: ('F-054', 'driverSoftware2 协议层与固件档案门控：帧/命令/寄存器/profile 四层与新增命令链路', 'F', 'embedded', 'reference', 'global', 323)
 入库: ('F-055', 'driverSoftware2 前端地图：13 页清单、路由注册五处、REST/WS 与示波器 uPlot 图表', 'F', 'embedded', 'reference', 'global', 367)
 入库: ('F-056', 'driverSoftware2 Electron 壳：拉起后端、端口回执与窗口安全项', 'F', 'frontend', 'reference', 'global', 346)
 入库: ('F-057', 'driverSoftware2 测试分层、CI 门禁与构建发布（旧前端随 server.dist 走的根因）', 'F', 'embedded', 'reference', 'global', 628)
 入库: ('F-058', 'driverSoftware2 下线检测（产线出厂检测）功能全貌与 duoji 口径', 'F', 'embedded', 'reference', 'global', 421)
 入库: ('F-059', 'driverSoftware2 文档三层地图、协作上下文与三条自验路径', 'F', 'embedded', 'reference', 'global', 426)
最新备份: snapshot-stage-R20260925-053031.sqlite3 76197888 bytes

=== 向量检索（limit 5）===
后端 reader 双形态 端口 无响应
   top5=[('F-053', 0.9539), ('P-018', 0.6693), ('H-004', 0.6502), ('F-059', 0.5735), ('全局功能开发记录 (F)', 0.5634)]  新记录命中=[('F-053', 0.9539), ('F-059', 0.5735)]  PASS
协议 寄存器 固件档案 V3.3 新加命令
   top5=[('F-054', 0.8718), ('P-20260926', 0.8184), ('KB-SOL-20260921-REGREAD-ID15', 0.7307), ('H-004', 0.7276), ('knowledge:why-reg-read-fails', 0.7249)]  新记录命中=[('F-054', 0.8718)]  PASS
前端 页面 注册 示波器 切页
   top5=[('F-055', 0.8815), ('P-020#2', 0.7854), ('P-025', 0.7354), ('全局功能开发记录 (F)', 0.6099), ('F-FRONTEND-MINPLAN', 0.4802)]  新记录命中=[('F-055', 0.8815)]  PASS
Electron 壳 启动 端口 黑屏
   top5=[('F-056', 0.9519), ('K-REPO-DRIVERSOFTWARE-20260924', 0.6609), ('全局功能开发记录 (F)', 0.6525), ('K-REPO-CLAUDE-CODE-20260924', 0.6474), ('K-REPO-CREDENTIAL-GENERATOR-20260924', 0.6241)]  新记录命中=[('F-056', 0.9519)]  PASS
测试 打包 旧前端 CI 发布
   top5=[('F-057', 0.9746), ('F-024', 0.7011), ('E-007', 0.6989), ('全局功能开发记录 (F)', 0.6772), ('F-056', 0.602)]  新记录命中=[('F-057', 0.9746), ('F-056', 0.602)]  PASS
下线检测 坏点 额定扭矩 建零
   top5=[('F-058', 0.9875), ('F-052', 0.7192), ('全局功能开发记录 (F)', 0.6371), ('F-055', 0.4616), ('P-019', 0.418)]  新记录命中=[('F-058', 0.9875), ('F-055', 0.4616)]  PASS
文档 必读 skill 缺陷池 真机台账
   top5=[('F-059', 0.949), ('全局功能开发记录 (F)', 0.6751), ('F-024', 0.6208), ('全局功能开发记录 (F)', 0.5767), ('全局功能开发记录 (F)', 0.5729)]  新记录命中=[('F-059', 0.949)]  PASS

=== 关键词检索（sire_kb search, top5）===
后端 reader 双形态 端口 无响应
   top5=['F-053', 'P-018', 'F-056', 'F-010', 'P-012']  PASS
协议 寄存器 固件档案 V3.3 新加命令
   top5=['F-054', 'P-20260926', 'K-servo-fw-host-compatibility-register-read', 'F-MD-20260924-001']  PASS
前端 页面 注册 示波器 切页
   top5=['F-055', 'F-057', 'F-FRONTEND-MINPLAN', 'P-020#2', 'P-025']  PASS
Electron 壳 启动 端口 黑屏
   top5=['F-056', 'F-053', 'K-REPO-CLAUDE-CODE-20260924', 'K-REPO-DRIVERSOFTWARE-20260924', 'P-001']  PASS
测试 打包 旧前端 CI 发布
   top5=['F-057', 'F-024', 'E-007', 'F-046', 'H-004']  PASS
下线检测 坏点 额定扭矩 建零
   top5=['F-058', 'F-052', 'F-053', 'F-055', 'F-057']  PASS
文档 必读 skill 缺陷池 真机台账
   top5=['F-059', 'F-043', 'F-042', 'K-driver-v345-doc-drift', 'E-008']  PASS

=== 新旧对比（同一问法）===
   top5: [('K-CODEBASE-MAP-20260924', 0.951), ('K-26b560f247dd', 0.8083), ('F-019', 0.7944), ('F-042', 0.7672), ('F-043', 0.7241)]
   旧摘要 K-REPO-DRIVERSOFTWARE 名次: 未进前5 | 新记录名次: {}

总判定: PASS

```
