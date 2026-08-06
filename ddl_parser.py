# -*- coding: utf-8 -*-
"""
DDL 提取器：从一段粘贴的文字里，自动找出截止时间和任务名。
核心工具是"正则表达式"——一种找字规则。规则都集中在文件顶部，方便调整。
"""

import datetime
import re

# ---------- 日期规则 ----------
# 支持：2026-08-20、2026/8/20、2026.8.20、2026年8月20日、8月20日、8/20、8.20
DATE_RE = re.compile(
    r"(?P<year>20\d{2})[年\-/\.](?P<month>\d{1,2})[月\-/\.](?P<day>\d{1,2})日?|"
    r"(?P<month2>\d{1,2})月(?P<day2>\d{1,2})日?|"
    r"(?P<month3>\d{1,2})[/\.](?P<day3>\d{1,2})"
)

# ---------- 时间规则 ----------
# 支持：23:00、下午3点、晚上9点半、3点
TIME_RE = re.compile(
    r"(?P<hour1>\d{1,2}):(?P<minute1>\d{2})|"
    r"(?P<ampm>上午|下午|晚上|凌晨)?(?P<hour2>\d{1,2})点(?P<minute2>\d{1,2}|半)?"
)

# ---------- 任务名触发词 ----------
# 日期附近出现这些词，说明它属于一个任务
TRIGGER_WORDS = ["截止", "提交", "考试", "交", "ddl", "DDL", "Due", "之前", "前"]

# 任务名尾部要剥掉的连接词/标点（如"考试时间：" → "考试"、"实验下" → "实验"）
TITLE_CLEAN_RE = re.compile(r"[：:，,。、\s到于前之内时间下]+$")

# 日期后面跟着"XX前交/提交/考试 XXX"时，从这里抠任务名
AFTER_DATE_RE = re.compile(r"(?:前|之前)?(?:交|提交|考试|截止)[：:]?([^，。；、\s]{2,12})")

# 在日期后面多远范围内找时间（如"8月20日23:00"的时间在日期后面）
TIME_WINDOW = 40

# ---------- 相对时间规则（"下周三下午两点"这类说法）----------
# 中文数字 → 阿拉伯数字（两点→2，十点半→10:30，二十五→25）
CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
WEEKDAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

# 相对日期：今天/明天/后天/大后天、周X/下周X、X天后、X月X日、X号
RELATIVE_DATE_RE = re.compile(
    r"(今天|明天|后天|大后天)|"
    r"(下(?:周|星期|礼拜))?(?:周|星期|礼拜)([一二三四五六日天])|"
    r"(\d{1,2})天(?:后|之内)|"
    r"(\d{1,2})月(\d{1,2})[日号]?|"
    r"(\d{1,2})号"
)

# 中文时间："下午两点"、"晚上9点半"、"14:30"
TIME_CN_RE = re.compile(r"(上午|中午|下午|晚上|凌晨)?([0-9一二两三四五六七八九十]+)点(半)?")
TIME_24_RE = re.compile(r"(\d{1,2}):(\d{2})")


def cn2num(s):
    """中文数字转阿拉伯数字：两→2，十→10，十五→15，二十→20，二十五→25"""
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    if s.startswith("十"):
        return 10 + CN_NUM.get(s[1:], 0)
    if s.endswith("十") and len(s) == 2:
        return CN_NUM.get(s[0], 0) * 10
    if "十" in s:
        left, right = s.split("十", 1)
        return CN_NUM.get(left, 0) * 10 + CN_NUM.get(right, 0)
    return None


def parse_relative(text, now=None, start_at=0):
    """
    解析自然语言时间："下周三下午两点"、"明天晚上9点"、"3天后"、"8月25日09:30"。
    start_at：从文字的第几个字符开始找（配合循环使用，逐个提取多个时间）。
    返回 {"date": 日期, "hour": 时, "minute": 分, "start": 日期在原文中的位置, "end": 结束位置}；
    找不到返回 None。
    """
    if now is None:
        now = datetime.datetime.now()
    today = now.date()

    # ---- 1. 找日期部分 ----
    m = RELATIVE_DATE_RE.search(text[start_at:])
    if not m:
        return None
    start, end = m.start() + start_at, m.end() + start_at

    if m.group(1):  # 今天/明天/后天/大后天
        delta = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}[m.group(1)]
        d = today + datetime.timedelta(days=delta)
    elif m.group(3):  # 周X / 下周X
        wd = WEEKDAY_MAP[m.group(3)]
        if m.group(2):  # 带"下"：下一个完整周的星期X
            d = today + datetime.timedelta(days=(7 - today.weekday()) + (wd - 1))
        else:  # 今天或之后的最近一个星期X（"周三"今天周四 → 下周三）
            d = today + datetime.timedelta(days=(wd - 1 - today.weekday()) % 7)
    elif m.group(4):  # X天后
        d = today + datetime.timedelta(days=int(m.group(4)))
    elif m.group(5):  # X月X日（没写年份：今年，已过则明年）
        month, day = int(m.group(5)), int(m.group(6))
        try:
            d = datetime.date(today.year, month, day)
        except ValueError:
            return None
        if d < today:
            d = datetime.date(today.year + 1, month, day)
    else:  # X号（本月，已过则下月）
        day = int(m.group(7))
        try:
            d = datetime.date(today.year, today.month, day)
        except ValueError:
            return None
        if d < today:
            try:
                d = datetime.date(today.year, today.month + 1, day)
            except ValueError:
                return None

    # ---- 2. 找时间部分（在日期前后一小段文字里）----
    hour, minute = 23, 59  # 没写时间默认当天 23:59
    window = text[max(0, start - 10): end + 40]
    tm = TIME_24_RE.search(window)
    if tm:
        hour, minute = int(tm.group(1)), int(tm.group(2))
    else:
        tm = TIME_CN_RE.search(window)
        if tm:
            hour = cn2num(tm.group(2)) or 0
            minute = 30 if tm.group(3) else 0
            ampm = tm.group(1) or ""
            if ampm in ("下午", "晚上") and hour < 12:
                hour += 12
            elif ampm == "凌晨" and hour == 12:
                hour = 0
    if hour > 23 or minute > 59:
        hour, minute = 23, 59

    return {"date": d, "hour": hour, "minute": minute, "start": start, "end": end}


