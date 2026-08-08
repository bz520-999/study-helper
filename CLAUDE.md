# 学习助手 Pro — 项目说明（给 Claude 看）

## 项目是什么
学生个人学习管理工具（本地 Web 应用）：课程资料归档、DDL 提醒、资料检索、复习清单生成、导出。
课程设计/竞赛项目。评审关注：实际使用价值、长期可用性、数据存储安全、功能稳定性、学生使用成本（免费）。

## 技术栈
- Python 3.12（本机 `python` 命令即 3.12；注意 `py -3` 指向的是 3.14 测试版，**不要用**）
- Flask + Jinja2 模板 + 原生 HTML/CSS/JS（无 Node.js 构建工具）
- SQLite 单文件数据库（data/study.db），WAL 模式
- 提醒不依赖后台任务：reminder.py 在打开页面时实时计算
- **智能体**：OpenAI 兼容 Function Calling 协议；默认智谱 GLM-4.7-Flash（免费）；备选 DeepSeek；`config.py` 里 `AGENT_MOCK=True` 可离线开发测试；API Key 存 settings 表（明文，阶段 7 加密）
- **后台任务**：APScheduler（仅用于智能体主动提醒，后续爬虫/备份也可用）

## 智能体架构（阶段 5）
```
用户 → /api/agent/chat → agent.py 对话循环 → 大模型(智谱/DeepSeek/Mock)
                                   ↓ 工具调用
                              tools.py → models.py（全部现有数据功能）
```
- 工具清单集中在 tools.py（约 10 个：查 DDL/资料/复习、增删改 DDL、生成复习计划）
- 系统提示词在 agent.py 顶部：先查库再回答、不编造数据、删除先确认、中文简洁
- 主动提醒：APScheduler 每天早上 config.AGENT_CHECK_HOUR 点检查当天 DDL → notifications 表 → 全站横幅

## 目录约定
```
study-helper/
├── app.py        # 入口：路由注册、启动建表
├── config.py     # 所有可配置项（端口、提醒规则等）
├── db.py         # 连接、建表、统一写操作（事务保护）
├── models.py     # 所有 SQL 增删改查集中在这里
├── reminder.py   # 剩余时间计算、过期/紧急分类
├── templates/    # base / index / ddl 等页面模板
├── static/       # style.css 等静态文件
├── data/         # 运行时自动创建：study.db
├── requirements.txt
├── run.bat       # 一键启动（自动建 venv、装依赖）
├── install_app.py   # 安装器（GUI：选目录+复制+桌面快捷方式；--silent --dir 静默模式）
└── build_exe.bat    # 一键打包：dist/StudyHelper/（主程序 onedir）+ dist/StudyHelper-Setup.exe（安装器）
```

## 关键约定
- 时间统一格式 `"YYYY-MM-DD HH:MM"`（本地时间，不做时区）
- 所有 SQL 集中在 models.py；路由（app.py）不直接写 SQL
- 新增依赖必须写进 requirements.txt
- 代码注释用中文、通俗，服务零基础用户
- **run.bat / build_exe.bat / 停止学习助手.bat 必须保持纯 ASCII（不能含中文）**：中文 Windows 的 cmd 用 GBK 解析 .bat 文件，UTF-8 中文会碎裂成乱码命令导致启动失败（2026-08-06 踩坑）
- 运行方式：双击 run.bat，浏览器打开 http://127.0.0.1:5000
- **exe 打包（2026-08-06）**：config.py 里 `BASE_DIR`/`DATA_DIR` 已按 frozen 模式切换（exe 版数据存 exe 旁边 data/）；app.py 有 `resource_path()`（模板/静态文件读打包内部）、frozen 时 stdout 重定向到 data/run.log、启动失败弹 MessageBox；**必须用 venv 的 python 打包**（`venv/Scripts/python.exe -m PyInstaller ...`，系统 python 没装依赖）；安装器用 `--add-data "dist/StudyHelper;app"` 内含主程序，复制时跳过 data/ 保护用户数据；安装器 docstring 里**不能出现反斜杠路径**（\U 会被 Python 当 unicode 转义）

## 进度
- [x] 阶段 1：DDL 手动录入 + 查看 + 应用内提醒（完成于 2026-08-06）
- [x] 阶段 2：资料归档 + 标签 + 检索（完成于 2026-08-06）
- [x] 阶段 3：复习清单生成 + iCal/CSV/Markdown 导出（完成于 2026-08-06，用户已验证 iCal 导入）
- [x] 阶段 4：自动提取（文件名识别 + 文本提取 DDL）（完成于 2026-08-06，自动化测试通过；待用户验证）
- [x] 阶段 5：智能体对话层（问答 → 自然语言操作 → 主动提醒）（完成于 2026-08-06，用户已用 DeepSeek 验证；含相对时间解析增强：ddl_parser.parse_relative 支持"下周三下午两点"等）
- [x] 阶段 6：爬虫（学习通，可降级）（开发完成 2026-08-06，2026-08-07 升级为扫码全自动；教务系统模板已废弃删除——用户明确不需要）
- [x] **学习通全自动同步（2026-08-07）**：废弃密码登录，改为**手机扫码登录**（Playwright 打开 https://i.mooc.chaoxing.com/space/index 截取 #quickCode 二维码 → 设置页显示 → 轮询页面出现"退出"= 登录成功 → storage_state 存 data/cookies/chaoxing.json 约 7 天）；抓取：恢复登录态 → FY_COURSE_URL 课程列表（'[class*=couritem]' + 'a[href*="entercoursenewfy"]'）→ 逐门课点 'li:has-text("作业"/"考试")' → 找 iframe（url 含 work/list/exam/task）→ 正则解析标题/状态/剩余时间 → 预览勾选导入（去重：models.ddl_exists）。状态机：crawler/chaoxing.py 模块级 _login/_sync + threading.Lock，前端每 3 秒轮询 /api/crawler/chaoxing/status。路由：/api/crawler/chaoxing/{qr,sync,import,logout,status}（旧密码版 /api/crawler/save 与 /api/crawler/sync 已删除）。半自动粘贴 /api/crawler/paste 保留为兜底。依赖：playwright==1.62.0（已加进 requirements.txt）；**浏览器内核三层兜底**（crawler/chaoxing.py `_launch()`）：exe 内置 ms-playwright（可选）→ 本机 playwright 下载的 chromium → 系统 Microsoft Edge（Windows 11 必有，无需任何下载）——因此源码版和打包版都不需要专门下载浏览器。
- [x] 阶段 7：安全加固 + 备份 + 长期可用性（完成于 2026-08-06：API Key 加密含旧明文迁移、backup.py 自动备份保留 10 份、FTS5+jieba 全文搜索自动降级、强杀进程数据完好已验证、README 演示脚本）
- [x] 额外功能：学习画像（初次引导问卷）+ 定制复习方案（2026-08-06）；课程规则库 100+ 条
- [x] **exe 打包发布（2026-08-06）**：PyInstaller 打包主程序 StudyHelper.exe（无窗口）+ 安装器 StudyHelper-Setup.exe（GUI 选目录、自动桌面快捷方式、数据保留、运行中重装提示）；全流程已自动化测试通过

## 全部阶段完成（2026-08-06）
项目已完整交付。答辩前建议：按 README.md 的「演示脚本」完整预演一遍；可让 Claude 模拟评委提问。
