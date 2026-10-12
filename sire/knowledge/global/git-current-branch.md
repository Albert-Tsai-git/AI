# Git 当前分支查询

记录编号：method-git-current-branch

关键词：Git, 当前分支, 实时状态, 历史记录

查询当前分支时必须读取目标仓库的实时 Git 状态。`git branch --show-current` 可读取分支，`git symbolic-ref --short HEAD` 可独立复核；历史任务记录中的分支名称只适用于当时的仓库与时间。若处于 detached HEAD，应说明没有当前分支，另查提交编号。

验证：2026-10-12 在 driverSoftware 实际执行上述两条命令及 `git status --short --branch`，结果一致。具体分支名称仅保存在本次任务证据中。
