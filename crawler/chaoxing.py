# -*- coding: utf-8 -*-
"""
学习通（超星）全自动爬虫 —— Playwright 浏览器自动化方案。
思路参考：github.com/HAppy-2436/ddl-monitor（二维码登录 + 页面抓取）。

三个能力：
1. 二维码登录：设置页显示二维码 → 手机学习通扫码 → Cookie 落盘（约 7 天有效）
2. 同步抓取：恢复登录 → 打开课程列表 → 逐门课点"作业/考试"标签 → 解析未交作业和剩余时间
3. 登录态失效自动降级：设置页提示重新扫码，也可用"半自动粘贴"模式兜底

设计要点：
- 所有耗时操作（打开浏览器、抓页面）都在【后台线程】执行，绝不卡页面
- 登录/同步状态存模块级变量（线程锁保护），前端轮询获取
- 抓取失败绝不抛异常到上层：状态里带友好错误信息

依赖（安装过一次就行）：
    venv\\Scripts\\python.exe -m pip install playwright
    set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
    venv\\Scripts\\python.exe -m playwright install chromium
"""

import base64
import datetime as dt
import os
import re
import sys
import threading
import time

import config
import models

# ---------- 路径与常量 ----------
COOKIE_PATH = os.path.join(config.DATA_DIR, "cookies", "chaoxing.json")
SPACE_URL = "https://i.mooc.chaoxing.com/space/index"           # 登录页（出二维码）
FY_COURSE_URL = "https://fycourse.fanya.chaoxing.com/fyportal/courselist/course"  # 课程列表
QR_TTL = 300          # 二维码有效期（秒，5 分钟，足够慢慢扫码）
SYNC_TABS = ("作业", "考试")   # 每门课点这两个标签各抓一遍
SYNC_TIMEOUT = 20     # 单个页面加载超时（秒），避免一门课卡死全部

# ---------- 全局状态（单实例，线程锁保护） ----------
_lock = threading.Lock()
# 登录状态机：idle(无流程) / waiting(二维码已生成) / done(登录成功) / expired / failed
_login = {"state": "idle", "png": None, "error": ""}
# 同步状态机：idle / running / done / failed
_sync = {"state": "idle", "items": [], "error": "", "detail": ""}
# 登录"代际"计数：每次点「生成/刷新二维码」就 +1。
# 旧一代的 worker 线程看到代际变了就立刻退出——防止多个浏览器并存、新二维码被旧流程顶掉。
_login_gen = 0


def is_logged_in():
    """是否已保存学习通登录态（有 cookie 文件）"""
    return os.path.exists(COOKIE_PATH)


def login_status():
    """当前登录流程状态（供前端轮询）"""
    with _lock:
        return dict(_login)


def sync_status():
    """当前同步流程状态（供前端轮询）"""
    with _lock:
        return dict(_sync)


def logout():
    """清除登录态（设置页"退出登录"）"""
    with _lock:
        _login.update(state="idle", png=None, error="")
        _sync.update(state="idle", items=[], error="", detail="")
    try:
        os.remove(COOKIE_PATH)
    except OSError:
        pass


# ---------- 浏览器 ----------

def _launch():
    """
    启动无头浏览器（Playwright 同步 API）。三层兜底，保证一定能启动：
      1. exe 打包时内置的浏览器内核（sys._MEIPASS/ms-playwright）
      2. 本机 playwright 下载的 chromium
      3. 系统自带的 Microsoft Edge（Windows 11 一定有，无需下载任何东西）
    """
    # exe 打包版：浏览器内核随 exe 一起打包（build_exe.bat 附带），运行时指到那个位置
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "ms-playwright")
        if os.path.isdir(bundled):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    try:
        browser = p.chromium.launch(headless=True)
    except Exception:
        try:  # 没有下载过 chromium → 用系统自带的 Edge
            browser = p.chromium.launch(headless=True, channel="msedge")
        except Exception:
            p.stop()
            raise RuntimeError("找不到可用的浏览器内核（已尝试 chromium 和 Edge），无法扫码。")
    return p, browser


# ---------- ① 二维码登录 ----------

def start_qr_login():
    """后台线程启动二维码登录流程；每次调用都会重新生成（旧的自动作废）。"""
    global _login_gen
    with _lock:
        _login_gen += 1
        _login.update(state="waiting", png=None, error="")
    threading.Thread(target=_qr_login_worker, args=(_login_gen,), daemon=True).start()
    return "started"


