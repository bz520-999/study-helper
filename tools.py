# -*- coding: utf-8 -*-
"""
智能体的"工具"：把学习助手 Pro 的现有功能包装成可被大模型调用的接口。
每个工具 = 名字 + 给大模型看的说明（description）+ 参数说明 + 执行函数。
大模型看完用户的话，会自己决定调用哪个工具、填什么参数。
"""

import json
import re

import autotag
import ddl_parser
import llm
import models
import reminder
import search


# ==================== 把数据变成好读的文字 ====================

def _fmt_ddl(t):
    """一条 DDL → 一句话（末尾带 id=数字，供模型执行操作时使用）"""
    status = "已完成" if t["status"] == "done" else "进行中"
    course = t["course_name"] or "未分类"
    return f"{t['title']}（{course}）截止 {t['due_at']}，{status}，id={t['id']}"


def _pending_ddls_text():
    items = models.list_ddl_tasks(status="pending")
    if not items:
        return "当前没有进行中的 DDL 任务。"
    return "；".join(_fmt_ddl(t) for t in items)


def _all_ddls_text():
    items = models.list_ddl_tasks()
    return "；".join(_fmt_ddl(t) for t in items) if items else "还没有任何 DDL 任务。"


def _materials_text(keyword="", course="", tag=""):
    items = search.search_materials(keyword=keyword, tag_name=tag)
    if course:
        items = [m for m in items if m["course_name"] == course]
    if not items:
        return "没有找到符合条件的学习资料。"
    parts = []
    for m in items:
        tags = "、".join(m["tags"]) or "无标签"
        parts.append(f"{m['title']}（{m['course_name'] or '未分类'}，标签：{tags}）")
    return "；".join(parts)


def _review_text(status=""):
    """复习计划按 DDL 分组输出（好读、信息全），可按完成状态过滤"""
    plans = models.list_review_plans()
    if not plans:
        return "还没有复习计划，可以让我为某条 DDL 生成复习清单。"
    if status:
        done_flag = 1 if status in ("done", "已完成", "完成") else 0
        plans = [p for p in plans if p["done"] == done_flag]
        if not plans:
            return "没有" + ("已完成" if done_flag else "未完成") + "的复习计划。"
    groups = {}
    for p in plans:
        groups.setdefault(p["ddl_id"],
            {"title": p["ddl_title"], "due": p["ddl_due"], "course": p["course_name"], "plans": []})
        groups[p["ddl_id"]]["plans"].append(p)
    out = []
    for g in groups.values():
        lines = [f"{g['title']}（{g['course'] or '未分类'}，截止 {g['due']}）："]
        for p in g["plans"]:
            mark = "已完成" if p["done"] else "未完成"
            lines.append(f"  {p['plan_date']} {p['content']}（{mark}，plan_id={p['id']}）")
        out.append("\n".join(lines))
    return "\n".join(out)


def _profile_text():
    """学习画像 → 好读的文字（复习节奏的定制依据）"""
    if models.get_setting("profile_done") != "1":
        return "还没填写学习画像，现在用的是默认规则：考前第 14、7、3、1 天各复习一次，7 天以内每天一次。"
    n = models.get_setting("profile_nickname") or "未设置"
    hours = models.get_setting("profile_hours") or "1"
    lead = models.get_setting("profile_lead_days") or "14"
    rhythm = models.get_setting("profile_rhythm") or "每天"
    weak = models.get_setting("profile_weak") or "（无）"
    return (f"学习画像：昵称 {n}；每天可投入 {hours} 小时；提前 {lead} 天开始复习；"
            f"复习节奏 {rhythm}；薄弱科目 {weak}。")


def _courses_text():
    """系统里出现过的课程名（DDL/资料关联时自动记录的标签，不是课表！）"""
    rows = models.list_courses()
    return "、".join(r["name"] for r in rows) if rows else "还没有课程。"


def _schedule_text():
    """真实课表（教务系统同步）：按星期分组列出课程 + 节次 + 教室"""
    rows = models.list_course_schedule()
    if not rows:
        return "还没有课表数据。可以到「设置」页同步教务系统导入课表。"
    by_day = {}
    for r in rows:
        by_day.setdefault(r["day"] or "未排", []).append(r)
    days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    lines = []
    for d in days:
        items = by_day.get(d)
        if not items:
            continue
        parts = []
        for r in items:
            s = r["course_name"]
            sec = (r["sections"] or r["slot"] or "").strip()
            loc = (r["location"] or "").strip()
            weeks = (r["weeks"] or "").strip()
            extra = []
            if sec:
                extra.append(f"{sec}节")
            if loc:
                extra.append(loc)
            if weeks:
                extra.append(f"{weeks}周")
            if extra:
                s += "（" + "，".join(extra) + "）"
            parts.append(s)
        lines.append(f"{d}：{'、'.join(parts)}")
    return "；".join(lines) if lines else "课表里还没有排课。"


def _find_ddl(ddl_id):
    for t in models.list_ddl_tasks():
        if t["id"] == ddl_id:
            return t
    return None


# ==================== 操作类工具的实现 ====================

def _add_ddl(title, due_at, course="", note="", remind_hours=None):
    if not title or not due_at:
        return "任务名称和截止时间不能为空。"
    due_at = due_at.strip().replace("T", " ")
    try:
        reminder.parse_dt(due_at)   # 标准格式直接用
    except ValueError:
        # 支持自然语言时间："下周三下午两点" → 自动换算成具体日期
        rel = ddl_parser.parse_relative(due_at)
        if not rel:
            return (f"时间我看不懂：{due_at}。可以用 2026-08-20 23:00 标准格式，"
                    f"或 下周三下午两点、明天晚上9点、3天后 这类自然说法。")
        due_at = f"{rel['date'].isoformat()} {rel['hour']:02d}:{rel['minute']:02d}"
    # 没给课程时，从任务名里自动识别（"高数作业" → 高等数学）
    if not course:
        course = autotag.suggest_course(title)
    course_id = models.find_or_create_course(course)
    # 查重：相同任务名+课程+截止时间说明已经记过了
    if models.ddl_exists(title, course_id, due_at):
        return f"这条 DDL 之前已经记过了（{title}，{course or '未分类'}，截止 {due_at}），没有重复添加。"
    # 提醒时机：默认提前 1 天；用户说了就按说的来（如"提前2天提醒我" → remind_hours=48）
    hours = remind_hours if remind_hours is not None else 24
    models.add_ddl(title, course_id, due_at, note, hours)
    remind_note = "（不提醒）" if hours == 0 else f"（提前 {hours} 小时提醒）"
    return f"已添加 DDL：{title}（{course or '未分类'}，截止 {due_at}）{remind_note}"


def _complete_ddl(ddl_id):
    if not _find_ddl(ddl_id):
        return f"找不到 id={ddl_id} 的 DDL。"
    models.complete_ddl(ddl_id)
    return f"已把 DDL id={ddl_id} 标记为完成。"


def _update_ddl(ddl_id, title="", due_at="", note=""):
    if not _find_ddl(ddl_id):
        return f"找不到 id={ddl_id} 的 DDL。"
    sets, params = [], []
    if title:
        sets.append("title = ?")
        params.append(title)
    if due_at:
        due_at = due_at.strip().replace("T", " ")
        try:
            reminder.parse_dt(due_at)
        except ValueError:
            rel = ddl_parser.parse_relative(due_at)
            if not rel:
                return f"时间我看不懂：{due_at}。可以用 2026-08-20 23:00 或 下周三下午两点 这类说法。"
            due_at = f"{rel['date'].isoformat()} {rel['hour']:02d}:{rel['minute']:02d}"
        sets.append("due_at = ?")
        params.append(due_at)
    if not sets:
        return "没有需要修改的内容。"
    params.append(ddl_id)
    models.db.execute(f"UPDATE ddl_tasks SET {', '.join(sets)} WHERE id = ?", params)
    return f"已修改 DDL id={ddl_id}。"


def _delete_ddl(ddl_id):
    if not _find_ddl(ddl_id):
        return f"找不到 id={ddl_id} 的 DDL。"
    models.delete_ddl(ddl_id)
    return f"已删除 DDL id={ddl_id}。"


def _generate_review(ddl_id):
    """为 DDL 生成复习计划：排期按画像规则，内容由智能体定制（失败降级默认模板）"""
    info = models.generate_review_plan(ddl_id)
    if info is None:
        return f"找不到 id={ddl_id} 的 DDL。"
    count, rows = info
    if count == 0:
        return "这条 DDL 已过期或今天截止，没有可安排的复习日。"
    custom = _custom_review_contents(rows)
    if custom:
        for r in rows:
            if r["plan_date"] in custom:
                models.db.execute(
                    "UPDATE review_plans SET content = ? WHERE id = ?",
                    (custom[r["plan_date"]], r["id"]),
                )
        return f"已为这条 DDL 生成 {count} 条复习计划，内容按你的课程和资料定制好了。"
    return f"已为这条 DDL 生成 {count} 条复习计划（智能体暂时不可用，用了默认复习内容）。"


def _custom_review_contents(rows):
    """
    调大模型为每个复习日写具体可执行的复习内容。
    成功返回 {复习日期: 内容}；任何失败（没配 Key / 网络 / 解析失败）返回 None，
    调用方会降级使用默认模板，绝不影响生成功能。
    """
    if not llm.api_key():
        return None
    ddl = rows[0]
    # 课程名 + 关联资料 + DDL 标题/截止（给模型当素材）
    # 注意：rows 来自 review_plans 表（只有 id/ddl_id/plan_date/content/done），
    # 标题和截止时间要另外查 ddl_tasks
    course_name, materials, ddl_title, ddl_due = "", [], "", ""
    try:
        conn = models.db.get_conn()
        ddl_row = conn.execute("SELECT * FROM ddl_tasks WHERE id = ?", (ddl["ddl_id"],)).fetchone()
        if ddl_row:
            ddl_title = ddl_row["title"]
            ddl_due = ddl_row["due_at"]
            if ddl_row["course_id"]:
                c = conn.execute("SELECT name FROM courses WHERE id = ?", (ddl_row["course_id"],)).fetchone()
                if c:
                    course_name = c["name"]
                materials = [m["title"] for m in conn.execute(
                    "SELECT title FROM materials WHERE course_id = ? ORDER BY created_at",
                    (ddl_row["course_id"],)).fetchall()]
        conn.close()
    except Exception:
        pass
    dates = "、".join(r["plan_date"] for r in rows)
    materials_text = "；".join(materials) if materials else "（暂无资料）"
    prompt = [
        {"role": "system", "content": (
            "你是经验丰富的学习规划师，为学生的考前复习安排具体可执行的复习内容。"
            "要求：只输出一个 JSON 数组，格式 [{\"date\": \"2026-08-16\", \"content\": \"复习内容\"}, ...]，"
            "数组长度和给出的复习日期数量一致，每个日期一条。"
            "content 用中文写 30-60 字，必须具体可执行：写清复习哪个章节/哪份资料/做什么练习；"
            "离截止日越近的内容越精（做真题、错题），越远越粗（通读、搭框架）；每条内容不能一样。"
        )},
        {"role": "user", "content": (
            f"任务：{ddl_title or '（未命名任务）'}，截止 {ddl_due or '（未知）'}。\n"
            f"课程：{course_name or '未分类'}。\n关联资料：{materials_text}。\n"
            f"复习日期：{dates}。"
        )},
    ]
    try:
        text = llm.call(prompt, max_tokens=2000)
    except Exception:
        return None
    return _parse_review_json(text)


def _parse_review_json(text):
    """模型可能包一层 ```json 代码块，逐层尝试解析；解析失败返回 None（降级）"""
    for s in (text.strip(), text.strip().strip("`"),
              re.sub(r"^```json\s*", "", text.strip()).rstrip("`").strip()):
        try:
            data = json.loads(s)
        except (ValueError, TypeError):
            continue
        if (isinstance(data, list) and len(data) > 0
                and all(isinstance(x, dict) and x.get("date") and x.get("content") for x in data)):
            return {x["date"]: x["content"].strip() for x in data if x["content"].strip()}
    return None


def _find_review_plan(plan_id):
    for p in models.list_review_plans():
        if p["id"] == plan_id:
            return p
    return None


def _set_review_done(plan_id, done):
    p = _find_review_plan(plan_id)
    if not p:
        return f"找不到 id={plan_id} 的复习计划。"
    if (p["done"] == 1) == done:
        return f"这条复习计划本来就是{'完成' if done else '未完成'}状态。"
    models.toggle_review_plan(plan_id)
    return f"已把复习计划标为{'完成' if done else '未完成'}：{p['plan_date']} {p['content']}"


def _clear_review(ddl_id):
    found = [p for p in models.list_review_plans() if p["ddl_id"] == ddl_id]
    if not found:
        return f"id={ddl_id} 的这条 DDL 没有复习计划。"
    models.clear_review_plans(ddl_id)
    return f"已清空这条 DDL 的全部 {len(found)} 条复习计划。"


def _update_profile(nickname="", hours="", lead_days="", rhythm="", weak=""):
    """只更新用户提到的画像字段，其余保持不变"""
    try:
        if hours:
            hours = str(float(hours))
            if hours not in ("0.5", "1.0", "2.0", "3.0", "4.0"):
                return "每天可投入时间只能是 0.5 / 1 / 2 / 3 / 4 小时。"
        if lead_days:
            lead = int(lead_days)
            if lead not in (7, 14, 30, 60):
                return "提前开始天数只能是 7 / 14 / 30 / 60 天。"
        if rhythm and rhythm not in ("每天", "隔天"):
            return "复习节奏只能是「每天」或「隔天」。"
    except (ValueError, TypeError):
        return "时间或天数填的数字不对，请用 7 / 14 / 30 / 60 这类整数。"
    if nickname:
        models.set_setting("profile_nickname", nickname)
    if hours:
        models.set_setting("profile_hours", hours)
    if lead_days:
        models.set_setting("profile_lead_days", str(lead))
    if rhythm:
        models.set_setting("profile_rhythm", rhythm)
    if weak is not None:
        models.set_setting("profile_weak", weak)
    models.set_setting("profile_done", "1")   # 填过就算完成画像
    return f"已更新学习画像。当前：{_profile_text()}"


# ==================== 工具清单 ====================
# description 是写给大模型看的：描述什么时候用这个工具

