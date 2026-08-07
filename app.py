# -*- coding: utf-8 -*-
"""
学习助手 Pro —— 入口文件
这个文件负责三件事：
  1. 创建 Flask 应用
  2. 注册所有"页面路由"（网址尾巴对应的功能）
  3. 启动本地服务器
"""

import json
import os
import sys
import threading
import uuid
import webbrowser
from urllib.parse import quote

# 让控制台输出的中文不乱码（Windows 专属处理）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 打包成 exe 后（无窗口模式），控制台不存在——把输出重定向到 data/run.log，
# 这样出问题时能查看日志文件排查。源码运行时不动。
if getattr(sys, "frozen", False) and sys.stdout is None:
    import io
    _log_dir = os.path.join(os.path.dirname(sys.executable), "data")
    try:
        os.makedirs(_log_dir, exist_ok=True)
        _log = open(os.path.join(_log_dir, "run.log"), "a", encoding="utf-8")
        sys.stdout = sys.stderr = _log
    except OSError:
        sys.stdout = sys.stderr = io.StringIO()


def resource_path(rel):
    """打包成 exe 后，模板/静态文件在 exe 内部（_MEIPASS）；源码时在项目目录。"""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

from flask import (
    Flask, flash, make_response, redirect, render_template, request,
    send_from_directory, url_for,
)

import agent
import autotag
import backup
import config
import crawler
import db
import ddl_parser
import exporter
import models
import reminder
import scheduler
import search
import security

app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
# 用于显示"已保存！"这类提示消息（本地应用，固定密钥即可）
app.secret_key = "study-helper-local-secret-key"
# 上传大小上限（超出会触发 413 错误，下面有专门的处理）
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024


@app.route("/")
def index():
    """首页：快到期的 DDL 醒目展示在最上面"""
    tasks = models.list_ddl_tasks(status="pending")
    items = reminder.annotate(tasks)
    items.sort(key=lambda x: (x["overdue"], x["task"]["due_at"]))  # 过期的最先显示
    overdue = [i for i in items if i["overdue"]]
    urgent = [i for i in items if (not i["overdue"]) and i["urgent"]]
    upcoming = [i for i in items if (not i["overdue"]) and (not i["urgent"])]
    schedule_rows = models.list_course_schedule()
    schedule_json = json.dumps([
        {
            "name": s["course_name"],
            "teacher": s["teacher"] or "",
            "day": s["day"] or "",
            "slot": s["slot"] or "",
            "weeks": s["weeks"] or "",
            "sections": s["sections"] or "",
            "location": s["location"] or "",
        }
        for s in schedule_rows
    ], ensure_ascii=False)

    # 考试数据（pending DDL 里含"考试"的），叠加到课表
    exam_json = json.dumps([
        {
            "title": t["title"],
            "due_at": t["due_at"],
            "course": t["course_name"] or "",
            "location": t["note"] or "",
        }
        for t in tasks
        if "考试" in (t["title"] or "")
    ], ensure_ascii=False)

    return render_template(
        "index.html",
        overdue=overdue,
        urgent=urgent,
        upcoming=upcoming,
        pending_count=len(items),
        schedule=schedule_rows,
        schedule_count=models.count_course_schedule(),
        schedule_json=schedule_json,
        exam_json=exam_json,
        semester_start=models.get_setting("semester_start") or "2026-09-07",
    )


@app.route("/ddl")
def ddl_list():
    """DDL 清单页：查看所有任务 + 新增表单"""
    items = reminder.annotate(models.list_ddl_tasks())
    return render_template("ddl.html", items=items)


@app.route("/ddl/add", methods=["POST"])
def ddl_add():
    """接收新增表单（POST 方式），存入数据库"""
    title = request.form.get("title", "").strip()
    due_at = request.form.get("due_at", "").strip()
    course_name = request.form.get("course_name", "").strip()
    note = request.form.get("note", "").strip()
    remind_1d = 1 if request.form.get("remind_1d") else 0
    remind_3h = 1 if request.form.get("remind_3h") else 0

    if not title or not due_at:
        flash("请填写任务名称和截止时间", "error")
        return redirect(url_for("ddl_list"))

    # 浏览器给的是 "2026-08-20T23:00"，数据库要的是 "2026-08-20 23:00"（把 T 换成空格）
    due_at = due_at.replace("T", " ")
    course_id = models.find_or_create_course(course_name)
    models.add_ddl(title, course_id, due_at, note, remind_1d, remind_3h)
    flash("已保存！", "ok")
    return redirect(url_for("ddl_list"))


