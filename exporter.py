# -*- coding: utf-8 -*-
"""
导出模块：把数据导出成三种通用格式。
  iCal      —— 日历软件都能读的 .ics 文件（DDL 事件带"提前1天""提前3小时"两个闹钟）
  CSV       —— Excel 能打开（加 BOM 签名，中文不乱码）
  Markdown  —— 笔记软件/记事本都能看
"""

import csv
import io
import json
import re
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

        # 闹钟：按自定义的提前小时数生成（如提前 6 小时 → "还剩 6 小时"）
        # 注意：d 是 sqlite3.Row，只能用下标 d["..."]，没有 .get() 方法
        hours = d["remind_before_hours"] or 0
        if hours > 0:
            alarm = icalendar.Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"提醒：{d['title']} 还剩 {_fmt_remind(hours)}！")
            alarm.add("trigger", timedelta(hours=-hours))   # 负号 = 提前
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


def _fmt_remind(hours):
    """把提前小时数写成好读的话：24 → "1 天"，48 → "2 天"，168 → "1 周" """
    hours = int(hours)
    if hours % 168 == 0:
        return f"{hours // 168} 周"
    if hours % 24 == 0:
        return f"{hours // 24} 天"
    return f"{hours} 小时"


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


def to_json_ddl(ddls):
    """DDL 清单 → JSON（换电脑/备份用，格式和 parse_import_content 兼容）"""
    rows = [{
        "title": d["title"],
        "course": d["course_name"] or "",
        "due_at": d["due_at"],
        "note": d["note"] or "",
        "done": d["status"] == "done",
    } for d in ddls]
    return json.dumps(rows, ensure_ascii=False, indent=2)


# ==================== 导入（CSV / JSON 解析） ====================

_TIME_RE = re.compile(
    r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?"
)


def _normalize_time(text):
    """把各种写法统一成 2026-08-20 23:00；识别不了返回 None"""
    if not text:
        return None
    text = str(text).strip()
    m = _TIME_RE.match(text)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    hour = int(m.group(4)) if m.group(4) else 23   # 只写了日期 → 默认当天 23:59
    minute = int(m.group(5)) if m.group(5) else 59
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _decode_bytes(raw):
    """按 UTF-8（带不带 BOM 都行）解码；Excel 存的是 GBK 时兜底"""
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_import_content(filename, raw):
    """
    解析导入文件（CSV 或 JSON），返回 (items, 错误消息或 None)。
    items 每项：{"title", "course", "due_at", "note", "done"}
    CSV 兼容本应用导出的格式：任务名称,课程,截止时间,状态,备注
    JSON 兼容本应用导出的格式：数组，每项 title/course/due_at/note/done
    """
    name = (filename or "").lower()
    text = _decode_bytes(raw)
    items = []

    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return [], f"JSON 解析失败：{e}"
        if isinstance(data, dict):
            data = data.get("ddl") or data.get("items") or []
        if not isinstance(data, list):
            return [], "JSON 格式不对：应是一个数组（可从导出页导出 JSON 得到）"
        for row in data:
            if not isinstance(row, dict):
                continue
            due_at = _normalize_time(row.get("due_at") or row.get("deadline"))
            title = (row.get("title") or "").strip()
            if not title or not due_at:
                continue
            items.append({
                "title": title,
                "course": (row.get("course") or row.get("course_name") or "").strip(),
                "due_at": due_at,
                "note": (row.get("note") or "").strip(),
                "done": bool(row.get("done")),
            })

    elif name.endswith(".csv") or name.endswith(".txt"):
        # 用 csv 模块解析（自动处理引号/逗号）
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return [], "文件是空的"
        # 表头识别：第一行里有没有"任务名称/标题/title"
        header = [c.strip() for c in rows[0]]
        idx_title = idx_course = idx_time = idx_note = idx_done = None
        for i, h in enumerate(header):
            if h in ("任务名称", "标题", "title", "Title", "任务名"):
                idx_title = i
            elif h in ("课程", "course", "课程名"):
                idx_course = i
            elif h in ("截止时间", "截止日期", "时间", "due_at", "due", "deadline"):
                idx_time = i
            elif h in ("备注", "note", "说明"):
                idx_note = i
            elif h in ("状态", "status"):
                idx_done = i
        if idx_title is None:
            # 没表头 → 按位置：第一列标题、第二列课程、第三列时间
            idx_title, idx_course, idx_time = 0, 1, 2
            data_rows = rows
        else:
            data_rows = rows[1:]
        for row in data_rows:
            if not row or not any(c.strip() for c in row):
                continue
            title = (row[idx_title] if len(row) > idx_title else "").strip()
            due_at = _normalize_time(row[idx_time] if len(row) > idx_time else "")
            if not title or not due_at:
                continue
            done = False
            if idx_done is not None and len(row) > idx_done:
                done = row[idx_done].strip() in ("已完成", "完成", "done", "1", "是", "true", "True")
            items.append({
                "title": title,
                "course": (row[idx_course] if idx_course is not None and len(row) > idx_course else "").strip(),
                "due_at": due_at,
                "note": (row[idx_note] if idx_note is not None and len(row) > idx_note else "").strip(),
                "done": done,
            })

    else:
        return [], "只支持 CSV 或 JSON 文件"

    return items, None


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
