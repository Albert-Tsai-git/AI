VERDICT: PASS

# U-02 R7 测试：SKILL.md / references/supervisor.md 的 RSI 规则与代码一致性

脚本：qa_u02.py（R7 自写）；完整输出：output.log；异常路径用的 SKILL.md 副本：SKILL.nolink.md

- 正常路径：共 14 条断言全部 PASS，rc=0。
  - 7 个词（rsi-check、finalize、rsi_unregistered_change、STOP、PROPOSED、EVALUATED_PASS、ACTIVE）都出现在文档中，并且在 sire_supervisor.py 中逐字存在。
  - propose、evaluate、activate、rollback 都出现在 SKILL.md 中，并且在 sire_rsi.py 中逐字存在。
  - SKILL.md 含 "## Workflow changes (RSI)"，链接 references/self-optimization.md，且该文件存在。
  - supervisor.md 第 8 项含 rsi-check。
- 异常路径：复制 SKILL.md 并删掉 self-optimization.md 链接后跑同一套断言，链接断言 FAIL，整体 ALL FAIL，rc=1，符合预期（断言能识别出缺失的链接）。
- 局限：只检查这些词是否逐字出现，不检查文档里的语义描述是否与代码一致；语义一致性由 U-01 的实测覆盖。
