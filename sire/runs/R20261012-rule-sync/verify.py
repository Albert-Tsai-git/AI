"""Actual alias/CLI acceptance; telemetry test data stays outside the repository."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

RUN = Path(__file__).resolve().parent
PACKAGE = RUN.parents[1]
SOURCE = PACKAGE / 'workflow/shared/sire'
HOME_DIR = Path.home()
ALIASES = {
    'codex': HOME_DIR / '.codex/skills/ai-dev-sire-workflow',
    'claude': HOME_DIR / '.claude/skills/sire-global-workflow',
}
results = {}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def invoke(command, *, payload=None, env=None):
    proc = subprocess.run(command, input=payload, text=True, encoding='utf-8',
                          capture_output=True, env=env, cwd=PACKAGE, timeout=45)
    if proc.returncode:
        raise AssertionError(f'command rc={proc.returncode}: {proc.stderr[:500]}')
    return proc

paths = []
for client, alias in ALIASES.items():
    assert alias.resolve() == SOURCE.resolve()
    for relative in ('SKILL.md', 'references/global-contract.md'):
        assert digest(alias / relative) == digest(SOURCE / relative)
    text = (alias / 'references/global-contract.md').read_text(encoding='utf-8')
    assert 'RSI 自动发现与自我优化' in text
    code = "import sys,json;sys.path.insert(0,sys.argv[1]);import sire_paths as p;print(json.dumps([str(p.SHARED_SKILL_DIR),str(p.DATABASE_PATH),str(p.KNOWLEDGE_DIR)]))"
    paths.append(json.loads(invoke([sys.executable, '-c', code, str(alias / 'scripts')]).stdout))
assert paths[0] == paths[1]
results['T1'] = {'status': 'PASS', 'same_source': True, 'same_paths': True,
                 'skill_sha256': digest(SOURCE / 'SKILL.md'),
                 'contract_sha256': digest(SOURCE / 'references/global-contract.md')}

codex = (HOME_DIR / '.codex/AGENTS.md').read_text(encoding='utf-8')
claude = (HOME_DIR / '.claude/sire-reminder.txt').read_text(encoding='utf-8')
codex_block = codex[codex.index('## 简单任务快速通道'):].strip().removeprefix('## ')
claude_block = claude[claude.index('简单任务快速通道'):].strip().removeprefix('## ')
assert codex_block == claude_block
for word in ('目录列表', '环境变量', '新建空文件', '概念或用法', '一到三条命令',
             '最多两条命令', '查看类只用一条', '目标不明确', '不存在', '转完整流程',
             '本轮实际执行', '三行', '模型选择门禁', '不换方法重试'):
    assert word in codex_block, word
assert 'tracked SQLite' not in codex
package_entry = (PACKAGE / 'AGENTS.md').read_text(encoding='utf-8')
assert 'tracked database' not in package_entry
assert 'database stays outside Git' in package_entry or 'database is temporarily outside Git' in package_entry
results['T2'] = {'status': 'PASS', 'identical_fast_path_copies': True,
                 'current_codex_context_received_updated_adapter': True}

test_dir = Path(tempfile.mkdtemp(prefix='sire-rule-sync-qa-'))
hook_results = []
for client, alias in ALIASES.items():
    hooks_file = HOME_DIR / ('.codex/hooks.json' if client == 'codex' else '.claude/settings.json')
    hooks = json.loads(hooks_file.read_text(encoding='utf-8'))['hooks']
    for event in ('UserPromptSubmit', 'PostToolUse', 'Stop'):
        commands = [h.get('command', '') for group in hooks[event] for h in group.get('hooks', [])]
        assert any('sire_telemetry.py' in command and f'--client {client}' in command for command in commands)
    db = test_dir / f'{client}.sqlite3'
    child_env = os.environ.copy()
    child_env['SIRE_TELEMETRY_DB'] = str(db)
    command = [sys.executable, str(alias / 'scripts/sire_telemetry.py'), 'hook', '--client', client]
    payloads = [
        {'hook_event_name': 'UserPromptSubmit', 'session_id': 'rule-sync-smoke', 'prompt': 'SIRE rule sync smoke'},
        {'hook_event_name': 'PostToolUse', 'session_id': 'rule-sync-smoke', 'tool_name': 'exec_command',
         'tool_input': {'cmd': 'python sire_vector_db.py stats'}, 'tool_response': {'exit_code': 0}},
        {'hook_event_name': 'Stop', 'session_id': 'rule-sync-smoke', 'last_assistant_message': '快速通道：否，完整流程'},
    ]
    for payload in payloads:
        proc = invoke(command, payload=json.dumps(payload), env=child_env)
        assert not proc.stdout and not proc.stderr
    invoke([sys.executable, str(alias / 'scripts/sire_telemetry.py'), 'analyze'], env=child_env)
    with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
        before = (conn.execute('select count(*) from events').fetchone()[0],
                  conn.execute('select count(*) from tasks').fetchone()[0])
        assert before == (3, 1), before
        assert conn.execute('select client,mode,tool_calls,failures,analyzed from tasks').fetchone() == (client, 'full', 1, 0, 1)
    proc = invoke(command, payload='{malformed', env=child_env)
    assert not proc.stdout and not proc.stderr
    with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as conn:
        after = (conn.execute('select count(*) from events').fetchone()[0],
                 conn.execute('select count(*) from tasks').fetchone()[0])
        assert after == before
    hook_results.append({'client': client, 'events': 3, 'tasks': 1, 'mode': 'full', 'silent': True})
results['T3'] = {'status': 'PASS', 'clients': hook_results, 'scope': 'configured command and actual script path'}
results['T4'] = {'status': 'PASS', 'malformed_json_silent': True, 'counts_unchanged': True}

work_db = Path(paths[0][1])
before_hash = digest(work_db)
searches = []
for alias in ALIASES.values():
    result = json.loads(invoke([sys.executable, str(alias / 'scripts/sire_vector_db.py'), 'search',
                                '--query', 'SIRE 单一来源', '--json', '--limit', '3']).stdout)
    assert result['hits']
    searches.append([h['id'] for h in result['hits']])
assert searches[0] == searches[1]
empty = json.loads(invoke([sys.executable, str(ALIASES['codex'] / 'scripts/sire_vector_db.py'), 'search',
                           '--query', 'rule-sync-no-match-20261012', '--threshold', '999', '--json']).stdout)
assert empty['hits'] == []
assert digest(work_db) == before_hash
results['T5'] = {'status': 'PASS', 'same_hit_ids': searches[0], 'boundary_hits': 0, 'database_unchanged': True}
pending = invoke([sys.executable, str(SOURCE / 'scripts/sire_telemetry.py'), 'pending']).stdout
assert not pending
results['T6_pending'] = {'status': 'PASS', 'pending_output': 'empty'}
results['T7'] = {'status': 'BLOCKED-无法真实验证', 'reason': '真实客户端自动触发路径尚未实测；配置与脚本不能替代事件证据。'}
(RUN / 'validation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: value['status'] for key, value in results.items()}, ensure_ascii=False))
