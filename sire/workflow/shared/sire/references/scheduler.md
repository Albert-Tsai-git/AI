# Unit scheduling and blocker isolation

Build a dependency DAG from R3 units. Run ready units in parallel only when both their dependencies and read/write sets permit it. Shared database writes and edits to the same workflow file are serialized. A failure isolates its affected unit; independent ready units continue.

For every unit, keep its owner, inputs, outputs, read/write sets, dependency, acceptance, independent reviewer, functional test, recovery note, and current status in the run ledger. Use the statuses supported by the current `sire_run.py` schema; do not invent an unrecognized state.

```powershell
python <SHARED_SKILL_DIR>\scripts\sire_run.py board
```

On review/test failure, record the observed failure and repair action, then repeat review and test. After three materially identical failures, stop the affected branch and report the blocker; continue unrelated ready units. A blocker record states the cause, attempts, affected requirements, and next action. Close only when all required units are accepted or explicitly reported as blocked.