@app.route("/ddl/<int:task_id>/done")
def ddl_done(task_id):
    """把一条 DDL 标记为已完成"""
    models.complete_ddl(task_id)
    flash("已标记完成，干得漂亮！", "ok")
    return redirect(url_for("ddl_list"))


@app.route("/ddl/<int:task_id>/delete")
def ddl_delete(task_id):
    """删除一条 DDL"""
    models.delete_ddl(task_id)
    flash("已删除", "ok")
    return redirect(url_for("ddl_list"))


@app.route("/api/autotag")
def api_autotag():
    """前端选文件后调用：根据文件名猜课程和标签（返回 JSON）"""
    filename = request.args.get("filename", "")
    return {"course": autotag.suggest_course(filename), "tags": autotag.suggest_tags(filename)}


@app.route("/api/parse_ddl", methods=["POST"])
def api_parse_ddl():
    """前端"粘贴提取"按钮调用：从文字里提取 DDL（返回 JSON）"""
    text = request.form.get("text", "")
    items = ddl_parser.parse_ddl_text(text)
    # 顺便自动识别课程：标题里含"高数"就补上"高等数学"（预览时用户可改）
    for it in items:
        it["course"] = autotag.suggest_course(it["title"])
    return {"items": items}


@app.route("/materials")
def materials_list():
    """资料库页：上传表单 + 全部资料列表"""
    return render_template(
        "materials.html",
        materials=models.list_materials(),
        courses=models.list_courses(),
        tags=models.list_tags(),
    )


@app.route("/materials/upload", methods=["POST"])
def material_upload():
    """接收上传的文件：保存到磁盘 + 记录档案 + 打标签"""
    file = request.files.get("file")
    title = request.form.get("title", "").strip()
    course_name = request.form.get("course_name", "").strip()
    notes = request.form.get("notes", "").strip()
    selected_tags = request.form.getlist("tags")          # 勾选的已有标签
    new_tags = request.form.get("new_tags", "").strip()   # 手动输入的新标签

    # 检查：有没有选文件
    if not file or not file.filename:
        flash("请选择要上传的文件", "error")
        return redirect(url_for("materials_list"))

    # 检查：文件类型是否允许
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in config.ALLOWED_EXTENSIONS:
        flash(f"不支持的文件类型 .{ext}（支持：{', '.join(sorted(config.ALLOWED_EXTENSIONS))}）", "error")
        return redirect(url_for("materials_list"))

    # 没填标题就用文件名当标题
    if not title:
        title = file.filename

    # 自动识别兜底：用户没填课程/标签时，从文件名猜（前端也会提前填好，这里双保险）
    if not course_name:
        course_name = autotag.suggest_course(file.filename)
    tag_names = list(selected_tags)
    for t in new_tags.replace("，", ",").split(","):  # 兼容中文逗号
        t = t.strip()
        if t:
            tag_names.append(t)
    if not tag_names:
        tag_names = autotag.suggest_tags(file.filename)

    # 保存文件本体：磁盘上用随机编号命名（防中文乱码），原名单独存数据库
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    stored_name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(config.UPLOAD_DIR, stored_name))

    # 记录档案 + 打标签
    course_id = models.find_or_create_course(course_name)
    material_id = models.add_material(course_id, title, file.filename, stored_name, ext, notes)
    if tag_names:
        models.set_material_tags(material_id, tag_names)
    models.rebuild_fts()  # 重建全文索引（新资料立即可搜）

    flash("资料已入库！", "ok")
    return redirect(url_for("materials_list"))


@app.route("/materials/<int:material_id>/download")
def material_download(material_id):
    """下载原始文件（文件名恢复成上传时的中文名）"""
    m = models.get_material(material_id)
    if not m:
        flash("资料不存在", "error")
        return redirect(url_for("materials_list"))
    return send_from_directory(
        config.UPLOAD_DIR,
        m["stored_name"],
        as_attachment=True,
        download_name=m["file_name"],
    )


