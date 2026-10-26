### P-20261053: 更新日志分类修复提交压缩后的追溯关系

**日期**: 2026-10-26
**项目**: driverSoftware
**关键词**: 压缩提交, squash, 本地提交, 更新日志分类, 26abd28e, 远端基线
**需求场景 / 现象**: 用户要求压缩当前会话的几个提交。工作区干净，development上仅f6ae85d9、6918168c、fb9f1499三项本地提交，均属于更新日志分类与通知修复。
**方案 / 架构**: 实际ls-remote确认远端development仍为86881cbf，与本地upstream一致。soft reset到此基线后重提交为26abd28e，保持远端基线与既有合并历史。只压缩业务仓库三项提交，不涉及共享知识仓库。
**关键文件与接口**: CHANGELOG.md、AGENTS.md、scripts/release.py、.gitlab-ci.yml及三个发布专项测试文件，共7个文件。before-commits.txt与before-refs.txt保留旧提交和tree证据。
**验证方法**: 原HEAD为fb9f1499，压缩后26abd28e；两者tree均为b088cb99ff5571e3ded4f09674cc873598279ab1。git diff旧HEAD新HEAD为空，父提交为86881cbf；diff --check无问题，工作区干净。没有再次执行测试，沿用内容未变时此前72项测试结果，不宣称重新测试。
**状态**: 压缩完成、内容完全一致，未推送，未重跑测试。极小Git操作主控直接执行，不涉及代码修改；协作未开启。
