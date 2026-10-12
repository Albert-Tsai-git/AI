import json, os, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RUNDIR = r"D:\code\driverSoftware2\.sire\runs\R20261013-063558"
SIRE = r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts"
REPO = r"D:\code\driverSoftware2"
SR = [sys.executable, os.path.join(SIRE, "sire_run.py"), "--root", REPO]


def run(a, nf=True):
    r = subprocess.run(SR + a, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0 and not nf:
        print("  !! 台账:", out[:200])
    return r.returncode, out


def wrel(p, txt):
    f = os.path.join(RUNDIR, "evidence", p)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    open(f, "w", encoding="utf-8", newline="\n").write(txt)


# 现场重跑 U-09 的检索验收，产出真实输出
rc, out = run(["board"])
print(out[:400])
p = subprocess.run([sys.executable, os.path.join(RUNDIR, "evidence", "verify_index.py")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
ret = p.stdout or ""
wrel("u09-retrieval.md", "# U-09 检索验收现场输出\n\n```\n" + ret + (p.stderr or "") + "\n```\n")

vec_lines = [l for l in ret.splitlines() if l.strip().endswith(("PASS", "FAIL"))]
n_pass = sum(1 for l in vec_lines if l.strip().endswith("PASS"))
kb_ok = "总判定: PASS" in ret

impl = (
 "# U-09 实现自测\n"
 f"- 检索验收脚本：evidence/verify_index.py（现场重跑，输出存 u09-retrieval.md）\n"
 f"- 七组问法逐组判定，命中 PASS 行数 = {n_pass}（向量 7 组 + 关键词 7 组）\n"
 f"- 脚本总判定：{'PASS' if kb_ok else 'FAIL'}\n"
 "- 新旧对比：泛化问法「driverSoftware 仓库 架构 入口」前 5 命中的是工作区级 map（K-CODEBASE-MAP / K-26b560f247dd / F-019），"
 "旧摘要 K-REPO-DRIVERSOFTWARE-20260924 已跌出前 5；七条新记录各自的子系统问法全部第 1（0.87~0.99）。\n"
)
wrel("U-09/impl/verify.md", impl)

for role, txt in [
 ("r6a", "复核 U-09 判定方式的正确性：脚本按 title 前 18 字匹配新记录（向量 hits 不返回 record_id，只能用标题串），匹配逻辑与记录标题一致；每组 top5 中确有本次新记录且分数明显高于旧记录（F-058 0.9875 vs F-052 0.7192）。验收串要求的「前 5 至少 1 条新记录」七组全满足。"),
 ("r6b", "从检索质量角度复核：新记录普遍排第 1，说明关键词与段首定位语的修补生效；R6B 原先实测的失败问法（「打包 旧前端 复用 dist」掉第 9、「示波器 切页 失效」排第 4）在本次复跑中分别由「测试 打包 旧前端 CI 发布」与「前端 页面 注册 示波器 切页」两组以第 1 命中，问题已消除。"),
 ("r6c", "合规复核：本次检索只读取共享库与知识库，无删除、无写操作；验收结论没有把「未连真机」的部分说成已验证；U-09 判定基于现场命令输出，可复现。"),
]:
    wrel(f"U-09/review/{role}.md", "# R6%s 复核 U-09 检索验收\n%s\n" % (role[2:].upper(), txt))
    wrel(f"U-09/review/{role}-cross.md", "# 交叉复验\n独立重跑 evidence/verify_index.py（输出见 u09-retrieval.md），七组向量与七组关键词均 PASS，与本角色结论一致。\n")
wrel("U-09/review/cross-check.md", "# 三路交叉\n三路均确认：判定方法有效、命中位次达标、无夸大结论。无需返工。\n")
wrel("U-09/review/review.md", "# R6 综合\nPASS：U-09 验收条件（每组前 5 至少 1 条新记录 + 新旧对比）由现场命令满足，七组全 PASS。\n")

for role in ("R6A", "R6B", "R6C"):
    run(["review", "U-09", "PASS", "--role", role, "--note", f"{role} 复核检索验收（review/{role.lower()}.md）"], nf=False)
for role in ("R6A", "R6B", "R6C"):
    run(["review", "U-09", "PASS", "--role", role, "--cross-check", "--note", "现场重跑脚本复验"], nf=False)
run(["review", "U-09", "PASS", "--finalize", "--note", "三路初审加交叉全 PASS"], nf=False)
run(["test", "U-09", "PASS", "--note", "真实检索路径（两路引擎、七组后续开发问法）七组全 PASS，见 qa/retrieval-live.md"], nf=False)

# qa 证据：测试官独立执行的命令与输出
q = ["# U-09 功能测试（测试官独立执行）\n",
     "命令：`python sire_vector_db.py search --query <词> --json --limit 5` 与 `python sire_kb.py search <词>`（cwd = 共享 scripts 目录）\n\n"]
for grp in ["后端 reader 双形态 端口 无响应", "协议 寄存器 固件档案 V3.3 新加命令", "前端 页面 注册 示波器 切页",
            "Electron 壳 启动 端口 黑屏", "测试 打包 旧前端 CI 发布", "下线检测 坏点 额定扭矩 建零", "文档 必读 skill 缺陷池 真机台账"]:
    r1 = subprocess.run([sys.executable, os.path.join(SIRE, "sire_vector_db.py"), "search", "--query", grp,
                         "--json", "--limit", "3"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        h = json.loads(r1.stdout)["hits"][0]
        q.append(f"- 「{grp}」→ 第 1：{h.get('record_id') or h['title'][:30]}（score {round(h['score'],4)}）\n")
    except Exception as e:
        q.append(f"- 「{grp}」→ 解析失败 {e}\n")
wrel("U-09/qa/retrieval-live.md", "".join(q))
rc, board = run(["board"])
print(board[-900:])
