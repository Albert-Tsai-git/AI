#!/bin/sh
# 复测 X1 / X4 / 真实库 rsi-check；字节码重定向到 tmp/pycache
QA=D:/code/driverSoftware/.sire/runs/R20260925-052105/evidence/U-01/qa
S=D:/sire/AI/AI/sire/workflow/shared/sire/scripts
export PYTHONPYCACHEPREFIX=$QA/tmp/pycache PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
unset SIRE_VECTOR_DB SIRE_KB_DIR SIRE_ROOT SIRE_DATA_DIR
DB=D:/sire/AI/AI/sire/data/sire_vectors.sqlite3
echo "== grep 修复点"; grep -n "except sqlite3\|except OSError\|except FileNotFoundError" $S/sire_supervisor.py
echo "== R1 X1 garbage sha_before=$(sha256sum $QA/tmp/garbage.sqlite3 | cut -c1-16)"
cd $S && SIRE_VECTOR_DB=$QA/tmp/garbage.sqlite3 python sire_supervisor.py rsi-check; echo "rc=$?"
echo "garbage sha_after=$(sha256sum $QA/tmp/garbage.sqlite3 | cut -c1-16)"
echo "== R2 X4 nonexistent skill_dir"
python $QA/t8_inproc.py $QA/tmp/does-not-exist; echo "rc=$?"
echo "== R3 real DB sha_before=$(sha256sum $DB | cut -c1-16) data=$(ls D:/sire/AI/AI/sire/data | tr '\n' ' ')"
python sire_supervisor.py rsi-check; echo "rc=$?"
echo "real DB sha_after=$(sha256sum $DB | cut -c1-16) data=$(ls D:/sire/AI/AI/sire/data | tr '\n' ' ')"
rm -rf $QA/tmp/pycache
