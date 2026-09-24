# 全局开发习惯 / 经验 (H)

### H-004: 硬件联调排查纪律 (来自 v3.4.6 力矩无响应排查)
**日期**: 2026-09-22
**项目**: driverSoftware (通用于上位机 + 固件联调)
**状态**: 生效
**关键词**: [排查纪律, 抓包, 真机测试, 固件档案, 签名同步, 波特率, 并行会话, 发布流程]

1. **先抓真实请求/回包, 再推理**: 浏览器 performance.getEntriesByType('resource') / read_network_requests 看有没有请求、返回码、响应体;
   preview 日志缓冲会被 hw_drain 刷满, 用 level=error 过滤直接看 Traceback。本案 500 的 TypeError 一眼就是根因。
2. **协议常量以固件头为唯一事实源**: 档案/刻度只能由生成器 (tools/gen_fw_profile.py) 产出, 手填必错; 并加"档案值 == 固件常量"的机械门禁。
   区分同名数值: 10000 是 Kp/Kd 量化 scale, 不是 pos/vel/tau 刻度。
3. **双实现接口改签名要两边同改**: 本仓 ReaderBackend 有 reader_mp (默认) 与 reader_wrapper 两份, 改一份必查另一份;
   用 inspect.signature 写测试钉住。
4. **总线参数单一真相源在后端连接状态**, 不信前端各自传的值 (前端 store 可能未同步, 回退默认值就静默错配)。
5. **真机测试要有安全兜底**: 小力矩 + 阻尼 (Kd) 限速, 每档限时, 出故障/温度越界即停, 结束必确认 kStopped;
   UI 自动化时用派发 keydown Enter 提交 (本页 blur 会回滚未提交输入), 不用 Tab。
6. **注意并行会话/他人提交**: 文件被莫名改回 (本案 17:36 档案回滚) 先查是否有别的会话在同仓工作;
   发版前必 fetch 对账 (本案远端多出同事修同一问题的 c8ad4e6, 需 rebase 取其版本)。
7. **发布按仓库流程**: CHANGELOG [未发布] 一句白话 → release.py <ver> (bump/截断/tag) → 分别推 development 与 tag →
   git ls-remote 核 tag 指向; 正式包由 CI Runner 构建, 本地不手传。发完回收缺陷池"待发布"占位。
8. **结论前先证伪**: 读一个寄存器就能否定的假设 (如 0x89 自动清除) 不要写进结论; 报告时把"已证实"与"推测"分开。
