// ============================================
// 学习助手 Pro 前端交互脚本（原生 JS，无需任何框架）
// ============================================

// 简单的 HTML 转义，防止粘贴的文字被当成网页代码执行
function esc(s) {
    return s.replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
}

// ============================================
// 上传资料页：选文件后，自动识别课程和标签并填好表单
// ============================================
document.querySelectorAll("input[type=file]").forEach(function (input) {
    input.addEventListener("change", function () {
        var titleInput = document.querySelector("input[name=title]");
        if (titleInput && !titleInput.value && input.files.length > 0) {
            titleInput.value = input.files[0].name;   // 标题自动填文件名
        }
        if (input.files.length === 0) return;

        // 问后端：这个文件名该归哪个课程、打什么标签
        fetch("/api/autotag?filename=" + encodeURIComponent(input.files[0].name))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var courseInput = document.querySelector("input[name=course_name]");
                if (courseInput && !courseInput.value && data.course) {
                    courseInput.value = data.course;   // 自动填课程
                }
                // 已有标签直接勾选；没有的新标签填进"新标签"输入框
                data.tags.forEach(function (tag) {
                    var cb = document.querySelector('input[name="tags"][value="' + tag + '"]');
                    if (cb) {
                        cb.checked = true;
                    } else {
                        var newTags = document.querySelector("input[name=new_tags]");
                        if (newTags && newTags.value.indexOf(tag) === -1) {
                            newTags.value = newTags.value ? newTags.value + "," + tag : tag;
                        }
                    }
                });
            });
    });
});

