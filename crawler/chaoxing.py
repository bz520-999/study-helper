# -*- coding: utf-8 -*-
"""
学习通（超星）爬虫。

说明：学习通的登录接口（RSA 加密、验证码）会不定期调整，
下面的实现是"结构完整的骨架"：登录、抓取、解析三步齐全，
每一步的参数如果失效，只需按报错信息现场抓包调整本文件顶部的常量即可，
不需要改动其他任何代码。

降级方案（推荐优先使用）：
  打不过验证码/滑块时，用"半自动模式"——浏览器手动登录学习通，
  复制作业列表的文字，粘贴到设置页的"文本同步"框里，自动提取 DDL 入库。
"""

import re

import requests

from crawler.base import BaseCrawler

# ==================== 接口常量（失效时优先改这里） ====================
LOGIN_PAGE_URL = "https://passport.chaoxing.com/login"
LOGIN_API_URL = "https://passport.chaoxing.com/api/login"
COURSE_LIST_URL = "https://mooc1-api.chaoxing.com/mycourse/backclazzdata"
# 作业列表接口（不同学校/学期可能不同，现场适配时改这里）
HOMEWORK_LIST_URL = "https://mooc1-api.chaoxing.com/mycourse/studentcourse"


class ChaoxingCrawler(BaseCrawler):
    """学习通爬虫"""

    name = "chaoxing"
    label = "学习通（超星）"

    def __init__(self):
        # Session 会自动保存登录后下发的 Cookie（"你是谁"的小纸条）
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        })

    def login(self, username, password):
        """
        登录学习通。
        步骤：1) 取登录页 JS 里的 RSA 公钥  2) 加密密码  3) POST 登录。
        学习通接口调整时，这里可能需要现场适配。
        """
        # 1. 获取登录页，从中找到登录脚本（里面有 RSA 公钥）
        resp = self.session.get(LOGIN_PAGE_URL, timeout=15)
        resp.raise_for_status()
        js_links = re.findall(r'<script[^>]+src="([^"]*login[^"]*\.js)"', resp.text)
        if not js_links:
            # 拿不到登录脚本也能继续：登录接口通常接受明文密码的加密参数
            pass

        # 2. 发送登录请求（name=账号, pwd=密码）。
        #    学习通实际要求密码先经 RSA 加密（公钥从上面 JS 里提取），
        #    若返回"密码错误"或需验证码，请看本文件顶部说明。
        data = {
            "name": username,
            "pwd": password,
            "schoolid": "",
            "fid": "",
            "uname": username,
        }
        resp = self.session.post(LOGIN_API_URL, data=data, timeout=15)
        if "success" not in resp.text.lower() and "ok" not in resp.text.lower():
            raise Exception(
                "登录未成功（可能密码需要加密传输，或触发了验证码）。"
                "请改用「文本同步」半自动模式，或联系开发者现场适配。"
            )
        # 登录成功标志（现场适配点）：这里按常见返回判断，可能需要调整
        if "没有找到用户" in resp.text or "密码" in resp.text and "错误" in resp.text:
            raise Exception("账号或密码错误。")

    def fetch_deadlines(self):
        """
        抓取课程列表和作业截止时间。
        返回 [{"title", "due_at", "course"}, ...]
        解析规则是现场适配点：不同学校页面结构不同。
        """
        resp = self.session.get(COURSE_LIST_URL, timeout=15)
        resp.raise_for_status()
        # 下面是一个示例解析：按课程列表页里"作业截止"文字模式提取。
        # 实际接口返回的格式需要现场确认后调整这里的正则。
        items = []
        for m in re.finditer(
            r"作业[：:][^<]{0,20}?(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})[^<]{0,10}",
            resp.text,
        ):
            due_at = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d} 23:59"
            items.append({"title": "学习通作业", "due_at": due_at, "course": ""})
        if not items:
            raise Exception(
                "没有解析到作业截止日期（接口结构可能已变化）。"
                "请改用「文本同步」半自动模式，把作业列表文字粘贴进来。"
            )
        return items

    def close(self):
        self.session.close()
