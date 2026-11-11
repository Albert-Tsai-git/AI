"""遥测检测口径单测：RULE_READ / FAST_SCOPE / FAST_SLOW / FAST_MISUSE / TOOL_RETRY。

这些规则此前把合同允许的行为（grep/sed 定位规则段落、维护规则文件、1~2 次查看台账）或高调用量的完整任务误判，
并掩盖了真正的问题（Codex 端声明快速通道却做了几百次调用）。纯函数测试，不碰任何真实数据库。
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sire_telemetry as t  # noqa: E402


def task(mode="full", total=100.0, calls=None, seconds=None, failures=0, tool_calls=10, prompt="普通提示"):
    return {"phases": json.dumps({"calls": calls or {}, "seconds": seconds or {}}), "total_s": total, "mode": mode,
            "failures": failures, "tool_calls": tool_calls, "prompt": prompt, "task_id": "T", "client": "claude",
            "end_ts": 0}


def rules(found):
    return [item[1] for item in found]


class RuleReadClassifyTest(unittest.TestCase):
    def test_whole_file_reads_count(self):
        self.assertEqual("rules", t.classify("Read", {"file_path": r"D:\x\SKILL.md"}))
        self.assertEqual("rules", t.classify("Bash", {"command": "cat references/global-contract.md"}))
        self.assertEqual("rules", t.classify("PowerShell", {"command": "Get-Content D:/x/references/roles.md"}))

    def test_locating_a_section_is_allowed_and_not_counted(self):
        """合同允许“需要回看时用 grep/sed 定位段落”，不能因此被判读规则过多。"""
        self.assertNotEqual("rules", t.classify("Grep", {"pattern": "R9", "path": "references/global-contract.md"}))
        self.assertNotEqual("rules", t.classify("Bash", {"command": "sed -n 100,120p references/global-contract.md"}))
        self.assertNotEqual("rules", t.classify("Bash", {"command": "grep -n 'R9' references/global-contract.md"}))
        self.assertNotEqual("rules", t.classify("PowerShell", {"command": "Select-String -Path D:/x/references/roles.md -Pattern R9"}))

    def test_maintaining_rule_files_is_not_reading_them(self):
        self.assertNotEqual("rules", t.classify("Edit", {"file_path": "references/global-contract.md"}))
        self.assertNotEqual("rules", t.classify("Write", {"file_path": "references/entry-reminder.md"}))

    def test_other_phases_unchanged(self):
        self.assertEqual("ledger", t.classify("Bash", {"command": "python sire_run.py status"}))
        self.assertEqual("commit", t.classify("Bash", {"command": "git commit -m x"}))
        self.assertEqual("subagent", t.classify("Agent", {"prompt": "x"}))
        self.assertEqual("execute", t.classify("Bash", {"command": "ls"}))

    def test_rule_read_threshold_still_fires_for_real_repeated_reads(self):
        found = t.detect(task(calls={"rules": 4}), [], [])
        self.assertIn("RULE_READ", rules(found))
        self.assertNotIn("RULE_READ", rules(t.detect(task(calls={"rules": 3}), [], [])))


class FastPathTest(unittest.TestCase):
    def test_genuinely_simple_slow_task_is_fast_slow(self):
        found = t.detect(task(mode="fast", total=90, tool_calls=2), [], [])
        self.assertIn("FAST_SLOW", rules(found))
        self.assertNotIn("FAST_MISUSE", rules(found))

    def test_fast_under_60s_is_fine(self):
        self.assertEqual([], t.detect(task(mode="fast", total=40, tool_calls=2), [], []))

    def test_heavy_task_declared_fast_is_misuse_not_fast_slow(self):
        """371 次调用、8326 秒却声明快速通道：问题是误用快速通道，不是“简单任务太慢”。"""
        found = rules(t.detect(task(mode="fast", total=8326, tool_calls=371), [], []))
        self.assertIn("FAST_MISUSE", found)
        self.assertNotIn("FAST_SLOW", found)

    def test_misuse_boundary(self):
        self.assertNotIn("FAST_MISUSE", rules(t.detect(task(mode="fast", total=30, tool_calls=t.FAST_MISUSE_CALLS), [], [])))
        self.assertIn("FAST_MISUSE", rules(t.detect(task(mode="fast", total=30, tool_calls=t.FAST_MISUSE_CALLS + 1), [], [])))

    def test_middle_sized_fast_task_is_neither_slow_nor_misuse(self):
        found = rules(t.detect(task(mode="fast", total=120, tool_calls=6), [], []))
        self.assertNotIn("FAST_SLOW", found)
        self.assertNotIn("FAST_MISUSE", found)

    def test_viewing_ledger_once_or_twice_is_not_scope_violation(self):
        self.assertNotIn("FAST_SCOPE", rules(t.detect(task(mode="fast", total=20, calls={"ledger": 1}, tool_calls=1), [], [])))
        self.assertNotIn("FAST_SCOPE", rules(t.detect(task(mode="fast", total=20, calls={"ledger": 1, "subagent": 1}, tool_calls=2), [], [])))

    def test_three_or_more_forbidden_calls_is_scope_violation(self):
        found = t.detect(task(mode="fast", total=20, calls={"ledger": 2, "commit": 1}, tool_calls=3), [], [])
        self.assertIn("FAST_SCOPE", rules(found))
        self.assertIn("ledger,commit", [item[2] for item in found if item[1] == "FAST_SCOPE"][0])

    def test_full_mode_task_is_not_checked_by_fast_rules(self):
        found = rules(t.detect(task(mode="full", total=500, calls={"ledger": 5}, tool_calls=100), [], []))
        for code in ("FAST_SLOW", "FAST_SCOPE", "FAST_MISUSE"):
            self.assertNotIn(code, found)

    def test_misuse_rule_exists_with_actionable_suggestion(self):
        need, suggestion = t.RULES["FAST_MISUSE"]
        self.assertIn("逐阶段汇报", suggestion)
        self.assertGreaterEqual(need, 1)


class ToolRetryTest(unittest.TestCase):
    def test_few_failures_in_a_long_task_is_normal(self):
        self.assertNotIn("TOOL_RETRY", rules(t.detect(task(failures=3, tool_calls=128), [], [])))

    def test_high_failure_rate_is_flagged(self):
        found = t.detect(task(failures=6, tool_calls=40), [], [])
        self.assertIn("TOOL_RETRY", rules(found))
        self.assertIn("6 次失败 / 40 次调用", [item[2] for item in found if item[1] == "TOOL_RETRY"][0])

    def test_boundary_ten_percent(self):
        self.assertIn("TOOL_RETRY", rules(t.detect(task(failures=3, tool_calls=30), [], [])))   # 恰好 10%
        self.assertNotIn("TOOL_RETRY", rules(t.detect(task(failures=3, tool_calls=31), [], [])))

    def test_two_failures_never_flagged(self):
        self.assertNotIn("TOOL_RETRY", rules(t.detect(task(failures=2, tool_calls=2), [], [])))

    def test_zero_calls_does_not_divide_by_zero(self):
        self.assertNotIn("TOOL_RETRY", rules(t.detect(task(failures=5, tool_calls=0), [], [])))


if __name__ == "__main__":
    unittest.main()
