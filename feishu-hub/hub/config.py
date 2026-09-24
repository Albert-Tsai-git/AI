# -*- coding: utf-8 -*-
"""[配置] 中间服务配置：数据目录 ~/.feishu_hub；飞书凭据只从本地 config.json 读取，日志不输出密钥。"""
import json
import logging
import os
import secrets

HOME_DIR = os.environ.get("FEISHU_HUB_HOME") or os.path.join(os.path.expanduser("~"), ".feishu_hub")
CONFIG_PATH = os.path.join(HOME_DIR, "config.json")
TOKEN_PATH = os.path.join(HOME_DIR, "token")
DB_PATH = os.path.join(HOME_DIR, "hub.sqlite3")
LOG_PATH = os.path.join(HOME_DIR, "hub.log")
# 旧飞书桥配置：首次启动时导入凭据与白名单，避免用户重新录入
LEGACY_CONFIG = os.path.join(os.path.expanduser("~"), ".feishu_bridge", "config.json")

DEFAULTS = {
    "app_id": "",
    "app_secret": "",
    # 白名单：只有这些 open_id 的消息会被处理
    "allowed_open_ids": [],
    # 通知发送对象，未设置时取白名单第一个
    "notify_open_id": "",
    "listen_host": "127.0.0.1",
    "listen_port": 8765,
    "lease_ttl_sec": 90,
    "heartbeat_sec": 30,
    "poll_wait_sec": 25,
    # 单任务执行上限（下发给执行器；桌面队列等待也按此超时）
    "task_timeout_sec": 1800,
    # 每日远程任务上限（按领取执行计数，含续跑）
    "daily_task_limit": 20,
    # 会话被桌面端占用时的最大自动重试次数
    "session_busy_max_retries": 3,
    # 目录缺失时展示给用户的建议目录（仍需用户确认，绝不自动使用）
    "suggest_cwd": r"D:\sire\AI\SESSION",
    # 单张卡片正文上限（超出拆分为多张）
    "card_max_chars": 2800,
    # 离线补拉：从上次存活时间往前多拉的秒数
    "backfill_margin_sec": 300,
    # 命中这些关键词的指令需要二次确认（防误触，不是安全边界；安全边界是白名单）
    "danger_keywords": ["删除", "删掉", "清空", "rm -rf", "reset --hard", "push -f",
                        "--force", "drop table", "格式化", "回滚", "Remove-Item", "rmdir", "del /s",
                        "git clean", "delete", "drop ",
                        "cc-switch", "ccswitch", "cc switch", "settings.json", "settings", "hooks",
                        "hook", "配置文件", "全局配置", "通用配置", ".claude-feishu", "config.json",
                        ".codex", "config.toml", "notify", ".feishu_hub", "token"],
    # 可选执行者
    "executors": ["claude", "codex"],
}


def _bootstrap():
    """首次启动：创建数据目录；若没有配置则从旧飞书桥导入凭据与白名单。"""
    os.makedirs(HOME_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        raw = {}
        if os.path.exists(LEGACY_CONFIG):
            with open(LEGACY_CONFIG, "r", encoding="utf-8-sig") as f:
                old = json.load(f)
            raw = {k: old[k] for k in ("app_id", "app_secret", "allowed_open_ids", "notify_open_id") if k in old}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    if not os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(secrets.token_urlsafe(32))


def load():
    """读取配置并补齐默认值。"""
    _bootstrap()
    cfg = dict(DEFAULTS)
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        cfg.update(json.load(f))
    return cfg


def token():
    _bootstrap()
    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        return f.read().strip()


def notify_target(cfg):
    return cfg.get("notify_open_id") or (cfg["allowed_open_ids"][0] if cfg["allowed_open_ids"] else "")


def get_logger(name="hub"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        os.makedirs(HOME_DIR, exist_ok=True)
        h = logging.FileHandler(LOG_PATH, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger
