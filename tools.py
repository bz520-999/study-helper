# -*- coding: utf-8 -*-
"""
智能体的"工具"：把学习助手 Pro 的现有功能包装成可被大模型调用的接口。
每个工具 = 名字 + 给大模型看的说明（description）+ 参数说明 + 执行函数。
大模型看完用户的话，会自己决定调用哪个工具、填什么参数。
"""

import autotag
import ddl_parser
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


def _review_text():
    plans = models.list_review_plans()
    if not plans:
        return "还没有生成复习计划，可以让我为某条 DDL 生成复习清单。"
    return "；".join(
        f"{p['plan_date']} {p['content']}（{'已完成' if p['done'] else '未完成'}）" for p in plans
    )


def _courses_text():
    rows = models.list_courses()
    return "、".join(r["name"] for r in rows) if rows else "还没有课程。"


def _find_ddl(ddl_id):
    for t in models.list_ddl_tasks():
        if t["id"] == ddl_id:
            return t
    return None


# ==================== 操作类工具的实现 ====================

def _add_ddl(title, due_at, course="", note="", remind_1d=True, remind_3h=True):
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
    models.add_ddl(title, course_id, due_at, note, 1 if remind_1d else 0, 1 if remind_3h else 0)
    return f"已添加 DDL：{title}（{course or '未分类'}，截止 {due_at}）"


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
    info = models.generate_review_plan(ddl_id)
    if info is None:
        return f"找不到 id={ddl_id} 的 DDL。"
    if info[0] == 0:
        return "这条 DDL 已过期或今天截止，没有可安排的复习日。"
    return f"已为这条 DDL 生成 {info[0]} 条复习计划。"


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
        "name": "query_courses",
        "description": "列出所有课程。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _courses_text(),
    },
    {
        "name": "query_review_plans",
        "description": "查询复习计划。当用户问\"复习\"相关问题时调用。",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda **kw: _review_text(),
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
                "remind_1d": {"type": "boolean", "description": "是否提前 1 天提醒，默认 true"},
                "remind_3h": {"type": "boolean", "description": "是否提前 3 小时提醒，默认 true"},
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
