# 🤝 团队协作指南（队友必读）

你好！欢迎加入「学习助手 Pro」开发。这份指南教你在**自己的电脑上**把项目跑起来、改代码、测试、并把修改交回来。全程照着做即可，**不用有编程基础**。

---

## 第 0 步：准备（一次性，约 15 分钟）

| 需要的东西 | 怎么做 |
|---|---|
| ① GitHub 账号 | 打开 github.com 注册（用邮箱） |
| ② Git 工具 | 下载安装：git-scm.com/download/win → 一路 Next 装完 |
| ③ Python 3.12 | 下载安装：python.org/downloads/ → ⚠️ 安装时**必须勾选** "Add python.exe to PATH" |
| ④ 接受邀请 | 仓库主人已发协作邀请，去 github.com 的**通知**里点接受（不点后面没权限推送） |

> 国内网络访问 GitHub 可能很慢/连不上（被墙）。连不上时下载一个免费加速器 **Watt Toolkit（原 Steam++）**，开启"GitHub 加速"后再继续。

---

## 第 1 步：把项目拿到自己电脑

1. 打开**桌面上的 `study-helper` 文件夹**（没有就先创建一个）
2. 点窗口**顶部地址栏**（显示路径那栏）→ 删掉 → 输入 `cmd` → 按回车
3. 弹出黑色窗口，输入以下命令回车：
   ```
   git clone https://github.com/bz520-999/study-helper.git
   ```
4. 看到 `done.` 说明成功，文件夹里出现 `study-helper` 子文件夹

---

## 第 2 步：建自己的工作分支

继续在黑色窗口里输入（一行一行回车）：

```
cd study-helper
git checkout -b my-feature
```

看到 `Switched to a new branch 'my-feature'` = 成功。
> 意思是给自己开一条独立的工作线：你的修改不影响主线，随时可以撤销。

---

## 第 3 步：配置你的署名（只做一次）

```
git config --global user.name "你的GitHub用户名"
git config --global user.email "你注册的邮箱"
```

---

## 第 4 步：修改代码

用 VS Code 打开 `study-helper` 文件夹：
- 双击文件夹里的任意 .py 文件就能编辑
- 文件说明：`app.py` 页面逻辑 / `models.py` 数据操作 / `config.py` 可调配置（端口、课程识别规则）……

---

## 第 5 步：调试测试（关键！改完必须跑一遍）

1. **双击 `run.bat`**（黑色窗口）
   - 第一次会创建环境、装依赖，等 1 分钟左右
   - 看到「学习助手 Pro 已启动」和网址就成功了
2. 浏览器打开 `http://127.0.0.1:5000`，把你改动的功能点一遍
3. ⚠️ **改了代码必须重启才生效**：关掉黑色窗口 → 重新双击 `run.bat`
4. 出错时：看黑色窗口里的**红色/英文报错**，截图发给仓库主人

**常见问题快速排查：**

| 现象 | 原因 | 解决 |
|---|---|---|
| 启动报"端口被占用" | 应用已经开着一个了 | 关掉旧的黑色窗口，或改 config.py 的 PORT=5001 |
| 页面 404 / 页面卡 | 开重复了 | 全部关掉，只保留一个 |
| 依赖装不上（网络慢） | pip 下载慢 | 换清华镜像：`python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 控制台中文乱码 | 编码问题 | run.bat 已内置处理，一般不会遇到 |

---

## 第 6 步：保存修改并推送（提交）

回到黑色窗口（先关掉 run.bat），输入：

```
git add -A
git commit -m "说清楚改了什么，例如：新增了导出 Excel 功能"
git push origin my-feature
```

- 第一次 push 会弹**登录窗口**（GitHub 账号密码登录一次，以后记住）
- 推送的是你的分支 `my-feature`，不会碰主线

---

## 第 7 步：申请合并（Pull Request）

1. 浏览器打开仓库 `https://github.com/bz520-999/study-helper`
2. 点黄色提示条 **Compare & pull request**
3. 写一句说明 → 点 **Create pull request**

仓库主人审查并点 **Merge pull request** 后，你的修改就进入主线了 🎉

---

## 第 8 步：以后每次干活前（重要！）

在黑色窗口输入，把主线最新代码同步到本地：

```
git pull origin main
```

> 不先 pull 就改代码，容易产生"冲突"（和你改同一处），处理起来麻烦。养成习惯：**开工先 pull**。

---

## 📌 三条铁律

1. **永远不要直接 push 到 main**——push 的永远是自己的分支（my-feature）
2. **改完必须测试**（双击 run.bat 跑一遍）再提交
3. **提交信息写人话**：`git commit -m "..."` 里写清楚改了什么

## 💡 常见疑问

- **我的数据会传上去吗？** 不会。`data/`（数据库、备份）已被 .gitignore 排除，每个人的数据在自己电脑上互不影响
- **改坏了怎么办？** 分支随时能删：`git checkout main` 回到主线，`git branch -D my-feature` 删掉自己的分支重来
- **网页也能改吗？** 小改动（README、配置）可以：仓库页面 → 点文件 → 铅笔图标 ✏️ 编辑。但**网页改代码没法测试**，核心代码请在本地改
