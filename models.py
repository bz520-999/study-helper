# -*- coding: utf-8 -*-
"""
数据访问层：所有对数据库的"增删改查"都集中在这个文件。
约定：路由代码（app.py）不直接写 SQL，只调用这里的函数。
"""

import datetime

import config
import db
import reminder


# ==================== 课程 ====================

def find_or_create_course(name):
    """按名字找课程；找不到就自动创建一条。返回课程 id（没填课程则返回 None）。"""
    if not name or not name.strip():
        return None
    name = name.strip()
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM courses WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO courses (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_courses():
    """列出全部课程（按名称排序）"""
    conn = db.get_conn()
    try:
        return conn.execute("SELECT * FROM courses ORDER BY name").fetchall()
    finally:
        conn.close()


# ==================== DDL 任务 ====================

def add_ddl(title, course_id, due_at, note="", remind_1d=1, remind_3h=1, source="manual"):
    """新增一条 DDL"""
    return db.execute(
        "INSERT INTO ddl_tasks (title, course_id, due_at, note, remind_1d, remind_3h, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, course_id, due_at, note, remind_1d, remind_3h, source),
    )


def ddl_exists(title, course_id, due_at):
    """同一标题+课程+截止时间是否已存在（防止爬虫重复导入）"""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM ddl_tasks WHERE title = ? AND course_id = ? AND due_at = ?",
            (title, course_id, due_at),
        ).fetchone()
        return row is not None
    finally:
        conn.close()



def list_ddl_tasks(status=None):
    """
    列出 DDL 任务（按截止时间从近到远排序），顺便带上课程名。
    status 传 'pending' 只看未完成；不传则全部。
    """
    conn = db.get_conn()
    try:
        sql = """
            SELECT d.*, c.name AS course_name
            FROM ddl_tasks d
            LEFT JOIN courses c ON d.course_id = c.id
        """
        if status:
            rows = conn.execute(sql + " WHERE d.status = ? ORDER BY d.due_at", (status,)).fetchall()
        else:
            rows = conn.execute(sql + " ORDER BY d.due_at").fetchall()
        return rows
    finally:
        conn.close()


def complete_ddl(task_id):
    """把一条 DDL 标记为已完成"""
    db.execute("UPDATE ddl_tasks SET status = 'done' WHERE id = ?", (task_id,))


def delete_ddl(task_id):
    """删除一条 DDL"""
    db.execute("DELETE FROM ddl_tasks WHERE id = ?", (task_id,))


# ==================== 资料 ====================

def add_material(course_id, title, file_name, stored_name, ext, notes="", source="manual"):
    """新增一份资料（文件本体已保存到磁盘，这里只记档案）"""
    return db.execute(
        "INSERT INTO materials (course_id, title, file_name, stored_name, ext, notes, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (course_id, title, file_name, stored_name, ext, notes, source),
    )


def get_material(material_id):
    """按 id 查一份资料"""
    conn = db.get_conn()
    try:
        return conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
    finally:
        conn.close()


