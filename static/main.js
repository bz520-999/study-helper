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
// 智能体对话页
// ============================================
var chatInput = document.getElementById("chat-input");
var chatSend = document.getElementById("chat-send");
var chatBox = document.getElementById("chat-box");
if (chatInput && chatSend && chatBox) {
    var chatHistory = [];   // 记住对话历史（最近 10 条），让智能体有上下文

    function appendMsg(role, text) {
        var div = document.createElement("div");
        div.className = "chat-msg " + role;
        div.textContent = text;   // 用 textContent 防止 HTML 注入
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return div;
    }

    function send() {
        var text = chatInput.value.trim();
        if (!text) return;
        chatInput.value = "";
        appendMsg("user", text);

        var typing = appendMsg("agent", "…");
        typing.classList.add("chat-typing");

        fetch("/api/agent/chat", {
            method: "POST",
            body: new URLSearchParams({
                message: text,
                history: JSON.stringify(chatHistory),
            }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                typing.remove();
                if (data.error) {
                    appendMsg("agent", "⚠️ " + data.error);
                } else {
                    appendMsg("agent", data.reply);
                    chatHistory.push({ role: "user", content: text });
                    chatHistory.push({ role: "assistant", content: data.reply });
                    if (chatHistory.length > 10) {
                        chatHistory = chatHistory.slice(-10);
                    }
                }
            })
            .catch(function () {
                typing.remove();
                appendMsg("agent", "⚠️ 网络或服务器出错，请稍后再试。");
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
