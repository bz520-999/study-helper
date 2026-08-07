# -*- coding: utf-8 -*-
"""
爬虫管理器：统一调度所有爬虫。
设计原则（评审重点）：
  - 默认关闭：设置里的开关关着时，爬虫完全不运行
  - 失败隔离：任何异常都捕获并写入 crawl_logs，绝不向外抛，绝不影响其他功能
  - 独立线程：在后台跑，不卡页面
  - 只新增不覆盖：爬到的 DDL 标记 source=crawler，人工可删可改
"""

import threading

import models
import security

# 显式导入验证码"人工输入桥"，让 app.py 的 crawler.captcha 能访问到
# （captcha 是子模块，光 import crawler 不会自动把它挂成属性）
import crawler.captcha as captcha


def is_enabled():
    """爬虫总开关（settings 表里 crawl_enabled，默认关闭）"""
    return models.get_setting("crawl_enabled") == "1"


def get_crawler():
    """根据配置返回爬虫实例；没有可用的返回 None"""
    provider = models.get_setting("crawl_provider") or "chaoxing"
    if provider == "chaoxing":
        from crawler.chaoxing import ChaoxingCrawler
        return ChaoxingCrawler()
    if provider == "jwxt":
        from crawler.jwxt import JwxtCrawler
        return JwxtCrawler()
    return None


def run_sync():
    """
    立即执行一次同步（在后台线程里跑）。
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
        provider = models.get_setting("crawl_provider") or "chaoxing"
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
