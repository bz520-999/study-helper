# -*- coding: utf-8 -*-
"""
验证码"人工输入桥"：爬虫登录遇到验证码时，把图片交给页面让用户看，
用户输入后爬虫再继续登录。和梨课程 App 的做法一样——OCR 认不动的验证码，
人眼一眼就能读出来。

原理：爬虫在后台线程里跑，遇到验证码就调用 request_captcha() 把图片
发到前端并阻塞等待；设置页前端轮询 captcha_status() 发现有图就显示出来，
用户输入后 submit() 把答案交回；爬虫拿到答案继续登录。
"""
import base64
import threading
import uuid

# 一把锁保护共享状态（前端和爬虫线程同时读写，防止错乱）
_lock = threading.Lock()
# 爬虫等用户输入的"门铃"：set() 后等待的人立即醒来
_wait = threading.Event()

# 当前验证码状态
_state = {
    "status": "idle",        # idle=没有待输入的 | waiting=爬虫在等用户输 | submitted=已提交 | timeout=超时
    "image_base64": "",      # 验证码图片（base64 编码，前端直接当图片显示）
    "token": "",             # 本次验证码的唯一编号（防止提交错位，暂作预留）
    "answer": "",
}

# 用户超过这个秒数没输入，就放弃本次登录（避免后台线程永远等下去）
WAIT_TIMEOUT = 120


def request_captcha(image_bytes):
    """
    爬虫线程调用：把验证码图片交给页面，阻塞等待用户输入。
    用户在 WAIT_TIMEOUT 秒内提交 → 返回输入的字符；超时/没输入 → 返回 None。
    """
    with _lock:
        _state["status"] = "waiting"
        _state["image_base64"] = base64.b64encode(image_bytes).decode("utf-8")
        _state["token"] = uuid.uuid4().hex
        _state["answer"] = ""
        _wait.clear()
    _wait.wait(timeout=WAIT_TIMEOUT)   # 等用户输入（或超时）
    with _lock:
        answer = _state["answer"]
        _state["status"] = "submitted" if answer else "timeout"
        _state["image_base64"] = ""    # 用完清掉，避免前端看到旧图
    return answer or None


def captcha_status():
    """设置页轮询用：当前有没有待输入的验证码、图片是什么。"""
    with _lock:
        return dict(_state)


def captcha_submit(answer):
    """设置页提交用户输入的验证码。返回 {"ok": 是否成功, "msg": 说明}。"""
    answer = (answer or "").strip()
    with _lock:
        if _state["status"] != "waiting":
            return {"ok": False, "msg": "当前没有待输入的验证码"}
        if not answer:
            return {"ok": False, "msg": "验证码不能为空"}
        _state["answer"] = answer
        _wait.set()   # 叫醒正在等待的爬虫线程
        return {"ok": True, "msg": "已提交"}
