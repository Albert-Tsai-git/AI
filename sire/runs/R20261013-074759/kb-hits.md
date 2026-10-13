# G0 知识检索记录（run R20261013-074759 · Qoder 端 SIRE 兼容适配）

**检索词**: `Qoder 客户端 入口 薄入口 别名 安装`、`钩子 hooks 插件 plugin 客户端配置`（sire_kb.py search --run，两组词均有回执）、`Qoder 客户端 SIRE 入口 钩子 插件 安装`（sire_vector_db.py search --run）

**命中**: E-010（v6.11 规则同步与两端别名/薄入口做法，score 26）、F-040、H-003、P-20260931（RSI 自审：采集单腿、Claude 断流、Qoder 无钩子，score 11）、F-035、E-009、P-023。

**判定**: 部分可参考 —— 薄入口/junction 的既有做法（E-010、E-008）可直接沿用；Qoder 客户端钩子能力、settings.json 钩子格式、插件注册表结构此前无任何记录，本轮实测补齐。

## 复用与新增

- 复用：skill 别名必须解析到唯一源（E-008/E-010）→ Qoder 用 junction 而非副本；数据库/知识库不得复制到客户端目录（契约）。
- 本轮新增实测事实：Qoder 钩子事件集（PostToolUse 6174 / PreToolUse 3506 / UserPromptSubmit 136 / QueryEnd 132 / Stop 54 / PostToolUseFailure 48 / SessionEnd 42 / SessionStart 38，取自 `logs/runs/*/qodercli.log` 的 `hook_event_name` 计数）、载荷字段与转录均为 Claude 同形、插件清单 `.qoder-plugin/plugin.json` + `hooks/hooks.json`、注册表 `plugins/installed_plugins_v2.json`、`~/.qoder-cn/skills/` 下新建 junction 后技能列表即时出现（无需重启），但钩子清单需重启才加载。
- 缺口：OS 级 computer-use 在 Qoder 有 `bin/qoder-cn-computer-use/QoderComputerUse.exe`，但是否作为工具暴露给模型未验证 → R10 仍按 `BLOCKED-无法真实验证` 处理。