@app.route("/materials/<int:material_id>/delete")
def material_delete(material_id):
    """删除资料：先删磁盘文件，再删数据库档案"""
    m = models.get_material(material_id)
    if not m:
        flash("资料不存在", "error")
        return redirect(url_for("materials_list"))
    file_path = os.path.join(config.UPLOAD_DIR, m["stored_name"])
    if os.path.exists(file_path):
        os.remove(file_path)
    models.delete_material(material_id)
    flash("资料已删除", "ok")
    return redirect(url_for("materials_list"))


@app.route("/search")
def search_page():
    """搜索页：关键词 + 课程 + 标签，任意组合筛选"""
    keyword = request.args.get("q", "").strip()
    course_id = request.args.get("course_id", "").strip()
    tag_name = request.args.get("tag", "").strip()
    course_id = int(course_id) if course_id.isdigit() else None

    results = search.search_materials(keyword=keyword, course_id=course_id, tag_name=tag_name)
    return render_template(
        "search.html",
        results=results,
        keyword=keyword,
        selected_course_id=course_id,
        selected_tag=tag_name,
        courses=models.list_courses(),
        tags=models.list_tags(),
    )


@app.route("/review")
def review_page():
    """复习清单页：为 DDL 生成计划 + 查看/勾选计划"""
    profile_done = models.get_setting("profile_done") == "1"
    plans = models.list_review_plans()

    # 把零散的计划按所属 DDL 分组（注意：键名不能叫 items，会和字典自带方法撞名）
    grouped = []
    for p in plans:
        if not grouped or grouped[-1]["ddl_id"] != p["ddl_id"]:
            grouped.append({
                "ddl_id": p["ddl_id"],
                "ddl_title": p["ddl_title"],
                "course_name": p["course_name"],
                "ddl_due": p["ddl_due"],
                "plans": [],
            })
        grouped[-1]["plans"].append(p)
    counts = {g["ddl_id"]: len(g["plans"]) for g in grouped}

    pending = reminder.annotate(models.list_ddl_tasks(status="pending"))
    return render_template(
        "review.html",
        pending=pending,
        grouped=grouped,
        counts=counts,
        profile_done=profile_done,
        profile_lead=models.get_setting("profile_lead_days") or 14,
        profile_rhythm=models.get_setting("profile_rhythm") or "每天",
        profile_weak=models.get_setting("profile_weak"),
    )


@app.route("/review/generate/<int:ddl_id>")
def review_generate(ddl_id):
    """为一条 DDL 生成（或重新生成）复习清单"""
    info = models.generate_review_plan(ddl_id)
    if info is None:
        flash("没找到这条 DDL", "error")
    elif info[0] > 0:
        flash(f"已生成 {info[0]} 条复习计划！", "ok")
    else:
        flash("这条 DDL 已过期或今天截止，没有可安排的复习日了", "error")
    return redirect(url_for("review_page"))


@app.route("/review/<int:plan_id>/toggle")
def review_toggle(plan_id):
    """把一条复习计划在 完成/未完成 之间切换"""
    models.toggle_review_plan(plan_id)
    return redirect(url_for("review_page"))


@app.route("/review/<int:ddl_id>/clear")
def review_clear(ddl_id):
    """清空某条 DDL 的复习计划"""
    models.clear_review_plans(ddl_id)
    flash("已清空该任务的复习计划", "ok")
    return redirect(url_for("review_page"))


@app.route("/export")
def export_page():
    """导出页：选择 数据类型 × 格式"""
    return render_template("export.html")


