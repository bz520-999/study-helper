# -*- coding: utf-8 -*-
"""
后台任务：智能体"主动提醒"。
每天早上定时检查当天到期/已过期的 DDL，生成一条站内通知。
（这是全项目第一个后台定时任务；提醒本身不依赖它，它是主动出击的部分。）
"""

import datetime

import config
import models


def check_today_ddls():
    """
    检查今天到期和已过期的 DDL，写一条通知。
    同一天只写一次（去重），没有要提醒的就什么都不做。
    """
    today = datetime.date.today()
    today_str = today.isoformat()

    conn = models.db.get_conn()
    try:
        # 去重：今天已经生成过 daily 通知就不再生成
        row = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE kind='daily' AND date(created_at)=?",
            (today_str,),
        ).fetchone()
        if row[0] > 0:
            return 0
    finally:
        conn.close()

    items = models.list_ddl_tasks(status="pending")
    due_today = [t for t in items if t["due_at"][:10] == today_str]
    overdue = [t for t in items if t["due_at"] < f"{today_str} 00:00"]

    parts = []
    if due_today:
        parts.append("今天截止：" + "、".join(t["title"] for t in due_today))
    if overdue:
        parts.append("已过期未完成：" + "、".join(t["title"] for t in overdue))
    if not parts:
        return 0

    models.add_notification("daily", "🤖 智能体提醒：" + "；".join(parts))
    return 1


def start_scheduler():
    """启动后台定时器（每天 AGENT_CHECK_HOUR 点检查一次）"""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    hour = int(models.get_setting("agent_check_hour") or config.AGENT_CHECK_HOUR)
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(check_today_ddls, CronTrigger(hour=hour, minute=5), id="agent_daily_check")
    sched.start()
