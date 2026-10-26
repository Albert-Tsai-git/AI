### P-20261054: 压缩后的发布流程及实际更新日志卡片复测

**日期**: 2026-10-26
**项目**: driverSoftware
**关键词**: 26abd28e, 更新日志分类, 复测, 飞书卡片, Kt, v0.20.3, v0.20.4, v0.20.5
**需求场景 / 现象**: 用户在压缩三项本地提交后再次要求自行测试发布流程。测试授权原话“自己测试一下这个流程是否正确”。
**方案 / 架构**: 在压缩后的26abd28e重跑六份发布与CI专项用例，并对当前实际CHANGELOG执行CI同一入口、生成三个已整理版本的卡片。当前未发布段在内存中模拟迁移到0.20.6，不写实际版本、不打tag、不发群。
**关键文件与接口**: scripts/release.py --check-changelog、cut_changelog；scripts/ci_notify_lark.py build_card；tests/unit/test_release_changelog.py、test_release_flow.py、test_release_dev_guard.py、test_ci_notify_lark_card.py、test_release_notification_flow.py、test_macos_ci_gates.py。
**验证方法**: 本轮重新执行72项全部通过、0失败、0跳过，final-tests.xml留痕。实际0.20.3分类计数修复4、0.20.4修复1、0.20.5新增1，三个CLI校验均成功且生成非空卡片；0.20.3通知展示前三条及另1条。未发布Kt条目在内存迁移后成功进入修复1卡片。实际CHANGELOG保持不变，Git工作区干净，HEAD仍为26abd28e、tree为b088cb99ff5571e3ded4f09674cc873598279ab1。
**状态**: 本地发布与卡片生成复测通过，无业务代码改动。证据actual-content-checks.json、card-0.20.3.json、card-0.20.4.json、card-0.20.5.json、unreleased-card-preview.json。未触发远端CI、未发送真实飞书消息。单一测试任务主控执行，独立代理复核证据。