@app.route("/export/download")
def export_download():
    """生成文件并让浏览器下载"""
    data_type = request.args.get("data_type", "ddl")
    fmt = request.args.get("fmt", "ical")

    # 收集数据
    ddls = models.list_ddl_tasks()
    pending_ddls = models.list_ddl_tasks(status="pending")   # iCal 只导进行中的（已完成的不该再响闹钟）
    plans = models.list_review_plans()
    materials = models.list_materials()

    # 学习画像说明（导出复习清单时附上，体现"定制"）
    profile_note = ""
    if models.get_setting("profile_done") == "1":
        profile_note = ("依据学习画像定制：提前 " +
                        (models.get_setting("profile_lead_days") or "14") + " 天、" +
                        (models.get_setting("profile_rhythm") or "每天") + "复习")

    # 根据选择生成内容（data_type × fmt 共 9 种组合）
    if data_type == "ddl":
        if fmt == "ical":
            payload, filename, mime = exporter.to_ical(pending_ddls, plans), "学习助手-DDL日历.ics", "text/calendar; charset=utf-8"
        elif fmt == "csv":
            payload, filename, mime = exporter.to_csv_ddl(ddls), "学习助手-DDL清单.csv", "text/csv; charset=utf-8"
        else:
            payload, filename, mime = exporter.to_markdown_ddl(ddls), "学习助手-DDL清单.md", "text/markdown; charset=utf-8"
    elif data_type == "review":
        if fmt == "ical":
            payload, filename, mime = exporter.to_ical([], plans), "学习助手-复习清单.ics", "text/calendar; charset=utf-8"
        elif fmt == "csv":
            payload, filename, mime = exporter.to_csv_plans(plans), "学习助手-复习清单.csv", "text/csv; charset=utf-8"
        else:
            payload, filename, mime = exporter.to_markdown_plans(plans, profile_note), "学习助手-复习清单.md", "text/markdown; charset=utf-8"
    else:  # materials：资料目录只有 CSV 和 Markdown（日历里放不了文件清单）
        if fmt == "ical":
            flash("资料目录不支持导出 iCal，请选择 CSV 或 Markdown", "error")
            return redirect(url_for("export_page"))
        elif fmt == "csv":
            payload, filename, mime = exporter.to_csv_materials(materials), "学习助手-资料目录.csv", "text/csv; charset=utf-8"
        else:
            payload, filename, mime = exporter.to_markdown_materials(materials), "学习助手-资料目录.md", "text/markdown; charset=utf-8"

    resp = make_response(payload)
    resp.mimetype = mime
    # filename*=UTF-8''... 是 RFC 5987 标准写法，浏览器能正确显示中文文件名
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return resp


@app.route("/agent")
def agent_page():
    """智能体对话页"""
    key_set = bool(models.get_setting("agent_api_key"))
    return render_template("agent.html", agent_ready=key_set, mock_mode=config.AGENT_MOCK)


@app.route("/api/agent/chat", methods=["POST"])
def agent_chat():
    """接收用户消息 → 智能体处理 → 返回回答"""
    message = (request.form.get("message") or "").strip()
    history = request.form.get("history") or "[]"
    if not message:
        return {"error": "消息不能为空"}

    try:
        history = json.loads(history)
    except json.JSONDecodeError:
        history = []
    messages = [m for m in history if m.get("role") in ("user", "assistant")][-10:]
    messages.append({"role": "user", "content": message})

    ok, result = agent.chat(messages)
    return {"reply": result} if ok else {"error": result}


@app.route("/settings")
def settings_page():
    """设置页：大模型 API 配置 + 爬虫配置"""
    return render_template(
        "settings.html",
        providers=config.AGENT_PROVIDERS,
        current_provider=models.get_setting("agent_provider") or "zhipu",
        current_model=models.get_setting("agent_model"),
        key_set=bool(models.get_setting("agent_api_key")),
        check_hour=models.get_setting("agent_check_hour") or str(config.AGENT_CHECK_HOUR),
        # 爬虫相关
        crawler_enabled=models.get_setting("crawl_enabled") == "1",
        crawl_provider=models.get_setting("crawl_provider") or "chaoxing",
        crawl_username=models.get_setting("crawl_username"),
        crawl_password_set=bool(models.get_setting("crawl_password")),
        crawl_logs=models.list_crawl_logs(),
        # 备份相关
        last_backup=backup.last_backup_time(),
        backup_count=len(backup._list_backups()),
        backup_keep=config.BACKUP_KEEP,
    )


@app.route("/api/backup", methods=["POST"])
def backup_now():
    """手动备份（设置页按钮触发）"""
    path = backup.backup_now()
    if path:
        return {"ok": True, "msg": "备份成功！文件已保存到 data/backups/"}
    return {"ok": False, "msg": "备份失败，请检查磁盘空间"}