def list_materials():
    """
    列出全部资料（最新在前），每条带课程名和标签。
    先把资料和标签分别查出来，再在代码里按 material_id 拼到一起。
    """
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT m.*, c.name AS course_name
            FROM materials m
            LEFT JOIN courses c ON m.course_id = c.id
            ORDER BY m.created_at DESC, m.id DESC
        """).fetchall()
        tag_rows = conn.execute("""
            SELECT mt.material_id, t.name
            FROM material_tags mt
            JOIN tags t ON mt.tag_id = t.id
            ORDER BY t.name
        """).fetchall()
        tags_by_material = {}
        for tr in tag_rows:
            tags_by_material.setdefault(tr["material_id"], []).append(tr["name"])

        result = []
        for r in rows:
            d = dict(r)  # sqlite 行 → 普通字典，方便加字段
            d["tags"] = tags_by_material.get(d["id"], [])
            result.append(d)
        return result
    finally:
        conn.close()


def delete_material(material_id):
    """删除资料档案（同时删掉它关联的标签配对）"""
    conn = db.get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM material_tags WHERE material_id = ?", (material_id,))
            conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        rebuild_fts()
    finally:
        conn.close()


# ==================== 全文搜索索引（FTS5 + jieba） ====================

def _fts_available(conn):
    """检查这个 SQLite 版本是否支持 FTS5"""
    if not config.FTS_ENABLED:
        return False
    try:
        conn.execute("SELECT count(*) FROM materials_fts LIMIT 1")
        return True
    except Exception:
        return False


def _fts_tokenize(text):
    """用 jieba 把中文拆成词（"高等数学第三章" → "高等数学 第三 章"），供 FTS 索引/查询"""
    import jieba
    words = [w.strip() for w in jieba.cut(text or "") if w.strip()]
    return " ".join(words)


def rebuild_fts():
    """重建全文索引（资料增删后调用；资料量小，全量重建简单可靠）"""
    conn = db.get_conn()
    try:
        if not _fts_available(conn):
            return
        with conn:
            conn.execute("DELETE FROM materials_fts")
            for m in list_materials():
                # rowid 必须显式等于资料 id！
                # （否则删除过资料后索引 rowid 会与真实 id 错位，搜索结果对不上）
                conn.execute(
                    "INSERT INTO materials_fts (rowid, title, filename, tags, notes, content) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        m["id"],
                        _fts_tokenize(m["title"]),
                        _fts_tokenize(m["file_name"]),
                        _fts_tokenize("、".join(m["tags"])),
                        _fts_tokenize(m["notes"]),
                        _fts_tokenize(m["course_name"]),
                    ),
                )
    finally:
        conn.close()


def fts_search(keyword):
    """
    用全文索引搜索资料，返回命中的 material_id 列表。
    FTS 不可用时返回 None（由调用方降级）。
    """
    conn = db.get_conn()
    try:
        if not _fts_available(conn):
            return None
        # 搜索词同样分词，每个词作为一个短语，用 OR 组合
        terms = [f'"{w}"' for w in _fts_tokenize(keyword).split() if w]
        if not terms:
            return None
        query = " OR ".join(terms)
        rows = conn.execute(
            "SELECT rowid FROM materials_fts WHERE materials_fts MATCH ?", (query,)
        ).fetchall()
        return [r["rowid"] for r in rows]
    except Exception:
        return None
    finally:
        conn.close()


# ==================== 标签 ====================

def list_tags():
    """列出全部标签（按名称排序）"""
    conn = db.get_conn()
    try:
        return conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
    finally:
        conn.close()


def set_material_tags(material_id, tag_names):
    """
    把一份资料的标签设置成 tag_names 列表。
    做法：先清掉旧的配对，再把新标签（找不到就自动创建）逐个配上。
    """
    conn = db.get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM material_tags WHERE material_id = ?", (material_id,))
            for name in tag_names:
                name = name.strip()
                if not name:
                    continue
                row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
                if row:
                    tag_id = row["id"]
                else:
                    cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
                    tag_id = cur.lastrowid
                conn.execute(
                    "INSERT OR IGNORE INTO material_tags (material_id, tag_id) VALUES (?, ?)",
                    (material_id, tag_id),
                )
    finally:
        conn.close()


# ==================== 复习清单 ====================

def _review_offsets(days_left, course_name):
    """
    按学习画像决定复习节奏：返回"截止日前第几天复习"的列表。
    未完成画像 → 默认规则（考前 14/7/3/1 天；7 天内每天一次）。
    已画像 → 按提前天数、节奏定制；薄弱科目多安排 2 次。
    """
    if days_left <= 0:
        return []

    # 未完成画像：默认固定规则
    if get_setting("profile_done") != "1":
        if days_left <= 7:
            return list(range(days_left, 0, -1))   # 7 天内每天一次
        return [o for o in (14, 7, 3, 1) if o <= days_left]

    # 定制规则
    lead = int(get_setting("profile_lead_days") or 14)   # 提前几天开始
    rhythm = get_setting("profile_rhythm") or "每天"
    n = 6 if rhythm == "每天" else 4                     # 复习总次数（每天 6 次 / 隔天 4 次）

    # 薄弱科目加权：多安排 2 次
    weak = [w.strip() for w in (get_setting("profile_weak") or "").replace("，", ",").split(",") if w.strip()]
    if course_name and any(w in course_name or course_name in w for w in weak):
        n += 2

    span = min(days_left, lead)   # 实际复习窗口
    if span <= 0:
        return []
    if span == 1:
        return [1]
    # 在 1..span 天内均匀分布 n 次复习（最后一天必复习）
    offsets = sorted({max(1, round((span - 1) * (1 - i / (n - 1))) + 1) for i in range(n)})
    return offsets


def generate_review_plan(ddl_id):
    """
    为一条 DDL 生成（或重新生成）复习清单。
    复习节奏按学习画像定制（提前天数/节奏/薄弱科目），未画像用默认规则。
    复习内容 = 复习《课程》+ 该课程的资料清单 + 目标 DDL 名称 + 建议时长。
    返回 (生成的条数, 复习计划列表)；找不到该 DDL 时返回 None。
    """
    conn = db.get_conn()
    try:
        ddl = conn.execute("SELECT * FROM ddl_tasks WHERE id = ?", (ddl_id,)).fetchone()
        if not ddl:
            return None

        # 先清掉旧计划（重新生成 = 推倒重来）
        conn.execute("DELETE FROM review_plans WHERE ddl_id = ?", (ddl_id,))

        due = reminder.parse_dt(ddl["due_at"])
        days_left = (due.date() - datetime.date.today()).days

        # 课程名（薄弱科目判断 + 内容展示用）
        course_row = conn.execute(
            "SELECT name FROM courses WHERE id = ?", (ddl["course_id"],)
        ).fetchone()
        course_name = course_row["name"] if course_row else ""

        # 决定复习日：截止日前第几天复习（按画像定制）
        offsets = _review_offsets(days_left, course_name)

        # 拼复习内容
        parts = []
        if course_name:
            parts.append(f"复习《{course_name}》")
            materials = conn.execute(
                "SELECT title FROM materials WHERE course_id = ? ORDER BY created_at",
                (ddl["course_id"],),
            ).fetchall()
            if materials:
                parts.append("资料：" + "、".join(m["title"] for m in materials))
        parts.append(f"目标：{ddl['title']}")
        content = "；".join(parts)

        # 画像填了每天可投入时间 → 内容附上建议时长
        if get_setting("profile_done") == "1":
            hours = get_setting("profile_hours") or ""
            if hours:
                content += f"（建议投入 {hours} 小时）"

        # 逐条插入
        for offset in offsets:
            plan_date = (due - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO review_plans (ddl_id, plan_date, content) VALUES (?, ?, ?)",
                (ddl_id, plan_date, content),
            )
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM review_plans WHERE ddl_id = ? ORDER BY plan_date", (ddl_id,)
        ).fetchall()
        return (len(rows), rows)
    finally:
        conn.close()


def list_review_plans():
    """列出全部复习计划项（按所属 DDL 截止时间、复习日期排序），带 DDL 信息"""
    conn = db.get_conn()
    try:
        return conn.execute("""
            SELECT r.*, d.title AS ddl_title, d.due_at AS ddl_due, c.name AS course_name
            FROM review_plans r
            JOIN ddl_tasks d ON r.ddl_id = d.id
            LEFT JOIN courses c ON d.course_id = c.id
            ORDER BY d.due_at, r.plan_date
        """).fetchall()
    finally:
        conn.close()


def toggle_review_plan(plan_id):
    """把一条复习计划在 完成/未完成 之间切换"""
    db.execute("UPDATE review_plans SET done = 1 - done WHERE id = ?", (plan_id,))


def clear_review_plans(ddl_id):
    """清空某条 DDL 的全部复习计划"""
    db.execute("DELETE FROM review_plans WHERE ddl_id = ?", (ddl_id,))


# ==================== 设置（键值对） ====================

def get_setting(key, default=""):
    """读取一条设置，不存在返回 default"""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    """写入一条设置（已有则更新）"""
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ==================== 课程安排（教务课表，队友新增） ====================

def clear_course_schedule():
    """清空全部课程安排（同步前先清，避免重复）"""
    db.execute("DELETE FROM course_schedule")


def add_course_schedule(course_name, teacher, day, slot, weeks, location, term="", sections=""):
    """新增一条课程安排"""
    course_id = find_or_create_course(course_name)
    return db.execute(
        "INSERT INTO course_schedule (course_id, course_name, teacher, day, slot, weeks, location, term, sections) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (course_id, course_name, teacher, day, slot, weeks, location, term, sections),
    )


def list_course_schedule():
    """列出全部课程安排（按课程名排序）"""
    conn = db.get_conn()
    try:
        return conn.execute(
            "SELECT * FROM course_schedule ORDER BY course_name"
        ).fetchall()
    finally:
        conn.close()


def count_course_schedule():
    """课程安排条数"""
    conn = db.get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM course_schedule").fetchone()[0]
    finally:
        conn.close()


# ==================== 通知（智能体主动提醒） ====================

def add_notification(kind, content):
    """生成一条通知"""
    db.execute("INSERT INTO notifications (kind, content) VALUES (?, ?)", (kind, content))


def list_notifications():
    """列出全部通知（最新在前）"""
    conn = db.get_conn()
    try:
        return conn.execute("SELECT * FROM notifications ORDER BY id DESC").fetchall()
    finally:
        conn.close()


def mark_notifications_read():
    """把所有通知标记为已读"""
    db.execute("UPDATE notifications SET read = 1 WHERE read = 0")


def unread_notifications_count():
    """未读通知数量（顶部横幅用）"""
    conn = db.get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM notifications WHERE read = 0").fetchone()[0]
    finally:
        conn.close()


# ==================== 爬虫日志 ====================

def add_crawl_log(source, status, message):
    """写一条爬虫日志"""
    db.execute(
        "INSERT INTO crawl_logs (source, status, message) VALUES (?, ?, ?)",
        (source, status, message),
    )


def list_crawl_logs(limit=20):
    """最近的爬虫日志（最新在前）"""
    conn = db.get_conn()
    try:
        return conn.execute(
            "SELECT * FROM crawl_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
