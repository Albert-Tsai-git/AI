# -*- coding: utf-8 -*-
"""[启动] 中间服务入口：HTTP 协议接口 + 后台发送/回收 + 飞书长连接（主线程）。
用法：python -m hub.main    （在 feishu-hub 目录下）"""
import json
import threading

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from hub import api, config, service

log = config.get_logger("hub")


def _on_message(data: P2ImMessageReceiveV1):
    # 飞书要求 3 秒内返回；处理只写库 + 入发送队列，不做耗时操作
    try:
        ev, msg = data.event, data.event.message
        service.handle_message(msg.message_id, ev.sender.sender_id.open_id, msg.chat_type, msg.chat_id,
                               msg.message_type, msg.content, msg.parent_id)
    except Exception:  # noqa: BLE001
        log.exception("[飞书] 处理事件异常")


def main():
    cfg = config.load()
    if not cfg["app_id"] or not cfg["app_secret"]:
        raise SystemExit("[启动] ~/.feishu_hub/config.json 缺少 app_id / app_secret")
    service.init(cfg)
    srv = api.serve(cfg["listen_host"], int(cfg["listen_port"]), config.token())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    stop = threading.Event()

    def _startup():
        try:
            service.recover()
        except Exception:  # noqa: BLE001
            log.exception("[启动] 恢复失败")
        service.background_loop(stop)

    threading.Thread(target=_startup, daemon=True).start()
    handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(_on_message).build()
    log.info("[启动] 中间服务启动，飞书长连接建立中 %s", json.dumps({"port": cfg["listen_port"]}))
    lark.ws.Client(cfg["app_id"], cfg["app_secret"], event_handler=handler, log_level=lark.LogLevel.INFO).start()


if __name__ == "__main__":
    main()