def _stale(gen):
    """这个代际的 worker 是否已被新流程顶替（返回 True 就退出）"""
    with _lock:
        return gen != _login_gen


def _qr_login_worker(gen):
    try:
        p, browser = _launch()
        try:
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto(SPACE_URL + "?t=" + str(int(time.time() * 1000)),
                      wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(3000)   # 等登录页把二维码渲染出来

            qr = page.locator("#quickCode")
            try:
                qr.wait_for(state="visible", timeout=15000)
            except Exception:
                raise RuntimeError("登录页没有显示二维码（学习通页面可能改版，请稍后再试）")

            if _stale(gen):
                return
            # 二维码截图 → base64 发给前端显示
            with _lock:
                _login["png"] = base64.b64encode(qr.screenshot()).decode()

            # 轮询等待扫码成功。判断方法（任一即成功，比只认文字可靠）：
            #   1) 页面出现"退出/个人中心"（登录后的页面文字）
            #   2) 二维码元素消失了（扫码成功后登录页会替换掉二维码）
            deadline = time.time() + QR_TTL
            ok = False
            while time.time() < deadline:
                time.sleep(2)
                if _stale(gen):
                    return
                try:
                    body = page.evaluate("() => document.body ? document.body.innerText : ''")
                    qr_gone = not qr.is_visible()
                    if ("退出" in body or "个人中心" in body) or qr_gone:
                        ok = True
                        break
                except Exception:
                    pass

            if not ok:
                with _lock:
                    _login.update(state="expired", png=None, error="二维码已过期，请点「重新生成」")
                return

            time.sleep(1.5)  # 等登录态 cookie 落定
            os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
            ctx.storage_state(path=COOKIE_PATH)
            with _lock:
                _login.update(state="done", png=None, error="")
            models.add_crawl_log("chaoxing", "success", "学习通扫码登录成功，登录态约 7 天有效。")
        finally:
            browser.close()
            p.stop()
    except Exception as e:
        models.add_crawl_log("chaoxing", "failed", f"学习通扫码登录失败：{e}")
        with _lock:
            _login.update(state="failed", png=None, error=str(e))


# ---------- ② 同步抓取 ----------

def start_sync():
    """后台线程启动同步抓取；未登录直接拒绝。返回 {"ok": bool, "msg": str}。"""
    if not is_logged_in():
        return {"ok": False, "msg": "还没有学习通登录态，请先扫码登录"}
    with _lock:
        if _sync["state"] == "running":
            return {"ok": False, "msg": "正在同步中，请稍候"}
        _sync.update(state="running", items=[], error="", detail="")
    threading.Thread(target=_sync_worker, daemon=True).start()
    return {"ok": True, "msg": "开始同步…"}


def _sync_worker():
    try:
        p, browser = _launch()
        try:
            ctx = browser.new_context(storage_state=COOKIE_PATH)
            page = ctx.new_page()
            page.goto(FY_COURSE_URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(5000)

            # 课程列表：名字 + 进课链接（Playwright evaluate 直接在页面里取）
            courses = page.evaluate("""() => {
                const items = Array.from(document.querySelectorAll('[class*=couritem]'));
                return items.map(it => {
                    const nameEl = it.querySelector('.overHidden2, .courseName, [class*=name]');
                    const link = it.querySelector('a[href*="entercoursenewfy"]');
                    return { name: nameEl ? nameEl.innerText.trim() : '',
                             href: link ? link.href : '' };
                }).filter(x => x.href);
            }""")
            if not courses:
                raise RuntimeError("没有找到课程列表（可能登录已过期，请重新扫码登录）")

            now = dt.datetime.now()
            items = []
            for c in courses:
                # 进入这门课
                try:
                    page.goto(c["href"], wait_until="domcontentloaded", timeout=SYNC_TIMEOUT * 1000)
                    page.wait_for_timeout(2000)
                except Exception:
                    continue  # 单门课打不开跳过，不中断全部
                for tab in SYNC_TABS:
                    try:
                        page.locator(f'li:has-text("{tab}")').first.click(timeout=5000)
                        page.wait_for_timeout(4000)
                    except Exception:
                        continue  # 这门课没有这个标签
                    # 作业/考试列表通常在一个 iframe 里，找它
                    frame = None
                    for f in page.frames:
                        if any(k in f.url for k in ("work/list", "exam", "task", "worklist")):
                            frame = f
                            break
                    if not frame:
                        continue
                    # 作业/考试列表是 JS 异步渲染的：轮询等它出内容（最多 12 秒），
                    # 不然慢网络下可能抓到还没渲染的空页面
                    for _ in range(12):
                        try:
                            txt = frame.evaluate("() => document.body ? document.body.innerText : ''")
                            if "剩余" in txt or "提交" in txt or "考试" in txt:
                                break
                        except Exception:
                            pass
                        time.sleep(1)
                    try:
                        html = frame.content()
                    except Exception:
                        html = frame.evaluate("() => document.documentElement.outerHTML")
                    items.extend(_parse_list_html(html, c["name"], tab, now))

            with _lock:
                detail = f"抓取完成：{len(items)} 条 DDL（" + "、".join(
                    f"{t} {sum(1 for i in items if i['tab'] == t)}条" for t in SYNC_TABS
                ) + "）"
                _sync.update(state="done", items=items, error="", detail=detail)
            models.add_crawl_log("chaoxing", "success", detail)
        finally:
            browser.close()
            p.stop()
    except Exception as e:
        models.add_crawl_log("chaoxing", "failed", f"学习通同步失败：{e}")
        with _lock:
            _sync.update(state="failed", items=[], error=str(e), detail="")


# ---------- ③ 页面解析 ----------

def _parse_remaining(text, now):
    """'剩余 X 天 Y 小时 Z 分钟' 之类 → 具体截止时间；解析不出返回 None"""
    text = text.strip()
    m = re.search(r"剩余\s*(\d+)\s*天\s*(\d+)\s*小时\s*(\d+)\s*分钟", text)
    if m:
        d, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return now + dt.timedelta(days=d, hours=h, minutes=mi)
    m = re.search(r"剩余\s*(\d+)\s*小时\s*(\d+)\s*分钟", text)
    if m:
        return now + dt.timedelta(hours=int(m.group(1)), minutes=int(m.group(2)))
    m = re.search(r"剩余\s*(\d+)\s*分钟", text)
    if m:
        return now + dt.timedelta(minutes=int(m.group(1)))
    m = re.search(r"剩余\s*(\d+)\s*天", text)
    if m:
        return now + dt.timedelta(days=int(m.group(1)))
    return None


def _parse_list_html(html, course_name, tab, now):
    """从作业/考试列表的 HTML 里提取未交/未完成项"""
    items = []
    for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.S):
        content = m.group(1)
        if "剩余" not in content:
            continue
        title_m = re.search(r'class="overHidden2\s*fl"[^>]*>\s*([^<]+)', content)
        if not title_m:
            title_m = re.search(r'class="[^"]*title[^"]*"[^>]*>\s*([^<]+)', content, re.I)
        if not title_m:
            continue
        title = title_m.group(1).strip()

        status_m = re.search(r'class="status\s*fl"[^>]*>\s*([^<]+)', content)
        status = status_m.group(1).strip() if status_m else "未知"

        time_m = re.search(
            r"剩余\s*(\d+\s*天\s*\d+\s*小时\s*\d+\s*分钟|\d+\s*小时\s*\d+\s*分钟|\d+\s*分钟|\d+\s*天)",
            content,
        )
        if not time_m:
            continue
        deadline = _parse_remaining(time_m.group(0), now)
        if deadline is None:
            continue

        items.append({
            "source": "学习通",
            "title": title,                  # 作业标题（课程单独存）
            "course": course_name,
            "tab": tab,
            "status": status,
            "deadline": deadline.strftime("%Y-%m-%d %H:%M"),   # 数据库统一格式
        })
    return items


if __name__ == "__main__":
    # 命令行自测（开发用）：python crawler/chaoxing.py
    if not is_logged_in():
        print("未登录。请从应用设置页扫码登录后再试。")
    else:
        start_sync()
        while sync_status()["state"] == "running":
            time.sleep(1)
        st = sync_status()
        print("状态:", st["state"], st["detail"] or st["error"])
        for i in st["items"]:
            print(f"  [{i['course']}] {i['title']} - {i['deadline']} ({i['status']})")
