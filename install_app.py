# -*- coding: utf-8 -*-
"""
学习助手 Pro 安装器（图形界面）
双击安装器 exe 后：
  1. 选择安装位置（默认 %LOCALAPPDATA%/Programs/StudyHelperPro）
  2. 把程序文件复制过去（已存在则覆盖更新，你的数据会保留）
  3. 在桌面创建「学习助手Pro」快捷方式
  4. 可选：立即启动

说明：
- 打包版（frozen）：程序文件打包在安装器内部（_MEIPASS/app），从这里复制出去
- 源码版（开发测试）：用 --src 参数指定要"安装"的文件夹
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "学习助手Pro"
EXE_NAME = "StudyHelper.exe"
SHORTCUT_NAME = "学习助手Pro.lnk"

DEFAULT_INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs", "StudyHelperPro",
)


def source_dir():
    """打包版从安装器内部取程序文件；源码版用 --src 参数指定"""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "app")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "StudyHelper")


def copy_tree(src, dst, on_progress=None):
    """把 src 整目录复制到 dst（跳过 data/ 数据目录，保护已有数据）"""
    total = sum(len(files) for _, _, files in os.walk(src))
    done = 0
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        if rel.split(os.sep)[0] == "data":
            continue
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target_dir, f))
            done += 1
            if on_progress:
                on_progress(done, total)
    return total


def create_desktop_shortcut(target_dir):
    """在桌面创建快捷方式（临时写一个 PowerShell 脚本执行，脚本用 UTF-8 BOM 保存防中文乱码）"""
    exe = os.path.join(target_dir, EXE_NAME)
    script = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$desktop = [Environment]::GetFolderPath('Desktop')\n"
        f"$lnk = $ws.CreateShortcut(\"$desktop\\{SHORTCUT_NAME}\")\n"
        f"$lnk.TargetPath = '{exe}'\n"
        f"$lnk.WorkingDirectory = '{target_dir}'\n"
        "$lnk.Description = '学习助手 Pro - 个人学习管理智能体'\n"
        "$lnk.Save()\n"
    )
    ps_path = os.path.join(tempfile.gettempdir(), "study_helper_shortcut.ps1")
    with open(ps_path, "w", encoding="utf-8-sig") as f:
        f.write(script)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_path],
        capture_output=True,
    )
    try:
        os.remove(ps_path)
    except OSError:
        pass
    return result.returncode == 0


class InstallerApp:
    def __init__(self, root, src):
        self.root = root
        self.src = src
        root.title(f"{APP_NAME} 安装程序")
        root.geometry("560x420")
        root.resizable(False, False)

        # 顶部标题
        tk.Label(root, text=f"📚 {APP_NAME}", font=("Microsoft YaHei", 20, "bold")).pack(pady=(24, 4))
        tk.Label(root, text="个人学习管理智能体 · 安装到你的电脑", font=("Microsoft YaHei", 10)).pack()

        # 安装目录选择区
        frame = ttk.LabelFrame(root, text="安装位置", padding=10)
        frame.pack(fill="x", padx=30, pady=16)

        self.dir_var = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.dir_entry = tk.Entry(frame, textvariable=self.dir_var, font=("Microsoft YaHei", 10))
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(frame, text="浏览...", command=self.browse_dir).pack(side="right")

        # 提示文字
        self.hint = tk.Label(root, text="", font=("Microsoft YaHei", 9), fg="#666")
        self.hint.pack(pady=(0, 4))

        # 进度条（安装时显示）
        self.progress = ttk.Progressbar(root, length=400, mode="determinate")
        self.progress.pack(pady=4)
        self.status = tk.Label(root, text="", font=("Microsoft YaHei", 9))
        self.status.pack()

        # 按钮区
        self.install_btn = ttk.Button(root, text="安装", command=self.install)
        self.install_btn.pack(pady=12)

        self.finish_btn = ttk.Button(root, text="退出", command=root.destroy, state="disabled")
        self.finish_btn.pack()

        self.launch_var = tk.BooleanVar(value=True)
        self.launch_check = tk.Checkbutton(
            root, text="安装完成后立即启动", variable=self.launch_var,
            font=("Microsoft YaHei", 9), state="disabled",
        )
        self.launch_check.pack(pady=(8, 0))

        self._check_existing()

    def browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)
            self._check_existing()

    def _check_existing(self):
        """目标目录已有程序 → 提示会覆盖更新（数据保留）"""
        target = self.dir_var.get().strip()
        if os.path.exists(os.path.join(target, EXE_NAME)):
            self.hint.config(text="检测到已安装，再次安装 = 覆盖更新（你的数据会保留）", fg="#c77d00")
        else:
            self.hint.config(text="")

    def install(self):
        target = self.dir_var.get().strip()
        if not target:
            messagebox.showwarning("提示", "请先选择安装位置")
            return
        if not os.path.exists(self.src):
            messagebox.showerror("错误", f"找不到要安装的程序文件：\n{self.src}")
            return
        if app_running():
            messagebox.showwarning(
                "程序正在运行",
                "学习助手 Pro 正在运行，覆盖更新前需要先关闭它。\n\n"
                "请先关闭它（双击安装目录里的「停止学习助手.bat」，"
                "或在任务管理器结束 StudyHelper.exe），然后再点「安装」。",
            )
            return

        self.install_btn.config(state="disabled")
        try:
            total = copy_tree(self.src, target, self._on_progress)
        except Exception as e:
            messagebox.showerror("安装失败", f"复制文件时出错：\n{e}")
            self.install_btn.config(state="normal")
            return

        self.progress["value"] = 100
        self.status.config(text=f"已复制 {total} 个文件，正在创建桌面快捷方式...")
        self.root.update()

        if create_desktop_shortcut(target):
            self.status.config(text="✅ 安装完成！桌面已生成「学习助手Pro」图标", fg="#1a7f37")
        else:
            self.status.config(text="安装完成，但创建桌面快捷方式失败（可手动创建）", fg="#c77d00")

        self.finish_btn.config(state="normal")
        self.launch_check.config(state="normal")

        if self.launch_var.get():
            self.root.after(800, lambda: self._launch(target))

    def _on_progress(self, done, total):
        self.progress["maximum"] = total
        self.progress["value"] = done
        self.status.config(text=f"正在复制文件... {done}/{total}")
        self.root.update()

    def _launch(self, target):
        try:
            subprocess.Popen(
                [os.path.join(target, EXE_NAME)],
                cwd=target,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            messagebox.showwarning("提示", f"启动失败：{e}\n请手动双击快捷方式启动")


def app_running():
    """学习助手是否正在运行（覆盖更新前必须先关闭它，否则 exe 文件被占用无法替换）"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq StudyHelper.exe", "/NH"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        return "StudyHelper.exe" in out
    except Exception:
        return False


