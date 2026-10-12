| Test | Operation | Expected | Actual / evidence | Conclusion |
|---|---|---|---|---|
| T1 | Check the five exact target paths; coordinator enumerates Recycle Bin entries matching source parent and exact names. | All five target paths absent and entries recoverable from Recycle Bin. | Independent `Test-Path` returned False for all five. Coordinator reports Shell.Application enumeration matched all five from `D:\code`, exit 0. | PASS |
| T2 | Compare direct-child directories of `D:\code` before/after, excluding five authorized targets. | All other direct-child directories unchanged. | Coordinator reports `Compare-Object` had no differences; independent after enumeration shows 22 direct-child directories. | PASS (coordinator before/after evidence) |