// ============================================
// 通用工具：HTML 转义（防止把用户输入当 HTML 执行，日历/聊天渲染共用）
// ============================================
function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ============================================
// 智能体对话页
// ============================================
var chatInput = document.getElementById("chat-input");
var chatSend = document.getElementById("chat-send");
var chatBox = document.getElementById("chat-box");
if (chatInput && chatSend && chatBox) {
    var chatWelcome = document.getElementById("chat-welcome");

    // ============================================
    // 聊天消息美化：把模型回答里的 Markdown 符号渲染成真实格式
    // **加粗** → 加粗、# 标题 → 标题、- 列表 → 列表、`代码` → 等宽字体
    // 安全顺序：先转义 HTML 再替换符号，所以 <script> 之类不可能被注入
    // 注意：escapeHtml 是全局函数（上方定义），聊天和日历共用
    // ============================================
    function mdToHtml(text) {
        if (!text) return "";
        var esc = escapeHtml(text);                       // 1. 先转义，防注入
        esc = esc.replace(/```([\s\S]*?)```/g,             // 2. 代码块 ```…```
            function (m, code) { return "<pre><code>" + code.trim() + "</code></pre>"; });
        esc = esc.replace(/`([^`\n]+)`/g, "<code>$1</code>");           // 3. 行内代码
        esc = esc.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,     // 4. 链接 [文字](网址)
            '<a href="$2" target="_blank" rel="noopener">$1</a>');
        esc = esc.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")   // 5. 粗体 **x**
                 .replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
        esc = esc.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")     // 6. 斜体 *x*
                 .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");
        esc = esc.replace(/^### (.*)$/gm, "<h6>$1</h6>")                 // 7. 标题（从大到小）
                 .replace(/^## (.*)$/gm, "<h5>$1</h5>")
                 .replace(/^# (.*)$/gm, "<h4>$1</h4>");
        esc = esc.replace(/(?:^|\n)[ \t]*[-*+][ \t]+[^\n]*(?:\n[ \t]*[-*+][ \t]+[^\n]*)*/g,  // 8. 无序列表
            function (m) {
                var items = m.trim().replace(/^[ \t]*[-*+][ \t]+/, "")   // 剥掉首项标记
                                 .split(/\n[ \t]*[-*+][ \t]+/).map(function (s) { return s.trim(); });
                return "<ul><li>" + items.join("</li><li>") + "</li></ul>";
            });
        esc = esc.replace(/(?:^|\n)[ \t]*\d+[.、][ \t]+[^\n]*(?:\n[ \t]*\d+[.、][ \t]+[^\n]*)*/g,  // 9. 有序列表
            function (m) {
                var items = m.trim().replace(/^[ \t]*\d+[.、][ \t]+/, "")   // 剥掉首项编号
                                 .split(/\n[ \t]*\d+[.、][ \t]+/).map(function (s) { return s.trim(); });
                return "<ol><li>" + items.join("</li><li>") + "</li></ol>";
            });
        esc = esc.replace(/\n/g, "<br>");                 // 10. 换行
        return esc;
    }

    function appendMsg(role, text) {
        var div = document.createElement("div");
        div.className = "chat-msg " + role;
        div.innerHTML = mdToHtml(text);   // 先转义再渲染 markdown，安全
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return div;
    }

    // 打开页面时恢复历史聊天记录（存数据库，刷新/重启都不丢）
    fetch("/api/agent/history")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var msgs = data.messages || [];
            if (msgs.length > 0) {
                if (chatWelcome) chatWelcome.remove();   // 有历史就不再显示欢迎语
                msgs.forEach(function (m) {
                    appendMsg(m.role, m.content);
                });
            }
        })
        .catch(function () { });

    function send() {
        var text = chatInput.value.trim();
        if (!text) return;
        chatInput.value = "";
        appendMsg("user", text);

        var typing = appendMsg("agent", "…");
        typing.classList.add("chat-typing");

        // 聊天记录由后端存数据库、后端组装上下文，前端不用再维护 history
        fetch("/api/agent/chat", {
            method: "POST",
            body: new URLSearchParams({ message: text }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                typing.remove();
                if (data.error) {
                    appendMsg("agent", "⚠️ " + data.error);
                } else {
                    appendMsg("agent", data.reply);
                }
            })
            .catch(function () {
                typing.remove();
                appendMsg("agent", "⚠️ 网络或服务器出错，请稍后再试。");
            });
    }

    // 清空对话（连同数据库里的历史一起删，恢复欢迎语）
    var chatClear = document.getElementById("chat-clear");
    if (chatClear) {
        chatClear.addEventListener("click", function () {
            if (!confirm("确定清空全部聊天记录吗？")) return;
            fetch("/api/agent/history/clear", { method: "POST" })
                .then(function () {
                    chatBox.innerHTML = "";
                    if (chatWelcome) chatBox.appendChild(chatWelcome);
                })
                .catch(function () { alert("清空失败，请稍后再试"); });
        });
    }

    chatSend.addEventListener("click", send);
    chatInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") send();
    });
}

// ============================================
// 设置页：保存大模型配置
// ============================================
var agentForm = document.getElementById("agent-form");
if (agentForm) {
    agentForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var msg = document.getElementById("save-msg");
        msg.textContent = "保存中…";
        fetch("/api/agent/settings", {
            method: "POST",
            body: new URLSearchParams(new FormData(agentForm)),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.ok ? "✅ 已保存（重启应用后新时间生效）" : "保存失败";
            })
            .catch(function () { msg.textContent = "保存失败"; });
    });
}

// ============================================
// 设置页：立即备份
// ============================================
var backupBtn = document.getElementById("backup-btn");
if (backupBtn) {
    backupBtn.addEventListener("click", function () {
        var msg = document.getElementById("backup-msg");
        msg.textContent = "备份中…";
        fetch("/api/backup", { method: "POST" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.ok ? "✅ " + data.msg : "❌ " + data.msg;
                if (data.ok) setTimeout(function () { location.reload(); }, 1000);
            });
    });
}

// ============================================
// 学习画像页：保存 / 清除
// ============================================
var profileForm = document.getElementById("profile-form");
if (profileForm) {
    profileForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var msg = document.getElementById("profile-msg");
        msg.textContent = "保存中…";
        fetch("/api/profile/save", {
            method: "POST",
            body: new URLSearchParams(new FormData(profileForm)),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.ok ? "✅ " + data.msg : "保存失败";
                setTimeout(function () { location.reload(); }, 1200);
            });
    });
}
var profileClearBtn = document.getElementById("profile-clear-btn");
if (profileClearBtn) {
    profileClearBtn.addEventListener("click", function () {
        if (!confirm("确定清除学习画像吗？复习方案将回到默认规则。")) return;
        fetch("/api/profile/clear", { method: "POST" })
            .then(function () { location.reload(); });
    });
}

// ============================================
// 设置页：学习通扫码登录 + 自动同步（Playwright）
// ============================================
var cxArea = document.getElementById("cx-login-area");
var cxSyncBox = document.getElementById("cx-sync-result");
var cxLastKey = "";        // 上次渲染的登录状态指纹（状态没变就不重建 DOM，防按钮丢失）
var cxLastSyncKey = "";    // 上次渲染的同步状态指纹
var cxAutoRefreshed = false;  // 二维码过期后是否已自动刷新过一次（防止死循环）

function cxPost(url) {
    return fetch(url, { method: "POST" }).then(function (r) { return r.json(); });
}

// 渲染登录区域。data = /api/crawler/chaoxing/status 返回
function cxRender(data) {
    if (!cxArea) return;
    // 状态指纹：登录与否 + 流程状态 + 二维码是否出现。变了才重建页面
    var key = data.logged_in ? "in" : ("out" + data.login.state + ":" + (data.login.png ? "p" : "-"));
    if (key === cxLastKey) return;
    cxLastKey = key;

    if (data.logged_in) {
        // 已登录：显示状态 + 开始同步 / 退出登录
        cxArea.innerHTML =
            '<p style="margin-bottom:10px">✅ <strong>学习通已登录</strong>' +
            '（登录态约 7 天有效，失效后重新扫码）</p>' +
            '<div>' +
            '<button type="button" class="btn btn-primary" id="cx-sync-btn">📥 开始同步抓取</button> ' +
            '<button type="button" class="btn" id="cx-logout-btn">退出登录</button> ' +
            '<span id="cx-msg" class="muted"></span>' +
            '</div>';
        document.getElementById("cx-sync-btn").addEventListener("click", cxStartSync);
        document.getElementById("cx-logout-btn").addEventListener("click", function () {
            if (!confirm("确定退出学习通登录吗？")) return;
            cxPost("/api/crawler/chaoxing/logout").then(function () { location.reload(); });
        });
        return;
    }

    var st = data.login.state;   // idle / waiting / expired / failed
    var html = "";
    if (st === "waiting" && data.login.png) {
        // 二维码已显示：可随时点刷新换新码
        html = '<p class="empty">📱 用<strong>手机学习通 App</strong>扫一扫下面的二维码：</p>' +
            '<img src="data:image/png;base64,' + data.login.png +
            '" style="width:200px;height:200px;border:1px solid #ddd;border-radius:8px;background:#fff">' +
            '<p class="empty">扫码成功后本页会自动进入已登录状态（二维码 5 分钟内有效，过期自动换新）。</p>' +
            '<div><button type="button" class="btn" id="cx-refresh-btn">🔄 刷新二维码</button></div>';
    } else if (st === "waiting") {
        html = '<p class="empty">⏳ 正在打开浏览器生成二维码…（约 10 秒）</p>';
    } else if (st === "expired") {
        html = '<p class="empty">❌ 二维码已过期，正在自动生成新二维码…</p>';
        // 过期自动刷新一次（不反复刷，靠 cxAutoRefreshed 挡住循环）
        if (!cxAutoRefreshed) {
            cxAutoRefreshed = true;
            cxPost("/api/crawler/chaoxing/qr").catch(function () {});
        }
    } else if (st === "failed") {
        html = '<p class="empty">❌ ' + esc(data.login.error || "登录失败，请重试") + '</p>' +
            '<div><button type="button" class="btn btn-primary" id="cx-qr-btn">📱 重新生成二维码</button></div>';
    } else {
        html = '<p class="empty">用手机学习通扫码登录，自动把作业 DDL 抓进清单（不用输密码）：</p>' +
            '<div><button type="button" class="btn btn-primary" id="cx-qr-btn">📱 生成登录二维码</button></div>';
    }
    cxArea.innerHTML = html;

    // 绑定按钮：生成二维码 / 刷新二维码（点刷新 = 重新生成，旧浏览器自动退出）
    var btn = document.getElementById("cx-qr-btn") || document.getElementById("cx-refresh-btn");
    if (btn) {
        btn.addEventListener("click", function () {
            cxPost("/api/crawler/chaoxing/qr").then(function (data) {
                if (!data.ok) {
                    cxLastKey = "";   // 强制重绘，显示错误
                    cxArea.innerHTML = '<p class="empty">❌ ' + esc(data.msg) + '</p>';
                }
            });
        });
    }
}

function cxStartSync() {
    var msg = document.getElementById("cx-msg");
    msg.textContent = "同步中…（每门课约 5-10 秒，请耐心等待）";
    cxPost("/api/crawler/chaoxing/sync").then(function (data) {
        msg.textContent = data.msg || "已开始同步";
    });
}

// 渲染同步结果区域。sync = status 返回里的 sync 字段
function cxRenderSync(sync) {
    if (!cxSyncBox) return;
    var key = sync.state + ":" + (sync.items ? sync.items.length : 0) + ":" + (sync.detail || "");
    if (key === cxLastSyncKey) return;
    cxLastSyncKey = key;

    if (sync.state === "running") {
        cxSyncBox.innerHTML = '<p class="empty">⏳ ' + esc(sync.detail || "正在抓取课程…") + '</p>';
    } else if (sync.state === "failed") {
        cxSyncBox.innerHTML = '<p class="empty">❌ ' + esc(sync.error) + '</p>';
    } else if (sync.state === "done") {
        if (sync.items.length === 0) {
            cxSyncBox.innerHTML = '<p class="empty">😄 没有找到待办的作业/考试 DDL。</p>';
            return;
        }
        cxImportPreview(sync.items, cxSyncBox, "学习通");
    }
}

// 抓取结果预览（学习通 / 教务处共用）：每条可勾选、可改课程，确认后导入 DDL 清单
function cxImportPreview(items, box, sourceName) {
    var html = '<p class="empty">抓到 ' + items.length + ' 条 DDL，勾选要导入的：</p>';
    items.forEach(function (item) {
        html += '<label class="extract-row">' +
            '<input type="checkbox" class="extract-check" checked> ' +
            '<input type="text" class="extract-title" value="' + esc(item.title) + '">' +
            '<input type="text" class="extract-course" value="' + esc(item.course || "") + '" placeholder="课程">' +
            '<input type="text" class="extract-due" value="' + esc(item.deadline) + '">' +
            '</label>';
    });
    html += '<div style="margin-top:8px"><button type="button" class="btn btn-primary cx-import-btn">' +
        '✅ 确认导入 DDL 清单</button> <span class="cx-import-msg muted"></span></div>';
    box.innerHTML = html;

    box.querySelector(".cx-import-btn").addEventListener("click", function () {
        var rows = box.querySelectorAll(".extract-row");
        var pending = [];
        rows.forEach(function (row) {
            if (!row.querySelector(".extract-check").checked) return;
            pending.push({
                title: row.querySelector(".extract-title").value.trim(),
                course: row.querySelector(".extract-course").value.trim(),
                deadline: row.querySelector(".extract-due").value.trim(),
                source: sourceName,
            });
        });
        if (pending.length === 0) { alert("请先勾选要导入的条目"); return; }
        var msg = box.querySelector(".cx-import-msg");
        msg.textContent = "导入中…";
        fetch("/api/crawler/import", {
            method: "POST",
            body: new URLSearchParams({ items: JSON.stringify(pending) }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                alert(data.msg);
                location.reload();
            })
            .catch(function () { msg.textContent = "导入失败，请重试"; });
    });
}

// 单一轮询（2 秒一次）：状态变化才重绘，避免按钮被重建丢掉
if (cxArea) {
    setInterval(function () {
        fetch("/api/crawler/chaoxing/status")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                cxRender(data);
                cxRenderSync(data.sync);
            })
            .catch(function () {});
    }, 2000);
}

// ============================================
// 设置页：教务爬虫（保存账号 / 立即同步 / 半自动粘贴提取）【队友功能】
// ============================================
var crawlerForm = document.getElementById("crawler-form");
if (crawlerForm) {
    crawlerForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var msg = document.getElementById("crawl-msg");
        msg.textContent = "保存中…";
        fetch("/api/crawler/save", {
            method: "POST",
            body: new URLSearchParams(new FormData(crawlerForm)),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.ok ? "✅ 已保存" : "保存失败";
            });
    });
}

var crawlSyncBtn = document.getElementById("crawl-sync-btn");
if (crawlSyncBtn) {
    crawlSyncBtn.addEventListener("click", function () {
        var msg = document.getElementById("crawl-msg");
        msg.textContent = "同步中…";
        fetch("/api/crawler/sync", { method: "POST" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.msg || "已开始同步";
                // 同步在后台跑，这里开始轮询"有没有要人工输入的验证码"
                checkCrawlerCaptcha(msg);
            });
    });
}

// 退出登录：清除账号密码 + 课表，回到初始状态
var logoutBtn = document.getElementById("crawler-logout-btn");
if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
        var msg = document.getElementById("crawler-logout-msg");
        if (!confirm("确定要退出登录吗？\n将清除教务账号密码，并清空已同步的课表数据。")) {
            return;
        }
        msg.textContent = "正在退出…";
        fetch("/api/crawler/logout", { method: "POST" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.ok ? "✅ " + data.msg : "退出失败";
                setTimeout(function () { location.reload(); }, 1200);   // 刷新回到初始状态
            });
    });
}

// 同步完成后刷新页面时，若上次同步失败且提示了"校园网/验证码/半自动"，
// 自动滚动到半自动粘贴区并高亮提示（引导用户用最稳妥的方式）
var crawlLogsBox = document.getElementById("crawl-logs");
if (crawlLogsBox) {
    var latest = crawlLogsBox.getAttribute("data-latest");
    var latestStatus = crawlLogsBox.getAttribute("data-latest-status");
    if (latestStatus === "failed") {
        var needPaste = /校园网|VPN|验证码|半自动|认证服务器连不上|结构可能已变化/.test(latest);
        if (needPaste) {
            var pasteCard = document.getElementById("crawl-paste-result");
            var hint = document.getElementById("crawl-paste-note");
            if (pasteCard) {
                pasteCard.innerHTML =
                    '<div class="note" style="margin-top:8px;border-color:#f0c040;background:#fffbea">' +
                    '<p><strong>全自动同步没成功</strong>，请用下面的「半自动同步」：</p>' +
                    '<p style="margin:6px 0 4px">① 浏览器打开教务系统，登录后进入「考试安排 / 作业」页</p>' +
                    '<p style="margin:4px 0">② 按 Ctrl+A 全选 → Ctrl+C 复制整页文字</p>' +
                    '<p style="margin:4px 0 6px">③ 粘贴到下方输入框 → 点「提取 DDL」→ 勾选确认导入</p>' +
                    '</div>';
                if (hint) {
                    pasteCard.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            }
        }
    }
}

// 轮询验证码：同步过程中若遇到需要人工输入，弹出验证码图让用户看
var captchaPollTimer = null;
function checkCrawlerCaptcha(msg) {
    if (captchaPollTimer) clearTimeout(captchaPollTimer);
    fetch("/api/crawler/captcha/status")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.status === "waiting" && data.image_base64) {
                showCaptchaDialog(data.image_base64, msg);
                return;   // 显示后不再轮询，等用户提交
            }
            if (data.status === "idle") {
                // 没有待输入的验证码，但同步可能还在跑：短暂后再查
                captchaPollTimer = setTimeout(function () {
                    checkCrawlerCaptcha(msg);
                }, 1500);
            }
            // submitted/timeout：验证码环节已结束，交给上面的 2500ms 刷新兜底
        })
        .catch(function () { });
}

function showCaptchaDialog(imageBase64, msg) {
    if (captchaPollTimer) clearTimeout(captchaPollTimer);
    var box = document.getElementById("crawl-paste-result");   // 复用页面上已有的结果区
    box.innerHTML =
        '<div class="note" style="margin-top:6px">' +
        '<p><strong>请输入验证码</strong>（图片如下，看不清可点「重新同步」）</p>' +
        '<img src="data:image/png;base64,' + imageBase64 + '" alt="验证码" ' +
        'style="border:1px solid #ccc;border-radius:4px;max-height:64px;display:block;margin:8px 0">' +
        '<input type="text" id="captcha-answer" placeholder="输入图中的字符" ' +
        'autocomplete="off" style="width:160px"> ' +
        '<button type="button" class="btn btn-primary" id="captcha-submit-btn">提交验证码</button>' +
        '</div>';
    var answerInput = document.getElementById("captcha-answer");
    answerInput.focus();
    function submitCaptcha() {
        var answer = answerInput.value.trim();
        if (!answer) { alert("请先输入验证码"); return; }
        fetch("/api/crawler/captcha/submit", {
            method: "POST",
            body: new URLSearchParams({ answer: answer }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                box.innerHTML = '<p class="empty">' + (data.ok ? "已提交，等待登录完成…" : ("提交失败：" + esc(data.msg))) + '</p>';
                if (data.ok) {
                    // 提交后同步线程继续，稍后刷新看结果
                    captchaPollTimer = setTimeout(function () { location.reload(); }, 3500);
                }
            });
    }
    document.getElementById("captcha-submit-btn").addEventListener("click", submitCaptcha);
    answerInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") submitCaptcha();
    });
}

var pasteBtn = document.getElementById("crawl-paste-btn");
if (pasteBtn) {
    pasteBtn.addEventListener("click", function () {
        var text = document.getElementById("crawl-paste-text").value;
        var box = document.getElementById("crawl-paste-result");
        if (!text.trim()) {
            box.innerHTML = '<p class="empty">请先粘贴文字</p>';
            return;
        }
        fetch("/api/crawler/paste", {
            method: "POST",
            body: new URLSearchParams({ text: text }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.items.length === 0) {
                    box.innerHTML = '<p class="empty">没有识别到日期，请检查复制的内容</p>';
                    return;
                }
                var html = '<p class="empty">识别到 ' + data.items.length + ' 条，确认后加入 DDL 清单：</p>';
                data.items.forEach(function (item) {
                    html += '<label class="extract-row">' +
                        '<input type="checkbox" class="extract-check" checked> ' +
                        '<input type="text" class="extract-title" value="' + esc(item.title) + '">' +
                        '<input type="text" class="extract-course" value="' + esc(item.course || "") + '" placeholder="课程">' +
                        '<input type="text" class="extract-due" value="' + esc(item.due_at) + '">' +
                        '</label>';
                });
                html += '<button type="button" class="btn btn-primary" id="crawl-import-btn">确认加入 DDL 清单</button>';
                box.innerHTML = html;

                document.getElementById("crawl-import-btn").addEventListener("click", function () {
                    var rows = box.querySelectorAll(".extract-row");
                    var pending = 0;
                    rows.forEach(function (row) {
                        if (row.querySelector(".extract-check").checked) pending++;
                    });
                    if (pending === 0) { alert("请先勾选要导入的条目"); return; }
                    var saved = 0;
                    rows.forEach(function (row) {
                        if (!row.querySelector(".extract-check").checked) return;
                        var title = row.querySelector(".extract-title").value.trim();
                        var course = row.querySelector(".extract-course").value.trim();
                        var due = row.querySelector(".extract-due").value.trim().replace("T", " ");
                        if (!title || !due) return;
                        fetch("/ddl/add", {
                            method: "POST",
                            body: new URLSearchParams({ title: title, course_name: course, due_at: due }),
                        }).then(function () {
                            saved++;
                            if (saved === pending) {
                                alert("已加入 DDL 清单 ✅");
                                location.reload();
                            }
                        });
                    });
                });
            });
    });
}

// ============================================
// 设置页：删除已保存的 API Key
// ============================================
var deleteKeyBtn = document.getElementById("delete-key-btn");
if (deleteKeyBtn) {
    deleteKeyBtn.addEventListener("click", function () {
        if (!confirm("确定删除已保存的 API Key 吗？删除后智能体将回到模拟模式，需要重新填写才能使用真实大模型。")) return;
        fetch("/api/agent/key/delete", { method: "POST" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.ok) location.reload();
            });
    });
}

// ============================================
// 设置页：测试大模型连接
// ============================================
var testBtn = document.getElementById("test-btn");
if (testBtn) {
    testBtn.addEventListener("click", function () {
        var msg = document.getElementById("save-msg");
        msg.textContent = "测试中…";
        fetch("/api/agent/test", { method: "POST" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                msg.textContent = data.ok ? "✅ " + data.msg : "❌ " + data.msg;
            })
            .catch(function () { msg.textContent = "❌ 测试失败，请稍后再试"; });
    });
}

// ============================================
// 通知页：全部标为已读
// ============================================
var readAllBtn = document.getElementById("read-all-btn");
if (readAllBtn) {
    readAllBtn.addEventListener("click", function () {
        fetch("/api/notifications/read_all", { method: "POST" })
            .then(function () { location.reload(); });
    });
}

// ============================================
// DDL 页：粘贴文本，一键提取 DDL
// ============================================
var extractBtn = document.getElementById("extract-btn");
if (extractBtn) {
    extractBtn.addEventListener("click", function () {
        var text = document.getElementById("extract-text").value;
        var box = document.getElementById("extract-result");
        if (!text.trim()) {
            box.innerHTML = '<p class="empty">请先在上面的框里粘贴文字</p>';
            return;
        }

        // 问后端：这段文字里有哪些 DDL
        var body = new URLSearchParams({ text: text });
        fetch("/api/parse_ddl", { method: "POST", body: body })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.items.length === 0) {
                    box.innerHTML = '<p class="empty">没有找到日期，试试手动添加？</p>';
                    return;
                }
                // 生成预览：每条可勾选、可改标题/课程/时间（课程已自动识别，可修改）
                var html = '<p class="empty">识别到 ' + data.items.length + ' 条，勾选要导入的（可修改）：</p>';
                data.items.forEach(function (item) {
                    html += '<label class="extract-row">' +
                        '<input type="checkbox" class="extract-check" checked> ' +
                        '<input type="text" class="extract-title" value="' + esc(item.title) + '">' +
                        '<input type="text" class="extract-course" value="' + esc(item.course || "") + '" placeholder="课程">' +
                        '<input type="text" class="extract-due" value="' + esc(item.due_at) + '">' +
                        '</label>';
                });
                html += '<button type="button" class="btn btn-primary" id="import-btn">确认导入</button>';
                box.innerHTML = html;

                // 确认导入：把勾选的条目逐条提交给后端保存
                document.getElementById("import-btn").addEventListener("click", function () {
                    var rows = box.querySelectorAll(".extract-row");
                    var pending = 0;
                    rows.forEach(function (row) {
                        if (row.querySelector(".extract-check").checked) pending++;
                    });
                    if (pending === 0) {
                        alert("请先勾选要导入的条目");
                        return;
                    }
                    var saved = 0;
                    rows.forEach(function (row) {
                        if (!row.querySelector(".extract-check").checked) return;
                        var title = row.querySelector(".extract-title").value.trim();
                        var course = row.querySelector(".extract-course").value.trim();
                        var due = row.querySelector(".extract-due").value.trim().replace("T", " ");
                        if (!title || !due) return;
                        fetch("/ddl/add", {
                            method: "POST",
                            body: new URLSearchParams({ title: title, course_name: course, due_at: due }),
                        }).then(function () {
                            saved++;
                            if (saved === pending) location.reload();  // 全部存完刷新页面
                        });
                    });
                });
            });
    });
}

// ============================================
// 右下角弹出提示（Toast）+ 浏览器通知
// ============================================
// showToast("文字", "ok/warn/error", "按钮文字", 点击按钮后执行的函数)
function showToast(msg, type, actionLabel, actionFn) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var el = document.createElement("div");
    el.className = "toast toast-" + (type || "ok");
    var text = document.createElement("span");
    text.textContent = msg;          // textContent：安全，不会执行 HTML
    el.appendChild(text);
    if (actionLabel && actionFn) {
        var btn = document.createElement("button");
        btn.className = "toast-action";
        btn.textContent = actionLabel;
        btn.addEventListener("click", function () {
            el.remove();             // 点按钮后立刻消失
            actionFn();
        });
        el.appendChild(btn);
    }
    var close = document.createElement("button");
    close.className = "toast-close";
    close.textContent = "✕";
    close.addEventListener("click", function () { el.remove(); });
    el.appendChild(close);
    container.appendChild(el);
    // 自动消失：带按钮的多留一会儿，给人点的时间
    setTimeout(function () { el.remove(); }, actionFn ? 8000 : 3500);
}

// 开启浏览器通知（需要用户点一次授权，只有 https 或 localhost 才支持）
function enableNotifications() {
    if (!("Notification" in window)) {
        showToast("此浏览器不支持通知", "error");
        return;
    }
    Notification.requestPermission().then(function (p) {
        if (p === "granted") {
            new Notification("学习助手 Pro", { body: "通知已开启！DDL 截止当天打开页面会提醒你。" });
        } else {
            showToast("通知权限未开启，仍会在页面内弹出提示", "warn");
        }
    });
}

// ==================== 深色模式 ====================
// 规则：用户手动点过切换按钮就记住选择；没点过则跟随系统偏好。
function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    var btn = document.getElementById("theme-toggle");
    if (btn) {
        btn.textContent = theme === "dark" ? "☀️ 浅色模式" : "🌙 深色模式";
    }
}
(function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("theme"); } catch (e) {}
    if (saved === "dark" || saved === "light") {
        applyTheme(saved);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        applyTheme("dark");   // 没手动选过，跟随系统深色
    }
    var btn = document.getElementById("theme-toggle");
    if (btn) {
        btn.addEventListener("click", function () {
            var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
            applyTheme(next);
            try { localStorage.setItem("theme", next); } catch (e) {}
        });
    }
})();

// ============================================
// 日历视图（/calendar 页）：月历上标 DDL 截止日，点某天看当天任务
// 数据 ALL_DDLS 由后端注入（模板里的 <script> 变量）
// ============================================
var calBody = document.getElementById("cal-body");
if (calBody) {
    var calTitle = document.getElementById("cal-title");
    var calDayPanel = document.getElementById("cal-day-panel");
    var calLegend = document.getElementById("cal-legend");
    var selDate = null;          // 当前选中的日期 YYYY-MM-DD
    var curYear, curMonth;       // 当前显示的月份（curMonth: 0-11）

    function calParseDue(dueAt) {
        var m = (dueAt || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
        return m ? m[1] + "-" + m[2] + "-" + m[3] : null;
    }
    function calTodayStr() {
        var d = new Date();
        return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
    }

    function renderCalendar() {
        var year = curYear, month = curMonth;
        var first = new Date(year, month, 1);
        var lead = (first.getDay() + 6) % 7;      // 周一开头（0=周一）
        var daysInMonth = new Date(year, month + 1, 0).getDate();
        var todayStr = calTodayStr();
        var byDate = {};
        ALL_DDLS.forEach(function (t) {
            var d = calParseDue(t.due_at);
            if (d) (byDate[d] = byDate[d] || []).push(t);
        });
        var html = "";
        for (var r = 0; r < 6; r++) {
            html += "<tr>";
            for (var c = 0; c < 7; c++) {
                var dayNum = r * 7 + c - lead + 1;
                if (dayNum < 1 || dayNum > daysInMonth) { html += '<td class="cal-cell cal-empty"></td>'; continue; }
                var ds = year + "-" + ("0" + (month + 1)).slice(-2) + "-" + ("0" + dayNum).slice(-2);
                var ddl = byDate[ds] || [];
                var overdue = ddl.some(function (t) { return t.status === "pending" && t.due_at < todayStr + " 00:00"; });
                var cls = "cal-cell";
                if (ds === todayStr) cls += " cal-today";
                if (ds === selDate) cls += " cal-selected";
                if (ddl.length) cls += overdue ? " cal-has-ddl-overdue" : " cal-has-ddl";
                var dots = "";
                if (ddl.length) {
                    dots = '<div class="cal-dots">' + ddl.slice(0, 3).map(function () {
                        return '<span class="cal-dot"></span>';
                    }).join("") + (ddl.length > 3 ? '<span class="cal-dot-more">+' + (ddl.length - 3) + "</span>" : "") + "</div>";
                }
                html += '<td class="' + cls + '" data-date="' + ds + '">' +
                    '<div class="cal-day-num">' + dayNum + "</div>" + dots + "</td>";
            }
            html += "</tr>";
            if ((r + 1) * 7 - lead >= daysInMonth) break;   // 行数够就停
        }
        calBody.innerHTML = html;
        calTitle.textContent = year + " 年 " + (month + 1) + " 月";

        // 图例：本月 DDL 分布
        var mPrefix = year + "-" + ("0" + (month + 1)).slice(-2);
        var activeCount = 0, overCount = 0, doneCount = 0;
        ALL_DDLS.forEach(function (t) {
            var d = calParseDue(t.due_at);
            if (d && d.indexOf(mPrefix) === 0) {
                if (t.status === "done") doneCount++;
                else if (t.due_at < todayStr + " 00:00") overCount++;
                else activeCount++;
            }
        });
        calLegend.textContent = "本月：" + activeCount + " 项待完成，" + overCount + " 项已过期，" + doneCount + " 项已完成";
    }

    // 点某天 → 下方显示当天任务（事件委托，防 XSS：内容都过 escapeHtml）
    calBody.addEventListener("click", function (e) {
        var td = e.target.closest ? e.target.closest("td[data-date]") : null;
        if (!td || !td.dataset.date) return;
        selDate = td.dataset.date;
        renderCalendar();
        var items = ALL_DDLS.filter(function (t) { return calParseDue(t.due_at) === selDate; });
        var p = selDate.split("-");
        var wd = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][new Date(+p[0], +p[1] - 1, +p[2]).getDay()];
        var todayStr = calTodayStr();
        if (!items.length) {
            calDayPanel.innerHTML = '<h2>' + selDate + "（" + wd + "）</h2><p class=\"empty\">这一天没有 DDL 截止，休息一下！</p>";
            return;
        }
        items.sort(function (a, b) { return a.due_at > b.due_at ? 1 : -1; });
        var html = "<h2>" + selDate + "（" + wd + "）· " + items.length + " 项任务</h2>";
        html += items.map(function (t) {
            var cls = "ddl-row" + (t.status === "done" ? " ddl-done" : (t.due_at < todayStr + " 00:00" ? " ddl-overdue" : ""));
            var badge = t.status === "done" ? '<span class="badge badge-done">已完成</span>'
                : (t.due_at < todayStr + " 00:00" ? '<span class="badge badge-overdue">已过期</span>' : '<span class="badge badge-normal">待完成</span>');
            return '<div class="' + cls + '"><div><strong>' + escapeHtml(t.title) + "</strong>" +
                (t.course ? '<span class="tag">' + escapeHtml(t.course) + "</span>" : "") + "</div>" +
                '<div class="right"><span class="muted">' + escapeHtml(t.due_at) + "</span>" + badge + "</div></div>";
        }).join("");
        calDayPanel.innerHTML = html;
    });

    document.getElementById("cal-prev").addEventListener("click", function () {
        calSetMonth(curMonth === 0 ? curYear - 1 : curYear, curMonth === 0 ? 11 : curMonth - 1);
    });
    document.getElementById("cal-next").addEventListener("click", function () {
        calSetMonth(curMonth === 11 ? curYear + 1 : curYear, curMonth === 11 ? 0 : curMonth + 1);
    });
    document.getElementById("cal-today").addEventListener("click", function () {
        var d = new Date();
        calSetMonth(d.getFullYear(), d.getMonth());
    });
    function calSetMonth(y, m) { curYear = y; curMonth = m; renderCalendar(); }
    var now = new Date();
    calSetMonth(now.getFullYear(), now.getMonth());
}

// ============================================
// 语音输入（智能体页）：用浏览器自带的语音识别，说中文自动填进输入框
// 浏览器不支持（如 Firefox）就自动隐藏麦克风按钮，不影响其他功能
// ============================================
var voiceBtn = document.getElementById("chat-voice");
if (voiceBtn) {
    var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
        var rec = new SpeechRec();
        rec.lang = "zh-CN";          // 识别普通话
        rec.interimResults = false;  // 识别完了一次性给结果
        rec.onresult = function (e) {
            var text = "";
            for (var i = 0; i < e.results.length; i++) {
                text += e.results[i][0].transcript;
            }
            chatInput.value = text;  // 填进输入框，用户确认后回车发送
            chatInput.focus();
        };
        function voiceEnd() { voiceBtn.classList.remove("voice-active"); }
        rec.onerror = voiceEnd;
        rec.onend = voiceEnd;
        voiceBtn.addEventListener("click", function () {
            if (voiceBtn.classList.contains("voice-active")) {
                rec.stop();          // 再点一次 = 停止录音
                return;
            }
            try {
                rec.start();
                voiceBtn.classList.add("voice-active");   // 变红 + 脉冲，提示正在听
            } catch (e) {
                voiceBtn.classList.remove("voice-active");
            }
        });
    } else {
        voiceBtn.style.display = "none";   // 浏览器不支持语音识别，不显示按钮
    }
}