def parse_ddl_text(text):
    """
    从文字里提取所有 DDL。
    返回列表，每项 {"title": 任务名, "due_at": "YYYY-MM-DD HH:MM"}；
    找不到任何日期时返回空列表。
    """
    results = []
    today = datetime.date.today()
    prev_end = 0  # 上一个日期的结束位置：往前看时不能越过它，否则会卷进上一个任务的内容
    for m in DATE_RE.finditer(text):
        # ---- 1. 确定年月日 ----
        # 没写年份就默认今年；如果已经过了，就自动当成明年
        if m.group("year"):
            year, month, day = int(m.group("year")), int(m.group("month")), int(m.group("day"))
        elif m.group("month2"):
            year, month, day = today.year, int(m.group("month2")), int(m.group("day2"))
        else:
            year, month, day = today.year, int(m.group("month3")), int(m.group("day3"))
        try:
            due_date = datetime.date(year, month, day)
        except ValueError:
            continue  # 日期不合法（如 13月40日），跳过
        if not m.group("year") and due_date < today:
            due_date = datetime.date(year + 1, month, day)

        # ---- 2. 在日期后面找时间 ----
        after = text[m.end(): m.end() + TIME_WINDOW]
        hour, minute = 23, 59  # 没写时间就默认当天 23:59
        tm = TIME_RE.search(after)
        if tm:
            if tm.group("hour1"):
                hour, minute = int(tm.group("hour1")), int(tm.group("minute1"))
            else:
                hour = int(tm.group("hour2"))
                minute = 30 if tm.group("minute2") == "半" else int(tm.group("minute2") or 0)
                if tm.group("ampm") in ("下午", "晚上") and hour < 12:
                    hour += 12
                elif tm.group("ampm") == "凌晨" and hour == 12:
                    hour = 0
            if hour > 23 or minute > 59:
                hour, minute = 23, 59

        # ---- 3. 找任务名 ----
        before = text[max(prev_end, m.start() - 20): m.start()]
        title = _extract_title(before, after)

        due_at = f"{due_date.year:04d}-{due_date.month:02d}-{due_date.day:02d} {hour:02d}:{minute:02d}"
        # 同样的任务重复出现时只留一次
        if not any(r["due_at"] == due_at and r["title"] == title for r in results):
            results.append({"title": title, "due_at": due_at})
        prev_end = m.end()  # 下一条往前看时，不能越过这条日期

    # 相对时间补充（"下周三前交实验报告"）：逐个提取所有相对日期。
    # 绝对日期（如"8月20日"）可能也会被相对规则匹配到，与已有结果去重即可。
    pos = 0
    while True:
        rel = parse_relative(text, start_at=pos)
        if not rel:
            break
        pos = rel["end"]
        # before 窗口不能越过上一个绝对日期（prev_end），否则会卷进前一条任务的内容
        before = text[max(prev_end, rel["start"] - 20): rel["start"]]
        after = text[rel["end"]: rel["end"] + TIME_WINDOW]
        title = _extract_title(before, after)
        due_at = (f"{rel['date'].year:04d}-{rel['date'].month:02d}-{rel['date'].day:02d} "
                  f"{rel['hour']:02d}:{rel['minute']:02d}")
        # 相对规则可能重复命中已提取的绝对日期（如"8月20日"），按截止时间去重
        if not any(r["due_at"] == due_at for r in results):
            results.append({"title": title, "due_at": due_at})
    return results


def _extract_title(before, after):
    """从日期前后的文字里确定任务名（两个提取器共用）"""
    before_title = _title_from_before(before)
    after_title = _title_from_after(after)
    has_trigger_before = any(w in before for w in TRIGGER_WORDS)
    if before_title and has_trigger_before:
        return before_title        # "高数作业截止于8月20日" → "高数作业"
    if after_title:
        return after_title         # "8月20日前交实验报告" → "实验报告"
    if before_title:
        return before_title
    return "待办事项"


def _title_from_before(before):
    """从日期前面的文字找任务名：取最后一个触发词前面的部分"""
    last = max((before.rfind(w) for w in TRIGGER_WORDS), default=-1)
    if last >= 0:
        title = before[:last]
        if not title.strip():
            # 触发词在开头（如"考试时间：..."）→ 直接用触发词当任务名
            title = TITLE_CLEAN_RE.sub("", before[last:]).strip()
            return title or before[last:]
    else:
        title = before
    title = TITLE_CLEAN_RE.sub("", title).strip()
    # 防污染：标题里若混入了标点（如"3:00，请大家按时提交。英语"），
    # 说明把别的句子卷进来了，只保留最后一个标点后面的部分
    punct = re.search(r"[：:，,。；、;]([^：:，,。；、;]*)$", title)
    if punct and punct.group(1).strip():
        return punct.group(1).strip()
    return title


def _title_from_after(after):
    """日期后面有"XX前交实验报告"这类写法时，抠出任务名"""
    m = AFTER_DATE_RE.search(after)
    return m.group(1) if m else ""