def silent_install(src, target):
    """命令行静默安装（自动化测试用）：复制文件 + 创建桌面快捷方式，返回是否成功"""
    if sys.stdout is None:  # 无窗口模式没有控制台，别让 print 崩溃
        sys.stdout = open(os.devnull, "w")
    if not os.path.exists(os.path.join(src, EXE_NAME)):
        print(f"ERROR: missing {EXE_NAME} in {src}")
        return False
    try:
        total = copy_tree(src, target)
        print(f"copied {total} files to {target}")
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    ok = create_desktop_shortcut(target)
    print("shortcut:", "ok" if ok else "failed")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--dir", default="")
    args = parser.parse_args()

    src = args.src or source_dir()
    if getattr(sys, "frozen", False):
        src = source_dir()  # 打包版永远用内部文件，忽略 --src

    if args.silent:
        sys.exit(0 if silent_install(src, args.dir or DEFAULT_INSTALL_DIR) else 1)

    if not os.path.exists(os.path.join(src, EXE_NAME)):
        # 源码直接运行时给个明确提示
        messagebox.showerror(
            "找不到程序文件",
            f"安装器未找到 {EXE_NAME}。\n"
            "请先打包主程序（见 build_exe.bat），"
            "或用 --src 指定文件夹。\n\n查找位置：\n" + src,
        )
        return

    root = tk.Tk()
    InstallerApp(root, src)
    root.mainloop()


if __name__ == "__main__":
    main()
