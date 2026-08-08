# -*- coding: utf-8 -*-
"""
数据库模块：负责连接 SQLite 数据库、创建数据表、提供统一的写操作。
SQLite 是一种"文件型"数据库——整个库就是 data/ 下的一个文件，方便、稳定、零配置。
"""

import os
import sqlite3

import config

# 数据库文件的完整路径（比如 d:\vscode\study-helper\data\study.db）
DB_PATH = os.path.join(config.DATA_DIR, config.DB_FILE)


def get_conn():
    """打开一个数据库连接（每次用都开新的，用完要关掉）"""
    os.makedirs(config.DATA_DIR, exist_ok=True)  # 第一次运行时创建 data 文件夹
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 查询结果可以用 行['字段名'] 的方式读取
    conn.execute("PRAGMA journal_mode=WAL")    # WAL 模式：写入更快更稳，断电不易损坏
    conn.execute("PRAGMA busy_timeout=5000")   # 两个操作撞车时最多等 5 秒
    return conn


def init_db():
    """首次启动时创建数据表（表已存在则跳过，不会覆盖已有数据）"""
    conn = get_conn()
    conn.executescript("""
    -- 课程表
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        teacher TEXT,
        semester TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    -- DDL 任务表（本阶段的核心）
    CREATE TABLE IF NOT EXISTS ddl_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,                  -- 任务名称，如"高数期中考试"
        course_id INTEGER,                    -- 关联的课程 id（可空）
        due_at TEXT NOT NULL,                 -- 截止时间，格式 "YYYY-MM-DD HH:MM"
        remind_1d INTEGER NOT NULL DEFAULT 1, -- 是否提前 1 天提醒（1=是 0=否）
        remind_3h INTEGER NOT NULL DEFAULT 1, -- 是否提前 3 小时提醒
        status TEXT NOT NULL DEFAULT 'pending',  -- pending=未完成 done=已完成
        source TEXT NOT NULL DEFAULT 'manual',   -- 来源：manual=手动录入
        note TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    -- 资料表（课件、PDF 等都存这里）
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,                    -- 外键：指向 courses.id（可空）
        title TEXT NOT NULL,                  -- 标题（显示用）
        file_name TEXT,                       -- 原始文件名（保留中文原名用于展示）
        stored_name TEXT NOT NULL,            -- 磁盘上的存储名（随机编号，防中文乱码）
        ext TEXT,                             -- 扩展名，如 pdf / pptx
        notes TEXT,                           -- 备注
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    -- 标签表
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    -- 资料-标签关联表（多对多：一份资料多个标签，一个标签多份资料）
    CREATE TABLE IF NOT EXISTS material_tags (
        material_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (material_id, tag_id)
    );

    -- 复习清单表（由 DDL 倒推生成）
    CREATE TABLE IF NOT EXISTS review_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ddl_id INTEGER NOT NULL,              -- 属于哪条 DDL
        plan_date TEXT NOT NULL,              -- 复习日期 YYYY-MM-DD
        content TEXT NOT NULL,                -- 复习内容（含课程和资料清单）
        done INTEGER NOT NULL DEFAULT 0,      -- 0=未完成 1=已完成
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    -- 通知表（智能体主动提醒生成的通知）
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL DEFAULT 'daily',   -- daily=每日 DDL 汇总
        content TEXT NOT NULL,
        read INTEGER NOT NULL DEFAULT 0,      -- 0=未读 1=已读
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    -- 资料全文搜索表（FTS5 虚拟表，阶段 7；用 jieba 分词后的文本）
    -- 注意：FTS5 不可用（个别精简版 SQLite）时会被跳过，搜索自动降级
    CREATE VIRTUAL TABLE IF NOT EXISTS materials_fts USING fts5(
        title, filename, tags, notes, content, tokenize = 'unicode61'
    );

    -- 爬虫日志表（记录每次同步的结果：成功/失败/原因）
    CREATE TABLE IF NOT EXISTS crawl_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,             -- chaoxing / jwxt / crawler / paste
        status TEXT NOT NULL,             -- success / failed / skipped
        message TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    -- 设置表（以后存爬虫账号等键值对，先建好）
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    -- 课程安排表（教务课表同步进来，2026-08-07 队友新增）
    CREATE TABLE IF NOT EXISTS course_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,                 -- 关联的课程 id
        course_name TEXT NOT NULL,         -- 课程名（冗余存一份，避免关联不到）
        teacher TEXT,                      -- 老师
        day TEXT,                          -- 星期（星期一~星期日）
        slot TEXT,                         -- 大节（第一大节~第五大节/网课）
        weeks TEXT,                        -- 周次（如 "4-5,7-18(周)"）
        sections TEXT,                     -- 精确小节（如 "04-05"）
        location TEXT,                     -- 教室
        term TEXT,                         -- 学期（如 2026-2027-1）
        source TEXT NOT NULL DEFAULT 'crawler',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_schedule_course ON course_schedule(course_id);
    """)
    # ---- 表结构迁移（老版本表的字段升级，2026-08-07 队友新增）----
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(course_schedule)")}
        if "time_info" in cols and "day" not in cols:
            # 老结构(teacher/time_info/location) → 新结构(day/slot/weeks)
            conn.execute("ALTER TABLE course_schedule ADD COLUMN day TEXT")
            conn.execute("ALTER TABLE course_schedule ADD COLUMN slot TEXT")
            conn.execute("ALTER TABLE course_schedule ADD COLUMN weeks TEXT")
            conn.execute("UPDATE course_schedule SET day='', slot='', weeks=''")
        if "sections" not in cols:
            conn.execute("ALTER TABLE course_schedule ADD COLUMN sections TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()


def execute(sql, params=()):
    """
    统一的"写"操作（新增/修改/删除）。
    用事务保护：要么全部成功，要么全部回滚——断电也不会写坏数据库。
    返回新插入行的 id。
    """
    conn = get_conn()
    try:
        with conn:  # with 会自动开启事务并提交；出错则自动回滚
            cur = conn.execute(sql, params)
            return cur.lastrowid
    finally:
        conn.close()
