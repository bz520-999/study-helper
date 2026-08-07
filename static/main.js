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
// 设置页：爬虫（保存账号 / 立即同步 / 半自动粘贴提取）
// ============================================
var crawlerForm = document.getElementById("crawler-form");
if (crawlerForm) {
    // 切换同步来源时，联动账号输入框的提示文字
    var providerSelect = crawlerForm.querySelector("select[name='crawl_provider']");
    var userLabel = document.getElementById("crawl-user-label");
    if (providerSelect && userLabel) {
        function syncCrawlerUi() {
            var isJwxt = providerSelect.value === "jwxt";
            userLabel.childNodes[0].textContent = isJwxt ? "教务系统账号（学号）" : "学习通账号（手机号）";
            var input = userLabel.querySelector("input[name='crawl_username']");
            if (input) input.placeholder = isJwxt ? "填学号" : "填手机号";
            var pasteNote = document.getElementById("crawl-paste-note");
            if (pasteNote) {
                pasteNote.innerHTML = isJwxt
                    ? "1. 浏览器登录教务系统 → 打开「考试安排 / 成绩」页 → 全选复制文字<br>2. 粘贴到下面 → 点「提取」→ 勾选确认后自动进入 DDL 清单"
                    : "1. 用浏览器登录学习通 → 打开「作业」列表页 → 全选复制文字<br>2. 粘贴到下面 → 点「提取」→ 勾选确认后自动进入 DDL 清单";
            }
        }
        providerSelect.addEventListener("change", syncCrawlerUi);
        syncCrawlerUi();
    }
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
        if (!confirm("确定要退出登录吗？\n将清除教务/学习通账号密码，并清空已同步的课表数据。")) {
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
                box.innerHTML = '<p class="empty">' + (data.ok ? "已提交，等待登录完成…" : ("提交失败：" + data.msg)) + '</p>';
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
