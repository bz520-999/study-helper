# -*- coding: utf-8 -*-
"""
提醒模块：算出每条 DDL 还剩多少时间、是否过期、是否紧急。
注意：我们没有后台定时任务——每次打开页面时现算，最简单、最可靠、零维护。
"""

import datetime

import config


def parse_dt(text):
    """把数据库里的 "YYYY-MM-DD HH:MM" 文字变成电脑能算的时间"""
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")


def annotate(tasks, now=None):
    """
    给每条任务附加计算好的信息（只算不算，不改数据库）：
      overdue     是否已过期
      urgent      是否在红色高亮时间窗内（默认 24 小时）
      hours_left  剩余小时数
      label       给人看的文字，如"剩 2 小时"、"已过期"
    """
    if now is None:
        now = datetime.datetime.now()
    result = []
    for t in tasks:
        due = parse_dt(t["due_at"])
        left = due - now
        hours_left = left.total_seconds() / 3600
        overdue = hours_left < 0
        urgent = (not overdue) and hours_left < config.URGENT_HOURS

        # 生成给人看的时间描述
        if overdue:
            label = "已过期"
        elif hours_left < 1:
            label = f"剩 {int(left.total_seconds() // 60)} 分钟"
        elif hours_left < config.REMIND_1D_HOURS:
            label = f"剩 {int(hours_left)} 小时"
        else:
            label = f"剩 {int(hours_left // 24)} 天"

        result.append({
            "task": t,
            "overdue": overdue,
            "urgent": urgent,
            "hours_left": hours_left,
            "label": label,
        })
    return result
