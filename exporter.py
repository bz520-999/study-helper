# -*- coding: utf-8 -*-
"""
导出模块：把数据导出成三种通用格式。
  iCal      —— 日历软件都能读的 .ics 文件（DDL 事件带"提前1天""提前3小时"两个闹钟）
  CSV       —— Excel 能打开（加 BOM 签名，中文不乱码）
  Markdown  —— 笔记软件/记事本都能看
"""

import csv
import io
import uuid
from datetime import date, datetime, timedelta

import icalendar

import reminder


# ==================== iCal ====================

def to_ical(ddls, plans):
    """
    生成 .ics 日历文件内容。
    ddls：DDL 任务列表（每条带提醒开关和课程名）
    plans：复习计划列表（转成全天事件）
    """
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Study Helper Pro//学习助手//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "学习助手 DDL")

    # ---- DDL 变成日历事件，附两个闹钟 ----
    for d in ddls:
        ev = icalendar.Event()
        ev.add("uid", str(uuid.uuid4()))
        title = f"[DDL] {d['title']}"
        if d["course_name"]:
            title += f"（{d['course_name']}）"
        ev.add("summary", title)
        if d["note"]:
            ev.add("description", d["note"])

        start = reminder.parse_dt(d["due_at"])   # 截止那一刻就是事件开始
        ev.add("dtstart", start)
        ev.add("dtend", start + timedelta(hours=1))
        ev.add("dtstamp", datetime.now())

        # 闹钟 1：提前 1 天
        if d["remind_1d"]:
            alarm = icalendar.Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"提醒：{d['title']} 还剩 1 天！")
            alarm.add("trigger", timedelta(days=-1))   # 负号 = 提前
            ev.add_component(alarm)

        # 闹钟 2：提前 3 小时
        if d["remind_3h"]:
            alarm = icalendar.Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"提醒：{d['title']} 还剩 3 小时！")
            alarm.add("trigger", timedelta(hours=-3))
            ev.add_component(alarm)

        cal.add_component(ev)

    # ---- 复习计划变成全天事件 ----
    for p in plans:
        ev = icalendar.Event()
        ev.add("uid", str(uuid.uuid4()))
        ev.add("summary", f"[复习] {p['ddl_title']}")
        ev.add("description", p["content"])
        ev.add("dtstamp", datetime.now())
        year, month, day = (int(x) for x in p["plan_date"].split("-"))
        ev.add("dtstart", date(year, month, day))   # 全天事件（直接传 date 对象）
        cal.add_component(ev)

    return cal.to_ical().decode("utf-8")


# ==================== CSV ====================

def _csv_bytes(rows):
    """把二维表格写成 CSV 字节（utf-8-sig = 带 BOM，Excel 打开中文不乱码）"""
    out = io.StringIO()
    writer = csv.writer(out)
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode("utf-8-sig")


def to_csv_ddl(ddls):
    """DDL 清单 → CSV"""
    rows = [["任务名称", "课程", "截止时间", "状态", "备注"]]
    for d in ddls:
        rows.append([
            d["title"],
            d["course_name"] or "",
            d["due_at"],
            "已完成" if d["status"] == "done" else "进行中",
            d["note"] or "",
        ])
    return _csv_bytes(rows)


def to_csv_plans(plans):
    """复习清单 → CSV"""
    rows = [["复习日期", "复习内容", "所属任务", "完成状态"]]
    for p in plans:
        rows.append([p["plan_date"], p["content"], p["ddl_title"], "已完成" if p["done"] else "未完成"])
    return _csv_bytes(rows)


def to_csv_materials(materials):
    """资料目录 → CSV（标签用顿号连接）"""
    rows = [["标题", "文件名", "课程", "标签", "上传时间", "备注"]]
    for m in materials:
        rows.append([
            m["title"],
            m["file_name"] or "",
            m["course_name"] or "",
            "、".join(m["tags"]),
            m["created_at"],
            m["notes"] or "",
        ])
    return _csv_bytes(rows)


# ==================== Markdown ====================

def to_markdown_ddl(ddls):
    """DDL 清单 → Markdown"""
    lines = ["# DDL 清单", "",
             f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for d in ddls:
        status = "✅ 已完成" if d["status"] == "done" else "⏳ 进行中"
        line = f"- **{d['title']}**（{d['course_name'] or '未分类'}）｜截止：{d['due_at']}｜{status}"
        if d["note"]:
            line += f"｜备注：{d['note']}"
        lines.append(line)
    return "\n".join(lines)


def to_markdown_plans(plans, profile_note=""):
    """复习清单 → Markdown（可附学习画像说明）"""
    lines = ["# 复习清单", ""]
    if profile_note:
        lines.append(f"> {profile_note}")
    lines += [f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for p in plans:
        mark = "✅" if p["done"] else "☐"
        lines.append(f"- [{mark}] **{p['plan_date']}** {p['content']}")
    return "\n".join(lines)


def to_markdown_materials(materials):
    """资料目录 → Markdown（按课程分组）"""
    by_course = {}
    for m in materials:
        by_course.setdefault(m["course_name"] or "未分类", []).append(m)

    lines = ["# 资料目录", "",
             f"共 {len(materials)} 份资料，导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for course_name in sorted(by_course):
        items = by_course[course_name]
        lines.append(f"## {course_name}（{len(items)} 份）")
        for m in items:
            tags = "、".join(m["tags"]) or "无标签"
            lines.append(f"- **{m['title']}**（{m['file_name']}）｜标签：{tags}｜上传：{m['created_at']}")
        lines.append("")
    return "\n".join(lines)
