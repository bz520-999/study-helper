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
- **run.bat 启动时会先自动杀掉所有旧实例（2026-08-07 队友新增）**：保证每次启动跑的一定是最新代码、且只有一个实例，避免旧进程占着端口导致"改了代码不生效"。杀旧命令与「停止学习助手.bat」一致（匹配 StudyHelper*/python.exe *app.py*）
- **exe 打包（2026-08-06）**：config.py 里 `BASE_DIR`/`DATA_DIR` 已按 frozen 模式切换（exe 版数据存 exe 旁边 data/）；app.py 有 `resource_path()`（模板/静态文件读打包内部）、frozen 时 stdout 重定向到 data/run.log、启动失败弹 MessageBox；**必须用 venv 的 python 打包**（`venv/Scripts/python.exe -m PyInstaller ...`，系统 python 没装依赖）；安装器用 `--add-data "dist/StudyHelper;app"` 内含主程序，复制时跳过 data/ 保护用户数据；安装器 docstring 里**不能出现反斜杠路径**（\U 会被 Python 当 unicode 转义）

## 进度
- [x] 阶段 1：DDL 手动录入 + 查看 + 应用内提醒（完成于 2026-08-06）
- [x] 阶段 2：资料归档 + 标签 + 检索（完成于 2026-08-06）
- [x] 阶段 3：复习清单生成 + iCal/CSV/Markdown 导出（完成于 2026-08-06，用户已验证 iCal 导入）
- [x] 阶段 4：自动提取（文件名识别 + 文本提取 DDL）（完成于 2026-08-06，自动化测试通过；待用户验证）
- [x] 阶段 5：智能体对话层（问答 → 自然语言操作 → 主动提醒）（完成于 2026-08-06，用户已用 DeepSeek 验证；含相对时间解析增强：ddl_parser.parse_relative 支持"下周三下午两点"等）
- [x] 阶段 6：爬虫（学习通扫码全自动 + 教务系统，可降级）（开发完成 2026-08-06，2026-08-07 升级为扫码全自动）
- [x] **学习通全自动同步（2026-08-07）**：废弃密码登录，改为**手机扫码登录**（Playwright 打开 https://i.mooc.chaoxing.com/space/index 截取 #quickCode 二维码 → 设置页显示 → 轮询页面出现"退出"= 登录成功 → storage_state 存 data/cookies/chaoxing.json 约 7 天）；抓取：恢复登录态 → FY_COURSE_URL 课程列表（'[class*=couritem]' + 'a[href*="entercoursenewfy"]'）→ 逐门课点 'li:has-text("作业"/"考试")' → 找 iframe（url 含 work/list/exam/task）→ **等 JS 渲染后再取内容** → 正则解析标题/状态/剩余时间 → 预览勾选导入（去重：models.ddl_exists）。状态机：crawler/chaoxing.py 模块级 _login/_sync + threading.Lock，前端轮询 /api/crawler/chaoxing/status。路由：/api/crawler/chaoxing/{qr,sync,import,logout,status}。半自动粘贴兜底。依赖：playwright==1.62.0；**浏览器内核三层兜底**（crawler/chaoxing.py `_launch()`）：exe 内置 ms-playwright（可选）→ 本机 chromium → 系统 Microsoft Edge（Windows 11 必有，无需下载）。
- [x] **教务系统爬虫（队友开发，2026-08-07 合并）**：南京理工大学强智教务 + 金智 ehall2 统一认证，crawler/jwxt.py + crawler/captcha.py（队友版本，保留）；首页课表（教务处爬取）。
- [x] 阶段 7：安全加固 + 备份 + 长期可用性（完成于 2026-08-06：API Key 加密含旧明文迁移、backup.py 自动备份保留 10 份、FTS5+jieba 全文搜索自动降级、强杀进程数据完好已验证、README 演示脚本）
- [x] 额外功能：学习画像（初次引导问卷）+ 定制复习方案（2026-08-06）；课程规则库 100+ 条
- [x] **评审优化（2026-08-08）**：对照小米模型对第一版 Demo 的评审逐条核对后落地 4 项——① XSS 补漏：验证码提交结果 `data.msg` 包 esc()（main.js）；② 手动添加查重：/ddl/add 与智能体工具 `_add_ddl` 都复用 models.ddl_exists，重复时 flash-warn 提示不重复加（爬虫导入原本就有）；③ 首页 Toast + 浏览器通知：base.html 加 #toast-container，main.js 加 showToast(msg,type,actionLabel,actionFn)/enableNotifications（textContent 防 XSS），style.css 加 .toast 系列样式，index 路由算 today_count 传给首页，今天有截止任务时弹"今天有 N 项 DDL 截止"+未授权则带"开启浏览器通知"按钮；④ CSV/JSON 导入：exporter.py 加 to_json_ddl + parse_import_content（UTF-8/GBK 容错、带/不带表头、时间容错 2026-8-20→补零补 23:59、坏文件友好报错），export.html 加"导入 DDL"卡片 + 格式下拉加 JSON，app.py 加 /import/ddl（去重 + done 状态原样恢复），导出 JSON 与导入格式对称。全部端到端实测通过。
- [x] **提醒自定义（2026-08-08）**：remind_1d/remind_3h 固定双开关 → `remind_before_hours`（提前多少小时，0=不提醒）。db.py 建表改新列 + 启动迁移合成旧数据（双开→3h、仅 1d→24h、都关→0）；models.add_ddl/update_ddl 签名更新（int 校验收进 0~8760）；DDL 表单（新增+编辑弹窗）改为下拉档位（1h/3h/1 天/2 天/3 天/1 周/自定义输入小时数），后端读 `remind_before_hours=="custom"` 时取 `remind_custom_hours`；exporter.to_ical 按小时生成单个 VALARM（`_fmt_remind` 把 24→"1 天"、168→"1 周"；⚠️ sqlite3.Row 没有 .get()，只能用下标）；tools.py 智能体 add_ddl 工具参数改为 `remind_hours`（schema 同步，"提前2天提醒我"→48）。
- [x] **聊天记录持久化（2026-08-08）**：chat_messages 表（role/content/created_at）；models.add_chat_message/list_chat_messages（倒序取最新 limit 条再正序返回，注意子查询要带 id 列、LIMIT 占位符要传参）/clear_chat_messages；/api/agent/chat 改为后端入库并自动组装最近 40 条上下文（前端不再传 history，回答成功才入库）；新增 /api/agent/history（页面加载恢复显示）+ /api/agent/history/clear；agent.html 欢迎语加 id=chat-welcome、加"🗑 清空"按钮，main.js 加载历史（有历史时移除欢迎语）、清空后恢复欢迎语。
- [x] **课表 vs 课程标签区分（2026-08-08）**：用户发现智能体回答"我有哪些课"时冒出课表上没有的课（数据结构/大学物理）。根因：query_courses 查的是 courses 表（DDL/资料关联时自动建的课程标签，28 门含测试残留），不是 course_schedule（真课表 14 门），且智能体没有查课表工具。修复：tools.py 加 `query_schedule` 工具（_schedule_text 按星期分组输出 课程+节次+教室+周次）；query_courses 描述明确"不是课表"；agent.py SYSTEM_PROMPT 加规则 9（课表问题必须用 query_schedule，查不到如实说"课表里没有"，禁止用课程标签冒充课表或编造时间）。清理 courses 表无引用的测试残留（测试课程/期末测验）。
- [x] **exe 打包发布（2026-08-06）**：PyInstaller 打包主程序 StudyHelper.exe（无窗口）+ 安装器 StudyHelper-Setup.exe（GUI 选目录、自动桌面快捷方式、数据保留、运行中重装提示）；全流程已自动化测试通过
- [x] **界面现代化改版（2026-08-09）**：顶栏文字导航 → 左侧边栏布局（品牌区 + 分组菜单「学习管理/智能/账户」+ 当前页浅蓝底+左侧蓝色竖条高亮 + 智能体未读角标，窄窗口 <860px 自动折叠为顶部横条导航）；CSS 变量设计系统（:root 定义全部颜色，[data-theme="dark"] 覆盖为深色套，改一处全站生效）；深色模式（默认跟随系统 prefers-color-scheme，侧栏底部按钮手动切换，localStorage 记忆，head 内联脚本防闪屏）；首页统计卡组（进行中/今天截止/课表课程）；移动端适配。全程只动 base.html/style.css/main.js，页面模板零改动
- [x] **界面精修（2026-08-09，design-taste-frontend skill 驱动）**：设计判断 = 效率软件风（VARIANCE 4 / MOTION 3 / DENSITY 6）。具体：正文 14px（软件感而非网页感）；圆角系统锁定（surface 12px / control 8px / pill 全圆，文档化在 style.css 头注释）；菜单 emoji 全部换成 feather 线性图标（MIT，内联 SVG，stroke-width 1.75 统一，无 npm 依赖）；去掉网页感装饰（主按钮渐变→纯色、h1 色条、卡片 hover 位移）；按钮按下 scale(0.98) 物理反馈；数字 tabular-nums；@media (prefers-reduced-motion) 关动画；侧栏底部「本地运行 · 数据不出本机」小字；清理模板 4 处破折号和 export.html 过时的"提前1天/3小时"iCal 说明文案（现为自定义提前 N 小时）。页面标题里的少量 emoji 保留（语义用途，无图标库环境下的有意选择）
- [x] **界面改版：学业纸感风（2026-08-09，ckw-design skill 驱动）**：设计方向 = 「纸与墨」——浅色 = 白纸学习桌（纸白 #f7f6f3 + 墨蓝钢笔水 #2f5e9e + 荧光笔点缀），深色 = 「深夜书桌」（蓝黑 #171a1f + 纸白字，荧光降饱和）。签名元素：`.hl` 荧光笔高亮（首页「今天截止」数字 >0 时被荧光笔划过）+ 墨蓝大标题 + 首页标题下当天日期行（作业本日期栏，JS 生成）。具体改动：① style.css 整套 token 换色（浅/深两套全走变量），h1 24px 墨蓝 750、h2 16px 墨色 650；② 全部 10 个页面 h1/h2 标题 emoji 清空（正文/按钮/聊天里的语义 emoji 保留）；③ 首页统计卡 emoji 图标 → feather 线性 SVG + 数字墨蓝大字；④ 深色主按钮/用户气泡改深色文字（白字浅蓝底只有 2.6:1 不达标）；⑤ 修复深色下链接不可见 bug（全局 a 色走主题变量，原来浏览器默认蓝 #0000EE 深色下 1.66:1）；⑥ 课表调色板 16 色全换深色版（原来有黄/粉等浅色，白字 2.1:1；现在全部 ≥4.8:1）；⑦ settings 页 4 处内联硬编码色清理（#666/#ddd/#f0c040/#999 → 主题变量）。验证：Playwright 全站审计 20/20 页面 × 浅色/深色全过（溢出=0、碰撞=0、文本对比度 ≥4.5:1），窄屏 390px/1024px 全页面溢出=0（ckw-design 水平溢出门禁）
- [x] **聊天消息 Markdown 美化（2026-08-09）**：模型回答里的 `**加粗**`/`# 标题`/`- 列表`/`` `代码` ``/代码块/链接符号不再裸露，main.js 加 mdToHtml 渲染器（**先 escapeHtml 再替换符号，防 HTML 注入**；顺序：代码块→行内代码→链接→粗体→斜体→标题→无序/有序列表→换行；列表首项要先剥标记再 split）；聊天区纸感升级：作业本横线底（repeating-linear-gradient + --border-soft）、智能体气泡白纸片+细边框+轻投影、消息内 strong/em/code/pre/ul/ol 配套样式。验证：10 渲染用例 + XSS 用例 + 窄屏溢出全过
- [x] **复习并入智能体 + 内容智能定制（2026-08-09）**：① 新工具 4 个（query_profile 查画像 / update_profile 改画像【校验 0.5-4 小时、7/14/30/60 天、每天/隔天，只改提到的字段】/ complete_review_plan 完成或取消【plan_id+done】/ clear_review_plans 清空整组【危险操作，SYSTEM_PROMPT 规则 10 要求先确认】）；query_review_plans 升级为按 DDL 分组输出 + status 过滤；_review_text 分组展示含 plan_id。② **复习内容智能定制**：新建 llm.py（从 agent.py 抽出 api_key()/provider_info()/call()，对话与工具共用；agent.py 删掉 _api_key 改用 llm）；tools._generate_review 生成排期后调大模型按课程/资料/截止日为每个复习日写具体内容（30-60 字、由近及远由粗到精、每条不同），落库 UPDATE review_plans；**降级保护**：没 Key/网络失败/JSON 解析失败（_parse_review_json 兼容 ```json 代码块）→ 退回默认模板，生成功能绝不停摆。⚠️ 坑：generate_review_plan 返回的 rows 只有 review_plans 列（无 ddl_title/ddl_due，要另查 ddl_tasks）；sqlite3.Row 取不存在的键报 IndexError "No item with that key"；db.execute 是 models.db 模块级函数（写操作自动事务）
- [x] **连续打卡 + 日历视图 + 语音输入（2026-08-10）**：① **连续打卡**：db.py 新表 daily_logs（log_date UNIQUE 防同日重复，completed_count/focus_seconds）；models.complete_ddl 完成 DDL 时 `INSERT ... ON CONFLICT(log_date) DO UPDATE` 记当日打卡（同日多次完成只累加不重复建行）；models.get_streak_info() 从今天（今天没完成则从昨天）往回数连续打卡天数 + today_done 标记；首页第 4 张统计卡「连续学习（天）」（feather 闪电红色图标，streak>0 荧光笔高亮，今日已打卡时标签带「· 今日已打卡」）。② **日历视图**：app.py 新路由 /calendar（渲染时把全部 DDL 的 title/due_at/course/status 序列化注入模板）+ templates/calendar.html + base.html 侧边栏「日历」菜单（feather calendar 图标）；main.js 原生 JS 月历（周一开头 `lead=(first.getDay()+6)%7`、整行补齐；ALL_DDLS 按日期分组；红点=当天有 DDL、过期 DDL 红点更深；今天=主题浅蓝圆点，选中格=墨蓝 outline；点格子在下方 #cal-day-panel 列当天任务+状态徽章，title/course 全过 escapeHtml；上月/下月/回到本月按钮；图例统计本月 待完成/已过期/已完成）。③ **语音输入**：agent.html 聊天输入行加麦克风按钮（feather mic SVG，btn-small）；main.js 用浏览器自带 SpeechRecognition/webkitSpeechRecognition（zh-CN、零依赖、无 API Key 消耗），识别结果自动填进输入框等用户确认后回车发送，录音时按钮 `.voice-active` 变红+脉冲动画（再点=停止），onerror/onend 都复位 class；不支持语音识别的浏览器（如 Firefox）自动 display:none 隐藏按钮。验证：Playwright 20/20 全过（含 390/1024px 溢出=0 门禁）；⚠️ 注意：本机 ms-playwright 浏览器已清空，Playwright 脚本用系统 Edge `executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"`；2026-08-01 是周六故 8 月日历 6 行 11 空位属正确渲染
- [x] **手机访问 + iCal 远程订阅（2026-08-10）**：① config.py 加 HOST 配置（默认 127.0.0.1 最安全；改 "0.0.0.0" 后同一局域网设备可访问，app.run 改用 config.HOST）；② 新增 GET `/ical/study.ics` 订阅路由（make_response 返回 exporter.to_ical(进行中 DDL + 复习计划) 完整日历，Content-Type text/calendar，Cache-Control no-store 保证每次拉取最新）；③ export.html 顶部加「手机日历订阅」卡片（readonly 输入框显示 `request.host` 动态订阅地址、点击全选复制、iOS/Android 订阅操作步骤 + Tailscale 换 IP 说明），style.css 加 .subscribe-url（等宽字体+主题虚线框）。用途：电脑装 Tailscale/ZeroTier 内网穿透 + 手机同账号后，手机日历「添加已订阅的日历」填 `http://电脑100地址:5000/ical/study.ics`，任何网络都能同步、DDL 变动自动更新（iOS 约一天内自动刷新），提醒闹钟照常生效。⚠️ 该地址无登录鉴权，仅适合私有内网使用，别外发链接
- [x] **合并队友分支 mai-feature（2026-08-11）**：队友在 74a2106 基础上做了「首页课表 DDL 时间轴 + 课堂小测标记」，与本项目日历视图撞车。用户选择「两套都要」。合并要点：① 队友改动 = index.html 课表区加日期行（随周次联动）+ 每列 DDL 覆盖层（ddl-overlay 时间轴小横杠+流动拖尾+详情弹窗 ddl-detail）+ 首页考试叠加区分 考试红/小测紫（exam_json 加 kind）+ is_quiz 课堂小测（db.py 迁移列 + models.add_ddl/update_ddl 参数 + ddl.html 新增/编辑勾选 + app.py ddl_add/ddl_edit/api_ddl_get）；② 深色适配 6 处硬编码（--surface-1 不存在变量、弹窗 #fff/#333/#555、遮罩 rgba(0,0,0,0.45)、覆盖层 rgba(248,245,240,0.96) → 全部换主题变量）；③ **关键坑：git 冲突解决脚本丢了 .subscribe-url 的闭合 `}` → 花括号配平深度=1 → 其后所有 CSS 规则被浏览器静默丢弃（覆盖层背景透明、日历/语音/订阅样式全失效）**。排查方法：python 花括号配平脚本（最终深度必须为 0）+ Playwright 遍历 document.styleSheets[].cssRules 验证规则存在 + getComputedStyle 验证背景为真实主题色（rgba(0,0,0,0) 就是样式没生效的信号）。④ 合并后智能体全链路实测（真实模型）：页面/历史/查询对话/新增 DDL 工具链 9/9 全过，上次用户反馈的「智能体功能受限」未复现（当时可能是 CSS 失效引发的误判）。⑤ 全站 Playwright 18/18 全过（含多列覆盖层开合、深色背景、390/1024 窄屏溢出=0）
- [x] **同步日志折叠 + favicon（2026-08-11）**：① 设置页「同步日志」卡片改可折叠——默认只显示最近 3 条，超过 3 条时尾部出现「还有 N 条记录，点此展开」（原生 `<details>/<summary>` 零 JS，style.css 加 .crawl-more 系列：隐藏浏览器默认三角换自定义 ▸/▾ 箭头、颜色走 --primary/--border-soft 主题变量深色自动适配）；模板 for 循环改 `crawl_logs[:3]` + `crawl_logs[3:]` 双段渲染，`{% if crawl_logs %}` 保留无日志空态。⚠️ 注意：app.py 传给模板的 crawl_logs 本就只取最近 20 条（不是全部 29 条）；**Playwright `.count()` 统计的是 DOM 节点数，details 收起时子节点仍在 DOM 中，必须用 `.ddl-row:visible` 过滤才准**。② favicon：顺手修了全站 404 的 /favicon.ico（base.html 加 `<link rel="icon">` 指向 static/favicon.png + app.py 加 /favicon.ico 转发路由，1x1 墨蓝 PNG 用 python zlib 手写）。验证：Playwright 11/11 全过（默认 3 条/展开 20 条/收起回 3 条/details.open 状态/390+1024 溢出=0/无 console 报错）。Flask debug=False 改模板必须重启
- [x] **邮箱定时发送 iCal（2026-08-11）**：设置页新增「邮箱定时发送 DDL 日历」卡片（QQ 邮箱 smtp.qq.com:465 SSL）。① 新文件 email_sender.py：build_ics_str（复用 exporter.to_ical 生成全部进行中 DDL+复习计划）、build_summary_text（正文纯文字摘要，不打开日历软件也能看）、parse_addresses（兼容逗号/分号/中文逗号分隔、去重）、send_ical_email（标准库 smtplib+email，SMTP_SSL timeout=15 防卡死，MIMEMultipart 正文 text/plain + 附件 study.ics text/calendar，login 用授权码）。② config.py 加 SMTP_HOST="smtp.qq.com"/SMTP_PORT=465/EMAIL_SEND_HOUR=8。③ scheduler.py 加 email_ical_daily 定时任务（email_enabled 开关默认关；授权码 security.decrypt_text 解密；成功/失败/跳过全写 crawl_logs（source='email'），失败绝不外抛——与爬虫同「失败隔离」哲学）；start_scheduler 注册 CronTrigger(hour=email_send_hour, minute=5)（minute 固定 05 避开整点高峰）。④ app.py：settings_page 注入 email_* 模板变量；POST /api/email/settings（授权码留空则不变、加密存储、send_hour 校验 0-23）；POST /api/email/test（立即发送，SMTPAuthenticationError→「授权码错误」友好中文，读已存配置——先保存再点测试）。⑤ settings.html 卡片插在「使用提示」后（SMTP/端口/发信邮箱/授权码/收件人/抄送/发送时间下拉 0-23/开关 checkbox + 保存按钮 + 立即发送按钮 + QQ 授权码获取指引文字）；main.js 照 crawl-msg 模式加保存/测试交互（textContent 防 XSS）。**答辩亮点话术**：「DDL 三重推送」应用内提醒 → iCal 订阅 → 邮箱定时投递（免内网穿透，任何网络收附件导入即日历）。⚠️ 验证经验：测试脚本先保存配置再点测试按钮会真实连 QQ SMTP（几秒），「请先填好」场景要在保存前测；跑两轮前要先清 settings 表 email_* 键避免状态污染。验证：Playwright 17/17（表单/回显/密文占位/未配置提示/深色 390-1280px 溢出=0）+ 后端 5 项（密文 gAAAAA 开头无明文、ics 含 VCALENDAR、解析器、摘要、定时任务失败隔离——假授权码真实连接失败写 failed 日志不崩）。真实发送待用户填真实授权码验证
- [x] **邮箱发送升级：自定义时间 + 频率（2026-08-11）**：① 时间精确到分钟（hour 下拉 0-23 + minute 下拉步长 5，settings 表新增 email_send_minute，默认 0 分）；② 频率三档（settings 表 email_freq）：daily=每天 / weekly=每周固定几天（email_weekdays 存 "0,2,4" 格式，0=周一，模板默认 0-4=周一~周五，前端 JS 校验至少勾一天）/ interval=每 N 天（email_interval_days 1-30，默认 3）。③ scheduler.py 重构：模块级 `_sched` 全局 + `_email_trigger()` 按 freq 生成 trigger（weekly → CronTrigger(day_of_week="mon,wed,fri")）+ **`reload_email_job()`**（保存设置后调用，remove_job + add_job，**不用重启应用即生效**——比 agent_check_hour 的重启生效体验更好）；interval 的实现是「每天 cron 跑 + 任务内判断距上次成功发送（settings 表 email_last_sent_date，发送成功才更新）≥N 天」，重启无副作用。④ app.py 保存路由校验新字段（minute 0-59、freq 白名单、weekdays 0-6 去重过滤、interval_days 1-30）+ settings_page 注入 email_weekdays_list（_parse_weekdays 辅助函数）。⑤ settings.html 频率切换区（#email-weekdays-box / #email-interval-box，hidden 属性切换）+ main.js toggleEmailFreq。**⚠️ 关键坑：多选 checkbox 后端必须用 `request.form.getlist("email_weekdays")`——`request.form.get()` 只取第一个值**，导致勾选 0,2,4 只存了 '0'（Playwright 回显只有周一勾选才暴露，手动 urllib 单值 POST 反而测不出来）。⚠️ 调试教训：scheduler.email_ical_daily() 首行检查 email_enabled，验证脚本没勾开关会静默 return，看起来像「没走到发送分支」。验证：Playwright 20/20（分钟下拉 12 档、三档切换显示/隐藏、默认周一~周五、保存回显、周几未勾拦截、interval 回显、390/1024 溢出=0）+ 后端 4 项（启动 trigger、weekly reload 后 trigger=mon,wed,fri、满间隔发送失败写 email failed 日志、刚发过跳过）。测试状态已清理（email_* 全部删除、crawl_logs source=email 清除）

## 全部阶段完成（2026-08-06）
项目已完整交付。答辩前建议：按 README.md 的「演示脚本」完整预演一遍；可让 Claude 模拟评委提问。
