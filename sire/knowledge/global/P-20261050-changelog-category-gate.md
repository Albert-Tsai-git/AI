### P-20261050: 防止更新日志缺分类导致发布通知丢失条目

**日期**: 2026-10-26
**项目**: driverSoftware
**关键词**: CHANGELOG, 新增, 修复, 分类标题, 飞书通知, release.py, 强制拦截
**需求场景 / 现象**: 用户要求后续更新日志必须同时具有新增和修复标题。此前v0.20.3起平铺条目被通知解析器丢弃，发布仍成功。
**根因**: 发布脚本只查存在短横线条目，通知仅处理三级分类标题下的条目，输入约定不一致。
**方案 / 架构**: release.py新增validate_changelog_body，剥离HTML注释、跳过围栏代码，要求###新增与###修复同时存在且至少一个分类下有真实条目；分类前条目拒绝。cut_changelog在写入版本文件之前校验，发布后自动保留两个空分类。--check-changelog只读检查指定版本，正式tag的CI在test阶段先检查再构建。历史段落保持原样。
**关键文件与接口**: scripts/release.py的validate_changelog_body、check_changelog_version、cut_changelog与main；.gitlab-ci.yml的test-gates；AGENTS.md发布纪律；tests/unit/test_release_changelog.py和test_release_flow.py。
**实施步骤**: 同步发布与CI门禁，补当前未发布段分类，保留原条目，补缺任一标题、伪标题、空内容、分类外条目、历史隔离、无写入以及同版本CI检查的回归用例。
**验证方法**: 独立R6静态复核通过，git diff --check无问题。没有运行任何测试、dry-run、构建、服务或真实CI；测试授权尚未取得。后续建议授权后运行发布脚本专项用例，并在隔离副本做删除标题的变异验证。
**状态**: 实现并本地提交f6ae85d9，未推送；未测试，待用户授权。当前工作目录development初始干净，按SIRE当前目录当前分支规则执行。协作未开启。
