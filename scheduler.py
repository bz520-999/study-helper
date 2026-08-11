# -*- coding: utf-8 -*-
"""
后台任务：智能体"主动提醒"。
每天早上定时检查当天到期/已过期的 DDL，生成一条站内通知。
（这是全项目第一个后台定时任务；提醒本身不依赖它，它是主动出击的部分。）
"""

import datetime

import config
import email_sender
import models
import security


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


_sched = None  # 全局调度器实例（start_scheduler 时创建，reload_email_job 复用）


def email_ical_daily():
    """定时发送：把最新 DDL 的 .ics 附件发到配置的邮箱。
    开关没开 / 配置不完整 / 间隔未到期就直接跳过；发失败只写日志，绝不外抛（失败隔离）。"""
    if models.get_setting("email_enabled") != "1":
        return
    # 每 N 天频率：距上次成功发送不足 N 天就不发
    if (models.get_setting("email_freq") or "daily") == "interval":
        n = int(models.get_setting("email_interval_days") or 3)
        last = models.get_setting("email_last_sent_date")
        if last:
            try:
                last_d = datetime.date.fromisoformat(last)
                if (datetime.date.today() - last_d).days < n:
                    return
            except ValueError:
                pass
    host = models.get_setting("email_smtp_host") or config.SMTP_HOST
    port = models.get_setting("email_smtp_port") or str(config.SMTP_PORT)
    sender = models.get_setting("email_username")
    auth = security.decrypt_text(models.get_setting("email_auth_code"))
    to = models.get_setting("email_to")
    cc = models.get_setting("email_cc")
    if not sender or not auth or not to:
        models.add_crawl_log("email", "skipped", "邮箱未配置完整，跳过本次定时发送")
        return
    try:
        to_addrs = email_sender.parse_addresses(to)
        cc_addrs = email_sender.parse_addresses(cc)
        n = email_sender.send_ical_email(host, port, sender, auth, to_addrs, cc_addrs)
        # 记录成功日期（每 N 天频率用）；今天已发过就覆盖为今天
        models.set_setting("email_last_sent_date", datetime.date.today().isoformat())
        models.add_crawl_log(
            "email", "success",
            f"已发送 DDL 日历到 {', '.join(to_addrs)}（含 {n} 条进行中任务）",
        )
    except Exception as e:
        models.add_crawl_log("email", "failed", f"定时发送失败：{e}")


def _email_trigger():
    """按设置生成邮箱任务的 CronTrigger：daily=每天 / weekly=每周几 / interval=每天跑但任务内判断间隔"""
    from apscheduler.triggers.cron import CronTrigger

    hour = int(models.get_setting("email_send_hour") or config.EMAIL_SEND_HOUR)
    minute = int(models.get_setting("email_send_minute") or 0)
    freq = models.get_setting("email_freq") or "daily"
    if freq == "weekly":
        weekdays = (models.get_setting("email_weekdays") or "0,1,2,3,4").split(",")
        names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        dows = ",".join(names[int(i)] for i in weekdays if i.strip().isdigit() and 0 <= int(i) <= 6)
        if dows:
            return CronTrigger(day_of_week=dows, hour=hour, minute=minute)
    return CronTrigger(hour=hour, minute=minute)


def reload_email_job():
    """按最新设置重排邮箱定时任务（保存设置后调用，不用重启应用）"""
    global _sched
    if _sched is None:
        return
    try:
        _sched.remove_job("email_ical_daily")
    except Exception:
        pass
    _sched.add_job(email_ical_daily, _email_trigger(), id="email_ical_daily")


def start_scheduler():
    """启动后台定时器（智能体主动提醒 + 邮箱定时发送 iCal）"""
    global _sched
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    hour = int(models.get_setting("agent_check_hour") or config.AGENT_CHECK_HOUR)
    _sched = BackgroundScheduler(daemon=True)
    _sched.add_job(check_today_ddls, CronTrigger(hour=hour, minute=5), id="agent_daily_check")
    _sched.add_job(email_ical_daily, _email_trigger(), id="email_ical_daily")
    _sched.start()
