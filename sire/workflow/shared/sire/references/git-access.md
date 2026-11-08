# 内网 GitLab 访问方式（Claude / Codex / Qoder 统一）

> 2026-11-07，用户定：**git / GitLab 需要认证时，按本文自行完成，不得再让用户登录或粘贴令牌。** 本文只记录位置与用法，**不含令牌值**。

## 1. 服务与令牌

- 地址：`http://192.168.1.200:8888/`（同一台机器的 SSH 主机名为 `gitlab.kingkong.tech`，解析到 192.168.1.200）。
- 令牌文件：`D:\sire\AI\AI\sire\secrets\git-token.txt`（在 AI 仓库目录内，但被 `sire/.gitignore` 的 `**/secrets/` 忽略，不进 Git；旧副本 `D:\sire\git-token.txt` 保留作备用；单行 `glpat-…`，读取时去掉首尾空白）。
- 令牌名 `sire-p-token`，用户 id 42，用户名 `caiyixuan`，到期 **2027-11-06**。
- 权限（scopes）：`api`、`read_api`、`read_user`、`create_runner`、`k8s_proxy`、`read_repository`、`write_repository`、`ai_features`。
- 令牌权限很大：不得回显、不得写进仓库 / 日志 / 台账 / 知识库 / 数据库 / 通讯消息；命令输出里出现 `glpat-` 一律先脱敏再展示。

## 2. 各通道怎么走（均已配置，直接用）

| 场景 | 方式 | 状态 |
|---|---|---|
| `git clone/fetch/push`（本机仓库的 remote 为 `git@gitlab.kingkong.tech:…`） | SSH 密钥 | 已通（`git ls-remote origin` 可用） |
| 通过 HTTP 访问 192.168.1.200:8888 的 git | Git Credential Manager（`credential.http://192.168.1.200:8888.provider=generic`） | 已存有凭据 |
| `glab` 命令与 gitlab MCP | `glab auth login` 已用令牌文件登录，存入系统钥匙串，主机 `192.168.1.200:8888`，API 走 http、git 走 ssh | 2026-11-07 已登录并核验 |
| 直接调 REST API | 请求头 `PRIVATE-TOKEN: $(tr -d '\r\n ' < /d/sire/AI/AI/sire/secrets/git-token.txt)` | 可用 |

核验（不输出令牌）：

```bash
glab auth status --hostname 192.168.1.200:8888
curl -s -m 15 -H "PRIVATE-TOKEN: $(tr -d '\r\n ' < /d/sire/AI/AI/sire/secrets/git-token.txt)" http://192.168.1.200:8888/api/v4/personal_access_tokens/self
```

## 3. 出现认证失败时（401 / 要求登录）

1. 先判断是哪个通道：SSH 失败看密钥；glab / MCP 报 401 通常是钥匙串里的令牌失效。
2. glab 失效时用令牌文件重新登录，**不要问用户**：
   `tr -d '\r\n ' < /d/sire/AI/AI/sire/secrets/git-token.txt | glab auth login --hostname 192.168.1.200:8888 --api-host 192.168.1.200:8888 --api-protocol http --git-protocol ssh --stdin`
3. 令牌文件本身失效（401 且 `personal_access_tokens/self` 也 401，或已过期）才请用户换新令牌，并只让用户更新 `D:\sire\AI\AI\sire\secrets\git-token.txt`（并同步旧副本），别让用户在对话里粘贴。
4. gitlab.com 的 glab 登录（401）与本项目无关，不用处理。

## 4. 权限边界（令牌可用 ≠ 可随意执行）

- 令牌只解决“认证”，**不扩大授权**。读取（查 MR / 流水线 / 议题 / 文件）可直接做；写入类按各项目规则与用户授权：
  - 不强推、不改写已发布历史、不推送到 upstream 以外；
  - 合并 MR、关闭 / 删除议题、删除仓库 / 分支 / 标签、改 CI 变量、改仓库设置与成员、创建 release / 推 tag：**必须用户明确要求**；
  - 提 tag 仍遵守“只给建议、不创建”的强制规则。
- 本项目（EncoderPlotter）额外遵守：`sub_algorithm` 算法仓永远不动（不改代码、不动分支、不推送）；`main` / `develop` 受保护，push = No one，走 MR。