TOOLS = [
    {
        "name": "query_pending_ddls",
        "description": "查询所有进行中的 DDL 任务（考试、作业、提交等截止事项）。当用户问\"有什么考试/作业/DDL/截止日期\"时调用。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _pending_ddls_text(),
    },
    {
        "name": "query_all_ddls",
        "description": "查询全部 DDL 任务（含已完成的）。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _all_ddls_text(),
    },
    {
        "name": "query_materials",
        "description": "搜索学习资料（课件/PDF 等），可按关键词、课程名或标签筛选。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "关键词，如\"第三章\""},
                "course": {"type": "string", "description": "课程名，如\"高等数学\""},
                "tag": {"type": "string", "description": "标签，如\"作业\""},
            },
        },
        "handler": lambda keyword="", course="", tag="": _materials_text(keyword, course, tag),
    },
    {
        "name": "query_schedule",
        "description": "查询我的开学课程表（教务系统同步的真实课表：星期几、第几节、教室、周次）。当用户问\"我有什么课/课表/每周几上什么课/某门课什么时候在哪上\"时调用。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _schedule_text(),
    },
    {
        "name": "query_courses",
        "description": "列出系统里出现过的课程名（DDL、资料关联时自动记录的课程标签）。注意：这不是课表！用户问\"我的课表/我有什么课\"请用 query_schedule。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _courses_text(),
    },
    {
        "name": "query_review_plans",
        "description": "查询复习计划（按任务分组展示，含每条计划的日期、内容和完成状态）。当用户问\"复习\"相关问题时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "可选：只看某状态，填 done 或 pending。如\"我还有哪些没复习\"→ pending"},
            },
        },
        "handler": lambda status="": _review_text(status),
    },
    {
        "name": "query_profile",
        "description": "查询学习画像（复习节奏的定制依据：每天可投入时间、提前几天开始复习、节奏、薄弱科目）。当用户问\"我的画像/复习设置/复习节奏\"时调用。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _profile_text(),
    },
    {
        "name": "update_profile",
        "description": "修改学习画像（影响之后生成的复习计划节奏）。只填用户提到的字段，没提到的保持不变。修改前建议先 query_profile 看看当前值，并把改动复述给用户确认。",
        "parameters": {
            "type": "object",
            "properties": {
                "nickname": {"type": "string", "description": "昵称（可选）"},
                "hours": {"type": "string", "description": "每天可投入复习时间：0.5 / 1 / 2 / 3 / 4（可选）"},
                "lead_days": {"type": "string", "description": "提前几天开始复习：7 / 14 / 30 / 60（可选）"},
                "rhythm": {"type": "string", "description": "复习节奏：每天 或 隔天（可选）"},
                "weak": {"type": "string", "description": "薄弱科目，逗号分隔，会多安排复习（可选；传空字符串=清空）"},
            },
        },
        "handler": _update_profile,
    },
    {
        "name": "complete_review_plan",
        "description": "把一条复习计划标记为完成，或取消完成（标错了时）。需要先查询得到 plan_id。",
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer", "description": "复习计划的 id"},
                "done": {"type": "boolean", "description": "true=标记完成；false=取消完成"},
            },
            "required": ["plan_id", "done"],
        },
        "handler": _set_review_done,
    },
    {
        "name": "clear_review_plans",
        "description": "清空某条 DDL 的全部复习计划（重新生成时也会覆盖）。危险操作：调用前必须先向用户复述要清空的任务名并征得明确同意。",
        "parameters": {
            "type": "object",
            "properties": {"ddl_id": {"type": "integer", "description": "DDL 的 id"}},
            "required": ["ddl_id"],
        },
        "handler": _clear_review,
    },
    {
        "name": "add_ddl",
        "description": "新增一条 DDL 任务（考试/作业截止）。用户要求添加/录入任务时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务名称，如\"高数期中考试\""},
                "due_at": {"type": "string", "description": "截止时间。可以是标准格式（2026-08-20 23:00），也可以是自然语言（下周三下午两点、明天晚上9点、3天后），工具会自动换算。用户怎么说就怎么填，不要自己心算日期。"},
                "course": {"type": "string", "description": "课程名（可选）"},
                "note": {"type": "string", "description": "备注（可选）"},
                "remind_hours": {"type": "integer", "description": "提前多少小时提醒（可选）。用户说\"提前2天\"就填 48，\"提前1小时\"填 1，\"不要提醒\"填 0；没提就省略，默认提前 24 小时（1 天）"},
            },
            "required": ["title", "due_at"],
        },
        "handler": _add_ddl,
    },
    {
        "name": "complete_ddl",
        "description": "把一条 DDL 标记为已完成。需要先查询得到 ddl_id。",
        "parameters": {
            "type": "object",
            "properties": {"ddl_id": {"type": "integer", "description": "DDL 的 id"}},
            "required": ["ddl_id"],
        },
        "handler": _complete_ddl,
    },
    {
        "name": "update_ddl",
        "description": "修改一条 DDL 的标题、截止时间或备注。需要先查询得到 ddl_id。",
        "parameters": {
            "type": "object",
            "properties": {
                "ddl_id": {"type": "integer"},
                "title": {"type": "string", "description": "新标题（可选）"},
                "due_at": {"type": "string", "description": "新截止时间 YYYY-MM-DD HH:MM（可选）"},
                "note": {"type": "string", "description": "新备注（可选）"},
            },
            "required": ["ddl_id"],
        },
        "handler": _update_ddl,
    },
    {
        "name": "delete_ddl",
        "description": "删除一条 DDL。删除是危险操作：调用前必须先向用户复述要删除的任务并征得明确同意。",
        "parameters": {
            "type": "object",
            "properties": {"ddl_id": {"type": "integer"}},
            "required": ["ddl_id"],
        },
        "handler": _delete_ddl,
    },
    {
        "name": "generate_review_plan",
        "description": "为一条 DDL 生成（或重新生成）复习清单。需要先查询得到 ddl_id。",
        "parameters": {
            "type": "object",
            "properties": {"ddl_id": {"type": "integer"}},
            "required": ["ddl_id"],
        },
        "handler": _generate_review,
    },
]

# 给大模型的工具清单（去掉执行函数，只留描述）
TOOL_SCHEMAS = [
    {"type": "function", "function": {k: v for k, v in t.items() if k != "handler"}}
    for t in TOOLS
]


def execute_tool(name, args):
    """执行一个工具。返回 (是否成功, 结果文字)。"""
    for t in TOOLS:
        if t["name"] == name:
            try:
                return True, str(t["handler"](**args))
            except TypeError as e:
                return False, f"参数不完整：{e}"
            except Exception as e:
                return False, f"执行失败：{e}"
    return False, f"未知工具：{name}"
