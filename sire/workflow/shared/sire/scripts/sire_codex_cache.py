"""Codex 用量事件投影与可丢弃缓存；不保存提示、回答或工具内容。

增量模式依赖 rollout 的正常追加语义。身份、时间戳和首尾锚点可检测
常规替换/截断/改写，但不能证明任意中部改写后追加；严格取证用 use_cache=False。
缓存不是来源身份授权，调用者仍须检查 session_meta.id/cwd。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from sire_paths import ledger_runs_dir

VERSION = 1
ANCHOR = 4096
COUNTERS = ("input_tokens", "output_tokens", "cached_input_tokens",
            "cache_write_input_tokens", "reasoning_output_tokens", "total_tokens")


def _pick(value, fields):
    if not isinstance(value, dict):
        return {}
    return {k: value[k] for k in fields if k in value
            and isinstance(value[k], (str, int, float, bool, type(None)))}


def _usage(value):
    if not isinstance(value, dict):
        return None
    return {k: value[k] for k in COUNTERS if type(value.get(k)) is int}


def _limits(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for key in ("primary", "secondary"):
        if isinstance(value.get(key), dict):
            result[key] = {k: value[key][k] for k in
                           ("used_percent", "window_minutes", "resets_at")
                           if type(value[key].get(k)) in (int, float)}
    return result


def _project(row):
    if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
        return None
    kind, p = row.get("type"), row["payload"]
    if kind == "session_meta":
        payload = _pick(p, ("id", "cwd"))
    elif kind == "turn_context":
        payload = _pick(p, ("turn_id", "model", "cwd"))
    elif kind == "token_usage_record":
        payload = _pick(p, ("thread_id", "turn_id", "response_id"))
        for key in ("usage", "thread_token_usage"):
            if key in p:
                payload[key] = _usage(p[key])
    elif kind == "event_msg" and p.get("type") in ("task_started", "task_complete"):
        payload = _pick(p, ("type", "turn_id"))
    elif kind == "event_msg" and p.get("type") == "token_count":
        info = p.get("info")
        payload = {"type": "token_count", "info": {
            key: _usage(info.get(key)) for key in ("total_token_usage", "last_token_usage")
        } if isinstance(info, dict) else None, "rate_limits": _limits(p.get("rate_limits"))}
    else:
        return None
    result = {"type": kind, "payload": payload}
    if isinstance(row.get("timestamp"), str):
        result["timestamp"] = row["timestamp"]
    return result


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _cache_path(kind, identity):
    return ledger_runs_dir() / "usage-cache" / (kind + "-" + hashlib.sha256(
        identity.encode("utf-8")).hexdigest() + ".json")


def _read_cache(path):
    try:
        envelope = json.loads(path.read_bytes())
        data = envelope["data"]
        if envelope["sha256"] == hashlib.sha256(_encoded(data)).hexdigest():
            return data
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        pass
    return None


def _write_cache(path, data):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_encoded({"data": data, "sha256": hashlib.sha256(_encoded(data)).hexdigest()}))
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _signature(stat):
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def _anchors(stream, offset):
    position = stream.tell()
    try:
        # SEEK_END 强制放弃 BufferedReader 的旧读缓冲，检查真实文件字节。
        stream.seek(0, os.SEEK_END)
        stream.seek(0)
        first = stream.read(min(ANCHOR, offset))
        stream.seek(max(0, offset - ANCHOR))
        last = stream.read(min(ANCHOR, offset))
        return [hashlib.sha256(first).hexdigest(), hashlib.sha256(last).hexdigest()]
    finally:
        stream.seek(position)


def _scan(stream, rows, warnings, limit):
    """只提交换行结束的行；最后半行留待下次读取。"""
    offset = stream.tell()
    while stream.tell() < limit:
        line = stream.readline(limit - stream.tell())
        if not line.endswith(b"\n"):
            if "转录尾行尚未完整写入" not in warnings:
                warnings.append("转录尾行尚未完整写入")
            break
        offset = stream.tell()
        try:
            row = _project(json.loads(line))
            if row is not None:
                rows.append(row)
        except (ValueError, UnicodeError, RecursionError):
            if "转录存在未完整写入或无效行" not in warnings:
                warnings.append("转录存在未完整写入或无效行")
    return offset


def _snapshot(path, cached=None):
    with path.open("rb") as stream:
        before = _signature(os.fstat(stream.fileno()))
        before_path = _signature(path.stat())
        prefix_anchors = _anchors(stream, before[2])
        rows, warnings, offset = [], [], 0
        if isinstance(cached, dict):
            try:
                old, end = cached["stat"], cached["offset"]
                valid = (cached["version"] == VERSION and cached["path"] == str(path)
                         and type(end) is int and 0 <= end <= old[2] <= before[2]
                         and old[:2] == before[:2]
                         and (old == before or (before[2] > old[2]
                              and before[3] >= old[3] and before[4] >= old[4]))
                         and cached["anchors"] == _anchors(stream, end)
                         and isinstance(cached["rows"], list)
                         and all(isinstance(r, dict) and _project(r) is not None
                                 and _project(r) == r for r in cached["rows"])
                         and isinstance(cached["warnings"], list)
                         and all(isinstance(w, str) for w in cached["warnings"]))
                if valid:
                    rows = list(cached["rows"])
                    warnings = [w for w in cached["warnings"] if w != "转录尾行尚未完整写入"]
                    offset = end
            except (KeyError, TypeError, ValueError, IndexError, RecursionError):
                pass
        stream.seek(offset)
        offset = _scan(stream, rows, warnings, before[2])
        anchors = _anchors(stream, offset)
        prefix_unchanged = prefix_anchors == _anchors(stream, before[2])
        after = _signature(os.fstat(stream.fileno()))
        current = _signature(path.stat())

        def retains_prefix(signature, baseline):
            return (signature[:2] == baseline[:2] and signature[2] >= baseline[2]
                    and (signature == baseline or (signature[2] > baseline[2]
                         and signature[3] >= baseline[3] and signature[4] >= baseline[4])))

        # 按开始大小截止；后续纯追加不影响本次已读取的一致前缀。
        # Windows 的 fstat/stat 对 ctime 可采用不同语义，各自与同种基线比较。
        stable = (before_path[:3] == before[:3] and prefix_unchanged
                  and retains_prefix(after, before) and retains_prefix(current, before_path))
    return rows, warnings, {"version": VERSION, "path": str(path), "stat": before,
                            "offset": offset, "anchors": anchors, "rows": rows,
                            "warnings": warnings}, stable


def read_events(path: Path, use_cache=True) -> tuple[list[dict], list[str]]:
    """逐行读取精简事件；缓存不可读/不可写均不阻断来源读取。"""
    path = Path(path).expanduser().resolve()
    if path.suffix != ".jsonl":
        raise ValueError("暂不支持压缩转录；没有真实记录，不猜测")
    cache_path, cached = None, None
    if use_cache:
        try:
            cache_path = _cache_path("events", str(path))
            cached = _read_cache(cache_path)
        except (OSError, ValueError):
            pass
    # 前缀变化时丢弃全部结果重读；纯追加由 _snapshot 接受。
    for attempt in range(3):
        rows, warnings, data, stable = _snapshot(path, cached if attempt == 0 else None)
        if stable:
            if cache_path is not None:
                _write_cache(cache_path, data)
            return rows, warnings
    raise ValueError("转录在读取期间持续变化，无法取得一致快照；请重试")


def locate_session(root: Path, session_id: str, use_cache=True) -> Path:
    """路径缓存按 root/session 隔离；命中后不再遍历 sessions。"""
    root = Path(root).expanduser().resolve()
    if not isinstance(session_id, str) or not session_id or any(c in session_id for c in "/\\\x00"):
        raise ValueError("无效的 Codex session_id")
    suffix = "-" + session_id + ".jsonl"

    def valid(path):
        return (path.is_relative_to(root) and path.name.startswith("rollout-")
                and path.name.endswith(suffix) and path.is_file())

    cache_path = None
    if use_cache:
        try:
            cache_path = _cache_path("location", str(root) + "\x00" + session_id)
            cached = _read_cache(cache_path)
            if (isinstance(cached, dict) and cached.get("version") == VERSION
                    and cached.get("root") == str(root) and cached.get("session_id") == session_id):
                candidate = Path(cached["path"]).resolve()
                if valid(candidate):
                    return candidate
        except (OSError, ValueError, TypeError, KeyError):
            pass
    matches = set()
    for candidate in root.rglob("rollout-*.jsonl"):
        candidate = candidate.resolve()
        if valid(candidate):
            matches.add(candidate)
    if len(matches) != 1:
        raise ValueError("没有找到唯一的 Codex rollout（压缩文件暂不支持）；没有真实记录")
    path = matches.pop()
    if cache_path is not None:
        _write_cache(cache_path, {"version": VERSION, "root": str(root),
                                 "session_id": session_id, "path": str(path)})
    return path
