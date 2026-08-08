# -*- coding: utf-8 -*-
"""
爬虫模块统一入口（2026-08-08 合并队友代码后版本）。

当前两个爬虫：
1. 学习通（超星）全自动同步（crawler/chaoxing.py，扫码版）
   - 登录：手机扫码（不用密码，绕开 RSA 加密和验证码）→ 登录态存本地约 7 天
   - 抓取：Playwright 无头浏览器打开课程列表 → 逐门课点"作业/考试"标签 → 解析 DDL
   - 交互：设置页显示二维码 → 扫码 → 前端轮询状态 → 预览勾选导入 DDL 清单
2. 教务系统（crawler/jwxt.py，队友开发）
   - 强智教务 + ehall2 统一认证；抓考试安排 + 课表同步（course_schedule 表）

设计原则（评审重点）：
  - 后台线程执行，不卡页面（登录/同步状态由前端轮询）
  - 失败隔离：任何异常只写 crawl_logs 日志 + 状态提示，绝不向外抛
  - 只新增不覆盖：抓到的 DDL 标记 source=crawler，可人工删改
  - 不影响核心功能：爬虫不开，其他功能照常
"""

import threading

import models
import security
from crawler import chaoxing

# 显式导入验证码"人工输入桥"，让 app.py 的 crawler.captcha 能访问到
# （captcha 是子模块，光 import crawler 不会自动把它挂成属性）
import crawler.captcha as captcha


def is_enabled():
    """爬虫总开关（settings 表里 crawl_enabled，默认关闭）"""
    return models.get_setting("crawl_enabled") == "1"


# 把学习通模块的常用函数直接暴露给 app.py 使用
# —— start_qr_login / start_sync / login_status / sync_status / is_logged_in / logout
start_qr_login = chaoxing.start_qr_login
start_sync = chaoxing.start_sync
login_status = chaoxing.login_status
sync_status = chaoxing.sync_status
is_logged_in = chaoxing.is_logged_in
logout = chaoxing.logout


def get_crawler():
    """根据配置返回爬虫实例；没有可用的返回 None"""
    provider = models.get_setting("crawl_provider") or "jwxt"
    if provider == "jwxt":
        from crawler.jwxt import JwxtCrawler
        return JwxtCrawler()
    # provider == "chaoxing"：学习通已改为扫码全自动（没有旧版 ChaoxingCrawler），
    # 同步走设置页的「学习通同步」按钮（start_sync），不走这里
    return None


def run_sync():
    """
    立即执行一次同步（在后台线程里跑）——教务爬虫的通用调度入口。
    结果写入 crawl_logs；用户随时可以在设置页查看。
    """
    def _job():
        if not is_enabled():
            models.add_crawl_log("sync", "skipped", "爬虫开关未开启，跳过同步。")
            return
        crawler = get_crawler()
        if crawler is None:
            models.add_crawl_log("sync", "failed", "没有可用的爬虫配置。")
            return
        provider = models.get_setting("crawl_provider") or "jwxt"
        username = models.get_setting("crawl_username")
        password = security.decrypt_text(models.get_setting("crawl_password"))
        if not username or not password:
            models.add_crawl_log("sync", "failed", "还没有配置账号密码，请先在设置页填写。")
            return

        try:
            crawler.login(username, password)
            # 1. 抓考试安排 → DDL
            items = crawler.fetch_deadlines()
            count = 0
            for it in items:
                title = (it.get("title") or "").strip()
                due_at = (it.get("due_at") or "").strip()
                if not title or not due_at:
                    continue
                course_id = models.find_or_create_course(it.get("course", ""))
                note = it.get("location") or ""
                models.add_ddl(title, course_id, due_at, note, 1, 1, source="crawler")
                count += 1

            # 2. 教务爬虫额外抓课表 → 课程安排
            sched_count = 0
            if provider == "jwxt":
                try:
                    sched = crawler.fetch_schedule()
                    if sched:
                        models.clear_course_schedule()   # 同步前先清旧课表
                        for s in sched:
                            models.add_course_schedule(
                                (s.get("title") or "").strip(),
                                (s.get("teacher") or "").strip(),
                                (s.get("day") or "").strip(),
                                (s.get("big_section") or "").strip(),
                                (s.get("weeks") or "").strip(),
                                (s.get("location") or "").strip(),
                                "",
                                (s.get("sections") or "").strip(),
                            )
                        sched_count = len(sched)
                except Exception as se:
                    models.add_crawl_log("sync", "failed", f"课表同步失败：{se}")
                    sched_count = -1

            crawler.close()
            parts = [f"新增 {count} 条考试DDL"]
            if sched_count >= 0:
                parts.append(f"课表 {sched_count} 门")
            models.add_crawl_log("sync", "success", f"同步完成，{'、'.join(parts)}。")
        except Exception as e:  # 失败隔离：任何错误都只是记日志
            models.add_crawl_log("sync", "failed", f"同步失败：{e}")
            try:
                crawler.close()
            except Exception:
                pass

    threading.Thread(target=_job, daemon=True).start()
    return "已开始同步，结果稍后可在下方日志中查看。"
