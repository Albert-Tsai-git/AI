# -*- coding: utf-8 -*-
"""[飞书] 飞书开放平台接口（发送/回复/历史消息）与卡片构造。只有中间服务调用本模块。"""
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://open.feishu.cn/open-apis"
_token_cache = {"token": "", "exp": 0.0}


def _call(req, timeout=10):
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError("[飞书] 接口错误 code=%s msg=%s" % (data.get("code"), data.get("msg")))
    return data


def _post(url, body, token=None):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return _call(urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers))


def _token(cfg):
    if _token_cache["token"] and time.time() < _token_cache["exp"]:
        return _token_cache["token"]
    data = _post(API + "/auth/v3/tenant_access_token/internal",
                 {"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]})
    _token_cache.update(token=data["tenant_access_token"], exp=time.time() + int(data.get("expire", 7200)) - 300)
    return _token_cache["token"]


def send(cfg, open_id, kind, payload):
    """私聊发送 text / card，返回 message_id。"""
    msg_type, content = _content(kind, payload)
    data = _post(API + "/im/v1/messages?receive_id_type=open_id",
                 {"receive_id": open_id, "msg_type": msg_type, "content": content}, _token(cfg))
    return data["data"]["message_id"]


def reply(cfg, message_id, kind, payload):
    """在指定消息下回复 text / card，返回 message_id。"""
    msg_type, content = _content(kind, payload)
    data = _post(API + "/im/v1/messages/%s/reply" % message_id, {"msg_type": msg_type, "content": content},
                 _token(cfg))
    return data["data"]["message_id"]


def _content(kind, payload):
    if kind == "card":
        return "interactive", payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return "text", json.dumps({"text": payload}, ensure_ascii=False)


def list_chat_messages(cfg, chat_id, start_sec, max_pages=100):
    """[补拉] 按时间升序列出会话中 start_sec 之后的消息（需要读取单聊消息权限）。"""
    items, page = [], ""
    for _ in range(max_pages):
        url = (API + "/im/v1/messages?container_id_type=chat&container_id=%s&start_time=%d"
               "&sort_type=ByCreateTimeAsc&page_size=50" % (urllib.parse.quote(chat_id), int(start_sec)))
        if page:
            url += "&page_token=" + urllib.parse.quote(page)
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _token(cfg)})
        data = _call(req)["data"]
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page = data.get("page_token", "")
    return items


# ---------------- 卡片 ----------------

def compact(text):
    """整理正文：保留 markdown，去掉 SIRE 通道声明行、分隔线和连续空行；标题降为粗体（卡片不支持 #）。"""
    lines = []
    for ln in (text or "").splitlines():
        s = ln.rstrip()
        t = s.strip()
        if t.startswith("[SIRE") or (t and set(t) <= set("-=_")):
            continue
        if t.startswith("#"):
            s = "**%s**" % t.lstrip("# ").replace("**", "")
        if not t and (not lines or not lines[-1]):
            continue
        lines.append(s)
    return "\n".join(lines).strip()


def _sections(body):
    """按标题行（独占一行的粗体）切分区块，代码块内不切。"""
    secs, cur, in_code = [], [], False
    for ln in body.splitlines():
        t = ln.strip()
        if t.startswith("```"):
            in_code = not in_code
        if not in_code and t.startswith("**") and t.endswith("**") and len(t) > 4 and any(x.strip() for x in cur):
            secs.append("\n".join(cur).strip())
            cur = []
        cur.append(ln)
    if any(x.strip() for x in cur):
        secs.append("\n".join(cur).strip())
    return secs or [body]


def _chunks(body, limit):
    """把正文按区块装箱成若干页，每页不超过 limit；超长区块按行硬切，并补齐被切开的代码块。"""
    pages, cur = [], ""
    for sec in _sections(body):
        while len(sec) > limit:
            cut = sec.rfind("\n", 0, limit)
            cut = cut if cut > limit // 2 else limit
            piece, sec = sec[:cut], sec[cut:].lstrip("\n")
            if piece.count("```") % 2:
                piece += "\n```"
                sec = "```\n" + sec
            if cur:
                pages.append(cur)
                cur = ""
            pages.append(piece)
        if cur and len(cur) + len(sec) + 2 > limit:
            pages.append(cur)
            cur = ""
        cur = (cur + "\n\n" + sec) if cur else sec
    if cur:
        pages.append(cur)
    return pages or ["(无文本输出)"]


def result_cards(executor, cwd, text, limit=2800, template="green", icon="✅"):
    """结果卡片：标题=「执行者 · 目录名」，副标题=完整目录；正文过长拆成多张（标注 i/n）。"""
    body = compact(text) or "(无文本输出)"
    name = os.path.basename((cwd or "").rstrip("\\/")) or (cwd or "（无目录）")
    pages = _chunks(body, limit)
    cards = []
    for i, page in enumerate(pages, 1):
        if page.count("```") % 2:
            page += "\n```"
        elements = []
        for j, sec in enumerate(_sections(page)):
            if j:
                elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": sec})
        title = "%s %s · %s" % (icon, (executor or "").title(), name)
        if len(pages) > 1:
            title += "（%d/%d）" % (i, len(pages))
        cards.append({"schema": "2.0", "config": {"wide_screen_mode": True},
                      "header": {"template": template, "title": {"tag": "plain_text", "content": title},
                                 "subtitle": {"tag": "plain_text", "content": cwd or ""}},
                      "body": {"elements": elements}})
    return cards
