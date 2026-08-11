# -*- coding: utf-8 -*-
"""
邮件发送模块：把 DDL 生成 .ics 附件，通过 SMTP 定时发到邮箱。
只用 Python 标准库（smtplib / email），零额外安装。
发信失败抛异常由调用方记录日志，绝不碰核心数据（失败隔离，与爬虫同哲学）。
"""

import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import exporter
import models


def build_ics_str():
    """生成当前全部进行中 DDL + 复习计划的 .ics 内容（str）"""
    return exporter.to_ical(
        models.list_ddl_tasks(status="pending"),
        models.list_review_plans(),
    )


def build_summary_text(ddls):
    """邮件正文：DDL 文字摘要（不打开日历软件也能直接看）"""
    if not ddls:
        return (
            "当前没有进行中的 DDL 任务。\n\n"
            "附件 study.ics 是完整日历文件，可用手机日历导入。\n"
            "—— 学习助手 Pro 自动发送"
        )
    lines = ["你的 DDL 清单（按截止时间排序）：", ""]
    for d in ddls:
        course = f"（{d['course_name']}）" if d["course_name"] else ""
        lines.append(f"· {d['due_at']}  {d['title']}{course}")
    lines += [
        "",
        "附件 study.ics 为日历文件：手机收到邮件后点开附件，",
        "选择「用日历打开」即可导入（支持自定义提醒闹钟）。",
        "—— 学习助手 Pro 自动发送",
    ]
    return "\n".join(lines)


def parse_addresses(text):
    """收件人文本 → 邮箱列表（兼容逗号/分号/中文逗号，去空格去重复）"""
    addrs = []
    for part in (text or "").replace("，", ",").replace("；", ";").replace(",", ";").split(";"):
        a = part.strip()
        if a and "@" in a and a not in addrs:
            addrs.append(a)
    return addrs


def send_ical_email(smtp_host, smtp_port, sender, auth_code, to_addrs, cc_addrs):
    """
    发送一封带 study.ics 附件的邮件（正文带 DDL 文字摘要）。
    成功返回进行中任务数；失败抛异常（smtplib.SMTPAuthenticationError 等），由调用方记录日志。
    """
    ddls = models.list_ddl_tasks(status="pending")
    ics_str = exporter.to_ical(ddls, models.list_review_plans())

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Subject"] = Header(f"学习助手 DDL 日历（{len(ddls)} 项进行中）", "utf-8")

    # 正文：文字摘要（纯文本，任何手机都能看）
    msg.attach(MIMEText(build_summary_text(ddls), "plain", "utf-8"))
    # 附件：study.ics 日历文件（手机日历直接导入）
    part = MIMEText(ics_str, "calendar", "utf-8")
    part.add_header("Content-Disposition", "attachment", filename="study.ics")
    msg.attach(part)

    all_addrs = list(to_addrs) + list(cc_addrs)
    with smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=15) as server:
        server.login(sender, auth_code)
        server.sendmail(sender, all_addrs, msg.as_string())
    return len(ddls)
