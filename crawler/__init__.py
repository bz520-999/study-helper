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


def is_enabled():
    """爬虫总开关（settings 表里 crawl_enabled，默认关闭）"""
    return models.get_setting("crawl_enabled") == "1"


def get_crawler():
    """根据配置返回爬虫实例；没有可用的返回 None"""
    provider = models.get_setting("crawl_provider") or "chaoxing"
    if provider == "chaoxing":
        from crawler.chaoxing import ChaoxingCrawler
        return ChaoxingCrawler()
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
        username = models.get_setting("crawl_username")
        password = security.decrypt_text(models.get_setting("crawl_password"))
        if not username or not password:
            models.add_crawl_log("sync", "failed", "还没有配置账号密码，请先在设置页填写。")
            return

        try:
            crawler.login(username, password)
            items = crawler.fetch_deadlines()
            count = 0
            for it in items:
                title = (it.get("title") or "").strip()
                due_at = (it.get("due_at") or "").strip()
                if not title or not due_at:
                    continue
                course_id = models.find_or_create_course(it.get("course", ""))
                models.add_ddl(title, course_id, due_at, "", 1, 1, source="crawler")
                count += 1
            crawler.close()
            models.add_crawl_log("sync", "success", f"同步完成，新增 {count} 条 DDL。")
        except Exception as e:  # 失败隔离：任何错误都只是记日志
            models.add_crawl_log("sync", "failed", f"同步失败：{e}")
            try:
                crawler.close()
            except Exception:
                pass

    threading.Thread(target=_job, daemon=True).start()
    return "已开始同步，结果稍后可在下方日志中查看。"