@app.route("/api/crawler/save", methods=["POST"])
def crawler_save():
    """保存爬虫账号（密码加密存储）、来源和开关"""
    username = request.form.get("crawl_username", "").strip()
    password = request.form.get("crawl_password", "")
    enabled = request.form.get("crawl_enabled") in ("1", "on", "true", "True")
    provider = request.form.get("crawl_provider", "").strip()

    # 记录来源：学习通 / 教务系统（没传则沿用当前值）
    if provider:
        models.set_setting("crawl_provider", provider)
    if username:
        models.set_setting("crawl_username", username)
    if password:
        # 加密后再存：数据库里是密文，页面永远不显示明文
        models.set_setting("crawl_password", security.encrypt_text(password))
    models.set_setting("crawl_enabled", "1" if enabled else "0")
    return {"ok": True}


@app.route("/api/crawler/sync", methods=["POST"])
def crawler_sync():
    """立即执行一次同步（后台线程，结果写日志）"""
    if not crawler.is_enabled():
        models.add_crawl_log("sync", "skipped", "爬虫开关未开启，先在上方开启再同步。")
        return {"ok": True, "msg": "爬虫开关未开启，已跳过。"}
    msg = crawler.run_sync()
    return {"ok": True, "msg": msg}


@app.route("/api/crawler/captcha/status", methods=["GET"])
def crawler_captcha_status():
    """设置页轮询：有没有待输入的验证码、图片是什么（base64）"""
    return crawler.captcha.captcha_status()


@app.route("/api/crawler/captcha/submit", methods=["POST"])
def crawler_captcha_submit():
    """设置页提交用户肉眼输入的验证码"""
    answer = request.form.get("answer", "")
    return crawler.captcha.captcha_submit(answer)


@app.route("/api/crawler/logout", methods=["POST"])
def crawler_logout():
    """退出登录：清除教务/学习通账号密码、关闭开关、清空已同步的课表。"""
    models.set_setting("crawl_username", "")
    models.set_setting("crawl_password", "")
    models.set_setting("crawl_enabled", "0")
    models.clear_course_schedule()
    models.add_crawl_log("logout", "success", "已退出登录，账号信息已清除。")
    return {"ok": True, "msg": "已退出登录，账号和课表已清除。"}


@app.route("/api/crawler/paste", methods=["POST"])
def crawler_paste():
    """半自动模式：粘贴学习通作业列表文字 → 提取 DDL 预览"""
    text = request.form.get("text", "")
    items = ddl_parser.parse_ddl_text(text)
    for it in items:
        it["course"] = autotag.suggest_course(it["title"])
    models.add_crawl_log("paste", "success", f"文本同步：识别到 {len(items)} 条 DDL。")
    return {"items": items}


@app.route("/api/agent/settings", methods=["POST"])
def agent_settings_save():
    """保存大模型配置（Key 留空 = 保持不变）"""
    provider = request.form.get("provider", "").strip()
    model = request.form.get("model", "").strip()
    api_key = request.form.get("api_key", "").strip()
    check_hour = request.form.get("check_hour", "").strip()

    if provider in config.AGENT_PROVIDERS:
        models.set_setting("agent_provider", provider)
    if model:
        models.set_setting("agent_model", model)
    if api_key:
        # 加密后存储：数据库里是密文，页面永远不显示明文
        models.set_setting("agent_api_key", security.encrypt_text(api_key))
    if check_hour.isdigit() and 0 <= int(check_hour) <= 23:
        models.set_setting("agent_check_hour", str(int(check_hour)))
    return {"ok": True}


@app.route("/api/agent/test", methods=["POST"])
def agent_test():
    """测试大模型连接（发一条最小请求）"""
    ok, msg = agent.test_connection()
    return {"ok": ok, "msg": msg}


@app.route("/api/agent/key/delete", methods=["POST"])
def agent_key_delete():
    """删除已保存的 API Key（清空后智能体回到模拟模式）"""
    models.set_setting("agent_api_key", "")
    return {"ok": True}


@app.route("/notifications")
def notifications_page():
    """通知中心：智能体主动提醒的历史"""
    return render_template("notifications.html", notes=models.list_notifications())


@app.route("/api/notifications/read_all", methods=["POST"])
def notifications_read_all():
    """把通知全部标记为已读"""
    models.mark_notifications_read()
    return {"ok": True}


@app.context_processor
def inject_globals():
    """给所有页面注入：未读通知数、是否完成学习画像"""
    return {
        "unread_count": models.unread_notifications_count(),
        "profile_done": models.get_setting("profile_done") == "1",
    }


@app.route("/profile")
def profile_page():
    """学习画像页：首次进入引导 + 随时可修改"""
    profile = {
        "nickname": models.get_setting("profile_nickname"),
        "hours": models.get_setting("profile_hours") or "1",
        "lead_days": models.get_setting("profile_lead_days") or "14",
        "rhythm": models.get_setting("profile_rhythm") or "每天",
        "weak": models.get_setting("profile_weak"),
    }
    return render_template(
        "profile.html",
        profile=profile,
        profile_done=models.get_setting("profile_done") == "1",
        courses=models.list_courses(),
    )


@app.route("/api/profile/save", methods=["POST"])
def profile_save():
    """保存学习画像"""
    nickname = request.form.get("nickname", "").strip()
    hours = request.form.get("hours", "").strip()
    lead_days = request.form.get("lead_days", "").strip()
    rhythm = request.form.get("rhythm", "").strip()
    weak = request.form.get("weak", "").strip()

    if hours not in ("0.5", "1", "2", "3", "4"):
        hours = "1"
    if lead_days not in ("7", "14", "30", "60"):
        lead_days = "14"
    if rhythm not in ("每天", "隔天"):
        rhythm = "每天"

    models.set_setting("profile_nickname", nickname)
    models.set_setting("profile_hours", hours)
    models.set_setting("profile_lead_days", lead_days)
    models.set_setting("profile_rhythm", rhythm)
    models.set_setting("profile_weak", weak)
    models.set_setting("profile_done", "1")
    return {"ok": True, "msg": "画像已保存！复习清单将按你的习惯生成。"}


@app.route("/api/profile/clear", methods=["POST"])
def profile_clear():
    """清除画像（回到默认规则）"""
    for key in ("profile_nickname", "profile_hours", "profile_lead_days",
                "profile_rhythm", "profile_weak", "profile_done"):
        models.set_setting(key, "")
    return {"ok": True}


@app.errorhandler(413)
def file_too_large(e):
    """上传文件超过大小上限时的友好提示"""
    flash(f"文件太大了，不能超过 {config.MAX_UPLOAD_MB} MB", "error")
    return redirect(url_for("materials_list"))


def _msgbox(title, text):
    """弹一个 Windows 消息框（打包版没有黑窗口，出错用弹窗告诉用户）"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # 0x10 = 红色感叹号图标
    except Exception:
        pass


if __name__ == "__main__":
    db.init_db()  # 启动时建表（已存在则跳过）
    models.rebuild_fts()          # 启动时同步一次全文索引
    backup.maybe_auto_backup()    # 启动自动备份（超过 24 小时没备份才备份）
    scheduler.start_scheduler()   # 启动后台定时器（智能体主动提醒）
    scheduler.check_today_ddls()  # 启动时先主动检查一次当天 DDL
    url = f"http://127.0.0.1:{config.PORT}"
    print("=" * 50)
    print("  学习助手 Pro 已启动！")
    print(f"  请在浏览器打开：{url}")
    print("  关闭这个窗口 = 关闭应用")
    print("=" * 50)
    # 启动 1 秒后自动打开浏览器（设置 NO_BROWSER 环境变量可关闭，测试用）
    if config.AUTO_OPEN_BROWSER and not os.environ.get("NO_BROWSER"):
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    try:
        app.run(host="127.0.0.1", port=config.PORT, debug=False)
    except OSError as e:
        print(f"\n[错误] 启动失败：{e}")
        if getattr(sys, "frozen", False):
            _msgbox("学习助手 Pro 启动失败",
                    f"很可能是端口 {config.PORT} 被占用（应用可能已经开着了）。\n"
                    "解决办法：先关闭正在运行的学习助手，再重新双击启动。\n\n"
                    f"详细信息：{e}")
        else:
            print(f"很可能是端口 {config.PORT} 被占用（比如应用已经开着了）。")
            print("解决办法：改 config.py 里的 PORT，或先关掉正在运行的应用。")
            input("按回车键退出...")
